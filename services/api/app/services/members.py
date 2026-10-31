"""Workspace membership service (API.md §6.4, decisions D18)."""

import datetime as dt
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.envelope import ApiError, access_denied, not_found
from app.models import User, Workspace, WorkspaceMember
from app.schemas import MemberCreate, MemberUpdate
from app.services.auth import LOCAL_PROVIDER

MANAGER_ROLES = frozenset({"owner", "admin"})


def _serialize(member: WorkspaceMember, user: User) -> dict:
    joined = member.joined_at
    return {
        "user_id": str(member.user_id),
        "email": user.email,
        "display_name": user.display_name,
        "role": member.role,
        "joined_at": joined.isoformat().replace("+00:00", "Z"),
    }


def _membership(
    session: Session, workspace_id: uuid.UUID, user_id: uuid.UUID
) -> WorkspaceMember | None:
    return session.get(WorkspaceMember, (workspace_id, user_id))


def _require_membership(
    session: Session, workspace_id: uuid.UUID, user: User
) -> WorkspaceMember:
    workspace = session.get(Workspace, workspace_id)
    member = _membership(session, workspace_id, user.id) if workspace else None
    if workspace is None or member is None:
        raise not_found("workspace")
    return member


def _owner_count(session: Session, workspace_id: uuid.UUID) -> int:
    return (
        session.execute(
            select(func.count())
            .select_from(WorkspaceMember)
            .where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.role == "owner",
            )
        )
    ).scalar_one()


def list_members(session: Session, user: User, workspace_id: uuid.UUID) -> list[dict]:
    _require_membership(session, workspace_id, user)
    rows = (
        session.execute(
            select(WorkspaceMember, User)
            .join(User, User.id == WorkspaceMember.user_id)
            .where(WorkspaceMember.workspace_id == workspace_id)
            .order_by(WorkspaceMember.joined_at, WorkspaceMember.user_id)
        )
    ).all()
    return [_serialize(member, member_user) for member, member_user in rows]


def add_member(
    session: Session, user: User, workspace_id: uuid.UUID, payload: MemberCreate
) -> dict:
    caller = _require_membership(session, workspace_id, user)
    if caller.role not in MANAGER_ROLES:
        raise access_denied()
    email = payload.email.strip().lower()
    target = (
        session.execute(
            select(User).where(
                User.auth_provider == LOCAL_PROVIDER,
                func.lower(User.email) == email,
                User.status == "active",
            )
        )
    ).scalar_one_or_none()
    if target is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "No active account uses this email.")
    if _membership(session, workspace_id, target.id) is not None:
        raise ApiError(409, "RESOURCE_CONFLICT", "This user is already a member.")
    member = WorkspaceMember(
        workspace_id=workspace_id,
        user_id=target.id,
        role=payload.role,
        joined_at=dt.datetime.now(dt.UTC),
        invited_by=user.id,
    )
    session.add(member)
    session.commit()
    session.refresh(member)
    return _serialize(member, target)


def update_member(
    session: Session,
    user: User,
    workspace_id: uuid.UUID,
    target_user_id: uuid.UUID,
    payload: MemberUpdate,
) -> dict:
    caller = _require_membership(session, workspace_id, user)
    if caller.role not in MANAGER_ROLES:
        raise access_denied()
    member = _membership(session, workspace_id, target_user_id)
    if member is None:
        raise not_found("workspace member")
    if member.role == "owner":
        # Owner is immutable in M2 (no transfer flow yet).
        raise ApiError(
            409,
            "INVALID_STATE_TRANSITION",
            "The owner role cannot be changed in this release.",
        )
    member.role = payload.role
    session.commit()
    session.refresh(member)
    target = session.get(User, target_user_id)
    assert target is not None
    return _serialize(member, target)


def remove_member(
    session: Session, user: User, workspace_id: uuid.UUID, target_user_id: uuid.UUID
) -> None:
    caller = _require_membership(session, workspace_id, user)
    member = _membership(session, workspace_id, target_user_id)
    if member is None:
        raise not_found("workspace member")
    is_self = target_user_id == user.id
    if not is_self and caller.role not in MANAGER_ROLES:
        raise access_denied()
    if member.role == "owner" and _owner_count(session, workspace_id) <= 1:
        raise ApiError(
            409,
            "INVALID_STATE_TRANSITION",
            "A workspace must keep at least one owner.",
        )
    session.delete(member)
    session.commit()
