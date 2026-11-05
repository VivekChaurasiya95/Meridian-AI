"""Sandbox execution reads (M5): persisted container outcomes, member-visible.

Execution rows are written by the trusted worker (``sandbox.lifecycle``)
and served here to workspace members. Unknown or foreign executions
answer 404 so existence is never leaked. Stdout/stderr are already
secret-redacted at write time; responses carry bounded tail excerpts plus
character counts, never unbounded output.
"""

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.envelope import not_found
from app.models import Job, SandboxExecution, User, WorkspaceMember

EXECUTION_EXCERPT_CHARS = 4000


def _iso(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def _excerpt(text: str | None) -> tuple[str | None, bool, int]:
    """Tail excerpt of stored output: (excerpt, cut, total_chars)."""
    if text is None:
        return None, False, 0
    if len(text) <= EXECUTION_EXCERPT_CHARS:
        return text, False, len(text)
    return (
        "[... truncated ...]\n" + text[-EXECUTION_EXCERPT_CHARS:],
        True,
        len(text),
    )


def serialize_execution(row: SandboxExecution) -> dict:
    stdout_excerpt, stdout_cut, stdout_chars = _excerpt(row.stdout)
    stderr_excerpt, stderr_cut, stderr_chars = _excerpt(row.stderr)
    return {
        "id": str(row.id),
        "job_id": str(row.job_id),
        "worker_id": row.worker_id,
        "snapshot_id": str(row.snapshot_id) if row.snapshot_id else None,
        "profile": row.profile,
        "run_key": row.run_key,
        "status": row.status,
        "attempt": row.attempt,
        "exit_code": row.exit_code,
        "timed_out": row.timed_out,
        "duration_ms": row.duration_ms,
        "stdout_excerpt": stdout_excerpt,
        "stdout_chars": stdout_chars,
        "stderr_excerpt": stderr_excerpt,
        "stderr_chars": stderr_chars,
        "output_truncated": bool(row.output_truncated or stdout_cut or stderr_cut),
        "error_code": row.error_code,
        "error_message": row.error_message,
        "cleanup_status": row.cleanup_status,
        "created_at": _iso(row.created_at),
        "completed_at": _iso(row.completed_at),
    }


def _require_job(session: Session, user: User, job_id: uuid.UUID) -> Job:
    row = (
        session.execute(
            select(Job, WorkspaceMember.role)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Job.workspace_id)
            .where(Job.id == job_id, WorkspaceMember.user_id == user.id)
        )
    ).one_or_none()
    if row is None:
        raise not_found("job")
    job = row[0]
    assert isinstance(job, Job)
    return job


def list_job_executions(session: Session, user: User, job_id: uuid.UUID) -> list[dict]:
    """Execution attempts for one visible job, oldest attempt first."""
    job = _require_job(session, user, job_id)
    rows = list(
        session.execute(
            select(SandboxExecution)
            .where(SandboxExecution.job_id == job.id)
            .order_by(
                SandboxExecution.attempt.asc(),
                SandboxExecution.created_at.asc(),
                SandboxExecution.id.asc(),
            )
        ).scalars()
    )
    return [serialize_execution(row) for row in rows]


def get_execution(session: Session, user: User, execution_id: uuid.UUID) -> dict:
    """One execution by id; cross-workspace ids answer 404."""
    row = (
        session.execute(
            select(SandboxExecution, WorkspaceMember.role)
            .join(Job, Job.id == SandboxExecution.job_id)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Job.workspace_id)
            .where(
                SandboxExecution.id == execution_id,
                WorkspaceMember.user_id == user.id,
            )
        )
    ).one_or_none()
    if row is None:
        raise not_found("execution")
    return serialize_execution(row[0])
