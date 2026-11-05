"""Trusted browser-reproduction runner (M6, worker side).

Materializes the pinned snapshot, bakes it with the trusted repro
script plus the server-validated steps into a per-execution image,
runs headless Chromium inside the isolated container, extracts the
bounded output files, and persists them as evidence. The container
holds no credentials and no network; findings cross back only through
``read_logs``/``read_files`` caps.
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from typing import Any, Callable

from app.config import get_settings
from app.envelope import ApiError
from app.services import evidence as evidence_service
from app.services import jobs as job_service
from app.services import projects as project_service
from app.services import storage as storage_service
from investigation import InvestigationAbort, InvestigationFailure
from sandbox import container_runtime, workspace
from sandbox.container_spec import build_spec
from sandbox.exceptions import SandboxError
from sandbox.execution_policy import get_policy
from sandbox.lifecycle import create_execution, finish_execution, update_cleanup

logger = logging.getLogger("meridian.investigation.browser")

SCRIPT_EXTRA = "Meridian.rules/repro.py"
STEPS_EXTRA = "Meridian.rules/steps.json"
OUT_PATH = "/tmp/meridian-out"
RESULT_FILE = "result.json"

_JSON_EVIDENCE = {"console.json": "log", "network.json": "network_summary"}
_KNOWN_FILE = re.compile(
    r"^(result\.json|console\.json|network\.json|trace\.zip|[A-Za-z0-9][A-Za-z0-9_\-]*\.png)$"
)


def _script_bytes() -> bytes:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "repro_container.py")
    with open(path, "rb") as handle:
        return handle.read()


def _map_api_error(exc: ApiError) -> InvestigationFailure:
    return InvestigationFailure(exc.code, exc.message, exc.status_code in (429, 503))


def _map_sandbox_error(exc: SandboxError) -> InvestigationFailure:
    return InvestigationFailure(exc.code, exc.message, exc.retryable)


def _redacted_steps(context: dict) -> list[dict]:
    """Steps safe for summaries: fill/assert text never persisted raw."""
    safe: list[dict] = []
    for step in context.get("steps", []):
        entry = {"action": step.get("action")}
        if step.get("selector") is not None:
            entry["selector"] = step["selector"]
        if step.get("ms") is not None:
            entry["ms"] = step["ms"]
        if step.get("name") is not None:
            entry["name"] = step["name"]
        if step.get("action") in ("fill", "assert_text"):
            entry["text"] = "[provided]"
        safe.append(entry)
    return safe


def run_browser_repro(
    session_factory: Any,
    *,
    job: dict,
    worker_id: str,
    investigation_id: uuid.UUID,
    context: dict,
    snapshot_id: uuid.UUID,
    workspace_id: uuid.UUID,
    client: Any = None,
    store: Any = None,
    is_cancelled: Callable[[], bool] | None = None,
    timeout_seconds: int | None = None,
    job_stage_key: str = "inv_reproduction",
    execution_key: str = "",
) -> dict:
    """Run one reproduction attempt; return the parsed finding summary.

    Raises InvestigationFailure (mapped to job failure) or
    InvestigationAbort (cooperative cancellation) on every other path.
    """
    try:
        job_id = uuid.UUID(str(job["id"]))
        attempt = int(job.get("attempts", 1))
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise InvestigationFailure("INVALID_JOB", "The job record is malformed.", False) from exc
    if attempt < 1:
        raise InvestigationFailure("INVALID_JOB", "Only claimed jobs may execute.", False)
    policy = get_policy("browser_repro")
    limit_seconds = timeout_seconds if timeout_seconds is not None else policy.timeout_seconds
    settings = get_settings()

    def _aborted() -> bool:
        if is_cancelled is None:
            return False
        try:
            return bool(is_cancelled())
        except Exception as exc:
            logger.warning("cancel watch failed job_id=%s error=%s", job_id, exc)
            return False

    # Snapshot must be ready and visible now, not just at enqueue time.
    try:
        with session_factory() as session:
            candidate = project_service.get_workspace_snapshot(
                session, workspace_id, snapshot_id
            )
            if candidate.storage_status != "ready" or not candidate.storage_key:
                raise InvestigationFailure(
                    "SNAPSHOT_NOT_READY", "The snapshot content is not stored.", False
                )
    except ApiError as exc:
        raise _map_api_error(exc) from exc

    tool_run_id: uuid.UUID | None = None
    try:
        with session_factory() as session:
            from app.services import investigations as investigation_service

            tool_run_id = investigation_service.create_tool_run(
                session, job_id=job_id, worker_id=worker_id,
                investigation_id=investigation_id, tool_name="browser_repro",
                request_summary={
                    "route": context.get("route", "/"),
                    "viewport": context.get("viewport", {}),
                    "steps": _redacted_steps(context),
                },
            )
    except ApiError as exc:
        if exc.code in ("LEASE_LOST", "JOB_SUPERSEDED"):
            raise InvestigationAbort() from exc
        raise _map_api_error(exc) from exc

    def _finish_tool(status: str, result: dict, error: tuple[str, str] | None = None) -> None:
        merged = dict(result)
        if error:
            merged["error_code"] = error[0]
            merged["error_message"] = error[1]
        try:
            with session_factory() as session:
                from app.services import investigations as investigation_service

                investigation_service.finish_tool_run(
                    session, tool_run_id=tool_run_id, status=status,
                    result_summary=merged,
                )
        except Exception as exc:
            logger.warning("tool run finish failed tool_run_id=%s error=%s", tool_run_id, exc)

    execution_uuid = uuid.uuid4()
    execution_id = execution_uuid.hex
    with session_factory() as session:
        try:
            create_execution(
                session, execution_id=execution_uuid, job_id=job_id,
                worker_id=worker_id, snapshot_id=snapshot_id,
                profile=policy.profile, attempt=attempt,
                run_key=execution_key,
            )
        except SandboxError as exc:
            _finish_tool("failed", {}, (exc.code, exc.message))
            raise _map_sandbox_error(exc) from exc

    ws_dir: str | None = None
    container: Any = None
    own_client: Any = client
    image_tag: str | None = None
    finished = False

    try:
        if _aborted():
            raise InvestigationAbort()
        if own_client is None:
            try:
                own_client = container_runtime.get_client()
            except SandboxError as exc:
                raise _map_sandbox_error(exc) from exc
        ws_dir = workspace.create_workspace()
        try:
            with session_factory() as session:
                storage_service.materialize_for_workspace(
                    session, workspace_id, snapshot_id, ws_dir, store=store
                )
        except ApiError as exc:
            raise _map_api_error(exc) from exc
        steps_blob = json.dumps(
            context, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        try:
            context_tar, context_digest = workspace.pack_build_context(
                ws_dir,
                base_image=policy.image,
                extra_root_files={SCRIPT_EXTRA: _script_bytes(), STEPS_EXTRA: steps_blob},
            )
        except SandboxError as exc:
            raise _map_sandbox_error(exc) from exc
        image_tag = f"meridian-repro-{context_digest[:16]}"
        try:
            container_runtime.build_source_image(own_client, context_tar, image_tag)
        except SandboxError as exc:
            raise _map_sandbox_error(exc) from exc
        try:
            spec = build_spec(policy, execution_id, image=image_tag)
            container = container_runtime.create_container(own_client, spec)
            run = container_runtime.run_to_completion(
                container, limit_seconds, should_abort=_aborted
            )
        except SandboxError as exc:
            if exc.code == "EXECUTION_CANCELLED":
                raise InvestigationAbort() from exc
            raise _map_sandbox_error(exc) from exc
        try:
            logs = container_runtime.read_logs(container, policy.max_output_bytes)
            extracted = container_runtime.read_files(
                container, OUT_PATH,
                max_files=settings.evidence_max_files,
                max_file_bytes=settings.evidence_max_artifact_bytes,
                max_total_bytes=settings.evidence_max_artifact_bytes
                * settings.evidence_max_files,
            )
        except SandboxError as exc:
            raise _map_sandbox_error(exc) from exc
        finally:
            if image_tag is not None:
                container_runtime.remove_image(own_client, image_tag)
        if run["timed_out"]:
            _finish_tool("timed_out", {"duration_ms": run["duration_ms"]})
            _finish_execution(
                session_factory, execution_uuid, status="timed_out",
                exit_code=run["exit_code"], timed_out=True,
                duration_ms=run["duration_ms"],
                stdout=logs["stdout"], stderr=logs["stderr"],
                truncated=logs["truncated"],
                error=("COMMAND_TIMEOUT", "Reproduction exceeded its time limit."),
            )
            finished = True
            raise InvestigationFailure(
                "COMMAND_TIMEOUT", "Reproduction exceeded its time limit.", True
            )
        if run["exit_code"] != 0:
            _finish_tool("failed", {"exit_code": run["exit_code"]})
            _finish_execution(
                session_factory, execution_uuid, status="failed",
                exit_code=run["exit_code"], duration_ms=run["duration_ms"],
                stdout=logs["stdout"], stderr=logs["stderr"],
                truncated=logs["truncated"],
                error=("REPRO_CONTAINER_FAILED", f"Exit code {run['exit_code']}."),
            )
            finished = True
            raise InvestigationFailure(
                "REPRO_CONTAINER_FAILED", f"Exit code {run['exit_code']}.", True
            )
        files: dict[str, bytes] = extracted["files"]
        raw_result = files.get(RESULT_FILE)
        if raw_result is None:
            raise InvestigationFailure(
                "REPRO_OUTPUT_INVALID", "Reproduction produced no result.", False
            )
        try:
            result_doc = json.loads(raw_result.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise InvestigationFailure(
                "REPRO_OUTPUT_INVALID", "Reproduction result is not valid JSON.", False
            ) from None
        if (
            not isinstance(result_doc, dict)
            or result_doc.get("version") != 1
            or "reproduced" not in result_doc
        ):
            raise InvestigationFailure(
                "REPRO_OUTPUT_INVALID", "Reproduction result has an unknown shape.", False
            )
        evidence_ids = _upload_evidence(
            session_factory, project_id=_project_of(session_factory, investigation_id),
            investigation_id=investigation_id, tool_run_id=tool_run_id,
            files=files, skipped=extracted["skipped"], store=store,
        )
        assertions = result_doc.get("assertions", [])
        passed = sum(1 for item in assertions if item.get("passed"))
        summary = {
            "reproduced": result_doc.get("reproduced"),
            "assertions_total": len(assertions),
            "assertions_passed": passed,
            "failed_step": result_doc.get("failed_step"),
            "console_errors": result_doc.get("console_errors", 0),
            "failed_requests": result_doc.get("failed_requests", 0),
            "trace_omitted": bool(result_doc.get("trace_omitted")),
            "evidence_ids": evidence_ids,
            "tool_run_id": str(tool_run_id),
            "playwright_version": result_doc.get("playwright_version"),
        }
        _finish_tool("succeeded", summary)
        _finish_execution(
            session_factory, execution_uuid, status="completed",
            exit_code=0, duration_ms=run["duration_ms"],
            stdout=logs["stdout"], stderr=logs["stderr"],
            truncated=logs["truncated"],
        )
        finished = True
        try:
            with session_factory() as session:
                job_service.record_stage(
                    session, job_id, worker_id, job_stage_key, "completed",
                    result_summary={
                        "reproduced": summary["reproduced"],
                        "evidence_count": len(evidence_ids),
                    },
                )
        except ApiError:
            pass
        return summary
    except InvestigationAbort:
        _finish_tool("cancelled", {})
        if not finished:
            _finish_execution(
                session_factory, execution_uuid, status="cancelled",
                error=("EXECUTION_CANCELLED", "The execution was cancelled."),
            )
        raise
    except InvestigationFailure as exc:
        if not finished:
            _finish_execution(
                session_factory, execution_uuid, status="failed",
                error=(exc.code, exc.message),
            )
            if tool_run_id is not None and exc.code not in (
                "COMMAND_TIMEOUT",
                "REPRO_CONTAINER_FAILED",
            ):
                _finish_tool("failed", {}, (exc.code, exc.message))
        raise
    finally:
        if container is not None:
            status = container_runtime.destroy_container(container)
            with session_factory() as session:
                update_cleanup(session, execution_uuid, status)
        if ws_dir is not None:
            workspace.destroy_workspace(ws_dir)


def _finish_execution(session_factory: Any, execution_uuid: uuid.UUID, **kwargs: Any) -> None:
    stdout = kwargs.pop("stdout", None)
    stderr = kwargs.pop("stderr", None)
    truncated = kwargs.pop("truncated", False)
    error = kwargs.pop("error", None)
    try:
        with session_factory() as session:
            finish_execution(
                session, execution_uuid,
                stdout=stdout.decode("utf-8", errors="replace") if stdout else None,
                stderr=stderr.decode("utf-8", errors="replace") if stderr else None,
                output_truncated=bool(truncated),
                error_code=error[0] if error else None,
                error_message=error[1] if error else None,
                **kwargs,
            )
    except SandboxError as exc:
        logger.warning("execution finish failed execution_id=%s code=%s", execution_uuid, exc.code)


def _project_of(session_factory: Any, investigation_id: uuid.UUID) -> uuid.UUID:
    from sqlalchemy import select

    from app.models import Investigation

    with session_factory() as session:
        project_id = session.execute(
            select(Investigation.project_id).where(Investigation.id == investigation_id)
        ).scalar_one()
    assert isinstance(project_id, uuid.UUID)
    return project_id


def _upload_evidence(
    session_factory: Any,
    *,
    project_id: uuid.UUID,
    investigation_id: uuid.UUID,
    tool_run_id: uuid.UUID | None,
    files: dict[str, bytes],
    skipped: int,
    store: Any,
) -> list[str]:
    """Persist contracted outputs as evidence; ignore unknown files loudly."""
    accepted = sorted(name for name in files if _KNOWN_FILE.fullmatch(name))
    ignored = sorted(name for name in files if not _KNOWN_FILE.fullmatch(name))
    if ignored:
        logger.warning("repro ignored unexpected files count=%d", len(ignored))
    evidence_ids: list[str] = []
    with session_factory() as session:
        for name in accepted:
            data = files[name]
            if name in _JSON_EVIDENCE:
                redacted, ok = evidence_service.redact_json_bytes(data)
                if not ok:
                    raise InvestigationFailure(
                        "EVIDENCE_REDACT_FAILED",
                        f"Evidence could not be redacted: {name}.", False,
                    )
                data = redacted
                redaction_status = "redacted"
                kind = _JSON_EVIDENCE[name]
            elif name == RESULT_FILE:
                redacted, ok = evidence_service.redact_json_bytes(data)
                data = redacted if ok else data
                redaction_status = "redacted" if ok else "failed"
                kind = "log"
            elif name == "trace.zip":
                redaction_status = "not_required"
                kind = "trace"
            else:
                redaction_status = "not_required"
                kind = "screenshot"
            try:
                record = evidence_service.create_evidence(
                    session, project_id=project_id,
                    investigation_id=investigation_id, tool_run_id=tool_run_id,
                    kind=kind, data=data, filename_hint=name,
                    redaction_status=redaction_status,
                    metadata={"source": "browser_repro", "filename": name},
                    store=store,
                )
            except ApiError as exc:
                raise _map_api_error(exc) from exc
            evidence_ids.append(record["id"])
        if skipped:
            logger.info("repro skipped=%d unreadable entries", skipped)
    return evidence_ids
