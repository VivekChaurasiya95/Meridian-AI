"""Sandbox orchestrator (M5.2.6/8): eligible job in, persisted result out.

The worker calls ``execute_job`` after claiming a ``sandbox_smoke`` job.
Every step is observable (job stages), every outcome is persisted (the
execution row), and cleanup is guaranteed by ``finally`` blocks — a
container or workspace is never left behind on any path, including
cancellation and lease loss.

Trust assumptions (documented, not verified here): the caller claimed
the job and owns its lease; ``is_cancelled`` reports cancellation and
lease loss promptly. Completion refusal in ``complete_job`` is the final
backstop — this module never completes jobs itself.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Callable

from app.envelope import ApiError
from app.services import jobs as job_service
from app.services.redact import redact_text
from app.services import projects as project_service
from app.services import storage as storage_service
from sandbox import container_runtime, workspace
from sandbox.container_spec import build_spec
from sandbox.exceptions import SandboxError
from sandbox.execution_policy import get_policy
from sandbox.lifecycle import (
    create_execution,
    finish_execution,
    new_execution_id,
    update_cleanup,
)

logger = logging.getLogger("meridian.sandbox.orchestrator")

# Bounded excerpts travel in the job result; full bounded output lives on
# the execution row. Both caps keep rows small and secrets out.
RESULT_EXCERPT_BYTES = 4096


def _excerpt(data: bytes) -> tuple[str, bool]:
    if len(data) <= RESULT_EXCERPT_BYTES:
        return (data.decode("utf-8", errors="replace"), False)
    tail = data[-RESULT_EXCERPT_BYTES:]
    return ("[... truncated ...]\n" + tail.decode("utf-8", errors="replace"), True)


def _map_api_error(exc: ApiError) -> SandboxError:
    retryable = exc.status_code in (429, 503)
    return SandboxError(exc.code, exc.message, retryable)


def execute_job(
    session_factory: Any,
    job: dict,
    worker_id: str,
    *,
    client: Any = None,
    store: Any = None,
    is_cancelled: Callable[[], bool] | None = None,
    timeout_seconds: int | None = None,
) -> dict:
    """Run one claimed ``sandbox_smoke`` job to a persisted result.

    Returns the job-result summary on success; raises ``SandboxError``
    (which the worker maps to job failure) on every other path. The
    execution row is finished and the environment destroyed in all cases.
    ``timeout_seconds`` overrides the profile default (tests only).
    """
    try:
        job_id = uuid.UUID(str(job["id"]))
        workspace_id = uuid.UUID(str(job["workspace_id"]))
        attempt = int(job.get("attempts", 1))
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise SandboxError("INVALID_JOB", "The job record is malformed.") from exc
    if attempt < 1:
        # Attempts start at 1 on the first claim: anything lower means the
        # job was never claimed, and unclaimed jobs must never execute.
        raise SandboxError("INVALID_JOB", "Only claimed jobs may execute.")
    if job.get("job_type") != "sandbox_smoke":
        raise SandboxError(
            "JOB_TYPE_NOT_IMPLEMENTED", "This orchestrator runs sandbox jobs only."
        )
    payload = job.get("payload")
    if not isinstance(payload, dict):
        raise SandboxError("INVALID_PAYLOAD", "The job payload must be an object.")
    profile = payload.get("profile", "sandbox_smoke")
    if not isinstance(profile, str):
        raise SandboxError("INVALID_PAYLOAD", "The execution profile must be a string.")
    try:
        snapshot_id = uuid.UUID(str(payload.get("snapshot_id")))
    except (ValueError, TypeError, AttributeError):
        raise SandboxError(
            "INVALID_PAYLOAD", "sandbox_smoke needs a snapshot_id."
        ) from None

    policy = get_policy(profile)
    limit_seconds = timeout_seconds if timeout_seconds is not None else policy.timeout_seconds

    # Validate the snapshot before recording anything: the execution row
    # carries a snapshot FK, and no row should exist for content that was
    # never reachable. Byte-level verification still happens at
    # materialization; a snapshot deleted in between fails safe there.
    try:
        with session_factory() as session:
            candidate = project_service.get_workspace_snapshot(
                session, workspace_id, snapshot_id
            )
            if candidate.storage_status != "ready" or not candidate.storage_key:
                raise SandboxError(
                    "SNAPSHOT_NOT_READY", "The snapshot content is not stored."
                )
    except ApiError as exc:
        raise _map_api_error(exc) from exc

    execution_uuid = uuid.UUID(hex=new_execution_id())
    execution_id = execution_uuid.hex
    with session_factory() as session:
        create_execution(
            session,
            execution_id=execution_uuid,
            job_id=job_id,
            worker_id=worker_id,
            snapshot_id=snapshot_id,
            profile=policy.profile,
            attempt=attempt,
        )

    ws_dir: str | None = None
    container: Any = None
    own_client: Any = client
    image_tag: str | None = None
    image_id: str | None = None
    image_released = False
    open_stage: str | None = None
    finished = False

    def _safe_abort() -> bool:
        if is_cancelled is None:
            return False
        try:
            return bool(is_cancelled())
        except Exception as exc:
            logger.warning("cancel watch failed execution_id=%s error=%s", execution_id, exc)
            return False

    try:
        if own_client is None:
            own_client = container_runtime.get_client()
        open_stage = "sandbox_prepare"
        _stage(session_factory, job_id, worker_id, open_stage, "running")
        ws_dir = workspace.create_workspace()
        try:
            with session_factory() as session:
                material = storage_service.materialize_for_workspace(
                    session, workspace_id, snapshot_id, ws_dir, store=store
                )
        except ApiError as exc:
            raise _map_api_error(exc) from exc
        context_tar, context_digest = workspace.pack_build_context(ws_dir)
        image_tag = f"meridian-sandbox-src-{context_digest[:16]}"
        _stage(
            session_factory, job_id, worker_id, open_stage, "completed",
            result_summary={"files": material["files"], "bytes": material["total_bytes"]},
        )

        open_stage = "sandbox_build"
        _stage(session_factory, job_id, worker_id, open_stage, "running")
        image_id = container_runtime.build_source_image(own_client, context_tar, image_tag)
        _stage(session_factory, job_id, worker_id, open_stage, "completed",
               result_summary={"image_id": image_id, "image_tag": image_tag})

        open_stage = "sandbox_execute"
        _stage(session_factory, job_id, worker_id, open_stage, "running")
        spec = build_spec(policy, execution_id, image=image_tag)
        container = container_runtime.create_container(own_client, spec)
        run = container_runtime.run_to_completion(
            container, limit_seconds, should_abort=_safe_abort
        )
        logs = container_runtime.read_logs(container, policy.max_output_bytes)
        image_status = container_runtime.remove_image(own_client, image_tag)
        image_released = True
        if run["timed_out"]:
            _finish(session_factory, execution_uuid, status="timed_out",
                    exit_code=run["exit_code"], timed_out=True,
                    duration_ms=run["duration_ms"], error_code="COMMAND_TIMEOUT",
                    error_message="The approved command exceeded its time limit.")
            finished = True
            _stage(session_factory, job_id, worker_id, open_stage, "failed",
                   error_code="COMMAND_TIMEOUT",
                   error_message="The approved command exceeded its time limit.")
            raise SandboxError(
                "COMMAND_TIMEOUT",
                "The approved command exceeded its time limit.", True,
            )
        if run["exit_code"] != 0:
            _finish(session_factory, execution_uuid, status="failed",
                    exit_code=run["exit_code"], duration_ms=run["duration_ms"],
                    error_code="COMMAND_FAILED",
                    error_message=f"Exit code {run['exit_code']}.")
            finished = True
            _stage(session_factory, job_id, worker_id, open_stage, "failed",
                   error_code="COMMAND_FAILED",
                   error_message=f"Exit code {run['exit_code']}.")
            raise SandboxError(
                "COMMAND_FAILED", f"Exit code {run['exit_code']}.", True,
            )
        out_text, out_cut = _excerpt(logs["stdout"])
        err_text, err_cut = _excerpt(logs["stderr"])
        # Job results are API-visible: redact before they leave the worker
        # (row persistence redacts again in finish_execution; idempotent).
        out_text = redact_text(out_text) or ""
        err_text = redact_text(err_text) or ""
        truncated = out_cut or err_cut or logs["truncated"]
        _finish(session_factory, execution_uuid, status="completed",
                exit_code=0, duration_ms=run["duration_ms"],
                stdout=logs["stdout"].decode("utf-8", errors="replace"),
                stderr=logs["stderr"].decode("utf-8", errors="replace"),
                output_truncated=truncated)
        finished = True
        _stage(session_factory, job_id, worker_id, open_stage, "completed",
               result_summary={"exit_code": 0, "duration_ms": run["duration_ms"]})
        return {
            "execution_id": execution_id,
            "profile": policy.profile,
            "snapshot_id": str(snapshot_id),
            "exit_code": 0,
            "timed_out": False,
            "duration_ms": run["duration_ms"],
            "files": material["files"],
            "tree_digest": material["tree_digest"],
            "stdout_excerpt": out_text,
            "stderr_excerpt": err_text,
            "output_truncated": out_cut or err_cut,
            "image_id": image_id,
            "image_tag": image_tag,
            "image_removed": image_status == "removed",
        }
    except SandboxError as exc:
        if not finished:
            status = "cancelled" if exc.code == "EXECUTION_CANCELLED" else "failed"
            _finish(session_factory, execution_uuid, status=status,
                    error_code=exc.code, error_message=exc.message)
            _stage(session_factory, job_id, worker_id, open_stage or "sandbox_prepare",
                   "cancelled" if status == "cancelled" else "failed",
                   error_code=exc.code, error_message=exc.message)
        raise
    except Exception as exc:
        if not finished:
            _finish(session_factory, execution_uuid, status="failed",
                    error_code="ORCHESTRATOR_ERROR",
                    error_message=f"{type(exc).__name__}: {exc}"[:500])
        raise SandboxError(
            "ORCHESTRATOR_ERROR", f"{type(exc).__name__}: {exc}"[:500], True,
        ) from exc
    finally:
        cleanup = "cleaned"
        if container is not None:
            cleanup = container_runtime.destroy_container(container)
        if image_tag is not None and not image_released:
            image_status = container_runtime.remove_image(own_client, image_tag)
            if image_status != "removed":
                logger.warning("image cleanup failed tag=%s", image_tag)
        if ws_dir is not None:
            workspace.destroy_workspace(ws_dir)
        try:
            with session_factory() as session:
                update_cleanup(session, execution_uuid, cleanup)
        except Exception as exc:
            logger.warning("cleanup record failed execution_id=%s error=%s",
                           execution_id, exc)


def _stage(session_factory: Any, job_id: uuid.UUID, worker_id: str,
           key: str, status: str, **kwargs: Any) -> None:
    """Best-effort stage recording: never breaks an execution."""
    try:
        with session_factory() as session:
            job_service.record_stage(session, job_id, worker_id, key, status, **kwargs)
    except ApiError as exc:
        logger.warning("stage record refused job_id=%s code=%s", job_id, exc.code)
    except Exception as exc:
        logger.warning("stage record failed job_id=%s error=%s", job_id, exc)


def _finish(session_factory: Any, execution_uuid: uuid.UUID, **kwargs: Any) -> None:
    with session_factory() as session:
        finish_execution(session, execution_uuid, **kwargs)
