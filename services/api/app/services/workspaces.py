"""Workspace domain service: membership-scoped queries, single transactions.

Every read and write is scoped through ``workspace_members`` — a caller can
only observe or mutate workspaces they belong to. Row existence is never
leaked to non-members (404 either way).
"""

import base64
import datetime as dt
import uuid

from sqlalchemy import and_, desc, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.envelope import ApiError, access_denied, not_found
from app.models import User, Workspace, WorkspaceMember
from app.schemas import WorkspaceCreate, WorkspaceUpdate

MANAGER_ROLES = frozenset({"owner", "admin"})


def _serialize(workspace: Workspace, role: str) -> dict:
    return {
        "id": str(workspace.id),
        "name": workspace.name,
        "slug": workspace.slug,
        "role": role,
        "created_at": workspace.created_at.isoformat().replace("+00:00", "Z"),
    }


def encode_cursor(created_at: dt.datetime, workspace_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{workspace_id}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str) -> tuple[dt.datetime, uuid.UUID] | None:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        created_raw, id_raw = raw.split("|", 1)
        return dt.datetime.fromisoformat(created_raw), uuid.UUID(id_raw)
    except (ValueError, TypeError):
        return None


def create_workspace(session: Session, user: User, payload: WorkspaceCreate) -> dict:
    """Create a workspace plus its owner membership in one transaction."""
    now = dt.datetime.now(dt.UTC)
    workspace = Workspace(
        id=uuid.uuid4(),
        name=payload.name,
        slug=payload.slug,
        created_by=user.id,
        created_at=now,
        updated_at=now,
    )
    session.add(workspace)
    session.flush()
    session.add(
        WorkspaceMember(
            workspace_id=workspace.id, user_id=user.id, role="owner", invited_by=user.id
        )
    )
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        # Only the slug unique constraint maps to 409; anything else is a bug.
        if "workspaces_slug_key" not in str(getattr(exc, "orig", exc)):
            raise
        raise ApiError(
            409, "RESOURCE_CONFLICT", "A workspace with this slug already exists."
        ) from exc
    session.refresh(workspace)
    return _serialize(workspace, "owner")


def list_workspaces(
    session: Session, user: User, limit: int, cursor: str | None
) -> tuple[list[dict], str | None]:
    """List the caller's workspaces, newest first, with an opaque cursor."""
    position: tuple[dt.datetime, uuid.UUID] | None = None
    if cursor:
        position = decode_cursor(cursor)
        if position is None:
            raise ApiError(422, "VALIDATION_ERROR", "The cursor is invalid.")

    stmt = (
        select(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id)
    )
    if position is not None:
        created_at, workspace_id = position
        stmt = stmt.where(
            or_(
                Workspace.created_at < created_at,
                and_(
                    Workspace.created_at == created_at,
                    Workspace.id < workspace_id,
                ),
            )
        )
    stmt = stmt.order_by(desc(Workspace.created_at), desc(Workspace.id)).limit(limit + 1)

    rows = list(session.execute(stmt).all())
    items = [_serialize(workspace, role) for workspace, role in rows[:limit]]
    next_cursor = None
    if len(rows) > limit:
        last_workspace = rows[limit - 1][0]
        next_cursor = encode_cursor(last_workspace.created_at, last_workspace.id)
    return items, next_cursor


def get_workspace(session: Session, user: User, workspace_id: uuid.UUID) -> dict:
    row = (
        session.execute(
            select(Workspace, WorkspaceMember.role)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(
                Workspace.id == workspace_id,
                WorkspaceMember.user_id == user.id,
            )
        )
    ).one_or_none()
    if row is None:
        raise not_found("workspace")
    workspace, role = row
    return _serialize(workspace, role)


def update_workspace(
    session: Session, user: User, workspace_id: uuid.UUID, payload: WorkspaceUpdate
) -> dict:
    row = (
        session.execute(
            select(Workspace, WorkspaceMember.role)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(
                Workspace.id == workspace_id,
                WorkspaceMember.user_id == user.id,
            )
            .with_for_update()
        )
    ).one_or_none()
    if row is None:
        raise not_found("workspace")
    workspace, role = row
    if role not in MANAGER_ROLES:
        session.rollback()
        raise access_denied()
    workspace.name = payload.name
    workspace.updated_at = dt.datetime.now(dt.UTC)
    session.commit()
    session.refresh(workspace)
    return _serialize(workspace, role)
