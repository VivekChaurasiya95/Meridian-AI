"""Investigation pipeline (M8, worker side): validated stage sequence.

One claimed ``investigation`` job runs the stage flow in order —
inspection → reproduction → analysis → review → test creation →
baseline → patch proposal → approval gate → application →
post-patch verification — recording every attempt, tool run, and
activity event. The approval gate parks the run honestly: the job
completes and a human decision enqueues the next leg.

Cancellation is cooperative: the pipeline checks the investigation
flag plus job ownership before every stage and inside the container
run, then unwinds through ``InvestigationAbort`` — finalizing the
investigation as cancelled and cancelling the job, never failing it.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Callable

from app.envelope import ApiError
from app.models import Investigation
from app.services import activity as activity_service
from app.services import evidence as evidence_service
from app.services import investigations as investigation_service
from app.services import jobs as job_service
from app.services.repro_spec import validate_context
from investigation import InvestigationAbort, InvestigationFailure, InvestigationParked
from investigation.browser import run_browser_repro

logger = logging.getLogger("meridian.investigation.pipeline")

FLOW = investigation_service.STAGE_FLOW_M8

# Handler-only stages (NOT in FLOW, so the M8 exact-sequence contract
# holds): each runs alone when a retry names it directly, never as part
# of the sequential run. Mirrors RETRYABLE_FROM on the API side.
TRAILING_RETRYABLE = ("report_generation",)

# Terminal verdicts that block instead of failing: stable outcomes the
# operator (or a retry with new inputs) must resolve, not the queue.
BLOCKING_FAILURES = frozenset(
    {"PROFILE_UNSUPPORTED", "MODEL_NOT_CONFIGURED", "NO_EXECUTABLE_TESTS"}
)

HYPOTHESIS_SYSTEM_PROMPT = (
    "You are Meridian's debugging analyst. Propose candidate causes for "
    "the reported bug as strict JSON matching hypotheses_v1: "
    '{"hypotheses": [{"title": "...", "description": "...", '
    '"confidence": 0.0-1.0 or null, "evidence_refs": [{"evidence_id": '
    '"...", "relationship": "supports|contradicts|context", "note": "..."}]}]}. '
    "Cite only the evidence ids provided. Every hypothesis needs at "
    "least one supports or contradicts link. Keep titles short and "
    "descriptions concrete."
)
HYPOTHESIS_RESAMPLES = 2
MODEL_RESAMPLES = 2
REPORT_SYSTEM_PROMPT = (
    "You are Meridian's debugging analyst. Summarize the completed "
    "investigation as strict JSON matching report_v1: "
    '{"report": {"title": "...", "summary": "...", '
    '"sections": [{"heading": "...", "body": "..."}]}}. '
    "1-8 sections with short headings. State only what the evidence, "
    "hypotheses, tests, and verification verdict support. Never invent "
    "citations, file paths, or results."
)
EVIDENCE_EXCERPT_CHARS = 3000
PROMPT_BUG_CHARS = 4000
SOURCE_EXCERPT_FILES = 8
SOURCE_EXCERPT_CHARS = 3000

TESTS_SYSTEM_PROMPT = (
    "You are Meridian's test author. Propose e2e regression tests as "
    "strict JSON matching regression_tests_v1: {tests: [{title, "
    "description, test_type: 'e2e', file_path, test_name, steps: "
    "[{action, selector?, text?, ms?, name?}]}]}. Actions: click, fill, "
    "wait, assert_text, screenshot. Assertions must describe the BUGGY "
    "behavior (they hold while the bug is present); the harness inverts "
    "them into pass/fail verdicts. Every test needs an assertion."
)
PATCH_SYSTEM_PROMPT = (
    "You are Meridian's patch author. Propose a minimal unified diff as "
    "strict JSON matching patch_v1: {summary, diff}. Rules: plain "
    "unified diff only (---/+++/@@ hunks), repo-relative paths, no "
    "renames, no mode changes, no binaries, no new files under "
    "reserved roots. Keep the diff focused on the failing tests."
)


def run_investigation(
    session_factory: Any,
    job: dict,
    worker_id: str,
    *,
    client: Any = None,
    store: Any = None,
    is_cancelled: Callable[[], bool] | None = None,
    model_provider: Any = None,
) -> dict:
    """Run the stage flow for one claimed investigation job.

    ``model_provider`` injects the reasoning backend (tests pass a
    scripted double); None resolves the operator-configured provider,
    blocking honestly when none is configured.
    """
    try:
        job_id = uuid.UUID(str(job["id"]))
        workspace_id = uuid.UUID(str(job["workspace_id"]))
        payload = job.get("payload", {})
        investigation_id = uuid.UUID(str(payload.get("investigation_id")))
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise InvestigationFailure("INVALID_JOB", "The job record is malformed.", False) from exc
    from_stage = payload.get("from_stage", FLOW[0])
    if from_stage not in FLOW and from_stage not in TRAILING_RETRYABLE:
        raise InvestigationFailure("INVALID_PAYLOAD", "The retry stage is not supported.", False)

    def _aborted() -> bool:
        if is_cancelled is not None:
            try:
                if is_cancelled():
                    return True
            except Exception as exc:
                logger.warning("cancel watch failed job_id=%s error=%s", job_id, exc)
        try:
            with session_factory() as session:
                if investigation_service.cancel_requested(session, investigation_id):
                    return True
                return not job_service.is_running_and_owned(session, job_id, worker_id)
        except Exception as exc:
            logger.warning("cancel watch failed job_id=%s error=%s", job_id, exc)
            return False

    sequence = FLOW[FLOW.index(from_stage):] if from_stage in FLOW else (from_stage,)
    try:
        for stage_key in sequence:
            if _aborted():
                raise InvestigationAbort()
            _run_stage(
                session_factory, job, worker_id, investigation_id, workspace_id,
                stage_key, client=client, store=store, is_cancelled=_aborted,
                model_provider=model_provider,
            )
    except InvestigationParked:
        # The gate stage finished and parked honestly: the job's work is
        # done, so complete it and let approval enqueue the next leg.
        with session_factory() as session:
            inv = session.get(Investigation, investigation_id)
            status = inv.status if inv is not None else "unknown"
        return {
            "parked": True, "investigation_id": str(investigation_id), "status": status,
        }
    except InvestigationAbort:
        # Abort can land before the first stage (nothing finalized yet)
        # or after a stage handler already finalized: the helper skips
        # terminal investigations, so both shapes converge here.
        with session_factory() as session:
            _finalize_best_effort(
                session, job_id, worker_id, investigation_id, "cancelled"
            )
        with session_factory() as session:
            try:
                job_service.cancel_job_as_worker(session, job_id, worker_id)
            except ApiError as exc:
                logger.warning("worker cancel refused job_id=%s code=%s", job_id, exc.code)
        return {"cancelled": True, "investigation_id": str(investigation_id)}
    with session_factory() as session:
        inv = session.get(Investigation, investigation_id)
        status = inv.status if inv is not None else "unknown"
    return {"investigation_id": str(investigation_id), "status": status}


def _run_stage(
    session_factory: Any,
    job: dict,
    worker_id: str,
    investigation_id: uuid.UUID,
    workspace_id: uuid.UUID,
    stage_key: str,
    *,
    client: Any,
    store: Any,
    is_cancelled: Callable[[], bool],
    model_provider: Any,
) -> None:
    job_id = uuid.UUID(str(job["id"]))
    attempt: dict | None = None
    try:
        with session_factory() as session:
            attempt = investigation_service.start_stage_attempt(
                session, job_id=job_id, worker_id=worker_id,
                investigation_id=investigation_id, stage_key=stage_key,
            )
            activity_service.append_event(
                session, investigation_id, "stage.started", f"Stage started: {stage_key}.",
                {"stage_key": stage_key, "attempt": attempt["attempt_number"]},
            )
    except ApiError as exc:
        if exc.code in ("LEASE_LOST", "JOB_SUPERSEDED"):
            raise InvestigationAbort() from exc
        raise InvestigationFailure(exc.code, exc.message, False) from exc
    assert attempt is not None
    stage_id = uuid.UUID(attempt["id"])

    def _finish(status: str, output: dict, error: tuple[str, str] | None = None) -> None:
        with session_factory() as session:
            try:
                investigation_service.finish_stage_attempt(
                    session, job_id=job_id, worker_id=worker_id, stage_id=stage_id,
                    status=status, output_summary=output,
                    error_code=error[0] if error else None,
                    error_message=error[1] if error else None,
                )
                activity_service.append_event(
                    session, investigation_id, f"stage.{status}",
                    f"Stage {status}: {stage_key}.",
                    {"stage_key": stage_key, "attempt": attempt["attempt_number"]},
                )
            except ApiError as exc:
                if exc.code in ("LEASE_LOST", "JOB_SUPERSEDED"):
                    raise InvestigationAbort() from exc
                raise

    try:
        if stage_key == "project_inspection":
            output = _inspect(session_factory, investigation_id)
        elif stage_key == "plan_investigation":
            output = _plan(session_factory, investigation_id)
        elif stage_key == "reproduction":
            output = _reproduce(
                session_factory, job, worker_id, investigation_id, workspace_id,
                client=client, store=store, is_cancelled=is_cancelled,
            )
        elif stage_key == "evidence_analysis":
            output = _analyze(session_factory, investigation_id)
        elif stage_key == "hypothesis_review":
            output = _review(
                session_factory, job_id, worker_id, investigation_id,
                stage_id=stage_id, store=store, model_provider=model_provider,
            )
        elif stage_key == "regression_test_creation":
            output = _create_tests(
                session_factory, job_id, worker_id, investigation_id,
                stage_id=stage_id, store=store, model_provider=model_provider,
            )
        elif stage_key == "baseline_test_execution":
            output = _baseline(
                session_factory, job, worker_id, investigation_id, workspace_id,
                stage_id=stage_id, client=client, store=store,
                is_cancelled=is_cancelled,
            )
        elif stage_key == "patch_proposal":
            output = _propose_patch(
                session_factory, job_id, worker_id, investigation_id,
                stage_id=stage_id, store=store, model_provider=model_provider,
            )
        elif stage_key == "awaiting_user_approval":
            output = _await_approval(
                session_factory, job_id, worker_id, investigation_id
            )
        elif stage_key == "patch_application":
            output = _apply_patch(
                session_factory, job_id, worker_id, investigation_id, workspace_id,
                store=store,
            )
        elif stage_key == "post_patch_verification":
            output = _post_verify(
                session_factory, job, worker_id, investigation_id, workspace_id,
                stage_id=stage_id, client=client, store=store,
                is_cancelled=is_cancelled, model_provider=model_provider,
            )
        elif stage_key == "report_generation":
            output = _report_generation(
                session_factory, job, worker_id, investigation_id, store=store,
            )
        else:
            raise InvestigationFailure(
                "STAGE_NOT_SUPPORTED", f"The stage {stage_key} is not built yet.", False
            )
    except InvestigationAbort:
        try:
            _finish("cancelled", {})
        except InvestigationAbort:
            pass
        with session_factory() as session:
            _finalize_best_effort(session, job_id, worker_id, investigation_id, "cancelled")
        raise
    except InvestigationParked as exc:
        _finish("completed", exc.output)
        raise
    except InvestigationFailure as exc:
        terminal = "blocked" if exc.code in BLOCKING_FAILURES else "failed"
        _finish(terminal, {}, (exc.code, exc.message))
        # Retryable failures leave the investigation running while job
        # attempts remain: the next claim re-runs from the retry stage
        # with fresh attempts. Only the last attempt (or a terminal
        # verdict like blocked) finalizes, so a retried job never lands
        # on an investigation it can no longer transition.
        exhausted = int(job.get("attempts", 1)) >= int(job.get("max_attempts", 1))
        if exc.retryable and not exhausted and terminal == "failed":
            raise
        with session_factory() as session:
            _finalize_best_effort(
                session, job_id, worker_id, investigation_id, terminal,
                result_summary=exc.message,
            )
        raise
    _finish("completed", output)


def _finalize_best_effort(
    session: Any, job_id: uuid.UUID, worker_id: str,
    investigation_id: uuid.UUID, status: str, result_summary: str | None = None,
) -> None:
    try:
        current = session.get(Investigation, investigation_id)
        if current is not None and current.status in investigation_service.TERMINAL_STATUSES:
            return
        investigation_service.finalize_investigation(
            session, job_id=job_id, worker_id=worker_id,
            investigation_id=investigation_id, status=status, result_summary=result_summary,
        )
    except ApiError as exc:
        logger.warning(
            "finalize failed investigation_id=%s code=%s", investigation_id, exc.code
        )


def _load_context(session_factory: Any, investigation_id: uuid.UUID) -> tuple[dict, uuid.UUID]:
    from sqlalchemy import select

    with session_factory() as session:
        row = session.execute(
            select(Investigation.reproduction_context, Investigation.repository_snapshot_id)
            .where(Investigation.id == investigation_id)
        ).one_or_none()
    if row is None or row[1] is None:
        raise InvestigationFailure("SNAPSHOT_MISSING", "The investigation has no snapshot.", False)
    try:
        context = validate_context(row[0])
    except ApiError as exc:
        raise InvestigationFailure(exc.code, exc.message, False) from exc
    snapshot_id = row[1]
    assert isinstance(snapshot_id, uuid.UUID)
    return context, snapshot_id


def _inspect(session_factory: Any, investigation_id: uuid.UUID) -> dict:
    """project_inspection: confirm a servable static snapshot (DB rows only)."""
    from sqlalchemy import func, select

    from app.models import RepositorySnapshot, SnapshotFile

    _context, snapshot_id = _load_context(session_factory, investigation_id)
    with session_factory() as session:
        snapshot = session.get(RepositorySnapshot, snapshot_id)
        if snapshot is None or snapshot.storage_status != "ready":
            raise InvestigationFailure(
                "SNAPSHOT_NOT_READY", "The snapshot content is not stored.", False
            )
        html_rows = list(
            session.execute(
                select(SnapshotFile.path)
                .where(
                    SnapshotFile.snapshot_id == snapshot_id,
                    SnapshotFile.path.like("%.html"),
                )
                .order_by(SnapshotFile.path.asc())
                .limit(6)
            ).scalars()
        )
        file_count = (
            session.execute(
                select(func.count()).where(SnapshotFile.snapshot_id == snapshot_id)
            )
        ).scalar_one()
    if not html_rows:
        raise InvestigationFailure(
            "PROFILE_UNSUPPORTED",
            "No servable HTML was found: M6 supports static snapshots only.", False,
        )
    entry = "index.html" if "index.html" in html_rows else sorted(html_rows)[0]
    return {"profile": "static", "entry": entry, "file_count": file_count}


def _plan(session_factory: Any, investigation_id: uuid.UUID) -> dict:
    """plan_investigation: deterministic check-plan labels (M9).

    Reads the runnable regression tests plus configured profiles and
    persists them as stage output. Label-only: this stage never writes
    runs or checks and never executes anything — verification legs
    persist the same plan on each new run and execute it there.
    """
    from app.services import verification as verification_service

    with session_factory() as session:
        plan = verification_service.plan_checks(session, investigation_id)
    return {
        "outcome": "completed",
        "required_checks": plan["required_checks"],
        "profiles": plan["profiles"],
        "test_count": plan["test_count"],
        "runnable_count": plan["runnable_count"],
    }


def _report_generation(
    session_factory: Any, job: dict, worker_id: str,
    investigation_id: uuid.UUID, *, store: Any,
) -> dict:
    """report_generation: queued file reports to stored bytes (M10).

    Handler-only like _plan (NOT in FLOW, so the M8 exact-sequence
    contract is untouched): generates rows users queued via the API,
    rendering only persisted state. Never finalizes — verification
    owns the terminal verdict.
    """
    from investigation.reporting import generate_pending_reports

    return generate_pending_reports(
        session_factory, uuid.UUID(str(job["id"])), worker_id,
        investigation_id, store=store,
    )


def _reproduce(
    session_factory: Any, job: dict, worker_id: str,
    investigation_id: uuid.UUID, workspace_id: uuid.UUID,
    *, client: Any, store: Any, is_cancelled: Callable[[], bool],
) -> dict:
    """reproduction: containerized Playwright run, findings as evidence."""
    context, snapshot_id = _load_context(session_factory, investigation_id)
    summary = run_browser_repro(
        session_factory, job=job, worker_id=worker_id,
        investigation_id=investigation_id, context=context,
        snapshot_id=snapshot_id, workspace_id=workspace_id,
        client=client, store=store, is_cancelled=is_cancelled,
    )
    # SAM evidence-image segmentation (best-effort, never blocks repro):
    # disabled/unconfigured providers are logged and skipped honestly.
    for evidence_id in summary.get("evidence_ids", [])[:3]:
        try:
            from app.ai.providers import segment_image
            from app.config import get_settings

            sam = get_settings()
            segment_image(
                sam.meta_sam_enabled, sam.meta_sam_base_url,
                sam.meta_sam_api_key, sam.meta_sam_model, str(evidence_id),
            )
        except Exception as exc:  # noqa: BLE001 — SAM must never break repro
            logger.info("sam skipped evidence=%s error=%s", evidence_id, exc)
    return {
        "reproduced": summary["reproduced"],
        "assertions_total": summary["assertions_total"],
        "assertions_passed": summary["assertions_passed"],
        "evidence_count": len(summary["evidence_ids"]),
        "tool_run_id": summary["tool_run_id"],
    }


def _analyze(session_factory: Any, investigation_id: uuid.UUID) -> dict:
    """evidence_analysis: deterministic outcome from the persisted repro run.

    Records the verdict as stage output; finalization belongs to the
    flow's last stage so later milestones extend without rewriting this.
    """
    from sqlalchemy import desc, select

    from app.models import ToolRun

    with session_factory() as session:
        run = (
            session.execute(
                select(ToolRun)
                .where(
                    ToolRun.investigation_id == investigation_id,
                    ToolRun.tool_name == "browser_repro",
                    ToolRun.status == "succeeded",
                )
                .order_by(desc(ToolRun.created_at), desc(ToolRun.id))
                .limit(1)
            )
        ).scalar_one_or_none()
        if run is None:
            raise InvestigationFailure(
                "ANALYSIS_NO_BASELINE", "No reproduction result to analyze.", False
            )
        result = dict(run.result_summary or {})
        evidence_total = evidence_service.evidence_count(session, investigation_id)
    reproduced = result.get("reproduced")
    if reproduced is True:
        outcome: str = "completed"
        summary_text = (
            f"Reproduced: all {result.get('assertions_total', 0)} scripted "
            f"assertion(s) held across {evidence_total} evidence artifact(s)."
        )
    elif reproduced is False:
        outcome = "completed"
        summary_text = (
            "Not reproduced: at least one scripted assertion failed. "
            "This does not establish that the bug is absent."
        )
    else:
        outcome = "inconclusive"
        if result.get("failed_step") is not None:
            summary_text = "Inconclusive: the scripted path broke before assertions completed."
        else:
            summary_text = "Inconclusive: no assertions were scripted to judge by."
    return {
        "outcome": outcome,
        "summary": summary_text,
        "reproduced": reproduced,
        "evidence_count": evidence_total,
    }


def _review(
    session_factory: Any,
    job_id: uuid.UUID,
    worker_id: str,
    investigation_id: uuid.UUID,
    *,
    stage_id: uuid.UUID,
    store: Any,
    model_provider: Any,
) -> dict:
    """hypothesis_review: evidence-grounded candidate causes (M7).

    Builds a bounded case bundle from persisted rows plus redacted
    text excerpts, takes up to two validated model samples, and
    persists hypotheses with evidence links. Finalization belongs to
    the flow's last stage. No configured provider blocks honestly —
    never fakes.
    """
    from sqlalchemy import desc, select

    from app.models import Investigation, InvestigationStage
    from app.services import hypotheses as hypothesis_service
    from app.services.model_gateway import SCHEMA_HYPOTHESES, parse_hypotheses

    with session_factory() as session:
        analysis = (
            session.execute(
                select(InvestigationStage.output_summary)
                .where(
                    InvestigationStage.investigation_id == investigation_id,
                    InvestigationStage.stage_key == "evidence_analysis",
                    InvestigationStage.status == "completed",
                )
                .order_by(desc(InvestigationStage.attempt_number))
                .limit(1)
            )
        ).scalar_one_or_none()
        if not analysis:
            raise InvestigationFailure(
                "ANALYSIS_NO_BASELINE", "No analysis verdict to review.", False
            )
        case = session.execute(
            select(Investigation.title, Investigation.bug_report).where(
                Investigation.id == investigation_id
            )
        ).one()
    provider = _resolve_provider(model_provider)
    bundle = _case_bundle(session_factory, investigation_id, store, case[0], case[1])

    tool_run_id: uuid.UUID | None = None
    try:
        with session_factory() as session:
            tool_run_id = investigation_service.create_tool_run(
                session, job_id=job_id, worker_id=worker_id,
                investigation_id=investigation_id, tool_name="model_hypothesis",
                request_summary={
                    "schema": SCHEMA_HYPOTHESES,
                    "evidence_count": bundle["evidence_count"],
                    "prompt_chars": len(bundle["prompt"]),
                },
                stage_execution_id=stage_id,
            )
    except ApiError as exc:
        if exc.code in ("LEASE_LOST", "JOB_SUPERSEDED"):
            raise InvestigationAbort() from exc
        raise InvestigationFailure(exc.code, exc.message, False) from exc

    last_error: InvestigationFailure | None = None
    for _ in range(HYPOTHESIS_RESAMPLES):
        try:
            result = _sample_model(
                provider, HYPOTHESIS_SYSTEM_PROMPT, bundle["prompt"],
                SCHEMA_HYPOTHESES, "root_cause_analysis",
            )
        except ApiError as exc:
            if exc.code == "MODEL_PROVIDER_UNAVAILABLE":
                raise InvestigationFailure(exc.code, exc.message, True) from exc
            raise InvestigationFailure(exc.code, exc.message, False) from exc
        try:
            drafts = parse_hypotheses(result.document)
        except ApiError:
            last_error = InvestigationFailure(
                "MODEL_OUTPUT_INVALID", "The model output failed validation.", False
            )
            continue
        try:
            with session_factory() as session:
                created = hypothesis_service.propose_hypotheses(
                    session, job_id=job_id, worker_id=worker_id,
                    investigation_id=investigation_id, stage_id=stage_id,
                    tool_run_id=tool_run_id, drafts=drafts,
                )
        except ApiError as exc:
            if exc.code in ("LEASE_LOST", "JOB_SUPERSEDED"):
                raise InvestigationAbort() from exc
            last_error = InvestigationFailure(exc.code, exc.message, False)
            continue
        with session_factory() as session:
            investigation_service.finish_tool_run(
                session, tool_run_id=tool_run_id, status="succeeded",
                result_summary={
                    "model": result.model,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "latency_ms": result.latency_ms,
                    "hypothesis_ids": [item["id"] for item in created],
                },
            )
        terminal = str(analysis.get("outcome", "completed"))
        return {
            "outcome": terminal,
            "hypothesis_count": len(created),
            "hypothesis_ids": [item["id"] for item in created],
        }
    assert last_error is not None
    with session_factory() as session:
        try:
            investigation_service.finish_tool_run(
                session, tool_run_id=tool_run_id, status="failed",
                result_summary={"error_code": last_error.code},
            )
        except ApiError:
            pass
    raise last_error


def _case_bundle(
    session_factory: Any, investigation_id: uuid.UUID, store: Any, title: str, bug_report: str
) -> dict:
    """Bounded redacted bundle for one model call (no bytes, no secrets)."""
    from sqlalchemy import select

    from app.config import get_settings
    from app.models import EvidenceArtifact

    with session_factory() as session:
        rows = list(
            session.execute(
                select(
                    EvidenceArtifact.id,
                    EvidenceArtifact.kind,
                    EvidenceArtifact.mime_type,
                    EvidenceArtifact.storage_key,
                )
                .where(EvidenceArtifact.investigation_id == investigation_id)
                .order_by(EvidenceArtifact.created_at.asc(), EvidenceArtifact.id.asc())
            )
        )
    settings_bucket = get_settings().s3_evidence_bucket
    active_store = store
    if active_store is None:
        from app.services import evidence as evidence_service

        active_store = evidence_service.get_store()
    excerpts: list[str] = []
    for row_id, kind, mime, storage_key in rows:
        if mime not in ("application/json", "text/plain") or kind not in (
            "log",
            "network_summary",
            "test_output",
            "build_output",
        ):
            excerpts.append(f"- {row_id} [{kind}]: (binary artifact, see evidence list)")
            continue
        try:
            raw = active_store.get_bytes(settings_bucket, storage_key)
        except Exception as exc:
            logger.warning("evidence excerpt failed kind=%s error=%s", kind, exc)
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
        clipped = text[:EVIDENCE_EXCERPT_CHARS]
        excerpts.append(f"- {row_id} [{kind}]:\n{clipped}")
    prompt = (
        f"Bug title: {title[:500]}\nBug report: {bug_report[:PROMPT_BUG_CHARS]}\n"
        f"Evidence ({len(rows)} artifacts):\n" + "\n".join(excerpts)
    )
    return {"prompt": prompt, "evidence_count": len(rows)}


def _stage_lines(session_factory: Any, investigation_id: uuid.UUID) -> list[str]:
    from sqlalchemy import select

    from app.models import InvestigationStage

    with session_factory() as session:
        rows = list(
            session.execute(
                select(
                    InvestigationStage.stage_key,
                    InvestigationStage.status,
                    InvestigationStage.attempt_number,
                )
                .where(InvestigationStage.investigation_id == investigation_id)
                .order_by(
                    InvestigationStage.created_at.asc(), InvestigationStage.id.asc()
                )
            )
        )
    lines = [
        f"- {key} [{status}] (attempt {attempt})" for key, status, attempt in rows
    ]
    return lines[:40]


def _generate_report(
    session_factory: Any,
    job_id: uuid.UUID,
    worker_id: str,
    investigation_id: uuid.UUID,
    *,
    stage_id: uuid.UUID,
    store: Any,
    model_provider: Any,
    verdict: str,
    verdict_summary: str,
) -> dict:
    """Build and persist the investigation report (D68, best-effort caller).

    Raises InvestigationFailure for provider/validation/persistence
    problems (MODEL_NOT_CONFIGURED when no provider is set); lease and
    cancel signals propagate as InvestigationAbort. The caller decides
    that a missing report never overrides the deterministic verdict.
    """
    from app.services import reports as report_service
    from app.services.model_gateway import SCHEMA_REPORT, parse_report

    with session_factory() as session:
        inv = session.get(Investigation, investigation_id)
        if inv is None:
            raise InvestigationFailure(
                "INVESTIGATION_GONE", "The investigation is gone.", False
            )
        title, bug_report = inv.title, inv.bug_report
    provider = _resolve_provider(model_provider)
    bundle = _case_bundle(session_factory, investigation_id, store, title, bug_report)
    prompt = (
        f"Verification verdict: {verdict}: {verdict_summary[:500]}\n"
        "Stage history:\n" + "\n".join(_stage_lines(session_factory, investigation_id)) + "\n"
        "Accepted hypotheses:\n"
        + "\n".join(_hypothesis_lines(session_factory, investigation_id)) + "\n"
        + bundle["prompt"]
    )
    tool_run_id = _start_model_tool_run(
        session_factory, job_id=job_id, worker_id=worker_id,
        investigation_id=investigation_id, stage_id=stage_id, tool_name="model_report",
        request_summary={
            "schema": SCHEMA_REPORT,
            "evidence_count": bundle["evidence_count"],
            "prompt_chars": len(prompt),
        },
    )
    last_error = "unknown error"
    for _ in range(MODEL_RESAMPLES):
        result = _sample_model(
            provider, REPORT_SYSTEM_PROMPT, prompt, SCHEMA_REPORT, "report_generation"
        )
        try:
            draft = parse_report(result.document)
        except ApiError as exc:
            last_error = exc.code
            continue
        try:
            with session_factory() as session:
                created = report_service.create_report(
                    session, job_id=job_id, worker_id=worker_id,
                    investigation_id=investigation_id, stage_id=stage_id,
                    tool_run_id=tool_run_id, model=result.model, draft=draft,
                )
        except ApiError as exc:
            if exc.code in ("LEASE_LOST", "JOB_SUPERSEDED"):
                raise InvestigationAbort() from exc
            last_error = exc.code
            continue
        with session_factory() as session:
            investigation_service.finish_tool_run(
                session, tool_run_id=tool_run_id, status="succeeded",
                result_summary={
                    "model": result.model,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "latency_ms": result.latency_ms,
                    "report_id": created["id"],
                },
            )
        return {"report_id": created["id"], "report_status": "ready"}
    _fail_tool_run(session_factory, tool_run_id, last_error)
    raise InvestigationFailure(
        "MODEL_OUTPUT_INVALID", "The report output failed validation.", False
    )


def _project_and_snapshot(
    session_factory: Any, investigation_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    with session_factory() as session:
        inv = session.get(Investigation, investigation_id)
        assert inv is not None
        project_id = inv.project_id
        snapshot_id = inv.repository_snapshot_id
    if snapshot_id is None:
        raise InvestigationFailure(
            "SNAPSHOT_MISSING", "The investigation has no snapshot.", False
        )
    return project_id, snapshot_id


def _resolve_provider(model_provider: Any) -> Any:
    """Resolve via the AI gateway: Meta Spark > Meta Llama > existing."""
    from app.ai.providers import resolve_text_provider

    if model_provider is not None:
        return model_provider
    resolved = resolve_text_provider()
    if not resolved.configured or resolved.provider is None:
        raise InvestigationFailure("MODEL_NOT_CONFIGURED", resolved.reason, False)
    return resolved.provider


def _start_model_tool_run(
    session_factory: Any,
    *,
    job_id: uuid.UUID,
    worker_id: str,
    investigation_id: uuid.UUID,
    stage_id: uuid.UUID,
    tool_name: str,
    request_summary: dict,
) -> uuid.UUID:
    try:
        with session_factory() as session:
            tool_run_id: uuid.UUID | None = investigation_service.create_tool_run(
                session, job_id=job_id, worker_id=worker_id,
                investigation_id=investigation_id, tool_name=tool_name,
                request_summary=request_summary, stage_execution_id=stage_id,
            )
    except ApiError as exc:
        if exc.code in ("LEASE_LOST", "JOB_SUPERSEDED"):
            raise InvestigationAbort() from exc
        raise InvestigationFailure(exc.code, exc.message, False) from exc
    assert tool_run_id is not None
    return tool_run_id


def _fail_tool_run(session_factory: Any, tool_run_id: uuid.UUID, code: str) -> None:
    with session_factory() as session:
        try:
            investigation_service.finish_tool_run(
                session, tool_run_id=tool_run_id, status="failed",
                result_summary={"error_code": code},
            )
        except ApiError:
            pass


def _sample_model(
    provider: Any, system_prompt: str, user_prompt: str, schema_name: str,
    task: str = "complex_reasoning",
) -> Any:
    from app.ai import timed_complete

    try:
        return timed_complete(provider, task, system_prompt, user_prompt, schema_name)
    except ApiError as exc:
        if exc.code == "MODEL_PROVIDER_UNAVAILABLE":
            raise InvestigationFailure(exc.code, exc.message, True) from exc
        raise InvestigationFailure(exc.code, exc.message, False) from exc


def _hypothesis_lines(session_factory: Any, investigation_id: uuid.UUID) -> list[str]:
    from sqlalchemy import select

    from app.models import Hypothesis

    with session_factory() as session:
        rows = list(
            session.execute(
                select(Hypothesis.title, Hypothesis.description, Hypothesis.confidence)
                .where(Hypothesis.investigation_id == investigation_id)
                .order_by(Hypothesis.created_at.asc(), Hypothesis.id.asc())
            )
        )
    return [
        f"- {title[:160]} (confidence {confidence}): {description[:500]}"
        for title, description, confidence in rows
    ]


def _create_tests(
    session_factory: Any,
    job_id: uuid.UUID,
    worker_id: str,
    investigation_id: uuid.UUID,
    *,
    stage_id: uuid.UUID,
    store: Any,
    model_provider: Any,
) -> dict:
    """regression_test_creation: model-authored e2e tests with artifacts (M8)."""
    from app.config import get_settings
    from app.services import regression_tests as regression_test_service
    from app.services.model_gateway import (
        SCHEMA_REGRESSION_TESTS,
        parse_regression_tests,
    )

    project_id, _snapshot_id = _project_and_snapshot(session_factory, investigation_id)
    with session_factory() as session:
        inv = session.get(Investigation, investigation_id)
        assert inv is not None
        title, bug_report = inv.title, inv.bug_report
    provider = _resolve_provider(model_provider)
    bundle = _case_bundle(session_factory, investigation_id, store, title, bug_report)
    prompt = bundle["prompt"] + "\nAccepted hypotheses:\n"
    prompt += "\n".join(_hypothesis_lines(session_factory, investigation_id))
    tool_run_id = _start_model_tool_run(
        session_factory, job_id=job_id, worker_id=worker_id,
        investigation_id=investigation_id, stage_id=stage_id, tool_name="model_tests",
        request_summary={
            "schema": SCHEMA_REGRESSION_TESTS,
            "evidence_count": bundle["evidence_count"],
            "prompt_chars": len(prompt),
        },
    )
    settings = get_settings()
    last_error: InvestigationFailure | None = None
    for _ in range(MODEL_RESAMPLES):
        result = _sample_model(
            provider, TESTS_SYSTEM_PROMPT, prompt, SCHEMA_REGRESSION_TESTS,
            "structured_extraction",
        )
        try:
            drafts = parse_regression_tests(result.document, settings)
        except ApiError:
            last_error = InvestigationFailure(
                "MODEL_OUTPUT_INVALID", "The model output failed validation.", False
            )
            continue
        try:
            with session_factory() as session:
                created = regression_test_service.create_from_drafts(
                    session, job_id=job_id, worker_id=worker_id,
                    investigation_id=investigation_id, stage_id=stage_id,
                    tool_run_id=tool_run_id, project_id=project_id,
                    drafts=drafts, store=store,
                )
        except ApiError as exc:
            if exc.code in ("LEASE_LOST", "JOB_SUPERSEDED"):
                raise InvestigationAbort() from exc
            last_error = InvestigationFailure(exc.code, exc.message, False)
            continue
        with session_factory() as session:
            investigation_service.finish_tool_run(
                session, tool_run_id=tool_run_id, status="succeeded",
                result_summary={
                    "model": result.model,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "latency_ms": result.latency_ms,
                    "test_ids": [item["id"] for item in created],
                },
            )
        return {
            "outcome": "completed",
            "test_count": len(created),
            "test_ids": [item["id"] for item in created],
        }
    assert last_error is not None
    _fail_tool_run(session_factory, tool_run_id, last_error.code)
    raise last_error


def _load_suite_items(
    session_factory: Any, tests: list[Any], store: Any
) -> tuple[list[dict], list[dict]]:
    """Validate executable steps; invalid artifacts block their test only."""
    from sqlalchemy import select

    from app.models import RegressionTest
    from app.services import regression_tests as regression_test_service

    items: list[dict] = []
    skipped: list[dict] = []
    for test in tests:
        with session_factory() as session:
            row = (
                session.execute(
                    select(RegressionTest).where(RegressionTest.id == test.id)
                )
            ).scalar_one()
            try:
                context = regression_test_service.load_artifact_steps(
                    session, row, store
                )
            except ApiError:
                regression_test_service.transition_test(session, test.id, "blocked")
                skipped.append({"test_id": test.id, "title": test.title})
                continue
        items.append({"test_id": test.id, "title": test.title, "context": context})
    return items, skipped


def _apply_verdicts(
    session_factory: Any,
    verdicts: list[dict],
    mapping: dict[str, str],
    run_id: uuid.UUID,
    skipped: list[dict],
) -> dict[str, int]:
    from app.services import regression_tests as regression_test_service
    from app.services import verification as verification_service

    counts = {"failed": 0, "passed": 0, "inconclusive": 0}
    with session_factory() as session:
        for verdict in verdicts:
            regression_test_service.transition_test(
                session, verdict["test_id"], mapping[verdict["verdict"]]
            )
            counts[verdict["verdict"]] += 1
        for item in skipped:
            verification_service.record_check(
                session, run_id=run_id, check_key=str(item["test_id"]),
                display_name=str(item["title"])[:300], status="skipped",
                regression_test_id=item["test_id"],
            )
    return counts


def _baseline(
    session_factory: Any,
    job: dict,
    worker_id: str,
    investigation_id: uuid.UUID,
    workspace_id: uuid.UUID,
    *,
    stage_id: uuid.UUID,
    client: Any,
    store: Any,
    is_cancelled: Any,
) -> dict:
    """baseline_test_execution: created tests against the base snapshot (M8).

    A failing baseline verdict means the test reproduces the bug — the
    expected outcome — so the stage completes either way and the run
    status carries the gate meaning.
    """
    from sqlalchemy import func, select

    from app.models import RegressionTest
    from app.services import regression_tests as regression_test_service
    from app.services import verification as verification_service
    from investigation.verification_runner import run_test_suite

    project_id, snapshot_id = _project_and_snapshot(session_factory, investigation_id)
    with session_factory() as session:
        tests = regression_test_service.executable_tests(session, investigation_id)
        test_refs = [(test.id, test.title) for test in tests]
        total = (
            session.execute(
                select(func.count()).where(
                    RegressionTest.investigation_id == investigation_id
                )
            )
        ).scalar_one()
    if not test_refs:
        if total == 0:
            raise InvestigationFailure(
                "NO_EXECUTABLE_TESTS",
                "No executable regression test is available for baseline.",
                False,
            )
        return {"outcome": "completed", "note": "no remaining executable tests"}
    items, skipped = _load_suite_items(session_factory, tests, store)
    outcome = run_test_suite(
        session_factory, job=job, worker_id=worker_id,
        investigation_id=investigation_id, project_id=project_id,
        snapshot_id=snapshot_id, workspace_id=workspace_id, tests=items,
        phase="baseline", patch_id=None, stage_id=stage_id,
        client=client, store=store, is_cancelled=is_cancelled,
    )
    counts = _apply_verdicts(
        session_factory,
        outcome["verdicts"],
        {
            "failed": "baseline_failed",
            "passed": "baseline_passed",
            "inconclusive": "blocked",
        },
        outcome["run_id"],
        skipped,
    )
    recorded = (
        ["failed"] * counts["failed"]
        + ["passed"] * counts["passed"]
        + ["inconclusive"] * counts["inconclusive"]
        + ["skipped"] * len(skipped)
    )
    run_status = verification_service.derive_verdict(recorded)
    summary = (
        f"baseline: {counts['failed']} reproducing, "
        f"{counts['passed']} passing, "
        f"{counts['inconclusive']} inconclusive, {len(skipped)} skipped"
    )
    if outcome.get("adopted"):
        planned = outcome.get("planned_total")
        qualifier = f"rerun of {planned} planned checks" if planned is not None else "rerun"
        summary = f"{qualifier}; {summary}"
    with session_factory() as session:
        verification_service.finish_run(
            session, run_id=outcome["run_id"], status=run_status, summary=summary,
        )
    return {
        "outcome": "completed", "run_id": str(outcome["run_id"]),
        "reproducing": counts["failed"], "passing": counts["passed"],
        "inconclusive": counts["inconclusive"], "skipped": len(skipped),
    }


def _baseline_lines(session_factory: Any, investigation_id: uuid.UUID) -> list[str]:
    from sqlalchemy import desc, select

    from app.models import RegressionTest, VerificationRun

    with session_factory() as session:
        tests = list(
            session.execute(
                select(RegressionTest.title, RegressionTest.status)
                .where(RegressionTest.investigation_id == investigation_id)
                .order_by(RegressionTest.created_at.asc(), RegressionTest.id.asc())
                .limit(12)
            )
        )
        run = (
            session.execute(
                select(VerificationRun.status, VerificationRun.summary)
                .where(
                    VerificationRun.investigation_id == investigation_id,
                    VerificationRun.phase == "baseline",
                )
                .order_by(desc(VerificationRun.created_at), desc(VerificationRun.id))
                .limit(1)
            )
        ).one_or_none()
    lines = [f"- {title[:120]}: {status}" for title, status in tests]
    if run is not None:
        lines.append(f"Baseline run {run[0]}: {(run[1] or '')[:300]}")
    return lines


def _source_excerpts(session_factory: Any, snapshot_id: uuid.UUID) -> list[str]:
    from sqlalchemy import select

    from app.models import SnapshotFile
    from app.services.redact import redact_text

    with session_factory() as session:
        rows = list(
            session.execute(
                select(SnapshotFile.path, SnapshotFile.content)
                .where(
                    SnapshotFile.snapshot_id == snapshot_id,
                    SnapshotFile.is_text.is_(True),
                    SnapshotFile.content.is_not(None),
                )
                .order_by(SnapshotFile.path.asc())
                .limit(SOURCE_EXCERPT_FILES)
            )
        )
    excerpts = []
    for path, content in rows:
        cleaned = redact_text(content) or ""
        excerpts.append(f"--- {path} ---\n{cleaned[:SOURCE_EXCERPT_CHARS]}")
    return excerpts


def _propose_patch(
    session_factory: Any,
    job_id: uuid.UUID,
    worker_id: str,
    investigation_id: uuid.UUID,
    *,
    stage_id: uuid.UUID,
    store: Any,
    model_provider: Any,
) -> dict:
    """patch_proposal: minimal unified diff grounded in failures (M8)."""
    from app.config import get_settings
    from app.services import patches as patch_service
    from app.services.model_gateway import SCHEMA_PATCH, parse_patch_proposal

    project_id, snapshot_id = _project_and_snapshot(session_factory, investigation_id)
    with session_factory() as session:
        inv = session.get(Investigation, investigation_id)
        assert inv is not None
        title, bug_report = inv.title, inv.bug_report
    provider = _resolve_provider(model_provider)
    bundle = _case_bundle(session_factory, investigation_id, store, title, bug_report)
    prompt = bundle["prompt"] + "\nAccepted hypotheses:\n"
    prompt += "\n".join(_hypothesis_lines(session_factory, investigation_id))
    prompt += "\nBaseline verdicts:\n"
    prompt += "\n".join(_baseline_lines(session_factory, investigation_id))
    prompt += "\nSource excerpts:\n"
    prompt += "\n".join(_source_excerpts(session_factory, snapshot_id))
    tool_run_id = _start_model_tool_run(
        session_factory, job_id=job_id, worker_id=worker_id,
        investigation_id=investigation_id, stage_id=stage_id, tool_name="model_patch",
        request_summary={
            "schema": SCHEMA_PATCH,
            "evidence_count": bundle["evidence_count"],
            "prompt_chars": len(prompt),
        },
    )
    settings = get_settings()
    last_error: InvestigationFailure | None = None
    for _ in range(MODEL_RESAMPLES):
        result = _sample_model(
            provider, PATCH_SYSTEM_PROMPT, prompt, SCHEMA_PATCH, "remediation_suggestion"
        )
        try:
            draft = parse_patch_proposal(result.document, settings.patch_max_diff_bytes)
        except ApiError:
            last_error = InvestigationFailure(
                "MODEL_OUTPUT_INVALID", "The model output failed validation.", False
            )
            continue
        try:
            with session_factory() as session:
                created = patch_service.create_proposal(
                    session, job_id=job_id, worker_id=worker_id,
                    investigation_id=investigation_id, project_id=project_id,
                    base_snapshot_id=snapshot_id, stage_id=stage_id,
                    tool_run_id=tool_run_id, summary=draft.summary,
                    diff_text=draft.diff, store=store,
                )
        except ApiError as exc:
            if exc.code in ("LEASE_LOST", "JOB_SUPERSEDED"):
                raise InvestigationAbort() from exc
            last_error = InvestigationFailure(exc.code, exc.message, False)
            continue
        with session_factory() as session:
            investigation_service.finish_tool_run(
                session, tool_run_id=tool_run_id, status="succeeded",
                result_summary={
                    "model": result.model,
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "latency_ms": result.latency_ms,
                    "patch_id": created["id"],
                },
            )
        return {
            "outcome": "completed", "patch_id": created["id"],
            "files_changed": created["files_changed"],
        }
    assert last_error is not None
    _fail_tool_run(session_factory, tool_run_id, last_error.code)
    raise last_error


def _await_approval(
    session_factory: Any,
    job_id: uuid.UUID,
    worker_id: str,
    investigation_id: uuid.UUID,
) -> dict:
    """awaiting_user_approval: submit the proposal, then park (M8).

    Always raises InvestigationParked: the stage completes and the job
    ends, leaving the investigation parked for a human decision.
    """
    from app.services import patches as patch_service

    try:
        with session_factory() as session:
            patch = patch_service.submit_for_approval(
                session, job_id=job_id, worker_id=worker_id,
                investigation_id=investigation_id,
            )
            patch_id = str(patch.id)
    except ApiError as exc:
        if exc.code in ("LEASE_LOST", "JOB_SUPERSEDED"):
            raise InvestigationAbort() from exc
        raise InvestigationFailure(exc.code, exc.message, False) from exc
    try:
        with session_factory() as session:
            investigation_service.park_for_approval(
                session, job_id=job_id, worker_id=worker_id,
                investigation_id=investigation_id,
            )
    except ApiError as exc:
        if exc.code in ("LEASE_LOST", "JOB_SUPERSEDED"):
            raise InvestigationAbort() from exc
        raise InvestigationFailure(exc.code, exc.message, False) from exc
    with session_factory() as session:
        activity_service.append_event(
            session, investigation_id, "patch.submitted",
            f"Patch proposed: {patch_id[:8]}.",
            {"patch_id": patch_id},
        )
    raise InvestigationParked({"outcome": "awaiting_approval", "patch_id": patch_id})


def _apply_patch(
    session_factory: Any,
    job_id: uuid.UUID,
    worker_id: str,
    investigation_id: uuid.UUID,
    workspace_id: uuid.UUID,
    *,
    store: Any,
) -> dict:
    """patch_application: strict isolated apply of the approved diff (M8)."""
    import hashlib
    import uuid as uuid_mod

    from app.config import get_settings
    from app.services import patches as patch_service
    from investigation.patch_apply import apply_patch_to_snapshot

    with session_factory() as session:
        inv = session.get(Investigation, investigation_id)
        assert inv is not None
        project_id = inv.project_id
        patch = patch_service.latest_with_status(
            session, investigation_id, ("approved",)
        )
        if patch is None or patch.approval_status != "approved":
            raise InvestigationFailure(
                "PATCH_NOT_APPROVED", "No approved patch is ready to apply.", False
            )
        patch_id = patch.id
        base_snapshot_id = patch.base_snapshot_id
        storage_key = patch.diff_storage_key
        digest = patch.diff_sha256
    settings = get_settings()
    active_store = store
    if active_store is None:
        active_store = evidence_service.get_store()
    try:
        raw = active_store.get_bytes(settings.s3_evidence_bucket, storage_key)
    except Exception as exc:
        raise InvestigationFailure(
            "PATCH_STORE_UNAVAILABLE", "The approved diff could not be fetched.", True
        ) from exc
    if hashlib.sha256(raw).hexdigest() != digest:
        raise InvestigationFailure(
            "PATCH_STORE_INVALID", "The stored diff does not match its digest.", False
        )
    try:
        diff_text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvestigationFailure(
            "PATCH_STORE_INVALID", "The stored diff is not valid text.", False
        ) from exc
    result = apply_patch_to_snapshot(
        session_factory, job_id=job_id, worker_id=worker_id,
        investigation_id=investigation_id, project_id=project_id,
        workspace_id=workspace_id, base_snapshot_id=base_snapshot_id,
        patch_id=patch_id, diff_text=diff_text, store=store,
    )
    try:
        with session_factory() as session:
            patch_service.mark_applied(
                session, job_id=job_id, worker_id=worker_id, patch_id=patch_id,
                applied_snapshot_id=uuid_mod.UUID(result["snapshot_id"]),
            )
    except ApiError as exc:
        if exc.code in ("LEASE_LOST", "JOB_SUPERSEDED"):
            raise InvestigationAbort() from exc
        raise InvestigationFailure(exc.code, exc.message, False) from exc
    return {
        "outcome": "completed", "patch_id": str(patch_id),
        "snapshot_id": result["snapshot_id"], "written": result["written"],
    }


def _post_verify(
    session_factory: Any,
    job: dict,
    worker_id: str,
    investigation_id: uuid.UUID,
    workspace_id: uuid.UUID,
    *,
    stage_id: uuid.UUID,
    client: Any,
    store: Any,
    is_cancelled: Any,
    model_provider: Any = None,
) -> dict:
    """post_patch_verification: gated tests on the patched tree (M8).

    Only baseline-failed tests gate the patch. A passing gate
    completes the investigation; a failing gate fails it with an
    honest summary so a retry can propose a fresh patch. A model
    report is attempted before finalization (D68): a missing report
    never overrides the deterministic verdict.
    """
    from sqlalchemy import func, select

    from app.models import RegressionTest
    from app.services import patches as patch_service
    from app.services import regression_tests as regression_test_service
    from app.services import verification as verification_service
    from investigation.verification_runner import run_test_suite

    project_id, _snapshot_id = _project_and_snapshot(session_factory, investigation_id)
    with session_factory() as session:
        patch = patch_service.latest_with_status(
            session, investigation_id, ("applied",)
        )
        if patch is None or patch.applied_snapshot_id is None:
            raise InvestigationFailure(
                "PATCH_NOT_APPLIED", "No applied patch is ready to verify.", False
            )
        patch_id = patch.id
        applied_snapshot_id = patch.applied_snapshot_id
        tests = regression_test_service.gated_tests(session, investigation_id)
        test_refs = [(test.id, test.title) for test in tests]
        total = (
            session.execute(
                select(func.count()).where(
                    RegressionTest.investigation_id == investigation_id
                )
            )
        ).scalar_one()
    if not test_refs:
        if total == 0:
            raise InvestigationFailure(
                "VERIFICATION_NO_BASELINE",
                "No baseline-failed test gates this patch.",
                False,
            )
        return {"outcome": "completed", "note": "no remaining gated tests"}
    items, skipped = _load_suite_items(session_factory, tests, store)
    outcome = run_test_suite(
        session_factory, job=job, worker_id=worker_id,
        investigation_id=investigation_id, project_id=project_id,
        snapshot_id=applied_snapshot_id, workspace_id=workspace_id, tests=items,
        phase="post_patch", patch_id=patch_id, stage_id=stage_id,
        client=client, store=store, is_cancelled=is_cancelled,
    )
    counts = _apply_verdicts(
        session_factory, outcome["verdicts"],
        {
            "failed": "post_patch_failed",
            "passed": "post_patch_passed",
            "inconclusive": "blocked",
        },
        outcome["run_id"], skipped,
    )
    recorded = (
        ["failed"] * counts["failed"]
        + ["passed"] * counts["passed"]
        + ["inconclusive"] * counts["inconclusive"]
        + ["skipped"] * len(skipped)
    )
    run_status = verification_service.derive_verdict(recorded)
    if run_status in ("failed", "timed_out"):
        terminal, passed = "failed", False
    elif run_status == "passed":
        terminal, passed = "completed", True
    else:
        terminal, passed = "inconclusive", None
    summary = (
        f"patch {str(patch_id)[:8]}: {counts['passed']} passing, "
        f"{counts['failed']} failing, {counts['inconclusive']} inconclusive, "
        f"{len(skipped)} skipped"
    )
    if outcome.get("adopted"):
        planned = outcome.get("planned_total")
        qualifier = f"rerun of {planned} planned checks" if planned is not None else "rerun"
        summary = f"{qualifier}; {summary}"
    try:
        with session_factory() as session:
            verification_service.finish_run(
                session, run_id=outcome["run_id"], status=run_status, summary=summary,
            )
            if passed is not None:
                patch_service.mark_verified(
                    session, job_id=uuid.UUID(str(job["id"])), worker_id=worker_id,
                    patch_id=patch_id, passed=passed,
                )
            if passed is True:
                result_summary = f"Patch verified: {summary}."
            elif passed is False:
                result_summary = f"Patch failed verification: {summary}."
            else:
                result_summary = f"Verification inconclusive: {summary}."
            report_outcome: dict[str, str | None] = {
                "report_id": None, "report_status": "skipped_no_provider"
            }
            try:
                generated = _generate_report(
                    session_factory, uuid.UUID(str(job["id"])), worker_id,
                    investigation_id, stage_id=stage_id, store=store,
                    model_provider=model_provider, verdict=terminal,
                    verdict_summary=result_summary,
                )
                report_outcome = generated
            except InvestigationAbort:
                raise
            except InvestigationFailure as exc:
                if exc.code != "MODEL_NOT_CONFIGURED":
                    logger.warning(
                        "report unavailable investigation_id=%s code=%s",
                        investigation_id, exc.code,
                    )
                    report_outcome = {
                        "report_id": None, "report_status": f"unavailable:{exc.code}"
                    }
            investigation_service.finalize_investigation(
                session, job_id=uuid.UUID(str(job["id"])), worker_id=worker_id,
                investigation_id=investigation_id, status=terminal,
                result_summary=result_summary,
            )
    except ApiError as exc:
        if exc.code in ("LEASE_LOST", "JOB_SUPERSEDED"):
            raise InvestigationAbort() from exc
        raise InvestigationFailure(exc.code, exc.message, False) from exc
    return {
        "outcome": "completed", "run_id": str(outcome["run_id"]),
        "run_status": run_status, "patch_id": str(patch_id),
        "passing": counts["passed"], "failing": counts["failed"],
        "inconclusive": counts["inconclusive"], "skipped": len(skipped),
        "report_id": report_outcome["report_id"],
        "report_status": report_outcome["report_status"],
    }
