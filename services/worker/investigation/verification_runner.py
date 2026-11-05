"""Verification runner (M8, worker side): execute regression tests.

Runs each executable test through the same isolated browser runner
as reproduction, records one check per test plus a verdict artifact,
and leaves the run open for the calling stage to finish with
phase-appropriate gate semantics. Every verdict traces to executed
container output — never to claims.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Any, Callable

from app.envelope import ApiError
from app.services import evidence as evidence_service
from app.services import verification as verification_service
from investigation import InvestigationAbort, InvestigationFailure
from investigation.browser import run_browser_repro
from sandbox.execution_policy import get_policy

logger = logging.getLogger("meridian.investigation.verify")


def _fingerprint(snapshot_id: uuid.UUID, context: dict) -> str:
    canonical = json.dumps(
        {"snapshot": str(snapshot_id), "context": context},
        sort_keys=True, separators=(",", ":"),
    )
    return "browser_repro:" + hashlib.sha256(canonical.encode()).hexdigest()[:48]


def run_test_suite(
    session_factory: Any,
    *,
    job: dict,
    worker_id: str,
    investigation_id: uuid.UUID,
    project_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    workspace_id: uuid.UUID,
    tests: list[dict],
    phase: str,
    patch_id: uuid.UUID | None,
    stage_id: uuid.UUID,
    client: Any = None,
    store: Any = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> dict:
    """Execute tests; return verdicts with the run left open.

    ``tests`` items carry test_id/title/context. When the user queued a
    rerun plan (M9), the newest queued plan is adopted and the suite is
    filtered to its requested subset; otherwise a fresh run opens with
    the executed set persisted as its plan. Raises
    InvestigationFailure/Abort like the browser runner.
    """
    job_id = uuid.UUID(str(job["id"]))
    policy = get_policy("browser_repro")
    base_profile = {"profile": "static", "runner": "browser_repro"}
    adopted: dict | None = None
    try:
        with session_factory() as session:
            adopted = verification_service.adopt_queued_run(
                session, job_id=job_id, worker_id=worker_id,
                investigation_id=investigation_id, project_id=project_id,
                patch_id=patch_id, snapshot_id=snapshot_id, stage_id=stage_id,
                phase=phase, runner_image=policy.image, runtime_profile=base_profile,
            )
            if adopted is not None:
                run_id = adopted["run_id"]
                wanted = adopted["selected_check_keys"]
                if wanted is not None:
                    tests = [item for item in tests if str(item["test_id"]) in set(wanted)]
            else:
                run_id = verification_service.start_run(
                    session, job_id=job_id, worker_id=worker_id,
                    investigation_id=investigation_id, project_id=project_id,
                    patch_id=patch_id, snapshot_id=snapshot_id, stage_id=stage_id,
                    phase=phase, runner_image=policy.image,
                    runtime_profile={
                        **base_profile,
                        "planned_checks": [
                            {
                                "check_key": str(item["test_id"]),
                                "display_name": str(item["title"])[:300],
                            }
                            for item in tests
                        ],
                    },
                )
    except ApiError as exc:
        if exc.code in ("LEASE_LOST", "JOB_SUPERSEDED"):
            raise InvestigationAbort() from exc
        raise InvestigationFailure(exc.code, exc.message, False) from exc
    verdicts: list[dict] = []
    try:
        for item in tests:
            if is_cancelled is not None:
                try:
                    if is_cancelled():
                        raise InvestigationAbort()
                except InvestigationAbort:
                    raise
                except Exception as exc:
                    logger.warning("cancel watch failed: %s", exc)
            test_tag = uuid.UUID(str(item["test_id"])).hex[:12]
            run_tag = f"verify_{phase}_{test_tag}"
            summary = run_browser_repro(
                session_factory, job=job, worker_id=worker_id,
                investigation_id=investigation_id, context=item["context"],
                snapshot_id=snapshot_id, workspace_id=workspace_id,
                client=client, store=store, is_cancelled=is_cancelled,
                job_stage_key=run_tag, execution_key=run_tag,
            )
            reproduced = summary.get("reproduced")
            if reproduced is True:
                verdict, check_status, exit_code = "failed", "failed", 1
            elif reproduced is False:
                verdict, check_status, exit_code = "passed", "passed", 0
            else:
                verdict, check_status, exit_code = "inconclusive", "inconclusive", None
            verdict_doc = {
                "test_id": str(item["test_id"]),
                "verdict": verdict,
                "reproduced": reproduced,
                "assertions_total": summary.get("assertions_total", 0),
                "assertions_passed": summary.get("assertions_passed", 0),
                "failed_step": summary.get("failed_step"),
                "evidence_ids": summary.get("evidence_ids", []),
            }
            with session_factory() as session:
                record = evidence_service.create_evidence(
                    session, project_id=project_id, investigation_id=investigation_id,
                    tool_run_id=uuid.UUID(summary["tool_run_id"]),
                    kind="test_output",
                    data=json.dumps(verdict_doc, separators=(",", ":")).encode(),
                    filename_hint="verdict.json", redaction_status="redacted",
                    metadata={"source": "verification", "phase": phase},
                    store=store,
                )
                check = verification_service.record_check(
                    session, run_id=run_id, check_key=str(item["test_id"]),
                    display_name=str(item["title"])[:300], status=check_status,
                    regression_test_id=item["test_id"],
                    command_fingerprint=_fingerprint(snapshot_id, item["context"]),
                    exit_code=exit_code,
                    stdout_artifact_id=uuid.UUID(record["id"]),
                )
            verdicts.append(
                {
                    "test_id": item["test_id"], "verdict": verdict,
                    "check_id": check["id"], "evidence_ids": summary.get("evidence_ids", []),
                }
            )
    except InvestigationAbort:
        with session_factory() as session:
            try:
                verification_service.finish_run(
                    session, run_id=run_id, status="cancelled",
                    summary="Verification cancelled.",
                )
            except ApiError as exc:
                logger.warning("run cancel failed run_id=%s code=%s", run_id, exc.code)
        raise
    except InvestigationFailure as exc:
        # A mid-suite fault must not strand the run: finish it failed
        # with the recorded checks intact, then let the stage decide.
        with session_factory() as session:
            try:
                verification_service.finish_run(
                    session, run_id=run_id, status="failed",
                    summary=f"Verification interrupted: {exc.message}",
                )
            except ApiError as api_exc:
                logger.warning(
                    "run fail failed run_id=%s code=%s", run_id, api_exc.code
                )
        raise
    return {
        "run_id": run_id,
        "verdicts": verdicts,
        "adopted": adopted is not None,
        "planned_total": (adopted or {}).get("planned_total"),
    }
