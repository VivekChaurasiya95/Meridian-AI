"""Execution lifecycle (M5.2.7): IDs, persistence, liveness, orphans.

Every function takes an explicit session (or client) and commits its own
writes, so the orchestrator uses short transactions throughout. Rows are
the source of truth for recovery: after a worker restart, containers
whose execution rows are not live are pruned by label.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Job, SandboxExecution
from sandbox.container_runtime import destroy_container
from sandbox.exceptions import SandboxError

logger = logging.getLogger("meridian.sandbox.lifecycle")


def new_execution_id() -> str:
    """Fresh 32-hex execution identity (also the row id and label value)."""
    return uuid.uuid4().hex


def _now(session: Session):  # type: ignore[no-untyped-def]
    return session.execute(select(func.now())).scalar_one()


def create_execution(
    session: Session,
    *,
    execution_id: uuid.UUID,
    job_id: uuid.UUID,
    worker_id: str,
    snapshot_id: uuid.UUID | None,
    profile: str,
    attempt: int,
) -> SandboxExecution:
    """Insert the running row. A duplicate (job, attempt) is a hard error."""
    row = SandboxExecution(
        id=execution_id,
        job_id=job_id,
        worker_id=worker_id,
        snapshot_id=snapshot_id,
        profile=profile,
        status="running",
        attempt=attempt,
        created_at=_now(session),
    )
    session.add(row)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        # Narrow the mapping: only the (job, attempt) unique violation
        # means a duplicate execution. Anything else (a broken FK, a bad
        # CHECK) is an internal data bug, and misreporting it as a
        # duplicate would send debugging down the wrong path entirely.
        if "uq_sandbox_exec_job_attempt" in str(getattr(exc, "orig", exc)):
            raise SandboxError(
                "DUPLICATE_EXECUTION",
                "An execution row already exists for this job attempt.",
            ) from exc
        raise SandboxError(
            "EXECUTION_RECORD_FAILED",
            "The execution row could not be recorded.",
        ) from exc
    logger.info(
        "execution created execution_id=%s job_id=%s attempt=%d",
        execution_id, job_id, attempt,
    )
    return row


def finish_execution(
    session: Session,
    execution_id: uuid.UUID,
    *,
    status: str,
    exit_code: int | None = None,
    timed_out: bool = False,
    duration_ms: int | None = None,
    stdout: str | None = None,
    stderr: str | None = None,
    output_truncated: bool = False,
    error_code: str | None = None,
    error_message: str | None = None,
) -> SandboxExecution:
    """Mark an execution terminal. Missing rows are a caller bug: loud."""
    row = session.get(SandboxExecution, execution_id)
    if row is None:
        raise SandboxError("EXECUTION_NOT_FOUND", "The execution row is missing.")
    row.status = status
    row.exit_code = exit_code
    row.timed_out = timed_out
    row.duration_ms = duration_ms
    row.stdout = stdout
    row.stderr = stderr
    row.output_truncated = output_truncated
    row.error_code = error_code
    row.error_message = error_message
    row.completed_at = _now(session)
    session.commit()
    return row


def update_cleanup(session: Session, execution_id: uuid.UUID, cleanup_status: str) -> None:
    """Record container cleanup. Never raises: cleanup must not fail jobs."""
    try:
        row = session.get(SandboxExecution, execution_id)
        if row is None:
            return
        row.cleanup_status = cleanup_status
        session.commit()
    except Exception as exc:
        logger.warning("cleanup record failed execution_id=%s error=%s", execution_id, exc)


def is_execution_live(session: Session, execution_id: uuid.UUID) -> bool:
    """True only while the recorded attempt still owns a running job.

    A reclaimed job (new owner, bumped attempt, expired lease, or any
    non-running status) makes the old row stale, so its container is a
    prune candidate even though the row says running.
    """
    row = session.get(SandboxExecution, execution_id)
    if row is None or row.status != "running":
        return False
    job = session.get(Job, row.job_id)
    if job is None:
        return False
    now = _now(session)
    return (
        job.status == "running"
        and job.worker_id == row.worker_id
        and job.attempts == row.attempt
        and job.lease_expires_at is not None
        and job.lease_expires_at > now
    )


def prune_stale_containers(
    client: Any, is_live: Callable[[str], bool]
) -> dict:
    """Destroy managed containers whose executions are not live.

    Only containers carrying our management label are touched; anything
    else is left alone. Per-container failures are counted, never raised.
    """
    try:
        containers = client.containers.list(all=True, filters={"label": "meridian.managed=true"})
    except Exception as exc:
        raise SandboxError(
            "PRUNE_LIST_FAILED", "Managed containers could not be listed.", True
        ) from exc
    pruned = 0
    kept = 0
    failed = 0
    for container in containers:
        try:
            labels = getattr(container, "labels", None) or {}
            execution_id = labels.get("meridian.execution_id", "")
            if execution_id and is_live(execution_id):
                kept += 1
                continue
            status = destroy_container(container)
            if status == "cleaned":
                pruned += 1
            else:
                failed += 1
        except Exception:
            failed += 1
    logger.info("orphan prune pruned=%d kept=%d failed=%d", pruned, kept, failed)
    return {"pruned": pruned, "kept": kept, "failed": failed}
