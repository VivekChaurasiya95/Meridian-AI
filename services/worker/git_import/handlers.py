"""Git import handlers for the trusted worker (design §3, §6)."""

import datetime as dt
import os
import shutil
import tempfile
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Project
from app.services import jobs as job_service
from app.services import snapshot_creation
from app.services.archive_security import SKIP_DIRS
from app.services.git_url_policy import (
    choose_pinned_address,
    parse_github_url,
    resolve_public_addresses,
    validate_branch_name,
    validate_commit_sha,
)
from app.services.inspection import inspect_tree, runtime_profile
from app.services.snapshot_creation import SnapshotProvenance
from git_import.runner import GitFetchError, fetch_and_checkout, ls_remote
from git_import.tree_validate import TreeLimits, validate_tree

SAMPLE = 8192


def _stage(
    session: Session,
    job_id: uuid.UUID,
    worker_id: str,
    key: str,
    status: str,
    **kw: object,
) -> None:
    job_service.record_stage(session, job_id, worker_id, key, status, **kw)  # type: ignore[arg-type]


def _parse_payload(job: dict) -> tuple[str, str | None, str | None]:
    payload = job.get("payload") or {}
    repo = parse_github_url(str(payload.get("repository_url", "")))
    branch = validate_branch_name(str(payload["branch"])) if payload.get("branch") else None
    sha = validate_commit_sha(str(payload["commit_sha"])) if payload.get("commit_sha") else None
    return repo.canonical_url, branch, sha


def handle_git_preview(session: Session, job: dict, worker_id: str) -> dict:
    job_id = uuid.UUID(job["id"])
    canonical, _branch, _sha = _parse_payload(job)
    _stage(session, job_id, worker_id, "validate", "running")
    _stage(session, job_id, worker_id, "validate", "completed")
    _stage(session, job_id, worker_id, "resolve", "running")
    pinned = choose_pinned_address(resolve_public_addresses("github.com"))
    _stage(session, job_id, worker_id, "resolve", "completed")
    _stage(session, job_id, worker_id, "preview", "running")
    settings = get_settings()
    with tempfile.TemporaryDirectory(prefix="meridian-git-preview-") as tmp:
        result = ls_remote(canonical, pinned, tmp, settings.git_import_timeout_seconds)
    _stage(
        session,
        job_id,
        worker_id,
        "preview",
        "completed",
        result_summary={"branches": len(result["branches"])},
    )
    return {"provider": "github", "canonical_url": canonical, **result}


def _previews(
    root: str, indexed: list, budget: int, cap: int
) -> dict[str, tuple[bool, str | None]]:
    out: dict[str, tuple[bool, str | None]] = {}
    stored = 0
    for entry in sorted(indexed, key=lambda e: e.path):
        content: str | None = None
        is_text = False
        if entry.size > 0:
            try:
                with open(os.path.join(root, *entry.path.split("/")), "rb") as handle:
                    sample = handle.read(SAMPLE + 1)
                if sample and b"\x00" not in sample:
                    sample.decode("utf-8")
                    is_text = True
            except (OSError, UnicodeDecodeError):
                is_text = False
        if is_text and entry.size <= cap and stored + entry.size <= budget:
            try:
                with open(os.path.join(root, *entry.path.split("/")), encoding="utf-8") as handle:
                    content = handle.read(cap + 1)[:cap]
                stored += entry.size
            except (OSError, UnicodeDecodeError):
                content = None
        out[entry.path] = (is_text, content)
    return out


def handle_git_import(session: Session, job: dict, worker_id: str) -> dict:
    job_id = uuid.UUID(job["id"])
    canonical, branch, pinned_sha = _parse_payload(job)
    payload = job.get("payload") or {}
    project_id = uuid.UUID(str(payload.get("project_id")))
    project = session.execute(select(Project).where(Project.id == project_id)).scalar_one_or_none()
    if project is None or str(project.workspace_id) != str(job.get("workspace_id")):
        raise GitFetchError("GIT_PROJECT_NOT_FOUND", "The project was not found.", False)
    if project.status != "active":
        raise GitFetchError("INVALID_STATE", "Only active projects accept imports.", False)
    settings = get_settings()
    _stage(session, job_id, worker_id, "validate", "running")
    _stage(session, job_id, worker_id, "validate", "completed")
    _stage(session, job_id, worker_id, "resolve", "running")
    pinned = choose_pinned_address(resolve_public_addresses("github.com"))
    _stage(session, job_id, worker_id, "resolve", "completed")
    ref = pinned_sha or branch or "HEAD"
    tmp = tempfile.mkdtemp(prefix="meridian-git-import-")
    try:
        _stage(session, job_id, worker_id, "fetch", "running")
        sha = fetch_and_checkout(
            canonical, ref, pinned, tmp, settings.git_import_timeout_seconds, pinned_sha
        )
        _stage(
            session,
            job_id,
            worker_id,
            "fetch",
            "completed",
            result_summary={"commit_sha": sha},
        )
        repo_dir = os.path.join(tmp, "repo")
        git_dir = os.path.join(repo_dir, ".git")
        if os.path.isdir(git_dir):
            shutil.rmtree(git_dir, ignore_errors=True)
        _stage(session, job_id, worker_id, "validate_tree", "running")
        tree = validate_tree(
            repo_dir,
            TreeLimits(
                max_files=settings.max_archive_files,
                max_bytes=settings.extracted_max_bytes,
                max_file_bytes=settings.git_import_max_file_bytes,
                max_depth=settings.max_archive_depth,
            ),
        )
        inspection = inspect_tree(repo_dir, set(SKIP_DIRS))
        _stage(
            session,
            job_id,
            worker_id,
            "validate_tree",
            "completed",
            result_summary={"files": len(tree.indexed)},
        )
        manifest = {
            "policy_version": "m3.1",
            "file_count": len(tree.indexed),
            "total_bytes": sum(e.size for e in tree.indexed),
            "languages": inspection.languages,
            "frameworks": inspection.frameworks,
            "package_manager": inspection.package_manager,
            "test_framework": inspection.test_framework,
            "build_system": inspection.build_system,
            "entry_points": inspection.entry_points,
            "skipped_dirs": tree.skipped_dirs,
            "secrets_excluded": tree.secrets_excluded,
            "warnings": sorted(
                set(inspection.warnings)
                | (
                    {f"{tree.secrets_excluded} secret file(s) excluded from indexing."}
                    if tree.secrets_excluded
                    else set()
                )
            ),
            "provenance": {
                "provider": "github",
                "canonical_url": canonical,
                "branch": branch,
                "commit_sha": sha,
                "imported_at": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
            },
        }
        previews = _previews(
            repo_dir,
            tree.indexed,
            settings.index_budget_bytes,
            settings.preview_max_bytes,
        )  # type: ignore[arg-type]
        _stage(session, job_id, worker_id, "snapshot", "running")
        snapshot = snapshot_creation.snapshot_from_tree(
            session,
            project=project,
            indexed=tree.indexed,
            source_dir=repo_dir,
            manifest=manifest,
            file_previews=previews,
            provenance=SnapshotProvenance(
                source_type="git_provider",
                source_ref=canonical,
                commit_sha=sha,
                branch_name=branch,
            ),
            project_runtime_profile=runtime_profile(inspection),
            store=snapshot_creation.default_store(),
        )
        _stage(
            session,
            job_id,
            worker_id,
            "snapshot",
            "completed",
            result_summary={"snapshot_id": str(snapshot.id)},
        )
        return {
            "snapshot_id": str(snapshot.id),
            "commit_sha": sha,
            "branch": branch,
            "tree_digest": snapshot.tree_digest,
            "file_count": len(tree.indexed),
            "total_bytes": sum(e.size for e in tree.indexed),
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


__all__ = ["handle_git_import", "handle_git_preview"]
