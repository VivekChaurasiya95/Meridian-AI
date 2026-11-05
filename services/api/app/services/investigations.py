"""Investigations (M6): debugging sessions over pinned snapshots.

Create flow is single-POST → 202 per C2: the API validates, persists the
investigation with its activity seed, and enqueues one durable
``investigation`` job — never waiting for reproduction. The worker owns
stage execution; the API owns transitions requested by users (cancel,
retry). Unknown or foreign resources answer 404; role failures 403.
"""

import base64
import datetime as dt
import hashlib
import json
import uuid

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.envelope import ApiError, access_denied, not_found
from app.models import (
    Investigation,
    InvestigationStage,
    Project,
    RepositorySnapshot,
    ToolRun,
    User,
    WorkspaceMember,
)
from app.schemas import InvestigationCreate, InvestigationRetry
from app.services import activity as activity_service
from app.services import audit as audit_service
from app.services import evidence as evidence_service
from app.services import jobs as job_service
from app.services import projects as project_service
from app.services.activity import db_now, investigation_access
from app.services.jobs import check_json_bounds
from app.services.repro_spec import validate_context

CONTRIBUTOR_ROLES = frozenset({"owner", "admin", "developer"})

TERMINAL_STATUSES = frozenset({"completed", "failed", "blocked", "inconclusive", "cancelled"})

INVESTIGATION_STATUSES = (
    "queued",
    "running",
    "awaiting_approval",
    "completed",
    "failed",
    "blocked",
    "inconclusive",
    "cancelled",
)
SEVERITIES = ("low", "medium", "high", "critical", "unspecified")

# Explicit lifecycle map. Terminal states exit only to queued, and only
# through the retry path (via_retry), never through worker transitions.
INVESTIGATION_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "cancelled", "failed"}),
    "running": frozenset(
        {"completed", "failed", "blocked", "inconclusive", "cancelled", "awaiting_approval"}
    ),
    "awaiting_approval": frozenset({"queued", "running", "completed", "failed", "cancelled"}),
    "completed": frozenset({"queued"}),
    "failed": frozenset({"queued"}),
    "blocked": frozenset({"queued"}),
    "inconclusive": frozenset({"queued"}),
    "cancelled": frozenset({"queued"}),
}

STAGE_STATUSES = (
    "pending",
    "running",
    "completed",
    "failed",
    "blocked",
    "skipped",
    "inconclusive",
    "cancelled",
)
STAGE_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"running", "skipped", "cancelled"}),
    "running": frozenset(
        {"completed", "failed", "blocked", "skipped", "inconclusive", "cancelled"}
    ),
    "completed": frozenset(),
    "failed": frozenset(),
    "blocked": frozenset(),
    "skipped": frozenset(),
    "inconclusive": frozenset(),
    "cancelled": frozenset(),
}

# M6 executes the first three stages; later milestones extend the flow.
STAGE_FLOW_M6 = ("project_inspection", "reproduction", "evidence_analysis")
STAGE_FLOW_M7 = (*STAGE_FLOW_M6, "hypothesis_review")
STAGE_FLOW_M8 = (
    *STAGE_FLOW_M7,
    "regression_test_creation",
    "baseline_test_execution",
    "patch_proposal",
    "awaiting_user_approval",
    "patch_application",
    "post_patch_verification",
)
# report_generation is handler-only (not in the flow): retryable on its own
# once it has an attempt, never part of the sequential run (M8 contract).
RETRYABLE_FROM = frozenset((*STAGE_FLOW_M8, "report_generation"))
RETRYABLE_STAGE_OUTCOMES = frozenset({"failed", "blocked", "inconclusive", "cancelled"})
RETRYABLE_INVESTIGATION = frozenset({"failed", "blocked", "inconclusive"})

SUMMARY_MAX_BYTES = 8192
RESULT_SUMMARY_MAX = 2000


def _iso(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def encode_cursor(created_at: dt.datetime, row_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{created_at.isoformat()}|{row_id}".encode()).decode()


def decode_cursor(cursor: str) -> tuple[dt.datetime, uuid.UUID] | None:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        created_raw, id_raw = raw.split("|", 1)
        return dt.datetime.fromisoformat(created_raw), uuid.UUID(id_raw)
    except (ValueError, TypeError):
        return None


def _check_transition(current: str, target: str, *, via_retry: bool = False) -> None:
    if target not in INVESTIGATION_TRANSITIONS.get(current, frozenset()):
        raise ApiError(
            409, "INVALID_TRANSITION", f"Cannot move an investigation from {current} to {target}."
        )
    if current in TERMINAL_STATUSES and not via_retry:
        raise ApiError(409, "INVALID_TRANSITION", "A terminal investigation cannot change.")


def serialize_investigation(inv: Investigation, role: str | None = None) -> dict:
    return {
        "id": str(inv.id),
        "project_id": str(inv.project_id),
        "title": inv.title,
        "status": inv.status,
        "current_stage": inv.current_stage,
        "severity": inv.severity,
        "result_summary": inv.result_summary,
        "repository_snapshot_id": str(inv.repository_snapshot_id)
        if inv.repository_snapshot_id
        else None,
        "cancel_requested": inv.cancel_requested,
        "role": role,
        "started_at": _iso(inv.started_at),
        "completed_at": _iso(inv.completed_at),
        "cancelled_at": _iso(inv.cancelled_at),
        "created_at": _iso(inv.created_at),
        "updated_at": _iso(inv.updated_at),
    }


def serialize_stage(row: InvestigationStage) -> dict:
    return {
        "id": str(row.id),
        "stage_key": row.stage_key,
        "attempt_number": row.attempt_number,
        "status": row.status,
        "input_summary": row.input_summary or {},
        "output_summary": row.output_summary or {},
        "error_code": row.error_code,
        "error_message": row.error_message,
        "started_at": _iso(row.started_at),
        "finished_at": _iso(row.finished_at),
        "created_at": _iso(row.created_at),
    }


def _request_hash(payload: InvestigationCreate, context: dict) -> str:
    canonical = json.dumps(
        {
            "title": payload.title,
            "bug_report": payload.bug_report,
            "severity": payload.severity,
            "snapshot": payload.repository_snapshot_id,
            "context": context,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_investigation(
    session: Session,
    user: User,
    project_id: uuid.UUID,
    payload: InvestigationCreate,
    idempotency_key: str | None,
    request_id: str,
) -> tuple[dict, bool]:
    """Validate, persist, seed activity/audit, and enqueue one job (202).

    Returns (investigation, created). Idempotent replays return the
    original with created=False; a reused key with a different request
    fails closed instead of forking a duplicate.
    """
    project, role = project_service.get_project_record(session, user, project_id)
    if role not in CONTRIBUTOR_ROLES:
        raise access_denied()
    if project.status != "active":
        raise ApiError(409, "INVALID_STATE", "Only active projects accept investigations.")
    if payload.attachments:
        raise ApiError(
            422, "ATTACHMENTS_NOT_SUPPORTED", "Report attachments are not supported yet."
        )
    if idempotency_key is not None and not job_service.IDEMPOTENCY_PATTERN.fullmatch(
        idempotency_key
    ):
        raise ApiError(422, "VALIDATION_ERROR", "The idempotency key is invalid.")
    try:
        snapshot_id = uuid.UUID(payload.repository_snapshot_id)
    except (ValueError, TypeError, AttributeError):
        raise ApiError(422, "VALIDATION_ERROR", "The snapshot id is invalid.") from None
    snapshot = (
        session.execute(
            select(RepositorySnapshot).where(
                RepositorySnapshot.id == snapshot_id,
                RepositorySnapshot.project_id == project.id,
            )
        )
    ).scalar_one_or_none()
    if snapshot is None:
        raise not_found("snapshot")
    if snapshot.storage_status != "ready" or not snapshot.storage_key:
        raise ApiError(409, "SNAPSHOT_NOT_READY", "The snapshot content is not stored.")
    context = validate_context(payload.reproduction_context)
    wanted_hash = _request_hash(payload, context)

    if idempotency_key:
        existing = (
            session.execute(
                select(Investigation).where(
                    Investigation.project_id == project.id,
                    Investigation.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            if existing.request_hash != wanted_hash:
                raise ApiError(
                    422,
                    "IDEMPOTENCY_CONFLICT",
                    "This idempotency key was already used for a different request.",
                )
            return serialize_investigation(existing, role), False

    now = db_now(session)
    inv = Investigation(
        id=uuid.uuid4(),
        project_id=project.id,
        created_by=user.id,
        repository_snapshot_id=snapshot.id,
        title=payload.title.strip(),
        bug_report=payload.bug_report.strip(),
        status="queued",
        severity=payload.severity,
        reproduction_context=context,
        idempotency_key=idempotency_key,
        request_hash=wanted_hash,
        created_at=now,
        updated_at=now,
    )
    session.add(inv)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if "uq_investigations_project_idempotency" not in str(getattr(exc, "orig", exc)):
            raise
        existing = (
            session.execute(
                select(Investigation).where(
                    Investigation.project_id == project.id,
                    Investigation.idempotency_key == idempotency_key,
                )
            )
        ).scalar_one_or_none()
        if existing is None or existing.request_hash != wanted_hash:
            raise ApiError(
                422,
                "IDEMPOTENCY_CONFLICT",
                "This idempotency key was already used for a different request.",
            ) from exc
        return serialize_investigation(existing, role), False
    session.refresh(inv)
    activity_service.append_event(
        session,
        inv.id,
        "investigation.created",
        f"Investigation opened: {inv.title[:120]}.",
        {"snapshot_id": str(snapshot.id), "severity": inv.severity},
        actor=user,
    )
    audit_service.append_audit(
        session,
        workspace_id=project.workspace_id,
        actor_type="user",
        action=audit_service.ACTION_INVESTIGATION_CREATED,
        resource_type="investigation",
        resource_id=inv.id,
        actor=user,
        request_id=request_id,
        metadata={"project_id": str(project.id), "snapshot_id": str(snapshot.id)},
    )
    try:
        job, _ = job_service.submit_job(
            session,
            user,
            project.workspace_id,
            "investigation",
            {"investigation_id": str(inv.id)},
            f"inv.{inv.id}",
            0,
            None,
        )
    except ApiError as exc:
        inv.status = "failed"
        inv.result_summary = "The investigation could not be queued."
        inv.completed_at = db_now(session)
        inv.updated_at = inv.completed_at
        session.commit()
        activity_service.append_event(
            session,
            inv.id,
            "investigation.failed",
            "The investigation could not be queued.",
            {"code": exc.code},
        )
        raise
    inv.job_id = uuid.UUID(job["id"])
    inv.updated_at = db_now(session)
    session.commit()
    session.refresh(inv)
    return serialize_investigation(inv, role), True


def list_investigations(
    session: Session,
    user: User,
    project_id: uuid.UUID,
    limit: int,
    cursor: str | None,
    status: str | None,
    severity: str | None,
) -> tuple[list[dict], str | None]:
    """Newest-first project investigations with allowlisted filters."""
    project, role = project_service.get_project_record(session, user, project_id)
    if status is not None and status not in INVESTIGATION_STATUSES:
        raise ApiError(422, "VALIDATION_ERROR", "The status filter is not supported.")
    if severity is not None and severity not in SEVERITIES:
        raise ApiError(422, "VALIDATION_ERROR", "The severity filter is not supported.")
    stmt = (
        select(Investigation)
        .where(Investigation.project_id == project.id)
        .order_by(desc(Investigation.created_at), desc(Investigation.id))
    )
    if status is not None:
        stmt = stmt.where(Investigation.status == status)
    if severity is not None:
        stmt = stmt.where(Investigation.severity == severity)
    if cursor:
        position = decode_cursor(cursor)
        if position is None:
            raise ApiError(422, "VALIDATION_ERROR", "The cursor is invalid.")
        stamp, cursor_id = position
        stmt = stmt.where(
            or_(
                Investigation.created_at < stamp,
                and_(Investigation.created_at == stamp, Investigation.id < cursor_id),
            )
        )
    rows = list(session.execute(stmt.limit(limit + 1)).scalars())
    items = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last = items[-1]
        next_cursor = encode_cursor(last.created_at, last.id)
    return [serialize_investigation(row, role) for row in items], next_cursor


def list_workspace_investigations(
    session: Session,
    user: User,
    workspace_id: uuid.UUID,
    limit: int,
    cursor: str | None,
) -> tuple[list[dict], str | None]:
    """Newest-first investigations across one workspace (for /app/investigations)."""
    role = (
        session.execute(
            select(WorkspaceMember.role).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if role is None:
        raise not_found("workspace")
    stmt = (
        select(Investigation)
        .join(Project, Project.id == Investigation.project_id)
        .where(Project.workspace_id == workspace_id)
        .order_by(desc(Investigation.created_at), desc(Investigation.id))
    )
    if cursor:
        position = decode_cursor(cursor)
        if position is None:
            raise ApiError(422, "VALIDATION_ERROR", "The cursor is invalid.")
        stamp, cursor_id = position
        stmt = stmt.where(
            or_(
                Investigation.created_at < stamp,
                and_(Investigation.created_at == stamp, Investigation.id < cursor_id),
            )
        )
    rows = list(session.execute(stmt.limit(limit + 1)).scalars())
    items = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last = items[-1]
        next_cursor = encode_cursor(last.created_at, last.id)
    return [serialize_investigation(row, role) for row in items], next_cursor


def get_investigation(session: Session, user: User, investigation_id: uuid.UUID) -> dict:
    """Detail with linked counts. Unbuilt milestones stay honest zeros."""
    from app.services import hypotheses as hypothesis_service
    from app.services import patches as patch_service
    from app.services import verification as verification_service

    inv, role = investigation_access(session, user, investigation_id)
    data = serialize_investigation(inv, role)
    data["counts"] = {
        "evidence": evidence_service.evidence_count(session, inv.id),
        "hypotheses": hypothesis_service.hypothesis_count(session, inv.id),
        "patches": patch_service.patch_count(session, inv.id),
        "verification_runs": verification_service.run_count(session, inv.id),
    }
    return data


def get_stages(session: Session, user: User, investigation_id: uuid.UUID) -> list[dict]:
    """Stage history in execution order, retries included."""
    inv, _role = investigation_access(session, user, investigation_id)
    rows = list(
        session.execute(
            select(InvestigationStage)
            .where(InvestigationStage.investigation_id == inv.id)
            .order_by(InvestigationStage.created_at.asc(), InvestigationStage.id.asc())
        ).scalars()
    )
    return [serialize_stage(row) for row in rows]


def cancel_investigation(
    session: Session, user: User, investigation_id: uuid.UUID, request_id: str
) -> dict:
    """Request cancellation. The worker confirms; actual state is retained
    until then — except when no live job remains, which finalizes now."""
    inv, role = investigation_access(session, user, investigation_id)
    if role not in CONTRIBUTOR_ROLES:
        raise access_denied()
    if inv.status in TERMINAL_STATUSES:
        raise ApiError(409, "INVALID_TRANSITION", "A terminal investigation cannot change.")
    project = session.get(Project, inv.project_id)
    assert project is not None
    job_running = False
    if inv.job_id is not None:
        from app.models import Job

        job = session.get(Job, inv.job_id)
        if job is not None and job.status not in job_service.TERMINAL_STATUSES:
            job_running = job.status == "running"
            try:
                job_service.cancel_job(session, user, job.id)
            except ApiError as exc:
                if exc.code != "INVALID_TRANSITION":
                    raise
    inv.cancel_requested = True
    if not job_running:
        # No worker can ack (queued job included): finalize honestly now
        # instead of stranding the investigation behind a dead flag.
        _check_transition(inv.status, "cancelled")
        now = db_now(session)
        open_attempts = list(
            session.execute(
                select(InvestigationStage).where(
                    InvestigationStage.investigation_id == inv.id,
                    InvestigationStage.status.in_(("pending", "running")),
                )
            ).scalars()
        )
        for attempt in open_attempts:
            attempt.status = "cancelled"
            attempt.finished_at = now
        inv.status = "cancelled"
        inv.cancelled_at = now
        inv.completed_at = now
        inv.updated_at = now
    else:
        inv.updated_at = db_now(session)
    session.commit()
    session.refresh(inv)
    activity_service.append_event(
        session,
        inv.id,
        "investigation.cancel_requested",
        "Cancellation requested.",
        {"finalized": not job_running},
        actor=user,
    )
    audit_service.append_audit(
        session,
        workspace_id=project.workspace_id,
        actor_type="user",
        action=audit_service.ACTION_INVESTIGATION_CANCEL_REQUESTED,
        resource_type="investigation",
        resource_id=inv.id,
        actor=user,
        request_id=request_id,
        metadata={"finalized": not job_running},
    )
    return serialize_investigation(inv, role)


def retry_investigation(
    session: Session,
    user: User,
    investigation_id: uuid.UUID,
    payload: InvestigationRetry,
    request_id: str,
) -> dict:
    """Requeue from one retryable stage. Prior attempts persist untouched."""
    inv, role = investigation_access(session, user, investigation_id)
    if role not in CONTRIBUTOR_ROLES:
        raise access_denied()
    if inv.status not in RETRYABLE_INVESTIGATION:
        raise ApiError(
            409, "INVALID_STATE", "Only failed, blocked, or inconclusive work can retry."
        )
    if payload.from_stage not in RETRYABLE_FROM:
        raise ApiError(422, "VALIDATION_ERROR", "This stage cannot be retried yet.")
    latest = (
        session.execute(
            select(InvestigationStage)
            .where(
                InvestigationStage.investigation_id == inv.id,
                InvestigationStage.stage_key == payload.from_stage,
            )
            .order_by(desc(InvestigationStage.attempt_number))
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest is None or latest.status not in RETRYABLE_STAGE_OUTCOMES:
        raise ApiError(409, "INVALID_STATE", "This stage has no retryable attempt.")
    project = session.get(Project, inv.project_id)
    assert project is not None
    _check_transition(inv.status, "queued", via_retry=True)
    now = db_now(session)
    inv.status = "queued"
    inv.current_stage = payload.from_stage
    inv.cancel_requested = False
    inv.result_summary = None
    inv.completed_at = None
    inv.cancelled_at = None
    inv.updated_at = now
    session.commit()
    job, _ = job_service.submit_job(
        session,
        user,
        project.workspace_id,
        "investigation",
        {"investigation_id": str(inv.id), "from_stage": payload.from_stage},
        f"retry.{inv.id}.{payload.from_stage}.{latest.attempt_number + 1}",
        0,
        None,
    )
    inv.job_id = uuid.UUID(job["id"])
    inv.updated_at = db_now(session)
    session.commit()
    session.refresh(inv)
    activity_service.append_event(
        session,
        inv.id,
        "investigation.retry_requested",
        f"Retry requested from {payload.from_stage}: {payload.reason[:160]}.",
        {"from_stage": payload.from_stage},
        actor=user,
    )
    audit_service.append_audit(
        session,
        workspace_id=project.workspace_id,
        actor_type="user",
        action=audit_service.ACTION_INVESTIGATION_RETRIED,
        resource_type="investigation",
        resource_id=inv.id,
        actor=user,
        request_id=request_id,
        metadata={"from_stage": payload.from_stage},
    )
    return serialize_investigation(inv, role)


def start_stage_attempt(
    session: Session,
    *,
    job_id: uuid.UUID,
    worker_id: str,
    investigation_id: uuid.UUID,
    stage_key: str,
    input_summary: dict | None = None,
) -> dict:
    """Open attempt N+1 for a stage (trusted worker path).

    Refuses work for superseded jobs: only the investigation's current
    job may advance it, and only while it still owns a live lease.
    """
    require_job_ownership(session, job_id, worker_id, investigation_id)
    if stage_key not in job_service.KNOWN_STAGE_KEYS:
        raise ApiError(422, "VALIDATION_ERROR", "The stage key is not supported.")
    details = dict(input_summary or {})
    check_json_bounds(details, max_bytes=SUMMARY_MAX_BYTES, label="stage input")
    latest_number = (
        session.execute(
            select(func.max(InvestigationStage.attempt_number)).where(
                InvestigationStage.investigation_id == investigation_id,
                InvestigationStage.stage_key == stage_key,
            )
        )
    ).scalar_one_or_none() or 0
    now = db_now(session)
    row = InvestigationStage(
        id=uuid.uuid4(),
        investigation_id=investigation_id,
        stage_key=stage_key,
        attempt_number=latest_number + 1,
        status="running",
        input_summary=details,
        started_at=now,
        created_at=now,
    )
    session.add(row)
    inv = session.get(Investigation, investigation_id)
    assert inv is not None
    if inv.status == "queued":
        _check_transition("queued", "running")
        inv.status = "running"
        inv.started_at = inv.started_at or now
    inv.current_stage = stage_key
    inv.updated_at = now
    session.commit()
    session.refresh(row)
    return serialize_stage(row)


def finish_stage_attempt(
    session: Session,
    *,
    job_id: uuid.UUID,
    worker_id: str,
    stage_id: uuid.UUID,
    status: str,
    output_summary: dict | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> dict:
    """Finish one running attempt (trusted worker path)."""
    row = session.get(InvestigationStage, stage_id)
    if row is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "The stage attempt was not found.")
    require_job_ownership(session, job_id, worker_id, row.investigation_id)
    if status not in STAGE_TRANSITIONS.get(row.status, frozenset()):
        raise ApiError(
            409,
            "INVALID_TRANSITION",
            f"Cannot move stage {row.stage_key} from {row.status} to {status}.",
        )
    details = dict(output_summary or {})
    check_json_bounds(details, max_bytes=SUMMARY_MAX_BYTES, label="stage output")
    now = db_now(session)
    row.status = status
    row.output_summary = details
    row.error_code = error_code[:64] if error_code else None
    row.error_message = error_message[:2000] if error_message else None
    row.finished_at = now
    inv = session.get(Investigation, row.investigation_id)
    assert inv is not None
    inv.updated_at = now
    session.commit()
    session.refresh(row)
    return serialize_stage(row)


def finalize_investigation(
    session: Session,
    *,
    job_id: uuid.UUID,
    worker_id: str,
    investigation_id: uuid.UUID,
    status: str,
    result_summary: str | None,
) -> dict:
    """Move an investigation to a terminal state (trusted worker path)."""
    require_job_ownership(session, job_id, worker_id, investigation_id)
    if status not in TERMINAL_STATUSES:
        raise ApiError(422, "VALIDATION_ERROR", "The terminal status is not supported.")
    inv = session.get(Investigation, investigation_id)
    assert inv is not None
    _check_transition(inv.status, status)
    now = db_now(session)
    inv.status = status
    inv.result_summary = (result_summary or "")[:RESULT_SUMMARY_MAX] or None
    inv.completed_at = now
    if status == "cancelled":
        inv.cancelled_at = now
    inv.updated_at = now
    session.commit()
    session.refresh(inv)
    _emit_terminal_activity(session, inv)
    project = session.get(Project, inv.project_id)
    assert project is not None
    audit_service.append_audit(
        session,
        workspace_id=project.workspace_id,
        actor_type="system",
        action=audit_service.ACTION_INVESTIGATION_TERMINAL,
        resource_type="investigation",
        resource_id=inv.id,
        request_id=None,
        metadata={"status": status},
    )
    return serialize_investigation(inv)


TOOL_RUN_STATUSES = (
    "queued",
    "running",
    "succeeded",
    "failed",
    "timed_out",
    "blocked",
    "cancelled",
)
TOOL_RUN_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "cancelled"}),
    "running": frozenset({"succeeded", "failed", "timed_out", "blocked", "cancelled"}),
    "succeeded": frozenset(),
    "failed": frozenset(),
    "timed_out": frozenset(),
    "blocked": frozenset(),
    "cancelled": frozenset(),
}


def create_tool_run(
    session: Session,
    *,
    job_id: uuid.UUID,
    worker_id: str,
    investigation_id: uuid.UUID,
    tool_name: str,
    request_summary: dict | None = None,
    stage_execution_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Open one running tool run (trusted worker path)."""
    require_job_ownership(session, job_id, worker_id, investigation_id)
    if not tool_name or len(tool_name) > 100:
        raise ApiError(422, "VALIDATION_ERROR", "The tool name is invalid.")
    details = dict(request_summary or {})
    check_json_bounds(details, max_bytes=SUMMARY_MAX_BYTES, label="tool request")
    now = db_now(session)
    row = ToolRun(
        id=uuid.uuid4(),
        investigation_id=investigation_id,
        stage_execution_id=stage_execution_id,
        tool_name=tool_name,
        status="running",
        request_summary=details,
        started_at=now,
        created_at=now,
    )
    session.add(row)
    session.commit()
    return row.id


def finish_tool_run(
    session: Session,
    *,
    tool_run_id: uuid.UUID | None,
    status: str,
    result_summary: dict | None = None,
) -> None:
    """Finish one tool run. Missing rows are caller bugs: loud.

    Errors travel inside ``result_summary`` (the table carries no
    error columns by design); callers merge code/message there.
    """
    if tool_run_id is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "The tool run was not found.")
    row = session.get(ToolRun, tool_run_id)
    if row is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "The tool run was not found.")
    if status not in TOOL_RUN_TRANSITIONS.get(row.status, frozenset()):
        raise ApiError(
            409,
            "INVALID_TRANSITION",
            f"Cannot move tool run {row.tool_name} from {row.status} to {status}.",
        )
    details = dict(result_summary or {})
    check_json_bounds(details, max_bytes=SUMMARY_MAX_BYTES, label="tool result")
    row.status = status
    row.result_summary = details
    row.finished_at = db_now(session)
    session.commit()


def transition_for_approval(session: Session, investigation_id: uuid.UUID) -> None:
    """Requeue after approval: awaiting_approval → queued (no commit)."""
    inv = session.get(Investigation, investigation_id)
    if inv is None:
        raise not_found("investigation")
    if inv.status != "awaiting_approval":
        raise ApiError(409, "INVALID_STATE", "The investigation is not awaiting approval.")
    _check_transition(inv.status, "queued")
    inv.status = "queued"
    inv.current_stage = "patch_application"
    inv.cancel_requested = False
    inv.updated_at = db_now(session)


def transition_for_rejection(
    session: Session, investigation_id: uuid.UUID, reason: str, actor: User
) -> None:
    """Terminal rejection: awaiting_approval → completed, nothing applied."""
    inv = session.get(Investigation, investigation_id)
    if inv is None:
        raise not_found("investigation")
    _check_transition(inv.status, "completed")
    now = db_now(session)
    inv.status = "completed"
    inv.result_summary = f"Patch rejected by reviewer: {reason[:160]} No changes applied."[
        :RESULT_SUMMARY_MAX
    ]
    inv.completed_at = now
    inv.updated_at = now
    session.commit()
    activity_service.append_event(
        session,
        inv.id,
        "investigation.completed",
        f"Patch rejected: {reason[:160]}.",
        {"status": "completed"},
        actor=actor,
    )


def park_for_approval(
    session: Session,
    *,
    job_id: uuid.UUID,
    worker_id: str,
    investigation_id: uuid.UUID,
) -> None:
    """Park a running investigation at the human gate (worker path).

    Idempotent: re-parking an already parked investigation is a no-op
    so stage retries converge instead of conflicting.
    """
    require_job_ownership(session, job_id, worker_id, investigation_id)
    inv = session.get(Investigation, investigation_id)
    assert inv is not None
    if inv.status == "awaiting_approval":
        return
    _check_transition(inv.status, "awaiting_approval")
    inv.status = "awaiting_approval"
    inv.updated_at = db_now(session)
    session.commit()
    activity_service.append_event(
        session,
        inv.id,
        "investigation.awaiting_approval",
        "Patch proposed: waiting for human approval.",
        {"status": "awaiting_approval"},
    )


def cancel_requested(session: Session, investigation_id: uuid.UUID) -> bool:
    """Read-only cancel flag for worker abort polling (no locks, no writes)."""
    return (
        session.execute(
            select(Investigation.cancel_requested).where(Investigation.id == investigation_id)
        ).scalar_one_or_none()
    ) is True


def require_job_ownership(
    session: Session, job_id: uuid.UUID, worker_id: str, investigation_id: uuid.UUID
) -> None:
    inv = session.get(Investigation, investigation_id)
    if inv is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "The investigation was not found.")
    if inv.job_id != job_id:
        raise ApiError(409, "JOB_SUPERSEDED", "A newer job owns this investigation.")
    if not job_service.is_running_and_owned(session, job_id, worker_id):
        raise ApiError(409, "LEASE_LOST", "The job lease expired or was cancelled.")


def _emit_terminal_activity(session: Session, inv: Investigation) -> None:
    kinds = {
        "completed": ("investigation.completed", "Investigation completed."),
        "failed": ("investigation.failed", "Investigation failed."),
        "blocked": ("investigation.blocked", "Investigation blocked."),
        "inconclusive": ("investigation.inconclusive", "Investigation inconclusive."),
        "cancelled": ("investigation.cancelled", "Investigation cancelled."),
    }
    event_type, message = kinds.get(inv.status, ("investigation.completed", "Done."))
    detail = (inv.result_summary or "")[:200]
    activity_service.append_event(
        session,
        inv.id,
        event_type,
        f"{message} {detail}".strip(),
        {"status": inv.status},
    )
