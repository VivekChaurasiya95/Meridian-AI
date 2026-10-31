"""Workspace membership routes (API.md §6.4, decision D18)."""

import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, DbSession, RequestId
from app.envelope import ok
from app.schemas import MemberCreate, MemberUpdate
from app.services import members as member_service

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/members", tags=["membership"]
)


@router.get("")
def list_members(
    workspace_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    return ok(member_service.list_members(session, user, workspace_id), request_id)


@router.post("", status_code=201)
def add_member(
    workspace_id: uuid.UUID,
    payload: MemberCreate,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = member_service.add_member(session, user, workspace_id, payload)
    return ok(data, request_id, status_code=201)


@router.patch("/{target_user_id}")
def update_member(
    workspace_id: uuid.UUID,
    target_user_id: uuid.UUID,
    payload: MemberUpdate,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = member_service.update_member(session, user, workspace_id, target_user_id, payload)
    return ok(data, request_id)


@router.delete("/{target_user_id}", status_code=204)
def remove_member(
    workspace_id: uuid.UUID,
    target_user_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    member_service.remove_member(session, user, workspace_id, target_user_id)
    return JSONResponse(status_code=204, content=None)
