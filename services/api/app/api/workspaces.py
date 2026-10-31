"""Workspace routes (API.md §6.3). Thin handlers over the domain service."""

import uuid

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, DbSession, RequestId
from app.config import get_settings
from app.envelope import ok, paged
from app.schemas import WorkspaceCreate, WorkspaceUpdate
from app.services import workspaces as workspace_service

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


@router.post("", status_code=201)
def create_workspace(
    payload: WorkspaceCreate,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = workspace_service.create_workspace(session, user, payload)
    return ok(data, request_id, status_code=201)


@router.get("")
def list_workspaces(
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=512),
) -> JSONResponse:
    settings = get_settings()
    effective_limit = min(limit or settings.page_default_limit, settings.page_max_limit)
    items, next_cursor = workspace_service.list_workspaces(
        session, user, effective_limit, cursor
    )
    return paged(items, effective_limit, next_cursor, request_id)


@router.get("/{workspace_id}")
def get_workspace(
    workspace_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = workspace_service.get_workspace(session, user, workspace_id)
    return ok(data, request_id)


@router.patch("/{workspace_id}")
def update_workspace(
    workspace_id: uuid.UUID,
    payload: WorkspaceUpdate,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = workspace_service.update_workspace(session, user, workspace_id, payload)
    return ok(data, request_id)
