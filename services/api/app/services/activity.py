"""Investigation activity timeline (M6): user-visible events, oldest first.

Events are backend-authored only: the worker and the API write them at
meaningful transitions. Payloads are small, redacted, versioned
details — never stack traces, secrets, or unfiltered tool output.
"""

import datetime as dt
import re
import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.envelope import ApiError
from app.models import ActivityEvent, Investigation, Project, User, WorkspaceMember
from app.services.jobs import check_json_bounds

EVENT_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_.]{1,80}$")
MESSAGE_MAX = 500
PAYLOAD_MAX_BYTES = 4096


def _iso(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def serialize_event(row: ActivityEvent) -> dict:
    return {
        "id": str(row.id),
        "event_type": row.event_type,
        "message": row.message,
        "payload": row.payload or {},
        "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
        "created_at": _iso(row.created_at),
    }


def append_event(
    session: Session,
    investigation_id: uuid.UUID,
    event_type: str,
    message: str,
    payload: dict | None = None,
    actor: User | None = None,
) -> dict:
    """Append one timeline event. Backend-authored types only."""
    if not EVENT_TYPE_PATTERN.fullmatch(event_type):
        raise ApiError(422, "VALIDATION_ERROR", "The event type is invalid.")
    clean_message = (message or "").strip()
    if not clean_message or len(clean_message) > MESSAGE_MAX:
        raise ApiError(422, "VALIDATION_ERROR", "The event message is invalid.")
    details = dict(payload or {})
    check_json_bounds(details, max_bytes=PAYLOAD_MAX_BYTES, label="activity payload")
    row = ActivityEvent(
        id=uuid.uuid4(),
        investigation_id=investigation_id,
        actor_user_id=actor.id if actor else None,
        event_type=event_type,
        message=clean_message,
        payload=details,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return serialize_event(row)


def list_events(
    session: Session,
    investigation_id: uuid.UUID,
    limit: int,
    cursor: str | None,
) -> tuple[list[dict], str | None]:
    """Chronological timeline page. Caller must have authorized access."""
    from app.services import investigations as investigation_service

    stmt = (
        select(ActivityEvent)
        .where(ActivityEvent.investigation_id == investigation_id)
        .order_by(ActivityEvent.created_at.asc(), ActivityEvent.id.asc())
    )
    if cursor:
        position = investigation_service.decode_cursor(cursor)
        if position is None:
            raise ApiError(422, "VALIDATION_ERROR", "The cursor is invalid.")
        stamp, cursor_id = position
        stmt = stmt.where(
            or_(
                ActivityEvent.created_at > stamp,
                (ActivityEvent.created_at == stamp) & (ActivityEvent.id > cursor_id),
            )
        )
    rows = list(session.execute(stmt.limit(limit + 1)).scalars())
    items = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last = items[-1]
        next_cursor = investigation_service.encode_cursor(last.created_at, last.id)
    return [serialize_event(row) for row in items], next_cursor


def investigation_access(
    session: Session, user: User, investigation_id: uuid.UUID
) -> tuple[Investigation, str]:
    """Shared access check: investigation + caller role, 404 for foreign."""
    row = (
        session.execute(
            select(Investigation, WorkspaceMember.role)
            .join(Project, Project.id == Investigation.project_id)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Project.workspace_id)
            .where(
                Investigation.id == investigation_id,
                WorkspaceMember.user_id == user.id,
            )
        )
    ).one_or_none()
    if row is None:
        from app.envelope import not_found

        raise not_found("investigation")
    investigation = row[0]
    assert isinstance(investigation, Investigation)
    return investigation, row[1]


def db_now(session: Session) -> dt.datetime:
    now = session.execute(select(func.now())).scalar_one()
    assert isinstance(now, dt.datetime)
    return now
