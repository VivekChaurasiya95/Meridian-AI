"""Evidence artifacts (M6): metadata in Postgres, bytes in MinIO.

The worker records artifacts after capturing them; members read metadata
and request short-lived signed downloads. Storage keys and credentials
never appear in responses, logs, or errors — only opaque metadata plus
a per-request signed URL whose issuance is audited.
"""

import contextlib
import datetime as dt
import hashlib
import json
import os
import tempfile
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.envelope import ApiError, not_found
from app.models import EvidenceArtifact, Project, User, WorkspaceMember
from app.services import audit as audit_service
from app.services.activity import db_now, investigation_access
from app.services.jobs import check_json_bounds
from app.services.object_store import MinioObjectStore, ObjectStore, StorageError
from app.services.redact import redact_text

EVIDENCE_KINDS = (
    "log",
    "screenshot",
    "trace",
    "video",
    "source_excerpt",
    "test_output",
    "build_output",
    "network_summary",
    "report",
    "other",
)
REDACTION_STATUSES = ("pending", "redacted", "not_required", "failed")
METADATA_MAX_BYTES = 4096
LIST_LIMIT_MAX = 200

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"
_ZIP_MAGIC = b"PK\x03\x04"

MIME_BY_MAGIC = "application/octet-stream"


def sniff_mime(data: bytes) -> str:
    """Server-side MIME detection. Never trusts caller claims (pure)."""
    if data.startswith(_PNG_MAGIC):
        return "image/png"
    if data.startswith(_JPEG_MAGIC):
        return "image/jpeg"
    if data.startswith(_ZIP_MAGIC):
        return "application/zip"
    stripped = data.strip()
    if stripped.startswith((b"{", b"[")):
        try:
            json.loads(stripped.decode("utf-8"))
            return "application/json"
        except (UnicodeDecodeError, ValueError):
            pass
    if b"\x00" not in data:
        try:
            data.decode("utf-8")
            return "text/plain"
        except UnicodeDecodeError:
            pass
    return MIME_BY_MAGIC


def evidence_key(investigation_id: uuid.UUID, digest: str, suffix: str) -> str:
    return f"evidence/{investigation_id}/{digest[:16]}-{uuid.uuid4().hex}{suffix}"


def _iso(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def serialize_evidence(row: EvidenceArtifact) -> dict:
    return {
        "id": str(row.id),
        "project_id": str(row.project_id),
        "investigation_id": str(row.investigation_id),
        "tool_run_id": str(row.tool_run_id) if row.tool_run_id else None,
        "kind": row.kind,
        "mime_type": row.mime_type,
        "byte_size": row.byte_size,
        "sha256": row.sha256,
        "redaction_status": row.redaction_status,
        "visibility": row.visibility,
        "metadata": row.metadata_ or {},
        "captured_at": _iso(row.captured_at),
        "created_at": _iso(row.created_at),
    }


def get_store() -> ObjectStore:
    settings = get_settings()
    return MinioObjectStore(
        endpoint_url=settings.s3_endpoint_url,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        region=settings.s3_region,
    )


def create_evidence(
    session: Session,
    *,
    project_id: uuid.UUID,
    investigation_id: uuid.UUID,
    tool_run_id: uuid.UUID | None,
    kind: str,
    data: bytes,
    filename_hint: str,
    redaction_status: str,
    metadata: dict | None = None,
    store: ObjectStore | None = None,
) -> dict:
    """Persist one artifact (trusted worker path). Bytes are hashed,
    sniffed, capped, uploaded, then indexed — in that order."""
    if kind not in EVIDENCE_KINDS:
        raise ApiError(422, "VALIDATION_ERROR", "The evidence kind is not supported.")
    if redaction_status not in REDACTION_STATUSES:
        raise ApiError(422, "VALIDATION_ERROR", "The redaction status is not supported.")
    settings = get_settings()
    if len(data) > settings.evidence_max_artifact_bytes:
        raise ApiError(413, "EVIDENCE_TOO_LARGE", "The evidence object exceeds the size limit.")
    mime = sniff_mime(data)
    if mime == MIME_BY_MAGIC:
        raise ApiError(422, "EVIDENCE_TYPE_REJECTED", "The evidence file type is not supported.")
    details = dict(metadata or {})
    check_json_bounds(details, max_bytes=METADATA_MAX_BYTES, label="evidence metadata")
    digest = hashlib.sha256(data).hexdigest()
    suffix = "".join(char for char in filename_hint.rsplit(".", 1)[-1:][0][:10] if char.isalnum())
    key = evidence_key(investigation_id, digest, f".{suffix.lower()}" if suffix else "")
    active_store = store or get_store()
    bucket = settings.s3_evidence_bucket
    fd, tmp_path = tempfile.mkstemp(prefix="meridian-evidence-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        byte_size = active_store.put_file(bucket, key, tmp_path, content_type=mime)
    except StorageError as exc:
        raise ApiError(503, exc.code, exc.message) from exc
    finally:
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
    now = db_now(session)
    row = EvidenceArtifact(
        id=uuid.uuid4(),
        project_id=project_id,
        investigation_id=investigation_id,
        tool_run_id=tool_run_id,
        kind=kind,
        storage_key=key,
        mime_type=mime,
        byte_size=byte_size,
        sha256=digest,
        redaction_status=redaction_status,
        visibility="workspace",
        metadata_=details,
        captured_at=now,
        created_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return serialize_evidence(row)


def list_evidence(
    session: Session,
    user: User,
    investigation_id: uuid.UUID,
    kind: str | None,
    redaction_status: str | None,
) -> list[dict]:
    """Capture-ordered metadata. Allowlisted filters only."""
    investigation_access(session, user, investigation_id)
    if kind is not None and kind not in EVIDENCE_KINDS:
        raise ApiError(422, "VALIDATION_ERROR", "The kind filter is not supported.")
    if redaction_status is not None and redaction_status not in REDACTION_STATUSES:
        raise ApiError(422, "VALIDATION_ERROR", "The redaction filter is not supported.")
    stmt = (
        select(EvidenceArtifact)
        .where(EvidenceArtifact.investigation_id == investigation_id)
        .order_by(EvidenceArtifact.created_at.asc(), EvidenceArtifact.id.asc())
        .limit(LIST_LIMIT_MAX)
    )
    if kind is not None:
        stmt = stmt.where(EvidenceArtifact.kind == kind)
    if redaction_status is not None:
        stmt = stmt.where(EvidenceArtifact.redaction_status == redaction_status)
    return [serialize_evidence(row) for row in session.execute(stmt).scalars()]


def get_evidence(session: Session, user: User, evidence_id: uuid.UUID) -> dict:
    """One artifact's metadata. Keys stay server-side; 404 for foreign."""
    row = (
        session.execute(
            select(EvidenceArtifact, Project.workspace_id)
            .join(Project, Project.id == EvidenceArtifact.project_id)
            .join(
                WorkspaceMember,
                WorkspaceMember.workspace_id == Project.workspace_id,
            )
            .where(
                EvidenceArtifact.id == evidence_id,
                WorkspaceMember.user_id == user.id,
            )
        )
    ).one_or_none()
    if row is None:
        raise not_found("evidence")
    return serialize_evidence(row[0])


def issue_download_url(
    session: Session,
    user: User,
    evidence_id: uuid.UUID,
    request_id: str,
    store: ObjectStore | None = None,
) -> dict:
    """Authorize and mint a short-lived download URL (audited, never logged)."""
    found = (
        session.execute(
            select(EvidenceArtifact, Project.workspace_id)
            .join(Project, Project.id == EvidenceArtifact.project_id)
            .join(
                WorkspaceMember,
                WorkspaceMember.workspace_id == Project.workspace_id,
            )
            .where(
                EvidenceArtifact.id == evidence_id,
                WorkspaceMember.user_id == user.id,
            )
        )
    ).one_or_none()
    if found is None:
        raise not_found("evidence")
    row, workspace_id = found
    assert isinstance(row, EvidenceArtifact)
    if row.redaction_status == "failed":
        raise ApiError(409, "EVIDENCE_NOT_READY", "This artifact failed redaction review.")
    settings = get_settings()
    active_store = store or get_store()
    try:
        url = active_store.generate_download_url(
            settings.s3_evidence_bucket, row.storage_key, settings.evidence_download_ttl_seconds
        )
    except StorageError as exc:
        raise ApiError(503, exc.code, exc.message) from exc
    audit_service.append_audit(
        session,
        workspace_id=workspace_id,
        actor_type="user",
        action=audit_service.ACTION_EVIDENCE_DOWNLOAD_ISSUED,
        resource_type="evidence",
        resource_id=row.id,
        actor=user,
        request_id=request_id,
        metadata={"kind": row.kind, "byte_size": row.byte_size},
    )
    expires_at = db_now(session) + dt.timedelta(seconds=settings.evidence_download_ttl_seconds)
    return {"url": url, "expires_at": _iso(expires_at)}


def redact_json_bytes(data: bytes) -> tuple[bytes, bool]:
    """Redact every string inside a JSON document (pure).

    Returns (redacted_bytes, changed). Non-UTF-8 or non-JSON input is
    returned unchanged with changed=False so callers can fail closed.
    """
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return data, False

    def _walk(node: object) -> tuple[object, bool]:
        if isinstance(node, str):
            redacted = redact_text(node)
            return redacted, redacted != node
        if isinstance(node, list):
            changed_any = False
            out: list[object] = []
            for item in node:
                walked, changed = _walk(item)
                changed_any = changed_any or changed
                out.append(walked)
            return out, changed_any
        if isinstance(node, dict):
            changed_any = False
            out_dict: dict[object, object] = {}
            for key, value in node.items():
                walked, changed = _walk(value)
                changed_any = changed_any or changed
                out_dict[key] = walked
            return out_dict, changed_any
        return node, False

    walked, _ = _walk(document)
    return json.dumps(walked, separators=(",", ":")).encode("utf-8"), True


def evidence_count(session: Session, investigation_id: uuid.UUID) -> int:
    return (
        session.execute(
            select(func.count()).where(EvidenceArtifact.investigation_id == investigation_id)
        )
    ).scalar_one()
