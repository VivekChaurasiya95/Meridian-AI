"""Source-upload ingestion: validate, inspect, store, snapshot (M3/M5.1).

Single-shot synchronous pipeline (docs/DECISIONS.md D37): the archive is
validated, extracted to an isolated temporary directory, statically
inspected, packed into a deterministic tarball, uploaded to private
object storage, and persisted as an immutable snapshot — all inside the
request, under the configured caps. There is no M4 job queue yet, so
long-running background processing is deferred, not faked: the endpoint
returns only after backend work completes.

The raw archive bytes are never retained: after inspection the temporary
directories are removed. The snapshot keeps metadata, the file index,
small text previews, and a content-addressed object in MinIO — the
immutable source context investigations need.
"""

import io
import logging
import shutil
import tempfile
import uuid
import zipfile

from sqlalchemy.orm import Session

from app.config import get_settings
from app.envelope import ApiError, access_denied
from app.models import User
from app.security import SlidingWindowLimiter
from app.services import projects as project_service
from app.services import snapshot_creation
from app.services.archive_security import (
    SKIP_DIRS,
    ArchiveLimits,
    ArchiveRejected,
    ValidatedEntry,
    extract_archive,
    is_secret_file,
    validate_archive,
)
from app.services.inspection import inspect_tree, runtime_profile
from app.services.object_store import ObjectStore
from app.services.snapshot_creation import SnapshotProvenance

logger = logging.getLogger("meridian.ingestion")


def _default_store() -> ObjectStore:
    return snapshot_creation.default_store()


# Route-level file-type gate (415 before any bytes are trusted).
ALLOWED_ARCHIVE_SUFFIX = ".zip"

SAMPLE_BYTES = 8192


def _limits() -> ArchiveLimits:
    settings = get_settings()
    return ArchiveLimits(
        max_upload_bytes=settings.upload_max_bytes,
        max_extracted_bytes=settings.extracted_max_bytes,
        max_files=settings.max_archive_files,
        max_depth=settings.max_archive_depth,
        max_compression_ratio=settings.max_compression_ratio,
    )


def _rejection_to_error(exc: ArchiveRejected) -> ApiError:
    status = 422
    if exc.code == "ARCHIVE_TOO_LARGE":
        status = 413
    elif exc.code == "ARCHIVE_NOT_ZIP":
        status = 415
    message = exc.message
    if exc.entry:
        message = f"{message} Entry: {exc.entry}"
    return ApiError(status, exc.code, message)


def _under_skipped_dir(path: str) -> str | None:
    """Return the skipped directory name when a parent is skipped, else None.

    Only parent components count: a root-level *file* that happens to share
    a skipped name (e.g. a file literally named ``build``) is still indexed.
    """
    parts = path.split("/")
    for part in parts[:-1]:
        if part in SKIP_DIRS:
            return part
    return None


def _sniff_text(data: zipfile.ZipFile, path: str) -> bool:
    """Cheap text heuristic over the first bytes (null byte / UTF-8)."""
    try:
        with data.open(path) as handle:
            sample = handle.read(SAMPLE_BYTES + 1)
        if not sample or b"\x00" in sample:
            return False
        sample.decode("utf-8")
        return True
    except (UnicodeDecodeError, KeyError, RuntimeError, zipfile.BadZipFile):
        return False


def upload_source(
    session: Session,
    user: User,
    project_id: uuid.UUID,
    filename: str,
    data: bytes,
    limiter: SlidingWindowLimiter,
    store: ObjectStore | None = None,
) -> dict:
    """Validate an archive, store its content, and persist an immutable snapshot.

    Nothing is reported successful until both the object upload and the
    database persistence have completed. ``store`` is injectable for
    tests; production always uses the configured MinIO bucket.
    """
    project, _role = project_service.get_project_record(session, user, project_id)
    workspace_role = project_service.get_membership_role(session, user, project.workspace_id)
    if workspace_role not in project_service.CONTRIBUTOR_ROLES:
        raise access_denied()
    # Per-user rate cap (M4 hardening): every accepted upload consumes
    # quota whether it validates or not, bounding synchronous API work.
    rate_key = f"upload:{user.id}:{project.workspace_id}"
    if not limiter.allowed(rate_key):
        raise ApiError(429, "RATE_LIMITED", "Too many uploads. Try again later.")
    limiter.register_failure(rate_key)
    if project.status != "active":
        raise ApiError(409, "INVALID_STATE", "Only active projects accept new source uploads.")
    if not filename.lower().endswith(ALLOWED_ARCHIVE_SUFFIX):
        raise ApiError(415, "UNSUPPORTED_MEDIA", "Only .zip archives are accepted.")

    limits = _limits()
    try:
        report = validate_archive(data, limits)
    except ArchiveRejected as exc:
        raise _rejection_to_error(exc) from exc

    settings = get_settings()
    active_store = store or _default_store()
    workdir = tempfile.mkdtemp(prefix="meridian-upload-")
    try:
        try:
            extracted = extract_archive(data, report.entries, workdir)
        except ArchiveRejected as exc:
            raise _rejection_to_error(exc) from exc
        inspection = inspect_tree(workdir, set(SKIP_DIRS))

        indexed: list[ValidatedEntry] = []
        skipped_dirs: dict[str, int] = {}
        secrets_excluded = 0
        for entry in extracted:
            skipped = _under_skipped_dir(entry.path)
            if skipped is not None:
                skipped_dirs[skipped] = skipped_dirs.get(skipped, 0) + 1
                continue
            if is_secret_file(entry.path.rsplit("/", 1)[-1]):
                secrets_excluded += 1
                continue
            indexed.append(entry)

        manifest = {
            "policy_version": "m3.1",
            "file_count": len(indexed),
            "total_bytes": sum(entry.size for entry in indexed),
            "archive_files": len(report.entries),
            "archive_uncompressed_bytes": report.total_uncompressed,
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

        # Text previews from the in-memory bytes under the index budget.
        file_previews: dict[str, tuple[bool, str | None]] = {}
        budget = settings.index_budget_bytes
        preview_cap = settings.preview_max_bytes
        stored = 0
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for entry in sorted(indexed, key=lambda e: e.path):
                content: str | None = None
                is_text = entry.size > 0 and _sniff_text(archive, entry.path)
                if is_text and entry.size <= preview_cap and stored + entry.size <= budget:
                    try:
                        with archive.open(entry.path) as handle:
                            content = handle.read(entry.size + 1).decode("utf-8")[:preview_cap]
                        stored += entry.size
                    except (UnicodeDecodeError, KeyError, RuntimeError, zipfile.BadZipFile):
                        content = None
                file_previews[entry.path] = (is_text, content)

        snapshot = snapshot_creation.snapshot_from_tree(
            session,
            project=project,
            indexed=indexed,
            source_dir=workdir,
            manifest=manifest,
            file_previews=file_previews,
            provenance=SnapshotProvenance(
                source_type="uploaded_archive",
                source_ref=filename,
                archive_name=filename,
                archive_size=len(data),
                archive_sha256=report.archive_sha256,
            ),
            project_runtime_profile=runtime_profile(inspection),
            store=active_store,
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    return {
        "snapshot": project_service.serialize_snapshot_summary(snapshot),
        "inspection": {
            "stages": [
                {"key": "received", "status": "completed"},
                {"key": "validated", "status": "completed"},
                {"key": "extracted", "status": "completed"},
                {"key": "inspected", "status": "completed"},
                {"key": "stored", "status": "completed"},
                {"key": "snapshot_created", "status": "completed"},
            ],
            "manifest": manifest,
        },
    }
