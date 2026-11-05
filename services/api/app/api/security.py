"""Security assessment retrieval (V1, read-only).

Serves persisted, sanitized assessments and findings. There is no
scan trigger here (preflight starts internally after snapshot
readiness) and no raw scanner output anywhere in these responses.
"""

import uuid

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, DbSession, RequestId
from app.config import get_settings
from app.envelope import ok, paged
from app.services import security_assessments as assessment_service

router = APIRouter(tags=["security-assessments"])


@router.get("/api/v1/projects/{project_id}/security-assessments")
def list_project_assessments(
    project_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=512),
) -> JSONResponse:
    settings = get_settings()
    effective_limit = min(limit or settings.page_default_limit, settings.page_max_limit)
    items, next_cursor = assessment_service.list_project_assessments(
        session, user, project_id, effective_limit, cursor
    )
    return paged(items, effective_limit, next_cursor, request_id)


@router.get("/api/v1/snapshots/{snapshot_id}/security-assessment")
def get_snapshot_assessment(
    snapshot_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = assessment_service.get_snapshot_assessment(session, user, snapshot_id)
    return ok(data, request_id)


@router.get("/api/v1/security-assessments/{assessment_id}")
def get_assessment(
    assessment_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = assessment_service.get_assessment(session, user, assessment_id)
    return ok(data, request_id)


@router.get("/api/v1/security-assessments/{assessment_id}/findings")
def list_findings(
    assessment_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=512),
    severity: str | None = Query(default=None, max_length=32),
    scanner: str | None = Query(default=None, max_length=32),
    category: str | None = Query(default=None, max_length=64),
    path_prefix: str | None = Query(default=None, max_length=512),
) -> JSONResponse:
    settings = get_settings()
    effective_limit = min(limit or settings.page_default_limit, settings.page_max_limit)
    items, next_cursor = assessment_service.list_findings(
        session,
        user,
        assessment_id,
        effective_limit,
        cursor,
        severity,
        scanner,
        category,
        path_prefix,
    )
    return paged(items, effective_limit, next_cursor, request_id)
