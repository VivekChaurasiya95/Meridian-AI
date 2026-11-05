"""File-report routes (M10): generate, list, read, download."""

import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, DbSession, RequestId
from app.envelope import ok
from app.schemas import ReportCreate
from app.services import reports as report_service

router = APIRouter(tags=["reports"])


@router.post("/api/v1/investigations/{investigation_id}/reports", status_code=201)
def create_report(
    investigation_id: uuid.UUID,
    payload: ReportCreate,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = report_service.request_report(session, user, investigation_id, payload.format)
    return ok(data, request_id, status_code=201)


@router.get("/api/v1/investigations/{investigation_id}/reports")
def list_reports(
    investigation_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = report_service.list_reports(session, user, investigation_id)
    return ok(data, request_id)


@router.get("/api/v1/workspaces/{workspace_id}/reports")
def list_workspace_reports(
    workspace_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = report_service.list_workspace_reports(session, user, workspace_id)
    return ok(data, request_id)


@router.get("/api/v1/reports/{report_id}")
def get_report(
    report_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = report_service.get_report(session, user, report_id)
    return ok(data, request_id)


@router.post("/api/v1/reports/{report_id}/download-url")
def download_url(
    report_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = report_service.issue_download_url(session, user, report_id, request_id)
    return ok(data, request_id)
