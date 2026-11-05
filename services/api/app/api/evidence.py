"""Evidence routes (API.md §6.10): metadata reads + signed downloads."""

import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, DbSession, RequestId
from app.envelope import ok
from app.services import evidence as evidence_service

router = APIRouter(tags=["evidence"])


@router.get("/api/v1/evidence/{evidence_id}")
def get_evidence(
    evidence_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = evidence_service.get_evidence(session, user, evidence_id)
    return ok(data, request_id)


@router.post("/api/v1/evidence/{evidence_id}/download-url")
def download_url(
    evidence_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = evidence_service.issue_download_url(session, user, evidence_id, request_id)
    return ok(data, request_id)
