"""Audit routes: owner/admin reads over append-only audit events."""

import uuid

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, DbSession, RequestId
from app.config import get_settings
from app.envelope import paged
from app.services import audit as audit_service

router = APIRouter(tags=["audit"])


@router.get("/api/v1/workspaces/{workspace_id}/audit-events")
def list_audit(
    workspace_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=512),
    action: str | None = Query(default=None, max_length=100),
) -> JSONResponse:
    settings = get_settings()
    effective_limit = min(limit or settings.page_default_limit, settings.page_max_limit)
    items, next_cursor = audit_service.list_audit(
        session, user, workspace_id, effective_limit, cursor, action
    )
    return paged(items, effective_limit, next_cursor, request_id)
