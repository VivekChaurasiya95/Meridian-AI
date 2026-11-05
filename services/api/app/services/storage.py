"""Snapshot content retrieval and integrity (M5.1).

Trusted-backend-only service for the future M5 orchestrator: it
materializes an immutable snapshot into a caller-provided empty
directory with full hash verification. It never executes repository
code, never writes outside the given directory, and never exposes
object keys or credentials — callers only pass snapshot IDs.

Companion to ingestion: ingestion stores, this module retrieves.
"""

import hashlib
import logging
import os
import posixpath
import shutil
import tempfile
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.envelope import ApiError
from app.models import RepositorySnapshot, SnapshotFile, User
from app.services import projects as project_service
from app.services.archive_security import (
    SKIP_DIRS,
    ValidatedEntry,
    compute_tree_digest,
    is_secret_file,
)
from app.services.object_store import MinioObjectStore, ObjectStore, StorageError, sha256_file

logger = logging.getLogger("meridian.storage")


def get_store() -> ObjectStore:
    """Build the configured store (MinIO in every real deployment)."""
    settings = get_settings()
    return MinioObjectStore(
        endpoint_url=settings.s3_endpoint_url,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        region=settings.s3_region,
    )


def _key_digest(storage_key: str) -> str:
    """Parse the content digest back out of a server-generated key."""
    name = storage_key.rsplit("/", 1)[-1]
    digest = name[:-4] if name.endswith(".tar") else ""
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ApiError(422, "INTEGRITY_FAILED", "The snapshot storage key is malformed.")
    return digest


def _mark_integrity_failed(
    session: Session, snapshot: RepositorySnapshot, code: str, message: str
) -> None:
    # Snapshots are immutable: no updated_at column exists by design.
    snapshot.storage_status = "integrity_failed"
    snapshot.error_code = code
    snapshot.error_message = message
    session.commit()


def download_snapshot_object(
    session: Session,
    user: User,
    snapshot_id: uuid.UUID,
    store: ObjectStore | None = None,
) -> tuple[RepositorySnapshot, str, str]:
    """Download a READY snapshot object to a temp file.

    Returns (snapshot, temp_path, expected_digest). Verifies the byte
    digest; on mismatch the snapshot is marked INTEGRITY_FAILED.
    Caller removes the temp directory.
    """
    snapshot, _role = project_service.get_snapshot_record(session, user, snapshot_id)
    tmp_path, expected = _download_object(session, snapshot, store)
    return snapshot, tmp_path, expected


def download_workspace_object(
    session: Session,
    workspace_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    store: ObjectStore | None = None,
) -> tuple[RepositorySnapshot, str, str]:
    """Workspace-scoped download for the trusted worker (no user session).

    The snapshot's project must belong to the given workspace; anything
    else is a 404, exactly like member access. Digest verification and
    failure marking are identical to member retrieval.
    """
    snapshot = project_service.get_workspace_snapshot(session, workspace_id, snapshot_id)
    tmp_path, expected = _download_object(session, snapshot, store)
    return snapshot, tmp_path, expected


def _download_object(
    session: Session,
    snapshot: RepositorySnapshot,
    store: ObjectStore | None,
) -> tuple[str, str]:
    """Download + digest-verify an authorized snapshot row.

    Returns (temp_path, expected_digest). Marks INTEGRITY_FAILED on a
    missing or mismatched object. Caller removes the temp directory.
    """
    if snapshot.storage_status != "ready" or not snapshot.storage_key:
        raise ApiError(409, "SNAPSHOT_NOT_READY", "The snapshot content is not stored.")
    active_store = store or get_store()
    bucket = get_settings().s3_repositories_bucket
    workdir = tempfile.mkdtemp(prefix="meridian-retrieve-")
    tmp_path = os.path.join(workdir, "snapshot.tar")
    try:
        active_store.download_file(bucket, snapshot.storage_key, tmp_path)
    except StorageError as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        if exc.code == "OBJECT_NOT_FOUND":
            _mark_integrity_failed(
                session, snapshot, "OBJECT_NOT_FOUND", "The stored object is missing."
            )
            raise ApiError(409, "SNAPSHOT_NOT_READY", "The stored object is missing.") from exc
        raise ApiError(503, exc.code, exc.message) from exc
    expected = _key_digest(snapshot.storage_key)
    actual = sha256_file(tmp_path)
    if actual != expected:
        shutil.rmtree(workdir, ignore_errors=True)
        _mark_integrity_failed(
            session, snapshot, "DIGEST_MISMATCH", "Stored bytes differ from the recorded digest."
        )
        raise ApiError(422, "INTEGRITY_FAILED", "Stored bytes differ from the recorded digest.")
    return tmp_path, expected


def verify_snapshot(
    session: Session, user: User, snapshot_id: uuid.UUID, store: ObjectStore | None = None
) -> dict:
    """Re-download a READY snapshot and confirm its digest (Phase 10 op).

    Updates storage_verified_at on success; marks INTEGRITY_FAILED on
    mismatch. Any workspace member may trigger verification.
    """
    snapshot, tmp_path, _expected = download_snapshot_object(session, user, snapshot_id, store)
    workdir = os.path.dirname(tmp_path)
    try:
        snapshot.storage_verified_at = session.execute(select(func.now())).scalar_one()
        session.commit()
        session.refresh(snapshot)
        logger.info("snapshot verified snapshot_id=%s", snapshot.id)
        return {
            "snapshot_id": str(snapshot.id),
            "ok": True,
            "tree_digest": snapshot.tree_digest,
            "verified_at": snapshot.storage_verified_at.isoformat().replace("+00:00", "Z"),
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _validate_member(name: str) -> str:
    """Normalize one tar member name; reject anything unsafe."""
    if not name or "\x00" in name or "\\" in name:
        raise ApiError(422, "INTEGRITY_FAILED", "The stored archive has an unsafe entry.")
    if name.startswith("/") or (len(name) > 1 and name[1] == ":"):
        raise ApiError(422, "INTEGRITY_FAILED", "The stored archive has an absolute path.")
    normalized = posixpath.normpath(name)
    parts = normalized.split("/")
    if normalized in ("", ".") or any(part in ("", ".", "..") for part in parts):
        raise ApiError(422, "INTEGRITY_FAILED", "The stored archive escapes its root.")
    return normalized


def materialize_snapshot(
    session: Session,
    user: User,
    snapshot_id: uuid.UUID,
    dest_dir: str,
    store: ObjectStore | None = None,
) -> dict:
    """Reconstruct a READY snapshot into ``dest_dir`` (must exist, empty).

    Verifies object digest, per-file hashes, set equality against the
    index, and the snapshot tree digest. Raises on any deviation and
    marks the snapshot INTEGRITY_FAILED. Never executes file contents.
    """
    snapshot, tmp_path, _expected = download_snapshot_object(session, user, snapshot_id, store)
    workdir = os.path.dirname(tmp_path)
    return _materialize_extracted(session, snapshot, tmp_path, dest_dir, workdir)


def materialize_for_workspace(
    session: Session,
    workspace_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    dest_dir: str,
    store: ObjectStore | None = None,
) -> dict:
    """Workspace-scoped materialization for the trusted worker process.

    Authorization is workspace equality (the snapshot's project must
    belong to the job's workspace), re-checked at execution time — the
    worker has no user session. Every byte-level check is identical to
    member retrieval; only the authorization root differs.
    """
    snapshot, tmp_path, _expected = download_workspace_object(
        session, workspace_id, snapshot_id, store
    )
    workdir = os.path.dirname(tmp_path)
    return _materialize_extracted(session, snapshot, tmp_path, dest_dir, workdir)


def _mark_security_failed(
    session: Session, snapshot: RepositorySnapshot, status: str, code: str, message: str
) -> None:
    snapshot.security_scan_status = status
    snapshot.error_code = code
    snapshot.error_message = message
    session.commit()


def download_security_object(
    session: Session,
    workspace_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    store: ObjectStore | None = None,
) -> tuple[RepositorySnapshot, str, str]:
    """Workspace-scoped security-artifact download for the trusted worker.

    No member variant exists by design: the artifact carries secret
    file contents, so only the preflight orchestrator may fetch it.
    Digest verification and failure marking mirror member retrieval,
    but mark the security status, never the main storage status.
    """
    snapshot = project_service.get_workspace_snapshot(session, workspace_id, snapshot_id)
    if snapshot.security_scan_status != "ready" or not snapshot.security_storage_key:
        raise ApiError(409, "SNAPSHOT_NOT_READY", "The security scan input is not stored.")
    if not snapshot.security_content_digest or snapshot.security_storage_bytes is None:
        raise ApiError(409, "SNAPSHOT_NOT_READY", "The security scan input record is incomplete.")
    active_store = store or get_store()
    bucket = get_settings().s3_repositories_bucket
    workdir = tempfile.mkdtemp(prefix="meridian-retrieve-")
    tmp_path = os.path.join(workdir, "security.tar")
    try:
        active_store.download_file(bucket, snapshot.security_storage_key, tmp_path)
    except StorageError as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        if exc.code == "OBJECT_NOT_FOUND":
            _mark_security_failed(
                session, snapshot, "integrity_failed",
                "OBJECT_NOT_FOUND", "The stored security object is missing.",
            )
            raise ApiError(
                409, "SNAPSHOT_NOT_READY", "The stored security object is missing."
            ) from exc
        raise ApiError(503, exc.code, exc.message) from exc
    expected = _key_digest(snapshot.security_storage_key)
    if expected != snapshot.security_content_digest:
        shutil.rmtree(workdir, ignore_errors=True)
        _mark_security_failed(
            session, snapshot, "integrity_failed",
            "DIGEST_MISMATCH", "The security key disagrees with the recorded digest.",
        )
        raise ApiError(
            422, "INTEGRITY_FAILED", "The security key disagrees with the recorded digest."
        )
    actual = sha256_file(tmp_path)
    if actual != expected or os.path.getsize(tmp_path) != snapshot.security_storage_bytes:
        shutil.rmtree(workdir, ignore_errors=True)
        _mark_security_failed(
            session, snapshot, "integrity_failed",
            "DIGEST_MISMATCH", "Stored security bytes differ from the recorded digest.",
        )
        raise ApiError(
            422, "INTEGRITY_FAILED", "Stored security bytes differ from the recorded digest."
        )
    return snapshot, tmp_path, expected


def materialize_security_input_for_workspace(
    session: Session,
    workspace_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    dest_dir: str,
    store: ObjectStore | None = None,
) -> dict:
    """Materialize the verified security scan input for the worker (D62).

    Indexed members must match the stored file rows exactly (hashes and
    tree digest); every extra member must satisfy the pure archive
    policy for secret files (secret basename, outside skipped dirs).
    Secret contents are written to the caller's directory with the same
    restrictive modes as member retrieval — the caller owns cleanup.
    """
    import tarfile

    snapshot, tmp_path, _expected = download_security_object(
        session, workspace_id, snapshot_id, store
    )
    workdir = os.path.dirname(tmp_path)
    try:
        if not os.path.isdir(dest_dir):
            raise ApiError(422, "VALIDATION_ERROR", "The destination is not a directory.")
        if os.listdir(dest_dir):
            raise ApiError(422, "VALIDATION_ERROR", "The destination directory is not empty.")
        settings = get_settings()
        max_files = settings.max_archive_files
        max_bytes = settings.extracted_max_bytes
        rows = list(
            session.execute(
                select(SnapshotFile).where(SnapshotFile.snapshot_id == snapshot.id)
            ).scalars()
        )
        expected_hashes = {row.path: row.sha256 for row in rows}
        seen: dict[str, str] = {}
        total = 0
        try:
            with tarfile.open(tmp_path, "r") as probe:
                members = probe.getmembers()
        except (tarfile.TarError, EOFError, OSError):
            _mark_security_failed(
                session, snapshot, "integrity_failed",
                "TARBALL_CORRUPT", "The stored security object is not a valid archive.",
            )
            raise ApiError(
                422, "INTEGRITY_FAILED", "The stored security object is not a valid archive."
            ) from None
        with tarfile.open(tmp_path, "r") as tar:
            files = [member for member in members if not member.isdir()]
            if len(files) > max_files:
                raise ApiError(422, "INTEGRITY_FAILED", "The stored security archive is too large.")
            for member in files:
                if not member.isfile():
                    raise ApiError(
                        422, "INTEGRITY_FAILED", "The stored security archive has a special file."
                    )
                rel = _validate_member(member.name)
                if rel in seen:
                    raise ApiError(
                        422, "INTEGRITY_FAILED", "The stored security archive has duplicate paths."
                    )
                if member.size > max_bytes or total + member.size > max_bytes:
                    raise ApiError(
                        422, "INTEGRITY_FAILED", "The stored security archive is too large."
                    )
                target = os.path.join(dest_dir, *rel.split("/"))
                parent = os.path.dirname(target)
                os.makedirs(parent, mode=0o700, exist_ok=True)
                extracted = tar.extractfile(member)
                if extracted is None:
                    raise ApiError(
                        422, "INTEGRITY_FAILED", "A stored security file cannot be read."
                    )
                digest = hashlib.sha256()
                written = 0
                with open(target, "wb") as out:
                    while True:
                        chunk = extracted.read(1024 * 1024)
                        if not chunk:
                            break
                        digest.update(chunk)
                        out.write(chunk)
                        written += len(chunk)
                os.chmod(target, 0o600)
                if written != member.size:
                    raise ApiError(422, "INTEGRITY_FAILED", "A stored security file changed size.")
                seen[rel] = digest.hexdigest()
                total += written
        indexed_paths = set(expected_hashes)
        extra_paths = sorted(set(seen) - indexed_paths)
        missing = sorted(indexed_paths - set(seen))
        if missing:
            raise ApiError(
                422, "INTEGRITY_FAILED", f"Security file set mismatch: missing {len(missing)}."
            )
        for rel in extra_paths:
            basename = rel.rsplit("/", 1)[-1]
            under_skipped = any(part in SKIP_DIRS for part in rel.split("/")[:-1])
            if under_skipped or not is_secret_file(basename):
                raise ApiError(
                    422, "INTEGRITY_FAILED",
                    "The stored security archive has an unexpected entry.",
                )
        for rel in indexed_paths:
            if seen[rel] != expected_hashes[rel]:
                raise ApiError(422, "INTEGRITY_FAILED", f"Hash mismatch for file: {rel}")
        authoritative = sorted(rows, key=lambda row: row.path)
        recomputed = compute_tree_digest(
            [
                ValidatedEntry(path=row.path, size=row.size, sha256=row.sha256)
                for row in authoritative
            ]
        )
        if recomputed != snapshot.tree_digest:
            raise ApiError(422, "INTEGRITY_FAILED", "Snapshot digest mismatch.")
        return {
            "snapshot_id": str(snapshot.id),
            "files": len(seen),
            "total_bytes": total,
            "secret_files": len(extra_paths),
            "tree_digest": snapshot.tree_digest,
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _materialize_extracted(
    session: Session,
    snapshot: RepositorySnapshot,
    tmp_path: str,
    dest_dir: str,
    workdir: str,
) -> dict:
    """Shared extraction core: digest-verified tarball becomes a verified tree."""
    import tarfile

    try:
        if not os.path.isdir(dest_dir):
            raise ApiError(422, "VALIDATION_ERROR", "The destination is not a directory.")
        if os.listdir(dest_dir):
            raise ApiError(422, "VALIDATION_ERROR", "The destination directory is not empty.")
        settings = get_settings()
        max_files = settings.max_archive_files
        max_bytes = settings.extracted_max_bytes

        rows = list(
            session.execute(
                select(SnapshotFile).where(SnapshotFile.snapshot_id == snapshot.id)
            ).scalars()
        )
        expected_hashes = {row.path: row.sha256 for row in rows}
        seen: dict[str, str] = {}
        total = 0
        # Structural pre-validation: only digest-verified bytes reach the
        # tar parser, but bit-rot or a damaged object must surface as a
        # marked integrity failure, never an unhandled 500.
        try:
            with tarfile.open(tmp_path, "r") as probe:
                members = probe.getmembers()
        except (tarfile.TarError, EOFError, OSError):
            _mark_integrity_failed(
                session,
                snapshot,
                "TARBALL_CORRUPT",
                "The stored object is not a valid archive.",
            )
            raise ApiError(
                422, "INTEGRITY_FAILED", "The stored object is not a valid archive."
            ) from None
        with tarfile.open(tmp_path, "r") as tar:
            files = [member for member in members if not member.isdir()]
            if len(files) > max_files:
                raise ApiError(422, "INTEGRITY_FAILED", "The stored archive is too large.")
            for member in files:
                if not member.isfile():
                    raise ApiError(
                        422, "INTEGRITY_FAILED", "The stored archive has a special file."
                    )
                rel = _validate_member(member.name)
                if rel in seen:
                    raise ApiError(
                        422, "INTEGRITY_FAILED", "The stored archive has duplicate paths."
                    )
                if member.size > max_bytes or total + member.size > max_bytes:
                    raise ApiError(422, "INTEGRITY_FAILED", "The stored archive is too large.")
                target = os.path.join(dest_dir, *rel.split("/"))
                parent = os.path.dirname(target)
                os.makedirs(parent, mode=0o700, exist_ok=True)
                extracted = tar.extractfile(member)
                if extracted is None:
                    raise ApiError(422, "INTEGRITY_FAILED", "A stored file cannot be read.")
                digest = hashlib.sha256()
                written = 0
                with open(target, "wb") as out:
                    while True:
                        chunk = extracted.read(1024 * 1024)
                        if not chunk:
                            break
                        digest.update(chunk)
                        out.write(chunk)
                        written += len(chunk)
                os.chmod(target, 0o600)
                if written != member.size:
                    raise ApiError(422, "INTEGRITY_FAILED", "A stored file changed size.")
                seen[rel] = digest.hexdigest()
                total += written

        if set(seen) != set(expected_hashes):
            missing = sorted(set(expected_hashes) - set(seen))
            extra = sorted(set(seen) - set(expected_hashes))
            detail = "; ".join(
                ([f"missing {len(missing)}"] if missing else [])
                + ([f"unexpected {len(extra)}"] if extra else [])
            )
            raise ApiError(422, "INTEGRITY_FAILED", f"File set mismatch: {detail}.")
        for path, actual in seen.items():
            if actual != expected_hashes[path]:
                raise ApiError(422, "INTEGRITY_FAILED", f"Hash mismatch for file: {path}")
        authoritative = session.execute(
            select(SnapshotFile).where(SnapshotFile.snapshot_id == snapshot.id)
        ).scalars()
        recomputed = compute_tree_digest(
            [
                ValidatedEntry(path=row.path, size=row.size, sha256=row.sha256)
                for row in sorted(authoritative, key=lambda row: row.path)
            ]
        )
        if recomputed != snapshot.tree_digest:
            raise ApiError(422, "INTEGRITY_FAILED", "Snapshot digest mismatch.")
        return {
            "snapshot_id": str(snapshot.id),
            "files": len(seen),
            "total_bytes": total,
            "tree_digest": snapshot.tree_digest,
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _delete_key_if_unreferenced(
    session: Session, snapshot_id: uuid.UUID, key: str, kind: str
) -> None:
    """Delete one object key when no other row references it. Never raises."""
    remaining = (
        session.execute(
            select(func.count())
            .select_from(RepositorySnapshot)
            .where(
                (
                    (RepositorySnapshot.storage_key == key)
                    | (RepositorySnapshot.security_storage_key == key)
                ),
                RepositorySnapshot.id != snapshot_id,
            )
        )
    ).scalar_one()
    if remaining > 0:
        logger.info(
            "snapshot object shared snapshot_id=%s kind=%s references=%d",
            snapshot_id,
            kind,
            remaining,
        )
        return
    try:
        get_store().delete_object(get_settings().s3_repositories_bucket, key)
        logger.info("snapshot object deleted snapshot_id=%s kind=%s", snapshot_id, kind)
    except StorageError as exc:
        logger.warning(
            "snapshot object orphaned snapshot_id=%s kind=%s code=%s",
            snapshot_id,
            kind,
            exc.code,
        )


def delete_snapshot_content(session: Session, snapshot: RepositorySnapshot) -> None:
    """Best-effort object removal honoring shared-key reference counts.

    Deletes each artifact only when no other snapshot row references
    its key (either column counts: the security fields may mirror the
    main object). Never raises: failures are logged for the future
    janitor (D51) so storage outages cannot block project deletion.
    """
    if snapshot.storage_key:
        _delete_key_if_unreferenced(session, snapshot.id, snapshot.storage_key, "snapshot")
    if snapshot.security_storage_key and snapshot.security_storage_key != snapshot.storage_key:
        _delete_key_if_unreferenced(session, snapshot.id, snapshot.security_storage_key, "security")


def list_orphan_keys(session: Session, store: ObjectStore | None = None) -> dict:
    """Object keys no snapshot row references (detection only, no deletion).

    Orphans arise from interrupted deletions or storage outages during
    cleanup; ingestion removes its own orphans on DB-commit failure.
    Cleanup stays an explicit operator action: shared content-addressed
    keys must never be removed by automation that cannot see every
    referencing row.
    """
    active_store = store or get_store()
    bucket = get_settings().s3_repositories_bucket
    try:
        listed = active_store.list_objects(bucket, "snapshots/")
    except StorageError as exc:
        raise ApiError(503, exc.code, exc.message) from exc
    referenced = {
        row[0]
        for row in session.execute(
            select(RepositorySnapshot.storage_key).where(
                RepositorySnapshot.storage_key.is_not(None)
            )
        ).all()
    } | {
        row[0]
        for row in session.execute(
            select(RepositorySnapshot.security_storage_key).where(
                RepositorySnapshot.security_storage_key.is_not(None)
            )
        ).all()
    }
    orphans = sorted(key for key, _size in listed if key not in referenced)
    orphan_bytes = sum(size for key, size in listed if key not in referenced)
    logger.info(
        "orphan scan objects=%d orphans=%d orphan_bytes=%d",
        len(listed),
        len(orphans),
        orphan_bytes,
    )
    return {
        "objects": len(listed),
        "orphan_keys": orphans,
        "orphan_bytes": orphan_bytes,
    }
