"""Project routes (API.md §6.5-§6.6). Thin handlers over domain services.

M3 serves single-shot multipart uploads on ``source-uploads``: the
session-based resumable flow from API.md §6.6 is deferred (D37) because
the 25 MB cap makes it unnecessary, and faking upload sessions would be
worse than a documented subset.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Query, UploadFile
from fastapi.responses import JSONResponse, Response

from app.api.deps import CurrentUser, DbSession, RequestId, upload_limiter
from app.config import get_settings
from app.envelope import ApiError, ok, paged
from app.schemas import ProjectCreate, ProjectUpdate
from app.services import ingestion as ingestion_service
from app.services import projects as project_service
from app.services import storage as storage_service

router = APIRouter(tags=["projects"])

MAX_FILENAME_LENGTH = 255


@router.post("/api/v1/workspaces/{workspace_id}/projects", status_code=201)
def create_project(
    workspace_id: uuid.UUID,
    payload: ProjectCreate,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = project_service.create_project(session, user, workspace_id, payload)
    return ok(data, request_id, status_code=201)


@router.get("/api/v1/workspaces/{workspace_id}/projects")
def list_projects(
    workspace_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=512),
    status: str | None = Query(default=None, max_length=32),
    q: str | None = Query(default=None, max_length=200),
    sort: str = Query(default="updated", max_length=32),
) -> JSONResponse:
    settings = get_settings()
    effective_limit = min(limit or settings.page_default_limit, settings.page_max_limit)
    items, next_cursor = project_service.list_projects(
        session, user, workspace_id, effective_limit, cursor, status, q, sort
    )
    return paged(items, effective_limit, next_cursor, request_id)


@router.get("/api/v1/workspaces/{workspace_id}/projects/summary")
def projects_summary(
    workspace_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = project_service.projects_summary(session, user, workspace_id)
    return ok(data, request_id)


@router.get("/api/v1/projects/{project_id}")
def get_project(
    project_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = project_service.get_project(session, user, project_id)
    return ok(data, request_id)


@router.patch("/api/v1/projects/{project_id}")
def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = project_service.update_project(session, user, project_id, payload)
    return ok(data, request_id)


@router.post("/api/v1/projects/{project_id}/archive")
def archive_project(
    project_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = project_service.archive_project(session, user, project_id)
    return ok(data, request_id)


@router.post("/api/v1/projects/{project_id}/unarchive")
def unarchive_project(
    project_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = project_service.unarchive_project(session, user, project_id)
    return ok(data, request_id)


@router.delete("/api/v1/projects/{project_id}", status_code=204)
def delete_project(
    project_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> Response:
    project_service.delete_project(session, user, project_id)
    return Response(status_code=204, headers={"X-Request-ID": request_id})


@router.post("/api/v1/projects/{project_id}/source-uploads", status_code=201)
async def upload_source(
    project_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
    file: Annotated[UploadFile, File(...)],
) -> JSONResponse:
    settings = get_settings()
    filename = (file.filename or "").strip()[:MAX_FILENAME_LENGTH]
    if not filename:
        raise ApiError(422, "VALIDATION_ERROR", "An archive file is required.")
    # Stream with a one-byte tripwire so oversized bodies fail fast
    # instead of buffering unboundedly into memory.
    cap = settings.upload_max_bytes + 1
    chunks: list[bytes] = []
    received = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        received += len(chunk)
        if received > cap:
            raise ApiError(
                413,
                "ARCHIVE_TOO_LARGE",
                f"The archive exceeds the {settings.upload_max_mb} MB upload limit.",
            )
        chunks.append(chunk)
    data = b"".join(chunks)
    result = ingestion_service.upload_source(
        session, user, project_id, filename, data, upload_limiter()
    )
    return ok(result, request_id, status_code=201)


@router.get("/api/v1/projects/{project_id}/snapshots")
def list_snapshots(
    project_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
    limit: int = Query(default=25, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=512),
) -> JSONResponse:
    settings = get_settings()
    effective_limit = min(limit or settings.page_default_limit, settings.page_max_limit)
    items, next_cursor = project_service.list_snapshots(
        session, user, project_id, effective_limit, cursor
    )
    return paged(items, effective_limit, next_cursor, request_id)


@router.get("/api/v1/snapshots/{snapshot_id}")
def get_snapshot(
    snapshot_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = project_service.get_snapshot(session, user, snapshot_id)
    return ok(data, request_id)


@router.post("/api/v1/snapshots/{snapshot_id}/verify")
def verify_snapshot(
    snapshot_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    data = storage_service.verify_snapshot(session, user, snapshot_id)
    return ok(data, request_id)


@router.get("/api/v1/snapshots/{snapshot_id}/tree")
def get_tree(
    snapshot_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
    prefix: str = Query(default="", max_length=1024),
    limit: int = Query(default=500, ge=1, le=2000),
    offset: int = Query(default=0, ge=0, le=100000),
) -> JSONResponse:
    data = project_service.get_tree(session, user, snapshot_id, prefix, limit, offset)
    return ok(data, request_id)


@router.get("/api/v1/snapshots/{snapshot_id}/file")
def get_file(
    snapshot_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
    path: str = Query(max_length=1024),
) -> JSONResponse:
    data = project_service.get_file(session, user, snapshot_id, path)
    return ok(data, request_id)
