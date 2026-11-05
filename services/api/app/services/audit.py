"""Append-only audit events (M6): security-sensitive actions, owner/admin reads.

Writes cover investigation lifecycle transitions and evidence download
issuance. Rows never hold tokens, cookies, full bodies, signed URLs, or
raw IPs — metadata is allowlisted and redacted by the caller.
"""

import datetime as dt
import re
import uuid

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.orm import Session

from app.envelope import ApiError, access_denied, not_found
from app.models import AuditEvent, User, WorkspaceMember
from app.services.jobs import check_json_bounds

ACTION_PATTERN = re.compile(r"^[a-z][a-z0-9_.]{1,80}$")
METADATA_MAX_BYTES = 4096
READER_ROLES = frozenset({"owner", "admin"})

# Backend-authored actions only; no caller-supplied action reaches the row.
ACTION_INVESTIGATION_CREATED = "investigation.created"
ACTION_INVESTIGATION_CANCELLED = "investigation.cancelled"
ACTION_INVESTIGATION_CANCEL_REQUESTED = "investigation.cancel_requested"
ACTION_INVESTIGATION_RETRIED = "investigation.retried"
ACTION_INVESTIGATION_TERMINAL = "investigation.terminal"
ACTION_EVIDENCE_DOWNLOAD_ISSUED = "evidence.download_issued"
ACTION_REPORT_DOWNLOAD_ISSUED = "report.download_issued"
ACTION_HYPOTHESIS_REVIEWED = "hypothesis.reviewed"


def _iso(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def serialize_event(row: AuditEvent) -> dict:
    return {
        "id": str(row.id),
        "workspace_id": str(row.workspace_id) if row.workspace_id else None,
        "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
        "actor_type": row.actor_type,
        "action": row.action,
        "resource_type": row.resource_type,
        "resource_id": str(row.resource_id) if row.resource_id else None,
        "request_id": row.request_id,
        "metadata": row.metadata_ or {},
        "created_at": _iso(row.created_at),
    }


def append_audit(
    session: Session,
    *,
    workspace_id: uuid.UUID | None,
    actor_type: str,
    action: str,
    resource_type: str | None = None,
    resource_id: uuid.UUID | None = None,
    actor: User | None = None,
    request_id: str | None = None,
    metadata: dict | None = None,
) -> dict:
    """Append one audit row. Never raises for bad input shape beyond 422."""
    if actor_type not in ("user", "system", "service"):
        raise ApiError(422, "VALIDATION_ERROR", "The actor type is invalid.")
    if not ACTION_PATTERN.fullmatch(action):
        raise ApiError(422, "VALIDATION_ERROR", "The audit action is invalid.")
    details = dict(metadata or {})
    check_json_bounds(details, max_bytes=METADATA_MAX_BYTES, label="audit metadata")
    row = AuditEvent(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        actor_user_id=actor.id if actor else None,
        actor_type=actor_type,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        request_id=request_id[:64] if request_id else None,
        metadata_=details,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return serialize_event(row)


def list_audit(
    session: Session,
    user: User,
    workspace_id: uuid.UUID,
    limit: int,
    cursor: str | None,
    action: str | None,
) -> tuple[list[dict], str | None]:
    """Newest-first audit page. Owners/admins only; foreign workspaces 404."""
    from app.services import investigations as investigation_service

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
    if role not in READER_ROLES:
        raise access_denied()
    if action is not None and not ACTION_PATTERN.fullmatch(action):
        raise ApiError(422, "VALIDATION_ERROR", "The action filter is invalid.")
    stmt = (
        select(AuditEvent)
        .where(AuditEvent.workspace_id == workspace_id)
        .order_by(desc(AuditEvent.created_at), desc(AuditEvent.id))
    )
    if action is not None:
        stmt = stmt.where(AuditEvent.action == action)
    if cursor:
        position = investigation_service.decode_cursor(cursor)
        if position is None:
            raise ApiError(422, "VALIDATION_ERROR", "The cursor is invalid.")
        stamp, cursor_id = position
        stmt = stmt.where(
            or_(
                AuditEvent.created_at < stamp,
                and_(AuditEvent.created_at == stamp, AuditEvent.id < cursor_id),
            )
        )
    rows = list(session.execute(stmt.limit(limit + 1)).scalars())
    items = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last = items[-1]
        next_cursor = investigation_service.encode_cursor(last.created_at, last.id)
    return [serialize_event(row) for row in items], next_cursor
