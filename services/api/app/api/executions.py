"""Execution routes (M5): read-only views over persisted container runs."""

import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, DbSession, RequestId
from app.envelope import ok
from app.services import executions as execution_service

router = APIRouter(tags=["executions"])


@router.get("/api/v1/jobs/{job_id}/executions")
def list_job_executions(
    job_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = execution_service.list_job_executions(session, user, job_id)
    return ok({"executions": data}, request_id)


@router.get("/api/v1/executions/{execution_id}")
def get_execution(
    execution_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = execution_service.get_execution(session, user, execution_id)
    return ok(data, request_id)
