"""Hypotheses (M7): candidate causes grounded in captured evidence.

Rows are written by the worker from schema-validated model output and
read by members with HATEOAS evidence links. Every referenced
artifact must belong to the same investigation — a model that cites
unknown evidence fails the sample instead of persisting fiction.
"""

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.envelope import ApiError, access_denied, not_found
from app.models import (
    EvidenceArtifact,
    Hypothesis,
    HypothesisEvidence,
    HypothesisReview,
    Project,
    User,
)
from app.services import audit as audit_service
from app.services import investigations as investigation_service
from app.services.activity import investigation_access
from app.services.model_gateway import HypothesisDraft

CONTRIBUTOR_ROLES = frozenset({"owner", "admin", "developer"})
REVIEW_VERDICTS = frozenset({"useful", "rejected", "needs_evidence"})
REVIEW_NOTE_MAX = 500


def _iso(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def _confidence(value: object) -> float | None:
    if value is None:
        return None
    return float(value)  # type: ignore[arg-type]


def serialize_review(row: HypothesisReview) -> dict:
    return {
        "id": str(row.id),
        "hypothesis_id": str(row.hypothesis_id),
        "reviewer_user_id": str(row.reviewer_user_id) if row.reviewer_user_id else None,
        "verdict": row.verdict,
        "note": row.note,
        "created_at": _iso(row.created_at),
    }


def serialize_hypothesis(
    row: Hypothesis, links: list[dict], reviews: list[dict] | None = None
) -> dict:
    return {
        "id": str(row.id),
        "title": row.title,
        "description": row.description,
        "confidence": _confidence(row.confidence),
        "status": row.status,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
        "links": {"evidence": links},
        "reviews": reviews if reviews is not None else [],
    }


def propose_hypotheses(
    session: Session,
    *,
    job_id: uuid.UUID,
    worker_id: str,
    investigation_id: uuid.UUID,
    stage_id: uuid.UUID,
    tool_run_id: uuid.UUID | None,
    drafts: list[HypothesisDraft],
) -> list[dict]:
    """Persist one validated model sample (trusted worker path)."""
    investigation_service.require_job_ownership(session, job_id, worker_id, investigation_id)
    if not drafts:
        raise ApiError(422, "MODEL_OUTPUT_INVALID", "The model proposed no hypotheses.")
    wanted: set[uuid.UUID] = set()
    for draft in drafts:
        for ref in draft.evidence_refs:
            try:
                wanted.add(uuid.UUID(ref.evidence_id))
            except (ValueError, TypeError, AttributeError):
                raise ApiError(
                    422, "MODEL_OUTPUT_INVALID", "A hypothesis cites invalid evidence."
                ) from None
    owned: dict[uuid.UUID, str] = {}
    if wanted:
        rows = list(
            session.execute(
                select(EvidenceArtifact.id, EvidenceArtifact.kind).where(
                    EvidenceArtifact.investigation_id == investigation_id,
                    EvidenceArtifact.id.in_(wanted),
                )
            )
        )
        owned = {row[0]: row[1] for row in rows}
        if set(owned) != wanted:
            raise ApiError(422, "MODEL_OUTPUT_INVALID", "A hypothesis cites unknown evidence.")
    now = investigation_service.db_now(session)
    created: list[dict] = []
    for draft in drafts:
        row = Hypothesis(
            id=uuid.uuid4(),
            investigation_id=investigation_id,
            created_by_stage_id=stage_id,
            tool_run_id=tool_run_id,
            title=draft.title,
            description=draft.description,
            confidence=draft.confidence,
            status="proposed",
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.flush()
        links: list[dict] = []
        for ref in draft.evidence_refs:
            artifact_id = uuid.UUID(ref.evidence_id)
            session.add(
                HypothesisEvidence(
                    hypothesis_id=row.id,
                    evidence_artifact_id=artifact_id,
                    relationship=ref.relationship,
                    note=ref.note,
                )
            )
            links.append(
                {
                    "evidence_id": str(artifact_id),
                    "kind": owned[artifact_id],
                    "relationship": ref.relationship,
                }
            )
        created.append(serialize_hypothesis(row, links))
    session.commit()
    return created


def list_hypotheses(session: Session, user: User, investigation_id: uuid.UUID) -> list[dict]:
    """Proposed causes with evidence links, oldest first."""
    inv, _role = investigation_access(session, user, investigation_id)
    rows = list(
        session.execute(
            select(Hypothesis)
            .where(Hypothesis.investigation_id == inv.id)
            .order_by(Hypothesis.created_at.asc(), Hypothesis.id.asc())
        ).scalars()
    )
    if not rows:
        return []
    link_rows = list(
        session.execute(
            select(
                HypothesisEvidence.hypothesis_id,
                HypothesisEvidence.evidence_artifact_id,
                HypothesisEvidence.relationship,
                EvidenceArtifact.kind,
            )
            .join(EvidenceArtifact, EvidenceArtifact.id == HypothesisEvidence.evidence_artifact_id)
            .where(HypothesisEvidence.hypothesis_id.in_([row.id for row in rows]))
        )
    )
    by_hypothesis: dict[uuid.UUID, list[dict]] = {}
    for hypothesis_id, artifact_id, relationship, kind in link_rows:
        by_hypothesis.setdefault(hypothesis_id, []).append(
            {"evidence_id": str(artifact_id), "kind": kind, "relationship": relationship}
        )
    reviews = _reviews_by_hypothesis(session, [row.id for row in rows])
    return [
        serialize_hypothesis(row, by_hypothesis.get(row.id, []), reviews.get(row.id, []))
        for row in rows
    ]


def _reviews_by_hypothesis(
    session: Session, hypothesis_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[dict]]:
    """Review histories, oldest first, for the given hypotheses."""
    if not hypothesis_ids:
        return {}
    rows = list(
        session.execute(
            select(HypothesisReview)
            .where(HypothesisReview.hypothesis_id.in_(hypothesis_ids))
            .order_by(HypothesisReview.created_at.asc(), HypothesisReview.id.asc())
        ).scalars()
    )
    grouped: dict[uuid.UUID, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row.hypothesis_id, []).append(serialize_review(row))
    return grouped


def get_hypothesis(session: Session, user: User, hypothesis_id: uuid.UUID) -> dict:
    """One hypothesis with evidence links and review history. Members read."""
    row = session.get(Hypothesis, hypothesis_id)
    if row is None:
        raise not_found("hypothesis")
    investigation_access(session, user, row.investigation_id)
    link_rows = list(
        session.execute(
            select(
                HypothesisEvidence.evidence_artifact_id,
                HypothesisEvidence.relationship,
                EvidenceArtifact.kind,
            )
            .join(EvidenceArtifact, EvidenceArtifact.id == HypothesisEvidence.evidence_artifact_id)
            .where(HypothesisEvidence.hypothesis_id == row.id)
        )
    )
    links = [
        {"evidence_id": str(artifact_id), "kind": kind, "relationship": relationship}
        for artifact_id, relationship, kind in link_rows
    ]
    reviews = _reviews_by_hypothesis(session, [row.id]).get(row.id, [])
    return serialize_hypothesis(row, links, reviews)


def review_hypothesis(
    session: Session,
    user: User,
    hypothesis_id: uuid.UUID,
    verdict: str,
    note: str | None,
    request_id: str,
) -> dict:
    """Append a user verdict. Contributors write; viewers read only."""
    if verdict not in REVIEW_VERDICTS:
        raise ApiError(422, "VALIDATION_ERROR", "The review verdict is invalid.")
    clean_note = (note or "").strip() or None
    if clean_note is not None and len(clean_note) > REVIEW_NOTE_MAX:
        raise ApiError(422, "VALIDATION_ERROR", "The review note is too long.")
    row = session.get(Hypothesis, hypothesis_id)
    if row is None:
        raise not_found("hypothesis")
    inv, role = investigation_access(session, user, row.investigation_id)
    if role not in CONTRIBUTOR_ROLES:
        raise access_denied()
    review = HypothesisReview(
        id=uuid.uuid4(),
        hypothesis_id=row.id,
        reviewer_user_id=user.id,
        verdict=verdict,
        note=clean_note,
    )
    session.add(review)
    session.commit()
    session.refresh(review)
    project = session.get(Project, inv.project_id)
    assert project is not None
    audit_service.append_audit(
        session,
        workspace_id=project.workspace_id,
        actor_type="user",
        action=audit_service.ACTION_HYPOTHESIS_REVIEWED,
        resource_type="hypothesis",
        resource_id=row.id,
        actor=user,
        request_id=request_id,
        metadata={"verdict": verdict},
    )
    return serialize_review(review)


def hypothesis_count(session: Session, investigation_id: uuid.UUID) -> int:
    from sqlalchemy import func

    return (
        session.execute(select(func.count()).where(Hypothesis.investigation_id == investigation_id))
    ).scalar_one()
