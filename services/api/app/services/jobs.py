"""Durable job queue over PostgreSQL (M4, C5/D10).

No broker: workers claim rows with SELECT ... FOR UPDATE SKIP LOCKED,
own them through leases + heartbeats, and record job_stages rows that
survive restarts. Database time (`_db_now`) drives every lease decision
so API and worker hosts never disagree.

Internal worker transitions (claim/heartbeat/complete/fail) run through
this same module in the worker process — there are no worker HTTP
credentials to protect (D45).
"""

import base64
import datetime as dt
import logging
import re
import uuid

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.envelope import ApiError, access_denied, not_found
from app.models import Job, JobStage, Project, User, WorkspaceMember

logger = logging.getLogger("meridian.jobs")

JOB_TYPES = ("lifecycle_test", "manifest_recheck", "sandbox_smoke")

TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})

# Explicit transition table (Phase 3). Terminal states have no exits:
# a completed job can never execute again.
JOB_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "cancelled"}),
    "running": frozenset({"completed", "retry_wait", "failed", "cancelled"}),
    "retry_wait": frozenset({"queued", "cancelled"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}

STAGE_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"running", "skipped", "cancelled"}),
    "running": frozenset({"completed", "failed", "blocked", "skipped", "cancelled"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "blocked": frozenset(),
    "skipped": frozenset(),
    "cancelled": frozenset(),
}

STAGE_KEY_PATTERN = re.compile(r"^[a-z0-9_]{1,64}$")

# Future investigation stages (Phase 7): recorded by workers when they
# exist. Unknown-but-wellformed keys are still persisted (forward
# compatible); nothing here fabricates their results.
KNOWN_STAGE_KEYS = (
    "project_inspection",
    "plan_investigation",
    "reproduction",
    "evidence_analysis",
    "hypothesis_review",
    "regression_test_creation",
    "baseline_test_execution",
    "patch_proposal",
    "awaiting_user_approval",
    "patch_application",
    "post_patch_verification",
    "report_generation",
)

CONTRIBUTOR_ROLES = frozenset({"owner", "admin", "developer"})


def _iso(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def _db_now(session: Session) -> dt.datetime:
    """Authoritative database timestamp for lease decisions."""
    now = session.execute(select(func.now())).scalar_one()
    assert isinstance(now, dt.datetime)
    return now


def backoff_for_attempt(attempts: int, base_seconds: int, cap_seconds: int) -> int:
    """Exponential backoff after ``attempts`` executions (pure, tested)."""
    delay: int = base_seconds * (2 ** max(attempts - 1, 0))
    return min(delay, cap_seconds)


def _check_transition(current: str, target: str) -> None:
    if target not in JOB_TRANSITIONS.get(current, frozenset()):
        raise ApiError(
            409, "INVALID_TRANSITION", f"Cannot move a job from {current} to {target}."
        )


def serialize_job(job: Job, include_payload: bool = True) -> dict:
    data: dict = {
        "id": str(job.id),
        "workspace_id": str(job.workspace_id),
        "project_id": str(job.project_id) if job.project_id else None,
        "investigation_id": str(job.investigation_id) if job.investigation_id else None,
        "job_type": job.job_type,
        "status": job.status,
        "priority": job.priority,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "worker_id": job.worker_id,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "available_at": _iso(job.available_at),
        "started_at": _iso(job.started_at),
        "completed_at": _iso(job.completed_at),
        "created_at": _iso(job.created_at),
        "updated_at": _iso(job.updated_at),
    }
    if include_payload:
        data["payload"] = job.payload or {}
        data["result"] = job.result
    return data


def encode_cursor(created_at: dt.datetime, job_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{job_id}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str) -> tuple[dt.datetime, uuid.UUID] | None:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        created_raw, id_raw = raw.split("|", 1)
        return dt.datetime.fromisoformat(created_raw), uuid.UUID(id_raw)
    except (ValueError, TypeError):
        return None


def _require_member(session: Session, user: User, workspace_id: uuid.UUID) -> str:
    row = (
        session.execute(
            select(WorkspaceMember.role).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user.id,
            )
        )
    ).one_or_none()
    if row is None:
        raise not_found("workspace")
    role = row[0]
    assert isinstance(role, str)
    return role


def _get_job(session: Session, user: User, job_id: uuid.UUID) -> tuple[Job, str]:
    row = (
        session.execute(
            select(Job, WorkspaceMember.role)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Job.workspace_id)
            .where(Job.id == job_id, WorkspaceMember.user_id == user.id)
        )
    ).one_or_none()
    if row is None:
        raise not_found("job")
    return row[0], row[1]


def submit_job(
    session: Session,
    user: User,
    workspace_id: uuid.UUID,
    job_type: str,
    payload: dict,
    idempotency_key: str | None = None,
    priority: int = 0,
    max_attempts: int | None = None,
) -> tuple[dict, bool]:
    """Queue a job. Returns (job, created); idempotent replays return the
    original with created=False instead of a duplicate."""
    role = _require_member(session, user, workspace_id)
    if role not in CONTRIBUTOR_ROLES:
        raise access_denied()
    if job_type not in JOB_TYPES:
        raise ApiError(422, "VALIDATION_ERROR", "The job type is not supported.")
    if not isinstance(payload, dict):
        raise ApiError(422, "VALIDATION_ERROR", "The job payload must be an object.")
    settings = get_settings()
    attempts_cap = max_attempts if max_attempts is not None else settings.job_max_attempts
    if attempts_cap < 1 or attempts_cap > 25:
        raise ApiError(422, "VALIDATION_ERROR", "max_attempts is out of range.")
    if priority < 0 or priority > 1000:
        raise ApiError(422, "VALIDATION_ERROR", "priority is out of range.")
    if idempotency_key is not None and not re.fullmatch(r"[A-Za-z0-9_.\-]{1,128}", idempotency_key):
        raise ApiError(422, "VALIDATION_ERROR", "The idempotency key is invalid.")
    project_id: uuid.UUID | None = None
    if job_type in ("manifest_recheck", "sandbox_smoke"):
        raw_snapshot = payload.get("snapshot_id")
        try:
            snapshot_id = uuid.UUID(str(raw_snapshot))
        except (ValueError, TypeError, AttributeError):
            raise ApiError(
                422, "VALIDATION_ERROR", f"{job_type} needs a snapshot_id."
            ) from None
        from app.models import RepositorySnapshot

        visible = (
            session.execute(
                select(RepositorySnapshot.id)
                .join(Project, Project.id == RepositorySnapshot.project_id)
                .join(
                    WorkspaceMember,
                    WorkspaceMember.workspace_id == Project.workspace_id,
                )
                .where(
                    RepositorySnapshot.id == snapshot_id,
                    WorkspaceMember.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        if visible is None:
            raise not_found("snapshot")
        project_row = (
            session.execute(
                select(RepositorySnapshot.project_id).where(
                    RepositorySnapshot.id == snapshot_id
                )
            )
        ).scalar_one()
        project_id = project_row

    if idempotency_key:
        existing = (
            session.execute(
                select(Job).where(
                    Job.workspace_id == workspace_id,
                    Job.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            logger.info("job deduplicated workspace_id=%s key=%s", workspace_id, idempotency_key)
            return serialize_job(existing), False

    now = _db_now(session)
    job = Job(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        project_id=project_id,
        job_type=job_type,
        status="queued",
        priority=priority,
        payload=dict(payload),
        attempts=0,
        max_attempts=attempts_cap,
        idempotency_key=idempotency_key,
        available_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if "uq_jobs_workspace_idempotency" not in str(getattr(exc, "orig", exc)):
            raise
        existing = (
            session.execute(
                select(Job).where(
                    Job.workspace_id == workspace_id,
                    Job.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            raise
        return serialize_job(existing), False
    session.refresh(job)
    logger.info(
        "job created job_id=%s workspace_id=%s type=%s", job.id, workspace_id, job_type
    )
    return serialize_job(job), True


def get_job(session: Session, user: User, job_id: uuid.UUID) -> dict:
    job, _role = _get_job(session, user, job_id)
    return serialize_job(job)


def list_jobs(
    session: Session,
    user: User,
    workspace_id: uuid.UUID,
    limit: int,
    cursor: str | None,
    status: str | None,
    job_type: str | None,
) -> tuple[list[dict], str | None]:
    """Workspace job history, newest first, payloads withheld (D45)."""
    _require_member(session, user, workspace_id)
    if status is not None and status not in JOB_TRANSITIONS:
        raise ApiError(422, "VALIDATION_ERROR", "The status filter is not supported.")
    if job_type is not None and job_type not in JOB_TYPES:
        raise ApiError(422, "VALIDATION_ERROR", "The job type filter is not supported.")
    stmt = select(Job).where(Job.workspace_id == workspace_id)
    if status is not None:
        stmt = stmt.where(Job.status == status)
    if job_type is not None:
        stmt = stmt.where(Job.job_type == job_type)
    stmt = stmt.order_by(desc(Job.created_at), desc(Job.id))
    if cursor:
        position = decode_cursor(cursor)
        if position is None:
            raise ApiError(422, "VALIDATION_ERROR", "The cursor is invalid.")
        created_at, cursor_id = position
        stmt = stmt.where(
            or_(
                Job.created_at < created_at,
                and_(Job.created_at == created_at, Job.id < cursor_id),
            )
        )
    rows = list(session.execute(stmt.limit(limit + 1)).scalars())
    items = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last = items[-1]
        next_cursor = encode_cursor(last.created_at, last.id)
    return ([serialize_job(job, include_payload=False) for job in items], next_cursor)


def cancel_job(session: Session, user: User, job_id: uuid.UUID) -> dict:
    """Cancel a live job. Terminal jobs answer 409; a cancelled job is
    never requeued, and a running worker's completion is refused."""
    job, role = _get_job(session, user, job_id)
    if role not in CONTRIBUTOR_ROLES:
        raise access_denied()
    _check_transition(job.status, "cancelled")
    job.status = "cancelled"
    job.completed_at = _db_now(session)
    job.updated_at = job.completed_at
    session.commit()
    session.refresh(job)
    logger.info("job cancelled job_id=%s by user", job.id)
    return serialize_job(job)


def claim_job(
    session: Session,
    worker_id: str,
    job_types: tuple[str, ...],
    lease_seconds: int,
) -> dict | None:
    """Atomically claim one eligible job (Phase 4).

    Eligible: queued, due retry_wait, or running with an expired lease
    (crash recovery). Exactly one worker wins via FOR UPDATE SKIP LOCKED.
    Attempts increment on every claim; exhausted jobs fail instead of
    running again. Returns None when no work is available.
    """
    now = _db_now(session)
    stmt = (
        select(Job)
        .where(
            Job.job_type.in_(job_types),
            or_(
                Job.status == "queued",
                and_(Job.status == "retry_wait", Job.available_at <= now),
                and_(Job.status == "running", Job.lease_expires_at < now),
            ),
        )
        .order_by(desc(Job.priority), Job.available_at.asc(), Job.created_at.asc(), Job.id.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = session.execute(stmt).scalar_one_or_none()
    if job is None:
        return None
    recovered = job.status == "running"
    job.attempts += 1
    if job.attempts > job.max_attempts:
        job.status = "failed"
        job.error_code = "MAX_ATTEMPTS_EXCEEDED"
        job.error_message = "The job exhausted its attempts without succeeding."
        job.completed_at = now
        job.updated_at = now
        session.commit()
        logger.info(
            "job attempts exhausted job_id=%s worker_id=%s", job.id, worker_id
        )
        return None
    previous_worker = job.worker_id
    job.status = "running"
    job.worker_id = worker_id
    job.lease_expires_at = now + dt.timedelta(seconds=lease_seconds)
    job.heartbeat_at = now
    if job.started_at is None:
        job.started_at = now
    job.error_code = None
    job.error_message = None
    job.updated_at = now
    session.commit()
    session.refresh(job)
    logger.info(
        "job claimed job_id=%s worker_id=%s attempt=%d recovered=%s previous_worker=%s",
        job.id,
        worker_id,
        job.attempts,
        recovered,
        previous_worker,
    )
    return serialize_job(job)


def heartbeat_job(
    session: Session, job_id: uuid.UUID, worker_id: str, lease_seconds: int
) -> dict:
    """Renew the lease. Refuses foreign or expired ownership (Phase 5)."""
    now = _db_now(session)
    updated = (
        session.execute(
            select(Job)
            .where(
                Job.id == job_id,
                Job.worker_id == worker_id,
                Job.status == "running",
                Job.lease_expires_at > now,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if updated is None:
        raise ApiError(
            409, "LEASE_LOST", "The job lease expired or the job is not owned by this worker."
        )
    updated.heartbeat_at = now
    updated.lease_expires_at = now + dt.timedelta(seconds=lease_seconds)
    updated.updated_at = now
    session.commit()
    session.refresh(updated)
    logger.info("job heartbeat job_id=%s worker_id=%s", job_id, worker_id)
    return serialize_job(updated)


def is_running_and_owned(session: Session, job_id: uuid.UUID, worker_id: str) -> bool:
    """Read-only ownership check for execution abort polling (D47: DB time).

    No locks, no writes, no commit: safe to call from a polling slice.
    """
    now = _db_now(session)
    return (
        session.execute(
            select(Job.id).where(
                Job.id == job_id,
                Job.worker_id == worker_id,
                Job.status == "running",
                Job.lease_expires_at > now,
            )
        ).scalar_one_or_none()
    ) is not None


def complete_job(session: Session, job_id: uuid.UUID, worker_id: str, result: dict) -> dict:
    """Finish a job. Refuses completion after lease loss or cancellation,
    so a cancelled job can never be completed by a stale worker."""
    if not isinstance(result, dict):
        raise ApiError(422, "VALIDATION_ERROR", "The job result must be an object.")
    now = _db_now(session)
    job = (
        session.execute(
            select(Job)
            .where(
                Job.id == job_id,
                Job.worker_id == worker_id,
                Job.status == "running",
                Job.lease_expires_at > now,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if job is None:
        raise ApiError(
            409,
            "LEASE_LOST",
            "The job cannot be completed: lease lost, cancelled, or finished.",
        )
    job.status = "completed"
    job.result = dict(result)
    job.error_code = None
    job.error_message = None
    job.completed_at = now
    job.updated_at = now
    session.commit()
    session.refresh(job)
    logger.info("job completed job_id=%s worker_id=%s", job_id, worker_id)
    return serialize_job(job)


def fail_job(
    session: Session,
    job_id: uuid.UUID,
    worker_id: str,
    error_code: str,
    error_message: str,
    retryable: bool,
) -> dict:
    """Record failure: retry with exponential backoff or finish FAILED.
    Cancelled jobs are never requeued; messages are truncated so secrets
    and stack traces cannot accumulate in the row."""
    settings = get_settings()
    now = _db_now(session)
    job = (
        session.execute(
            select(Job)
            .where(
                Job.id == job_id,
                Job.worker_id == worker_id,
                Job.status == "running",
                Job.lease_expires_at > now,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if job is None:
        raise ApiError(
            409,
            "LEASE_LOST",
            "The job cannot be failed: lease lost, cancelled, or finished.",
        )
    code = (error_code or "JOB_FAILED")[:64]
    message = (error_message or "The job failed.")[:2000]
    if retryable and job.attempts < job.max_attempts:
        delay = backoff_for_attempt(
            job.attempts, settings.job_retry_base_seconds, settings.job_retry_max_seconds
        )
        job.status = "retry_wait"
        job.error_code = code
        job.error_message = message
        job.available_at = now + dt.timedelta(seconds=delay)
        job.worker_id = None
        job.lease_expires_at = None
        job.updated_at = now
        session.commit()
        session.refresh(job)
        logger.info(
            "job retrying job_id=%s worker_id=%s attempt=%d delay_s=%d",
            job_id,
            worker_id,
            job.attempts,
            delay,
        )
    else:
        job.status = "failed"
        job.error_code = code
        job.error_message = message
        job.completed_at = now
        job.updated_at = now
        session.commit()
        session.refresh(job)
        logger.info("job failed job_id=%s worker_id=%s code=%s", job_id, worker_id, code)
    return serialize_job(job)


def record_stage(
    session: Session,
    job_id: uuid.UUID,
    worker_id: str,
    stage_key: str,
    status: str,
    result_summary: dict | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> dict:
    """Persist one stage transition for the owning, running worker.

    Latest attempt rows update in place; re-running a terminal stage
    opens a new attempt. Terminal stages never change.
    """
    if not STAGE_KEY_PATTERN.match(stage_key):
        raise ApiError(422, "VALIDATION_ERROR", "The stage key is invalid.")
    if status not in STAGE_TRANSITIONS:
        raise ApiError(422, "VALIDATION_ERROR", "The stage status is not supported.")
    if result_summary is not None and not isinstance(result_summary, dict):
        raise ApiError(422, "VALIDATION_ERROR", "The stage result must be an object.")
    job = (
        session.execute(
            select(Job).where(
                Job.id == job_id, Job.worker_id == worker_id, Job.status == "running"
            )
        )
    ).scalar_one_or_none()
    if job is None:
        raise ApiError(
            409, "LEASE_LOST", "Stages can only be recorded by the owning worker."
        )
    now = _db_now(session)
    latest = (
        session.execute(
            select(JobStage)
            .where(JobStage.job_id == job_id, JobStage.stage_key == stage_key)
            .order_by(desc(JobStage.attempt))
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest is None:
        if status != "pending" and status != "running":
            raise ApiError(
                409, "INVALID_TRANSITION", "A new stage must start as pending or running."
            )
        row = JobStage(
            id=uuid.uuid4(),
            job_id=job_id,
            stage_key=stage_key,
            status=status,
            attempt=1,
            result_summary=dict(result_summary or {}),
            started_at=now if status == "running" else None,
            finished_at=None,
            created_at=now,
        )
        session.add(row)
    elif latest.status in ("completed", "failed", "blocked", "skipped", "cancelled"):
        if status != "running":
            raise ApiError(409, "INVALID_TRANSITION", "A finished stage cannot change.")
        row = JobStage(
            id=uuid.uuid4(),
            job_id=job_id,
            stage_key=stage_key,
            status="running",
            attempt=latest.attempt + 1,
            result_summary=dict(result_summary or {}),
            started_at=now,
            finished_at=None,
            created_at=now,
        )
        session.add(row)
    else:
        if status not in STAGE_TRANSITIONS[latest.status]:
            raise ApiError(
                409,
                "INVALID_TRANSITION",
                f"Cannot move stage {stage_key} from {latest.status} to {status}.",
            )
        latest.status = status
        if result_summary is not None:
            latest.result_summary = dict(result_summary)
        latest.error_code = (error_code[:64] if error_code else None)
        latest.error_message = (error_message[:2000] if error_message else None)
        if status == "running" and latest.started_at is None:
            latest.started_at = now
        if status in ("completed", "failed", "blocked", "skipped", "cancelled"):
            latest.finished_at = now
        row = latest
    session.commit()
    session.refresh(row)
    return {
        "id": str(row.id),
        "job_id": str(row.job_id),
        "stage_key": row.stage_key,
        "status": row.status,
        "attempt": row.attempt,
        "result_summary": row.result_summary or {},
        "error_code": row.error_code,
        "error_message": row.error_message,
        "started_at": _iso(row.started_at),
        "finished_at": _iso(row.finished_at),
        "created_at": _iso(row.created_at),
    }


def get_stages(session: Session, user: User, job_id: uuid.UUID) -> list[dict]:
    """Stage history for a visible job (Phase 7/9 read path)."""
    job, _role = _get_job(session, user, job_id)
    rows = list(
        session.execute(
            select(JobStage)
            .where(JobStage.job_id == job.id)
            .order_by(JobStage.stage_key.asc(), JobStage.attempt.asc())
        ).scalars()
    )
    return [
        {
            "id": str(row.id),
            "job_id": str(row.job_id),
            "stage_key": row.stage_key,
            "status": row.status,
            "attempt": row.attempt,
            "result_summary": row.result_summary or {},
            "error_code": row.error_code,
            "error_message": row.error_message,
            "started_at": _iso(row.started_at),
            "finished_at": _iso(row.finished_at),
            "created_at": _iso(row.created_at),
        }
        for row in rows
    ]
