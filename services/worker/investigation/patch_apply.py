"""Patch application (M8, worker side): strict apply plus lineage snapshot.

Materializes the approved base snapshot, applies the validated diff
with zero fuzz, and persists the result as a new ``patched_tree``
snapshot so post-patch verification reuses the exact same machinery
as every other run. Application is worker-side file surgery under
traversal guards — never a shell, never a push.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import tempfile
import uuid
from typing import Any

from app.envelope import ApiError
from app.services import inspection as inspection_service
from app.services import investigations as investigation_service
from app.services import snapshot_creation as snapshot_creation_service
from app.services import storage as storage_service
from app.services.archive_security import SKIP_DIRS, ValidatedEntry, is_secret_file
from app.services.patch_diff import apply_unified_diff, parse_unified_diff
from investigation import InvestigationAbort, InvestigationFailure

logger = logging.getLogger("meridian.investigation.apply")

SAMPLE_BYTES = 8192


def _sniff_text(path: str) -> bool:
    try:
        with open(path, "rb") as handle:
            sample = handle.read(SAMPLE_BYTES + 1)
        if not sample or b"\x00" in sample:
            return False
        sample.decode("utf-8")
        return True
    except (OSError, UnicodeDecodeError):
        return False


def _under_skipped_dir(path: str) -> str | None:
    head = path.split("/", 1)[0]
    return head if head in SKIP_DIRS else None


def apply_patch_to_snapshot(
    session_factory: Any,
    *,
    job_id: uuid.UUID,
    worker_id: str,
    investigation_id: uuid.UUID,
    project_id: uuid.UUID,
    workspace_id: uuid.UUID,
    base_snapshot_id: uuid.UUID,
    patch_id: uuid.UUID,
    diff_text: str,
    store: Any = None,
) -> dict:
    """Apply an approved diff; return the new snapshot summary.

    Raises InvestigationFailure on conflicts (stable, non-retryable)
    or storage faults (retryable), InvestigationAbort when superseded.
    """
    try:
        files = parse_unified_diff(diff_text)
    except ApiError as exc:
        raise InvestigationFailure(exc.code, exc.message, False) from exc
    with session_factory() as session:
        try:
            from app.models import Project

            investigation_service.require_job_ownership(
                session, job_id, worker_id, investigation_id
            )
            project = session.get(Project, project_id)
            if project is None or project.workspace_id != workspace_id:
                raise ApiError(404, "RESOURCE_NOT_FOUND", "The project was not found.")
        except ApiError as exc:
            if exc.code in ("LEASE_LOST", "JOB_SUPERSEDED"):
                raise InvestigationAbort() from exc
            raise InvestigationFailure(exc.code, exc.message, False) from exc
    workdir = tempfile.mkdtemp(prefix="meridian-patch-apply-")
    try:
        with session_factory() as session:
            try:
                materialized = storage_service.materialize_for_workspace(
                    session, workspace_id, base_snapshot_id, workdir, store=store
                )
            except ApiError as exc:
                raise InvestigationFailure(exc.code, exc.message, False) from exc
        try:
            written = apply_unified_diff(workdir, files)
        except ApiError as exc:
            raise InvestigationFailure(exc.code, exc.message, False) from exc
        with session_factory() as session:
            try:
                snapshot = _snapshot_patched_tree(
                    session, project=project, source_dir=workdir,
                    base_snapshot_id=base_snapshot_id, patch_id=patch_id,
                    base_digest=materialized["tree_digest"], store=store,
                )
            except ApiError as exc:
                if exc.code in ("LEASE_LOST", "JOB_SUPERSEDED"):
                    raise InvestigationAbort() from exc
                raise InvestigationFailure(
                    exc.code, exc.message, exc.status_code in (429, 503)
                ) from exc
        return {"snapshot_id": str(snapshot.id), "written": written}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _snapshot_patched_tree(
    session: Any, *, project: Any, source_dir: str, base_snapshot_id: uuid.UUID,
    patch_id: uuid.UUID, base_digest: str, store: Any,
):  # type: ignore[no-untyped-def]
    """Index a patched tree exactly like the upload pipeline does."""
    from app.config import get_settings

    settings = get_settings()
    indexed: list[ValidatedEntry] = []
    secrets: list[ValidatedEntry] = []
    skipped_dirs: dict[str, int] = {}
    secrets_excluded = 0
    for root, dirs, names in os.walk(source_dir):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(names):
            full = os.path.join(root, name)
            if os.path.islink(full) or not os.path.isfile(full):
                continue
            rel = os.path.relpath(full, source_dir).replace(os.sep, "/")
            skipped = _under_skipped_dir(rel)
            if skipped is not None:
                skipped_dirs[skipped] = skipped_dirs.get(skipped, 0) + 1
                continue
            digest = hashlib.sha256()
            size = 0
            with open(full, "rb") as handle:
                for chunk in iter(lambda: handle.read(65536), b""):
                    digest.update(chunk)
                    size += len(chunk)
            entry = ValidatedEntry(path=rel, size=size, sha256=digest.hexdigest())
            if is_secret_file(name):
                secrets_excluded += 1
                secrets.append(entry)
                continue
            indexed.append(entry)
    inspection = inspection_service.inspect_tree(source_dir, set(SKIP_DIRS))
    manifest = {
        "policy_version": "m8.1",
        "file_count": len(indexed),
        "total_bytes": sum(entry.size for entry in indexed),
        "base_snapshot_id": str(base_snapshot_id),
        "base_tree_digest": base_digest,
        "patch_id": str(patch_id),
        "languages": inspection.languages,
        "frameworks": inspection.frameworks,
        "package_manager": inspection.package_manager,
        "test_framework": inspection.test_framework,
        "build_system": inspection.build_system,
        "entry_points": inspection.entry_points,
        "skipped_dirs": skipped_dirs,
        "secrets_excluded": secrets_excluded,
        "warnings": sorted(
            set(inspection.warnings)
            | (
                {f"{secrets_excluded} secret file(s) excluded from indexing."}
                if secrets_excluded
                else set()
            )
        ),
    }
    file_previews: dict[str, tuple[bool, str | None]] = {}
    budget = settings.index_budget_bytes
    preview_cap = settings.preview_max_bytes
    stored = 0
    for entry in sorted(indexed, key=lambda e: e.path):
        full = os.path.join(source_dir, entry.path)
        is_text = entry.size > 0 and _sniff_text(full)
        content: str | None = None
        if is_text and entry.size <= preview_cap and stored + entry.size <= budget:
            try:
                with open(full, encoding="utf-8") as handle:
                    content = handle.read(preview_cap + 1)[:preview_cap]
                stored += entry.size
            except (OSError, UnicodeDecodeError):
                content = None
        file_previews[entry.path] = (is_text, content)
    return snapshot_creation_service.snapshot_from_tree(
        session,
        project=project,
        indexed=indexed,
        source_dir=source_dir,
        manifest=manifest,
        file_previews=file_previews,
        provenance=snapshot_creation_service.SnapshotProvenance(
            source_type="patched_tree", source_ref=f"patch:{patch_id}"
        ),
        project_runtime_profile=inspection_service.runtime_profile(inspection),
        store=store,
        security_extra=secrets,
    )
