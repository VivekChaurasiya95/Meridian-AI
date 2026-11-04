"""Job routes (M4): submit, history, detail, cancel, stages.

Internal worker transitions (claim/heartbeat/complete/fail) are NOT
HTTP endpoints: the worker calls the service layer directly, so no
worker credentials exist to protect (D45).
"""

import uuid

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, DbSession, RequestId
from app.config import get_settings
from app.envelope import ok, paged
from app.schemas import JobSubmit
from app.services import jobs as job_service

router = APIRouter(tags=["jobs"])


@router.post("/api/v1/workspaces/{workspace_id}/jobs", status_code=201)
def submit_job(
    workspace_id: uuid.UUID,
    payload: JobSubmit,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data, created = job_service.submit_job(
        session,
        user,
        workspace_id,
        payload.job_type,
        payload.payload,
        payload.idempotency_key,
        payload.priority,
        payload.max_attempts,
    )
    return ok(data, request_id, status_code=201 if created else 200)


@router.get("/api/v1/workspaces/{workspace_id}/jobs")
def list_jobs(
    workspace_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=512),
    status: str | None = Query(default=None, max_length=32),
    job_type: str | None = Query(default=None, max_length=32),
) -> JSONResponse:
    settings = get_settings()
    effective_limit = min(limit or settings.page_default_limit, settings.page_max_limit)
    items, next_cursor = job_service.list_jobs(
        session, user, workspace_id, effective_limit, cursor, status, job_type
    )
    return paged(items, effective_limit, next_cursor, request_id)


@router.get("/api/v1/jobs/{job_id}")
def get_job(
    job_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = job_service.get_job(session, user, job_id)
    return ok(data, request_id)


@router.post("/api/v1/jobs/{job_id}/cancel")
def cancel_job(
    job_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = job_service.cancel_job(session, user, job_id)
    return ok(data, request_id)


@router.get("/api/v1/jobs/{job_id}/stages")
def get_stages(
    job_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = job_service.get_stages(session, user, job_id)
    return ok({"stages": data}, request_id)
