"""Shared immutable-snapshot creation from a validated file tree.

Single terminal pipeline for every source (ZIP upload today, Git import
next): deterministic tar -> content-addressed put -> snapshot + file rows
-> read-back verify -> ``ready``. Extracted from ``ingestion`` without
behaviour change: digests, storage keys, transaction boundaries, orphan
cleanup, and status semantics are exactly the ZIP pipeline's (D51/D52).
Callers own source validation and preview extraction; this module owns
only storage, persistence, and verification. Nothing here executes
repository content.
"""

import datetime as dt
import hashlib
import logging
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.envelope import ApiError
from app.models import Project, RepositorySnapshot, SnapshotFile
from app.services.archive_security import ValidatedEntry, compute_tree_digest
from app.services.object_store import (
    MinioObjectStore,
    ObjectStore,
    StorageError,
    build_snapshot_tar,
    security_key_for_digest,
    sha256_file,
    storage_key_for_digest,
)

logger = logging.getLogger("meridian.ingestion")


def default_store() -> ObjectStore:
    settings = get_settings()
    return MinioObjectStore(
        endpoint_url=settings.s3_endpoint_url,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        region=settings.s3_region,
    )


def _key_in_use(session: Session, storage_key: str) -> bool:
    """Whether any snapshot row references the key (dedup refcount).

    Both artifact columns count: the main and security keys live in
    disjoint prefixes, except the explicit mirror case where the
    security fields point at the main object itself.
    """
    return (
        session.execute(
            select(func.count())
            .select_from(RepositorySnapshot)
            .where(
                (RepositorySnapshot.storage_key == storage_key)
                | (RepositorySnapshot.security_storage_key == storage_key)
            )
        ).scalar_one()
        > 0
    )


def _delete_orphan_object(store: ObjectStore, bucket: str, storage_key: str) -> None:
    """Best-effort removal of an object no row references. Never raises."""
    try:
        store.delete_object(bucket, storage_key)
    except StorageError as exc:
        logger.warning("snapshot object orphaned key=%s code=%s", storage_key, exc.code)


@dataclass(frozen=True)
class SnapshotProvenance:
    source_type: str
    source_ref: str | None
    archive_name: str | None = None
    archive_size: int | None = None
    archive_sha256: str | None = None
    commit_sha: str | None = None
    branch_name: str | None = None


def snapshot_from_tree(
    session: Session,
    *,
    project: Project,
    indexed: list[ValidatedEntry],
    source_dir: str,
    manifest: dict,
    file_previews: dict[str, tuple[bool, str | None]],
    provenance: SnapshotProvenance,
    project_runtime_profile: dict | None,
    store: ObjectStore,
    security_extra: list[ValidatedEntry] | None = None,
) -> RepositorySnapshot:
    """Store ``indexed`` files from ``source_dir`` as a READY snapshot.

    ``source_dir`` must stay alive for the call (tar is built from it).
    ``file_previews`` maps path -> (is_text, content|None) for every
    indexed path. Commits exactly as the ZIP pipeline did: one commit for
    snapshot+files+project, then verification status in a second commit.

    ``security_extra`` (D62) holds validated secret-file entries excluded
    from the index; they are packed together with ``indexed`` into a
    second content-addressed object for security scanning. ``None``
    leaves the security artifact pending (sources without scan input);
    an empty list mirrors the main object instead of storing a copy.
    """
    settings = get_settings()
    bucket = settings.s3_repositories_bucket
    tardir = tempfile.mkdtemp(prefix="meridian-tar-")
    tar_path = os.path.join(tardir, "snapshot.tar")
    try:
        try:
            build_snapshot_tar([(e.path, e.sha256) for e in indexed], source_dir, tar_path)
        except StorageError as exc:
            raise ApiError(422, exc.code, exc.message) from exc
        object_sha256 = sha256_file(tar_path)
        storage_key = storage_key_for_digest(object_sha256)
        storage_bytes = os.path.getsize(tar_path)
        reused = _key_in_use(session, storage_key)
        if not reused:
            try:
                store.put_file(bucket, storage_key, tar_path)
            except StorageError as exc:
                raise ApiError(503, exc.code, exc.message) from exc
        security_key: str | None = None
        security_digest: str | None = None
        security_bytes: int | None = None
        reused_security = False
        if security_extra is not None:
            if not security_extra:
                security_key, security_digest, security_bytes = (
                    storage_key,
                    object_sha256,
                    storage_bytes,
                )
                reused_security = True
            else:
                sec_tar_path = os.path.join(tardir, "security.tar")
                try:
                    build_snapshot_tar(
                        [(e.path, e.sha256) for e in indexed + security_extra],
                        source_dir,
                        sec_tar_path,
                    )
                except StorageError as exc:
                    raise ApiError(422, exc.code, exc.message) from exc
                security_digest = sha256_file(sec_tar_path)
                security_key = security_key_for_digest(security_digest)
                security_bytes = os.path.getsize(sec_tar_path)
                reused_security = _key_in_use(session, security_key)
                if not reused_security:
                    try:
                        store.put_file(bucket, security_key, sec_tar_path)
                    except StorageError as exc:
                        raise ApiError(503, exc.code, exc.message) from exc
    finally:
        shutil.rmtree(tardir, ignore_errors=True)

    tree_digest = compute_tree_digest(indexed)
    now = dt.datetime.now(dt.UTC)
    snapshot = RepositorySnapshot(
        id=uuid.uuid4(),
        project_id=project.id,
        commit_sha=provenance.commit_sha,
        tree_digest=tree_digest,
        branch_name=provenance.branch_name,
        source_ref=provenance.source_ref[:255] if provenance.source_ref else None,
        source_type=provenance.source_type,
        archive_name=provenance.archive_name[:255] if provenance.archive_name else None,
        archive_size=provenance.archive_size,
        archive_sha256=provenance.archive_sha256,
        manifest=manifest,
        storage_status="uploading",
        storage_key=storage_key,
        storage_bytes=storage_bytes,
        security_storage_key=security_key,
        security_content_digest=security_digest,
        security_storage_bytes=security_bytes,
        created_at=now,
    )
    session.add(snapshot)
    for entry in sorted(indexed, key=lambda e: e.path):
        is_text, content = file_previews.get(entry.path, (False, None))
        session.add(
            SnapshotFile(
                snapshot_id=snapshot.id,
                path=entry.path,
                size=entry.size,
                sha256=entry.sha256,
                is_text=is_text,
                content=content,
            )
        )
    if project_runtime_profile is not None:
        project.runtime_profile = project_runtime_profile
    project.updated_at = now
    try:
        session.commit()
    except Exception:
        session.rollback()
        if not reused and not _key_in_use(session, storage_key):
            _delete_orphan_object(store, bucket, storage_key)
        if (
            security_key is not None
            and security_key != storage_key
            and not reused_security
            and not _key_in_use(session, security_key)
        ):
            _delete_orphan_object(store, bucket, security_key)
        raise
    session.refresh(snapshot)

    try:
        stored_bytes = store.get_bytes(bucket, storage_key)
    except StorageError as exc:
        snapshot.storage_status = "failed"
        snapshot.error_code = exc.code
        snapshot.error_message = exc.message
        session.commit()
        session.refresh(snapshot)
        raise ApiError(503, exc.code, exc.message) from exc
    if (
        hashlib.sha256(stored_bytes).hexdigest() != object_sha256
        or len(stored_bytes) != storage_bytes
    ):
        snapshot.storage_status = "integrity_failed"
        snapshot.error_code = "SNAPSHOT_INTEGRITY_MISMATCH"
        snapshot.error_message = "The stored object differs from the recorded digest."
        session.commit()
        session.refresh(snapshot)
        raise ApiError(
            503,
            "SNAPSHOT_INTEGRITY_MISMATCH",
            "The stored snapshot failed integrity verification. Please retry the upload.",
        )
    if security_key is not None:
        if security_digest is None or security_bytes is None:
            raise ApiError(500, "INTERNAL_ERROR", "The security artifact record is incomplete.")
        try:
            sec_bytes = store.get_bytes(bucket, security_key)
        except StorageError as exc:
            snapshot.storage_status = "failed"
            snapshot.security_scan_status = "failed"
            snapshot.error_code = exc.code
            snapshot.error_message = exc.message
            session.commit()
            session.refresh(snapshot)
            raise ApiError(503, exc.code, exc.message) from exc
        if (
            hashlib.sha256(sec_bytes).hexdigest() != security_digest
            or len(sec_bytes) != security_bytes
        ):
            snapshot.storage_status = "failed"
            snapshot.security_scan_status = "integrity_failed"
            snapshot.error_code = "SNAPSHOT_INTEGRITY_MISMATCH"
            snapshot.error_message = "The stored security object differs from the recorded digest."
            session.commit()
            session.refresh(snapshot)
            raise ApiError(
                503,
                "SNAPSHOT_INTEGRITY_MISMATCH",
                "The stored security object failed integrity verification. "
                "Please retry the upload.",
            )
    snapshot.storage_status = "ready"
    if security_key is not None:
        snapshot.security_scan_status = "ready"
    snapshot.error_code = None
    snapshot.error_message = None
    snapshot.storage_verified_at = dt.datetime.now(dt.UTC)
    session.commit()
    session.refresh(snapshot)
    logger.info(
        "snapshot stored snapshot_id=%s storage_key=%s bytes=%d files=%d deduplicated=%s "
        "security_key=%s security_bytes=%s security_deduplicated=%s",
        snapshot.id,
        storage_key,
        storage_bytes,
        len(indexed),
        reused,
        security_key,
        security_bytes,
        reused_security if security_key is not None else None,
    )
    return snapshot
