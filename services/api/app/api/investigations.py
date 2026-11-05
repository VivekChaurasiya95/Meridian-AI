"""Investigation routes (API.md §6.7-§6.10). Thin handlers over services."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Query
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, DbSession, RequestId, write_limiter
from app.config import get_settings
from app.envelope import ApiError, ok, paged
from app.schemas import (
    HypothesisReviewUpdate,
    InvestigationCreate,
    InvestigationRetry,
    RegressionTestCreate,
)
from app.services import activity as activity_service
from app.services import evidence as evidence_service
from app.services import hypotheses as hypothesis_service
from app.services import investigations as investigation_service
from app.services import regression_tests as regression_test_service
from app.services import reports as report_service

router = APIRouter(tags=["investigations"])


@router.post("/api/v1/projects/{project_id}/investigations", status_code=202)
def create_investigation(
    project_id: uuid.UUID,
    payload: InvestigationCreate,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
    idempotency_key: Annotated[str | None, Header(max_length=128)] = None,
) -> JSONResponse:
    data, created = investigation_service.create_investigation(
        session, user, project_id, payload, idempotency_key, request_id
    )
    links = {
        "self": f"/api/v1/investigations/{data['id']}",
        "activity": f"/api/v1/investigations/{data['id']}/activity",
    }
    return ok(data, request_id, status_code=202 if created else 200, links=links)


@router.get("/api/v1/projects/{project_id}/investigations")
def list_investigations(
    project_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=512),
    status: str | None = Query(default=None, max_length=32),
    severity: str | None = Query(default=None, max_length=32),
) -> JSONResponse:
    settings = get_settings()
    effective_limit = min(limit or settings.page_default_limit, settings.page_max_limit)
    items, next_cursor = investigation_service.list_investigations(
        session, user, project_id, effective_limit, cursor, status, severity
    )
    return paged(items, effective_limit, next_cursor, request_id)


@router.get("/api/v1/workspaces/{workspace_id}/investigations")
def list_workspace_investigations(
    workspace_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=512),
) -> JSONResponse:
    settings = get_settings()
    effective_limit = min(limit or settings.page_default_limit, settings.page_max_limit)
    items, next_cursor = investigation_service.list_workspace_investigations(
        session, user, workspace_id, effective_limit, cursor
    )
    return paged(items, effective_limit, next_cursor, request_id)


@router.get("/api/v1/investigations/{investigation_id}")
def get_investigation(
    investigation_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = investigation_service.get_investigation(session, user, investigation_id)
    return ok(data, request_id)


@router.post("/api/v1/investigations/{investigation_id}/cancel", status_code=202)
def cancel_investigation(
    investigation_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = investigation_service.cancel_investigation(session, user, investigation_id, request_id)
    return ok(data, request_id, status_code=202)


@router.post("/api/v1/investigations/{investigation_id}/retry", status_code=202)
def retry_investigation(
    investigation_id: uuid.UUID,
    payload: InvestigationRetry,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = investigation_service.retry_investigation(
        session, user, investigation_id, payload, request_id
    )
    return ok(data, request_id, status_code=202)


@router.get("/api/v1/investigations/{investigation_id}/stages")
def get_stages(
    investigation_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = investigation_service.get_stages(session, user, investigation_id)
    return ok(data, request_id)


@router.get("/api/v1/investigations/{investigation_id}/activity")
def get_activity(
    investigation_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=512),
) -> JSONResponse:
    activity_service.investigation_access(session, user, investigation_id)
    settings = get_settings()
    effective_limit = min(limit or settings.page_default_limit, settings.page_max_limit)
    items, next_cursor = activity_service.list_events(
        session, investigation_id, effective_limit, cursor
    )
    return paged(items, effective_limit, next_cursor, request_id)


@router.get("/api/v1/investigations/{investigation_id}/hypotheses")
def list_hypotheses(
    investigation_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = hypothesis_service.list_hypotheses(session, user, investigation_id)
    return ok(data, request_id)


@router.get("/api/v1/hypotheses/{hypothesis_id}")
def get_hypothesis(
    hypothesis_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = hypothesis_service.get_hypothesis(session, user, hypothesis_id)
    return ok(data, request_id)


@router.patch("/api/v1/hypotheses/{hypothesis_id}")
def review_hypothesis(
    hypothesis_id: uuid.UUID,
    payload: HypothesisReviewUpdate,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    rate_key = f"write:{user.id}"
    limiter = write_limiter()
    if not limiter.allowed(rate_key):
        raise ApiError(429, "RATE_LIMITED", "Too many requests. Try again later.")
    limiter.register_failure(rate_key)
    data = hypothesis_service.review_hypothesis(
        session, user, hypothesis_id, payload.verdict, payload.note, request_id
    )
    return ok(data, request_id)


@router.get("/api/v1/investigations/{investigation_id}/report")
def get_report(
    investigation_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = report_service.get_latest_report(session, user, investigation_id)
    return ok(data, request_id)


@router.get("/api/v1/investigations/{investigation_id}/regression-tests")
def list_regression_tests(
    investigation_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = regression_test_service.list_tests(session, user, investigation_id)
    return ok(data, request_id)


@router.post("/api/v1/investigations/{investigation_id}/regression-tests", status_code=201)
def create_regression_test(
    investigation_id: uuid.UUID,
    payload: RegressionTestCreate,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = regression_test_service.create_proposed(
        session,
        user,
        investigation_id,
        payload.title,
        payload.description,
        payload.test_type,
        payload.file_path,
        payload.test_name,
    )
    return ok(data, request_id, status_code=201)


@router.get("/api/v1/regression-tests/{test_id}")
def get_regression_test(
    test_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = regression_test_service.get_test(session, user, test_id)
    return ok(data, request_id)


@router.get("/api/v1/investigations/{investigation_id}/evidence")
def list_evidence(
    investigation_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
    kind: str | None = Query(default=None, max_length=32),
    redaction_status: str | None = Query(default=None, max_length=32),
) -> JSONResponse:
    data = evidence_service.list_evidence(session, user, investigation_id, kind, redaction_status)
    return ok(data, request_id)
