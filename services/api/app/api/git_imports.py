"""Git import routes: grammar validation + create-and-enqueue.

The API never runs git and never resolves DNS here. Validation is pure
grammar; fetching is exclusively the trusted worker's git_import job.
"""

import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, DbSession, RequestId
from app.config import get_settings
from app.envelope import ApiError, ok
from app.schemas import GitImportCreate, GitValidateRequest
from app.services import jobs as job_service
from app.services import projects as project_service
from app.services.git_url_policy import (
    GitUrlError,
    parse_github_url,
    validate_branch_name,
    validate_commit_sha,
)

router = APIRouter(tags=["git-imports"])


def _parse(
    payload_url: str, branch: str | None, commit_sha: str | None
) -> tuple[str, str | None, str | None]:
    try:
        repo = parse_github_url(payload_url)
        branch_v = validate_branch_name(branch) if branch else None
        sha_v = validate_commit_sha(commit_sha) if commit_sha else None
    except GitUrlError as exc:
        raise ApiError(422, exc.code, exc.message) from exc
    return repo.canonical_url, branch_v, sha_v


@router.post("/api/v1/git/validate")
def validate_git(
    payload: GitValidateRequest, user: CurrentUser, request_id: RequestId
) -> JSONResponse:
    canonical, _, _ = _parse(payload.repository_url, None, None)
    repo = parse_github_url(canonical)
    return ok(
        {
            "provider": repo.provider,
            "owner": repo.owner,
            "repo": repo.repo,
            "canonical_url": repo.canonical_url,
        },
        request_id,
    )


@router.post("/api/v1/workspaces/{workspace_id}/git-imports", status_code=201)
def create_git_import(
    workspace_id: uuid.UUID,
    payload: GitImportCreate,
    session: DbSession,
    user: CurrentUser,
    request_id: RequestId,
) -> JSONResponse:
    canonical, branch, sha = _parse(payload.repository_url, payload.branch, payload.commit_sha)
    project, role = project_service.create_git_project_record(
        session,
        user,
        workspace_id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        canonical_url=canonical,
        branch=branch,
    )
    job_payload: dict = {"project_id": str(project.id), "repository_url": canonical}
    if branch:
        job_payload["branch"] = branch
    if sha:
        job_payload["commit_sha"] = sha
    job, created = job_service.submit_job(
        session,
        user,
        workspace_id,
        "git_import",
        job_payload,
        payload.idempotency_key,
        0,
        get_settings().git_import_max_attempts,
    )
    data = {"project": project_service.serialize_project(project, role), "job": job}
    return ok(data, request_id, status_code=201 if created else 200)
