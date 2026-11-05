"""Verification routes (API.md §6.14): run reads, reruns, comparison."""

import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, DbSession, RequestId
from app.envelope import ok
from app.schemas import VerificationRunCreate
from app.services import verification as verification_service

router = APIRouter(tags=["verification"])


@router.get("/api/v1/investigations/{investigation_id}/verification-runs")
def list_verification_runs(
    investigation_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = verification_service.list_runs(session, user, investigation_id)
    return ok(data, request_id)


@router.get("/api/v1/verification-runs/{run_id}")
def get_verification_run(
    run_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = verification_service.get_run(session, user, run_id)
    return ok(data, request_id)


@router.post("/api/v1/investigations/{investigation_id}/verification-runs", status_code=201)
def create_verification_run(
    investigation_id: uuid.UUID,
    payload: VerificationRunCreate,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = verification_service.create_run(
        session, user, investigation_id, payload.selected_check_keys
    )
    return ok(data, request_id, status_code=201)


@router.get("/api/v1/investigations/{investigation_id}/verification-comparison")
def get_verification_comparison(
    investigation_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = verification_service.comparison(session, user, investigation_id)
    return ok(data, request_id)
