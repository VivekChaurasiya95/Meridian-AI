"""Security assessment persistence and retrieval (V1, D66).

The worker persists normalized assessments through this module; the
API serves them. Records carry sanitized data only — finding counts,
masked excerpts, versions, and fixed codes. Raw scanner output never
reaches these tables, and object-storage keys never leave them.
"""

import datetime as dt
import logging
import uuid

from sqlalchemy import and_, delete, desc, func, or_, select
from sqlalchemy.orm import Session

from app.envelope import ApiError, not_found
from app.models import Project, RepositorySnapshot, SecurityAssessment, SecurityFinding, User
from app.services.jobs import decode_cursor, encode_cursor

logger = logging.getLogger("meridian.security_assessments")

ASSESSMENT_STATUSES = (
    "pending",
    "running",
    "completed",
    "review_required",
    "partial",
    "failed",
    "cancelled",
)
FINDING_SEVERITIES = ("critical", "high", "medium", "low", "informational")
FINDING_SCANNERS = ("semgrep", "gitleaks")


def _iso(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.UTC)
    return value.isoformat().replace("+00:00", "Z")


def serialize_assessment(row: SecurityAssessment) -> dict:
    return {
        "id": str(row.id),
        "workspace_id": str(row.workspace_id),
        "project_id": str(row.project_id),
        "snapshot_id": str(row.snapshot_id),
        "job_id": str(row.job_id) if row.job_id else None,
        "generation": row.generation,
        "status": row.status,
        "policy_version": row.policy_version,
        "summary": dict(row.summary or {}),
        "scanner_versions": dict(row.scanner_versions or {}),
        "ruleset_version": row.ruleset_version,
        "started_at": _iso(row.started_at),
        "completed_at": _iso(row.completed_at),
        "created_at": _iso(row.created_at),
    }


def serialize_finding(row: SecurityFinding) -> dict:
    return {
        "id": str(row.id),
        "assessment_id": str(row.assessment_id),
        "fingerprint": row.fingerprint,
        "scanner": row.scanner,
        "rule_id": row.rule_id,
        "severity": row.severity,
        "confidence": row.confidence,
        "category": row.category,
        "title": row.title,
        "description": row.description,
        "location": dict(row.location or {}),
        "evidence": dict(row.evidence or {}),
        "created_at": _iso(row.created_at),
    }


def get_or_create_assessment(
    session: Session,
    *,
    job_id: uuid.UUID,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    snapshot_id: uuid.UUID,
    policy_version: str,
    ruleset_version: str,
) -> SecurityAssessment:
    """Fetch the job's assessment row, creating it on first attempt.

    Retries reuse the row (findings replaced, status reset to running)
    so one job never leaves two assessments behind.
    """
    row = (
        session.execute(
            select(SecurityAssessment).where(SecurityAssessment.job_id == job_id)
        )
    ).scalar_one_or_none()
    if row is not None:
        row.status = "running"
        row.started_at = session.execute(select(func.now())).scalar_one()
        row.completed_at = None
        row.summary = {}
        row.scanner_versions = {}
        session.execute(
            delete(SecurityFinding).where(SecurityFinding.assessment_id == row.id)
        )
        session.commit()
        session.refresh(row)
        return row
    generation = (
        session.execute(
            select(func.coalesce(func.max(SecurityAssessment.generation), 0)).where(
                SecurityAssessment.snapshot_id == snapshot_id
            )
        ).scalar_one()
        + 1
    )
    now = session.execute(select(func.now())).scalar_one()
    row = SecurityAssessment(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        project_id=project_id,
        snapshot_id=snapshot_id,
        job_id=job_id,
        generation=generation,
        status="running",
        policy_version=policy_version,
        summary={},
        scanner_versions={},
        ruleset_version=ruleset_version,
        started_at=now,
        created_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def mark_assessment(
    session: Session, assessment_id: uuid.UUID, status: str
) -> SecurityAssessment | None:
    """Set a terminal-ish status without findings (cancel/fail fast)."""
    if status not in ASSESSMENT_STATUSES:
        raise ApiError(422, "VALIDATION_ERROR", "The assessment status is not supported.")
    row = session.get(SecurityAssessment, assessment_id)
    if row is None:
        return None
    row.status = status
    row.completed_at = session.execute(select(func.now())).scalar_one()
    session.commit()
    session.refresh(row)
    return row


def store_assessment_result(
    session: Session,
    assessment_id: uuid.UUID,
    *,
    status: str,
    summary: dict,
    scanner_versions: dict,
    records: list[dict],
) -> SecurityAssessment:
    """Replace findings and close the assessment. Records are plain
    ``security_findings`` column dicts (worker maps its own types)."""
    if status not in ASSESSMENT_STATUSES:
        raise ApiError(422, "VALIDATION_ERROR", "The assessment status is not supported.")
    row = session.get(SecurityAssessment, assessment_id)
    if row is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "The assessment was not found.")
    session.execute(
        delete(SecurityFinding).where(SecurityFinding.assessment_id == assessment_id)
    )
    for record in records:
        session.add(SecurityFinding(assessment_id=assessment_id, **record))
    row.status = status
    row.summary = dict(summary)
    row.scanner_versions = dict(scanner_versions)
    row.completed_at = session.execute(select(func.now())).scalar_one()
    session.commit()
    session.refresh(row)
    logger.info(
        "assessment stored assessment_id=%s status=%s findings=%d",
        assessment_id,
        status,
        len(records),
    )
    return row


def _assessment_for_user(
    session: Session, user: User, assessment_id: uuid.UUID
) -> SecurityAssessment:
    from app.models import WorkspaceMember

    row = (
        session.execute(
            select(SecurityAssessment)
            .join(
                WorkspaceMember,
                WorkspaceMember.workspace_id == SecurityAssessment.workspace_id,
            )
            .where(
                SecurityAssessment.id == assessment_id,
                WorkspaceMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise not_found("assessment")
    return row


def get_assessment(session: Session, user: User, assessment_id: uuid.UUID) -> dict:
    return serialize_assessment(_assessment_for_user(session, user, assessment_id))


def get_snapshot_assessment(
    session: Session, user: User, snapshot_id: uuid.UUID
) -> dict:
    """Latest assessment generation for one snapshot (404 when none)."""
    from app.models import WorkspaceMember

    snapshot = (
        session.execute(
            select(RepositorySnapshot)
            .join(Project, Project.id == RepositorySnapshot.project_id)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Project.workspace_id)
            .where(
                RepositorySnapshot.id == snapshot_id,
                WorkspaceMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if snapshot is None:
        raise not_found("snapshot")
    row = (
        session.execute(
            select(SecurityAssessment)
            .where(SecurityAssessment.snapshot_id == snapshot_id)
            .order_by(desc(SecurityAssessment.generation))
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise not_found("assessment")
    return serialize_assessment(row)


def list_project_assessments(
    session: Session,
    user: User,
    project_id: uuid.UUID,
    limit: int,
    cursor: str | None,
) -> tuple[list[dict], str | None]:
    """Project assessments, newest first. Any workspace member may read."""
    from app.models import WorkspaceMember

    project = (
        session.execute(
            select(Project)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Project.workspace_id)
            .where(Project.id == project_id, WorkspaceMember.user_id == user.id)
        )
    ).scalar_one_or_none()
    if project is None:
        raise not_found("project")
    stmt = select(SecurityAssessment).where(SecurityAssessment.project_id == project_id)
    stmt = stmt.order_by(desc(SecurityAssessment.created_at), desc(SecurityAssessment.id))
    if cursor:
        position = decode_cursor(cursor)
        if position is None:
            raise ApiError(422, "VALIDATION_ERROR", "The cursor is invalid.")
        created_at, cursor_id = position
        stmt = stmt.where(
            or_(
                SecurityAssessment.created_at < created_at,
                and_(
                    SecurityAssessment.created_at == created_at,
                    SecurityAssessment.id < cursor_id,
                ),
            )
        )
    rows = list(session.execute(stmt.limit(limit + 1)).scalars())
    items = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last = items[-1]
        next_cursor = encode_cursor(last.created_at, last.id)
    return [serialize_assessment(row) for row in items], next_cursor


def list_findings(
    session: Session,
    user: User,
    assessment_id: uuid.UUID,
    limit: int,
    cursor: str | None,
    severity: str | None = None,
    scanner: str | None = None,
    category: str | None = None,
    path_prefix: str | None = None,
) -> tuple[list[dict], str | None]:
    """Assessment findings, newest first, with optional filters."""
    assessment = _assessment_for_user(session, user, assessment_id)
    if severity is not None and severity not in FINDING_SEVERITIES:
        raise ApiError(422, "VALIDATION_ERROR", "The severity filter is not supported.")
    if scanner is not None and scanner not in FINDING_SCANNERS:
        raise ApiError(422, "VALIDATION_ERROR", "The scanner filter is not supported.")
    stmt = select(SecurityFinding).where(SecurityFinding.assessment_id == assessment.id)
    if severity is not None:
        stmt = stmt.where(SecurityFinding.severity == severity)
    if scanner is not None:
        stmt = stmt.where(SecurityFinding.scanner == scanner)
    if category is not None:
        stmt = stmt.where(SecurityFinding.category == category)
    if path_prefix is not None:
        stmt = stmt.where(SecurityFinding.location["path"].astext.startswith(path_prefix))
    stmt = stmt.order_by(desc(SecurityFinding.created_at), desc(SecurityFinding.id))
    if cursor:
        position = decode_cursor(cursor)
        if position is None:
            raise ApiError(422, "VALIDATION_ERROR", "The cursor is invalid.")
        created_at, cursor_id = position
        stmt = stmt.where(
            or_(
                SecurityFinding.created_at < created_at,
                and_(
                    SecurityFinding.created_at == created_at,
                    SecurityFinding.id < cursor_id,
                ),
            )
        )
    rows = list(session.execute(stmt.limit(limit + 1)).scalars())
    items = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last = items[-1]
        next_cursor = encode_cursor(last.created_at, last.id)
    return [serialize_finding(row) for row in items], next_cursor
