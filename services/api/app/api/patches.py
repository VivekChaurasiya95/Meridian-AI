"""Patch routes (API.md §6.13): reads, diff bytes, scoped decisions."""

import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, DbSession, RequestId
from app.envelope import ApiError, ok
from app.schemas import PatchApprove, PatchReject
from app.services import patches as patch_service

router = APIRouter(tags=["patches"])


@router.get("/api/v1/investigations/{investigation_id}/patches")
def list_patches(
    investigation_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = patch_service.list_patches(session, user, investigation_id)
    return ok(data, request_id)


@router.get("/api/v1/patches/{patch_id}")
def get_patch(
    patch_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = patch_service.get_patch(session, user, patch_id)
    return ok(data, request_id)


@router.get("/api/v1/patches/{patch_id}/diff")
def get_patch_diff(
    patch_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = patch_service.get_diff(session, user, patch_id, request_id)
    return ok(data, request_id)


@router.post("/api/v1/patches/{patch_id}/approve", status_code=202)
def approve_patch(
    patch_id: uuid.UUID,
    payload: PatchApprove,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    try:
        snapshot_id = uuid.UUID(payload.base_snapshot_id)
    except (ValueError, TypeError, AttributeError):
        raise ApiError(422, "VALIDATION_ERROR", "The snapshot id is invalid.") from None
    data = patch_service.approve_patch(
        session, user, patch_id, payload.diff_sha256, snapshot_id, payload.note, request_id
    )
    return ok(data, request_id, status_code=202)


@router.post("/api/v1/patches/{patch_id}/reject")
def reject_patch(
    patch_id: uuid.UUID,
    payload: PatchReject,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = patch_service.reject_patch(session, user, patch_id, payload.reason, request_id)
    return ok(data, request_id)


@router.post("/api/v1/patches/{patch_id}/discard")
def discard_patch(
    patch_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = patch_service.discard_patch(session, user, patch_id, request_id)
    return ok(data, request_id)
