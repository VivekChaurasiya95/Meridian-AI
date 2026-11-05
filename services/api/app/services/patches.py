"""Patches (M8): proposals with scoped human approval, isolated apply.

Diffs are validated before storage and immutable afterwards. Approval
binds the exact reviewed digest plus base snapshot; application runs
only in the isolated pipeline after commit — never a push or merge.
Every decision is audited with the digest it covered.
"""

import datetime as dt
import hashlib
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.envelope import ApiError, access_denied, not_found
from app.models import Investigation, Patch, Project, User, VerificationRun, WorkspaceMember
from app.services import audit as audit_service
from app.services import evidence as evidence_service
from app.services import investigations as investigation_service
from app.services import jobs as job_service
from app.services.activity import db_now, investigation_access
from app.services.object_store import ObjectStore, StorageError
from app.services.patch_diff import files_changed_summary, parse_unified_diff

APPROVER_ROLES = frozenset({"owner", "admin"})
DISCARDABLE_STATUSES = frozenset(
    {"proposed", "awaiting_approval", "rejected", "failed", "verification_failed", "stale"}
)
PATCH_DIFF_MIME = "text/plain"


def _iso(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def serialize_patch(row: Patch, verification: dict | None = None) -> dict:
    return {
        "id": str(row.id),
        "investigation_id": str(row.investigation_id),
        "base_snapshot_id": str(row.base_snapshot_id),
        "applied_snapshot_id": str(row.applied_snapshot_id) if row.applied_snapshot_id else None,
        "status": row.status,
        "summary": row.summary,
        "diff_sha256": row.diff_sha256,
        "diff_byte_size": row.diff_byte_size,
        "files_changed": row.files_changed or [],
        "approval_status": row.approval_status,
        "approval_by": str(row.approval_by) if row.approval_by else None,
        "approval_note": row.approval_note,
        "approved_at": _iso(row.approved_at),
        "applied_at": _iso(row.applied_at),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
        "verification": verification,
    }


def create_proposal(
    session: Session,
    *,
    job_id: uuid.UUID,
    worker_id: str,
    investigation_id: uuid.UUID,
    project_id: uuid.UUID,
    base_snapshot_id: uuid.UUID,
    stage_id: uuid.UUID,
    tool_run_id: uuid.UUID | None,
    summary: str,
    diff_text: str,
    store: ObjectStore | None = None,
) -> dict:
    """Validate, store, and index one patch proposal (worker path)."""
    investigation_service.require_job_ownership(session, job_id, worker_id, investigation_id)
    settings = get_settings()
    raw = diff_text.encode("utf-8")
    if len(raw) > settings.patch_max_diff_bytes:
        raise ApiError(422, "PATCH_DIFF_INVALID", "The patch diff is too large.")
    files = parse_unified_diff(diff_text)
    digest = hashlib.sha256(raw).hexdigest()
    key = f"patch-diffs/{investigation_id}/{uuid.uuid4().hex}.diff"
    active_store = store or evidence_service.get_store()
    try:
        import contextlib
        import os
        import tempfile

        fd, tmp_path = tempfile.mkstemp(prefix="meridian-patch-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
            byte_size = active_store.put_file(
                settings.s3_evidence_bucket, key, tmp_path, content_type=PATCH_DIFF_MIME
            )
        finally:
            with contextlib.suppress(OSError):
                os.remove(tmp_path)
    except StorageError as exc:
        raise ApiError(503, exc.code, exc.message) from exc
    now = db_now(session)
    row = Patch(
        id=uuid.uuid4(),
        investigation_id=investigation_id,
        project_id=project_id,
        base_snapshot_id=base_snapshot_id,
        created_by_stage_id=stage_id,
        tool_run_id=tool_run_id,
        status="proposed",
        summary=summary.strip(),
        diff_storage_key=key,
        diff_sha256=digest,
        diff_byte_size=byte_size,
        files_changed=files_changed_summary(files),
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return serialize_patch(row)


def list_patches(session: Session, user: User, investigation_id: uuid.UUID) -> list[dict]:
    """Proposals in creation order with approval summaries."""
    inv, _role = investigation_access(session, user, investigation_id)
    rows = list(
        session.execute(
            select(Patch)
            .where(Patch.investigation_id == inv.id)
            .order_by(Patch.created_at.asc(), Patch.id.asc())
        ).scalars()
    )
    return [serialize_patch(row, _latest_verification(session, row.id)) for row in rows]


def get_patch(session: Session, user: User, patch_id: uuid.UUID) -> dict:
    """One patch with its latest verification summary. 404 for foreign."""
    row = _get_visible_patch(session, user, patch_id)
    return serialize_patch(row, _latest_verification(session, row.id))


def get_diff(
    session: Session,
    user: User,
    patch_id: uuid.UUID,
    request_id: str,
    store: ObjectStore | None = None,
) -> dict:
    """Authorized diff bytes: inline text when small, signed URL when large."""
    row = _get_visible_patch(session, user, patch_id)
    settings = get_settings()
    active_store = store or evidence_service.get_store()
    project = session.get(Project, row.project_id)
    assert project is not None
    audit_service.append_audit(
        session,
        workspace_id=project.workspace_id,
        actor_type="user",
        action="patch.diff_viewed",
        resource_type="patch",
        resource_id=row.id,
        actor=user,
        request_id=request_id,
        metadata={"byte_size": row.diff_byte_size, "sha256": row.diff_sha256},
    )
    if row.diff_byte_size <= settings.patch_diff_inline_bytes:
        try:
            raw = active_store.get_bytes(settings.s3_evidence_bucket, row.diff_storage_key)
        except StorageError as exc:
            raise ApiError(503, exc.code, exc.message) from exc
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ApiError(503, "PATCH_STORE_INVALID", "The stored diff is invalid.") from exc
        return {"diff_sha256": row.diff_sha256, "diff_text": text, "truncated": False}
    try:
        url = active_store.generate_download_url(
            settings.s3_evidence_bucket,
            row.diff_storage_key,
            settings.evidence_download_ttl_seconds,
        )
    except StorageError as exc:
        raise ApiError(503, exc.code, exc.message) from exc
    expires_at = db_now(session) + dt.timedelta(seconds=settings.evidence_download_ttl_seconds)
    return {"diff_sha256": row.diff_sha256, "download_url": url, "expires_at": _iso(expires_at)}


def approve_patch(
    session: Session,
    user: User,
    patch_id: uuid.UUID,
    diff_sha256: str,
    base_snapshot_id: uuid.UUID,
    note: str | None,
    request_id: str,
) -> dict:
    """Approve the exact reviewed digest for isolated application (202).

    Row-locked: verifies awaiting state, re-checks authorization and
    the digest/snapshot binding, persists approval + audit atomically,
    then enqueues application only after commit. Never pushes/merges.
    """
    row = (
        session.execute(select(Patch).where(Patch.id == patch_id).with_for_update())
    ).scalar_one_or_none()
    if row is None:
        raise not_found("patch")
    project = session.get(Project, row.project_id)
    assert project is not None
    membership = (
        session.execute(
            select(WorkspaceMember.role).where(
                WorkspaceMember.workspace_id == project.workspace_id,
                WorkspaceMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise not_found("patch")
    if membership not in APPROVER_ROLES:
        raise access_denied()
    if row.status != "awaiting_approval" or row.approval_status != "pending":
        raise ApiError(409, "INVALID_STATE", "This patch is not awaiting approval.")
    if row.diff_sha256 != diff_sha256 or row.base_snapshot_id != base_snapshot_id:
        raise ApiError(422, "APPROVAL_MISMATCH", "The reviewed digest or snapshot does not match.")
    now = db_now(session)
    row.status = "approved"
    row.approval_status = "approved"
    row.approval_by = user.id
    row.approval_note = (note or "").strip()[:500] or None
    row.approved_at = now
    row.updated_at = now
    session.commit()
    audit_service.append_audit(
        session,
        workspace_id=project.workspace_id,
        actor_type="user",
        action="patch.approved",
        resource_type="patch",
        resource_id=row.id,
        actor=user,
        request_id=request_id,
        metadata={"diff_sha256": row.diff_sha256, "base_snapshot_id": str(row.base_snapshot_id)},
    )
    inv = session.get(Investigation, row.investigation_id)
    assert inv is not None
    if inv.status != "awaiting_approval":
        raise ApiError(409, "INVALID_STATE", "The investigation is not awaiting approval.")
    job, _ = job_service.submit_job(
        session,
        user,
        project.workspace_id,
        "investigation",
        {"investigation_id": str(inv.id), "from_stage": "patch_application"},
        f"approve.{row.id}.{row.diff_sha256[:16]}",
        0,
        None,
    )
    investigation_service.transition_for_approval(session, inv.id)
    inv.job_id = uuid.UUID(job["id"])
    session.commit()
    return {
        "patch_id": str(row.id),
        "approval_status": "approved",
        "status": "approved",
        "application_status": "queued",
    }


def reject_patch(
    session: Session, user: User, patch_id: uuid.UUID, reason: str, request_id: str
) -> dict:
    """Reject a proposal. No application may proceed afterwards."""
    row = _get_visible_patch(session, user, patch_id, for_update=True)
    project = session.get(Project, row.project_id)
    assert project is not None
    role = _role(session, user, project.workspace_id)
    if role not in APPROVER_ROLES:
        raise access_denied()
    if row.status not in ("proposed", "awaiting_approval"):
        raise ApiError(409, "INVALID_STATE", "Only a pending proposal can be rejected.")
    clean_reason = (reason or "").strip()
    if not 1 <= len(clean_reason) <= 500:
        raise ApiError(422, "VALIDATION_ERROR", "A rejection reason is required.")
    now = db_now(session)
    row.status = "rejected"
    row.approval_status = "rejected"
    row.approval_by = user.id
    row.approval_note = clean_reason
    row.approved_at = now
    row.updated_at = now
    inv = session.get(Investigation, row.investigation_id)
    assert inv is not None
    if inv.status == "awaiting_approval":
        investigation_service.transition_for_rejection(session, inv.id, clean_reason, user)
    session.commit()
    audit_service.append_audit(
        session,
        workspace_id=project.workspace_id,
        actor_type="user",
        action="patch.rejected",
        resource_type="patch",
        resource_id=row.id,
        actor=user,
        request_id=request_id,
        metadata={"diff_sha256": row.diff_sha256},
    )
    session.refresh(row)
    return serialize_patch(row, _latest_verification(session, row.id))


def discard_patch(session: Session, user: User, patch_id: uuid.UUID, request_id: str) -> dict:
    """Discard a superseded proposal. Blocked while approval is pending."""
    row = _get_visible_patch(session, user, patch_id, for_update=True)
    project = session.get(Project, row.project_id)
    assert project is not None
    role = _role(session, user, project.workspace_id)
    if role not in APPROVER_ROLES:
        raise access_denied()
    if row.status not in DISCARDABLE_STATUSES:
        raise ApiError(409, "INVALID_STATE", "This patch can no longer be discarded.")
    inv = session.get(Investigation, row.investigation_id)
    assert inv is not None
    if inv.status == "awaiting_approval":
        raise ApiError(
            409, "INVALID_STATE", "Resolve the pending approval first (approve or reject)."
        )
    live_job = inv.job_id is not None and _job_live(session, inv.job_id)
    if live_job:
        raise ApiError(409, "INVALID_STATE", "A live job still references this work.")
    row.status = "discarded"
    row.updated_at = db_now(session)
    session.commit()
    audit_service.append_audit(
        session,
        workspace_id=project.workspace_id,
        actor_type="user",
        action="patch.discarded",
        resource_type="patch",
        resource_id=row.id,
        actor=user,
        request_id=request_id,
        metadata={"diff_sha256": row.diff_sha256},
    )
    session.refresh(row)
    return serialize_patch(row, _latest_verification(session, row.id))


def patch_count(session: Session, investigation_id: uuid.UUID) -> int:
    return (
        session.execute(select(func.count()).where(Patch.investigation_id == investigation_id))
    ).scalar_one()


def latest_with_status(
    session: Session, investigation_id: uuid.UUID, statuses: tuple[str, ...]
) -> Patch | None:
    """Newest patch in one of the given statuses (worker read)."""
    return (
        session.execute(
            select(Patch)
            .where(
                Patch.investigation_id == investigation_id,
                Patch.status.in_(statuses),
            )
            .order_by(Patch.created_at.desc(), Patch.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def submit_for_approval(
    session: Session,
    *,
    job_id: uuid.UUID,
    worker_id: str,
    investigation_id: uuid.UUID,
) -> Patch:
    """Move the newest proposal to the human gate (worker path).

    Idempotent: an already pending proposal is returned as-is so
    stage retries converge instead of conflicting.
    """
    investigation_service.require_job_ownership(session, job_id, worker_id, investigation_id)
    row = latest_with_status(session, investigation_id, ("proposed",))
    if row is None:
        pending = latest_with_status(session, investigation_id, ("awaiting_approval",))
        if pending is not None and pending.approval_status == "pending":
            return pending
        raise ApiError(409, "PATCH_NOT_PROPOSED", "No patch proposal is ready for review.")
    row.status = "awaiting_approval"
    row.approval_status = "pending"
    row.updated_at = db_now(session)
    session.commit()
    session.refresh(row)
    return row


def mark_applied(
    session: Session,
    *,
    job_id: uuid.UUID,
    worker_id: str,
    patch_id: uuid.UUID,
    applied_snapshot_id: uuid.UUID,
) -> Patch:
    """Record an approved patch as applied (worker path only)."""
    row = session.get(Patch, patch_id)
    if row is None:
        raise not_found("patch")
    investigation_service.require_job_ownership(session, job_id, worker_id, row.investigation_id)
    if row.status != "approved" or row.approval_status != "approved":
        raise ApiError(409, "PATCH_NOT_APPROVED", "Only an approved patch can be applied.")
    now = db_now(session)
    row.status = "applied"
    row.applied_snapshot_id = applied_snapshot_id
    row.applied_at = now
    row.updated_at = now
    session.commit()
    session.refresh(row)
    return row


def mark_verified(
    session: Session, *, job_id: uuid.UUID, worker_id: str, patch_id: uuid.UUID, passed: bool
) -> Patch:
    """Record the post-patch verdict on an applied patch (worker path)."""
    row = session.get(Patch, patch_id)
    if row is None:
        raise not_found("patch")
    investigation_service.require_job_ownership(session, job_id, worker_id, row.investigation_id)
    if row.status != "applied":
        raise ApiError(409, "INVALID_STATE", "Only an applied patch can be verified.")
    row.status = "verification_passed" if passed else "verification_failed"
    row.updated_at = db_now(session)
    session.commit()
    session.refresh(row)
    return row


def _get_visible_patch(
    session: Session, user: User, patch_id: uuid.UUID, for_update: bool = False
) -> Patch:
    stmt = (
        select(Patch)
        .join(Project, Project.id == Patch.project_id)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Project.workspace_id)
        .where(Patch.id == patch_id, WorkspaceMember.user_id == user.id)
    )
    if for_update:
        stmt = stmt.with_for_update(of=Patch)
    row = session.execute(stmt).scalar_one_or_none()
    if row is None:
        raise not_found("patch")
    return row


def _role(session: Session, user: User, workspace_id: uuid.UUID) -> str | None:
    return (
        session.execute(
            select(WorkspaceMember.role).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()


def _job_live(session: Session, job_id: uuid.UUID) -> bool:
    from app.models import Job

    job = session.get(Job, job_id)
    return job is not None and job.status not in job_service.TERMINAL_STATUSES


def _latest_verification(session: Session, patch_id: uuid.UUID) -> dict | None:
    run = (
        session.execute(
            select(VerificationRun)
            .where(VerificationRun.patch_id == patch_id)
            .order_by(VerificationRun.created_at.desc(), VerificationRun.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if run is None:
        return None
    return {"phase": run.phase, "status": run.status, "summary": run.summary}
