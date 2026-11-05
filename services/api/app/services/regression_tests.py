"""Regression tests (M8): executable e2e checks with verified history.

Tests are proposed (by users as metadata or by the worker with
executable step artifacts) and driven through baseline/post-patch
verdicts by trusted stages only. A test is never reported passing
without a corresponding verification check row.
"""

import datetime as dt
import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.envelope import ApiError, access_denied
from app.models import EvidenceArtifact, RegressionTest, User, VerificationCheck, VerificationRun
from app.services import evidence as evidence_service
from app.services import investigations as investigation_service
from app.services.activity import db_now, investigation_access
from app.services.model_gateway import RegressionTestDraft
from app.services.patch_paths import check_repo_path

CONTRIBUTOR_ROLES = frozenset({"owner", "admin", "developer"})
TEST_TYPES = ("unit", "integration", "e2e", "regression", "manual")
EXECUTABLE_TYPES = ("e2e",)
TEST_TRANSITIONS: dict[str, frozenset[str]] = {
    "proposed": frozenset({"created", "blocked", "not_run"}),
    "created": frozenset({"baseline_passed", "baseline_failed", "blocked", "not_run"}),
    "baseline_passed": frozenset({"blocked", "not_run"}),
    "baseline_failed": frozenset({"post_patch_passed", "post_patch_failed", "blocked", "not_run"}),
    "post_patch_passed": frozenset(),
    "post_patch_failed": frozenset(),
    "blocked": frozenset({"not_run"}),
    "not_run": frozenset(),
}


def _iso(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def serialize_test(row: RegressionTest, history: list[dict] | None = None) -> dict:
    data: dict[str, Any] = {
        "id": str(row.id),
        "title": row.title,
        "description": row.description,
        "test_type": row.test_type,
        "status": row.status,
        "file_path": row.file_path,
        "test_name": row.test_name,
        "created_artifact_id": str(row.created_artifact_id) if row.created_artifact_id else None,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }
    # Always present (empty for fresh rows) so readers never branch.
    data["verification_history"] = history if history is not None else []
    return data


def create_proposed(
    session: Session,
    user: User,
    investigation_id: uuid.UUID,
    title: str,
    description: str | None,
    test_type: str,
    file_path: str | None,
    test_name: str | None,
) -> dict:
    """Synchronous metadata-only creation (API 201, MVP flow)."""
    inv, role = investigation_access(session, user, investigation_id)
    if role not in CONTRIBUTOR_ROLES:
        raise access_denied()
    if inv.status in investigation_service.TERMINAL_STATUSES:
        raise ApiError(409, "INVALID_STATE", "A terminal investigation takes no new tests.")
    clean_title = (title or "").strip()
    if not 1 <= len(clean_title) <= 200:
        raise ApiError(422, "VALIDATION_ERROR", "The test title is invalid.")
    if description is not None and (not isinstance(description, str) or len(description) > 2000):
        raise ApiError(422, "VALIDATION_ERROR", "The test description is invalid.")
    if test_type not in TEST_TYPES:
        raise ApiError(422, "VALIDATION_ERROR", "The test type is not supported.")
    clean_path = check_repo_path(file_path, "The file path") if file_path else None
    if test_name is not None and (not isinstance(test_name, str) or not 1 <= len(test_name) <= 300):
        raise ApiError(422, "VALIDATION_ERROR", "The test name is invalid.")
    now = db_now(session)
    row = RegressionTest(
        id=uuid.uuid4(),
        investigation_id=inv.id,
        title=clean_title,
        description=description.strip() if description else None,
        test_type=test_type,
        status="proposed",
        file_path=clean_path,
        test_name=test_name,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return serialize_test(row)


def create_from_drafts(
    session: Session,
    *,
    job_id: uuid.UUID,
    worker_id: str,
    investigation_id: uuid.UUID,
    stage_id: uuid.UUID,
    tool_run_id: uuid.UUID | None,
    project_id: uuid.UUID,
    drafts: list[RegressionTestDraft],
    store=None,
) -> list[dict]:
    """Persist validated model tests with executable artifacts (worker)."""
    investigation_service.require_job_ownership(session, job_id, worker_id, investigation_id)
    created: list[dict] = []
    for draft in drafts:
        blob = json.dumps(
            {"steps": list(draft.steps)}, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        record = evidence_service.create_evidence(
            session,
            project_id=project_id,
            investigation_id=investigation_id,
            tool_run_id=tool_run_id,
            kind="other",
            data=blob,
            filename_hint="test.json",
            redaction_status="not_required",
            metadata={"source": "regression_test_creation", "title": draft.title},
            store=store,
        )
        now = db_now(session)
        row = RegressionTest(
            id=uuid.uuid4(),
            investigation_id=investigation_id,
            created_by_stage_id=stage_id,
            tool_run_id=tool_run_id,
            title=draft.title,
            description=draft.description,
            test_type=draft.test_type,
            status="created",
            file_path=draft.file_path,
            test_name=draft.test_name,
            created_artifact_id=uuid.UUID(record["id"]),
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        created.append(serialize_test(row))
    return created


def transition_test(session: Session, test_id: uuid.UUID, status: str) -> None:
    """Move one test along the lifecycle (trusted worker path)."""
    row = session.get(RegressionTest, test_id)
    if row is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "The regression test was not found.")
    if status not in TEST_TRANSITIONS.get(row.status, frozenset()):
        raise ApiError(409, "INVALID_TRANSITION", f"Cannot move test {row.title[:40]} to {status}.")
    row.status = status
    row.updated_at = db_now(session)
    session.commit()


def list_tests(session: Session, user: User, investigation_id: uuid.UUID) -> list[dict]:
    """Proposed tests with latest execution summaries."""
    inv, _role = investigation_access(session, user, investigation_id)
    rows = list(
        session.execute(
            select(RegressionTest)
            .where(RegressionTest.investigation_id == inv.id)
            .order_by(RegressionTest.created_at.asc(), RegressionTest.id.asc())
        ).scalars()
    )
    histories = _histories(session, [row.id for row in rows])
    return [serialize_test(row, histories.get(row.id, [])) for row in rows]


def get_test(session: Session, user: User, test_id: uuid.UUID) -> dict:
    """One test with linked verification history."""
    row = session.get(RegressionTest, test_id)
    if row is None:
        from app.envelope import not_found

        raise not_found("regression_test")
    investigation_access(session, user, row.investigation_id)
    histories = _histories(session, [row.id])
    return serialize_test(row, histories.get(row.id, []))


def executable_tests(session: Session, investigation_id: uuid.UUID) -> list[RegressionTest]:
    """Created e2e tests with artifacts, in creation order."""
    return list(
        session.execute(
            select(RegressionTest)
            .where(
                RegressionTest.investigation_id == investigation_id,
                RegressionTest.status == "created",
                RegressionTest.test_type.in_(EXECUTABLE_TYPES),
                RegressionTest.created_artifact_id.is_not(None),
            )
            .order_by(RegressionTest.created_at.asc(), RegressionTest.id.asc())
        ).scalars()
    )


def gated_tests(session: Session, investigation_id: uuid.UUID) -> list[RegressionTest]:
    """Baseline-failed e2e tests with artifacts, in creation order."""
    return list(
        session.execute(
            select(RegressionTest)
            .where(
                RegressionTest.investigation_id == investigation_id,
                RegressionTest.status == "baseline_failed",
                RegressionTest.test_type.in_(EXECUTABLE_TYPES),
                RegressionTest.created_artifact_id.is_not(None),
            )
            .order_by(RegressionTest.created_at.asc(), RegressionTest.id.asc())
        ).scalars()
    )


def load_artifact_steps(session: Session, row: RegressionTest, store=None) -> dict:
    """Fetch and validate a test's executable steps (worker path)."""
    from app.config import get_settings
    from app.services import repro_spec

    if row.created_artifact_id is None:
        raise ApiError(409, "TEST_NOT_EXECUTABLE", "The test has no executable artifact.")
    artifact = session.get(EvidenceArtifact, row.created_artifact_id)
    if artifact is None:
        raise ApiError(409, "TEST_NOT_EXECUTABLE", "The test artifact is missing.")
    active_store = store or evidence_service.get_store()
    settings = get_settings()
    raw = active_store.get_bytes(settings.s3_evidence_bucket, artifact.storage_key)
    try:
        document = json.loads(raw.decode("utf-8"))
        steps = document["steps"]
    except (UnicodeDecodeError, ValueError, KeyError, TypeError) as exc:
        raise ApiError(409, "TEST_NOT_EXECUTABLE", "The test artifact is invalid.") from exc
    if not isinstance(steps, list) or not steps:
        raise ApiError(409, "TEST_NOT_EXECUTABLE", "The test artifact is invalid.")
    return {
        "route": "/",
        "browser": "chromium",
        "viewport": {"width": 1440, "height": 900},
        "steps": [repro_spec.validate_step(step, settings) for step in steps],
    }


def _histories(session: Session, test_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[dict]]:
    if not test_ids:
        return {}
    rows = list(
        session.execute(
            select(VerificationCheck, VerificationRun.phase, VerificationRun.status)
            .join(VerificationRun, VerificationRun.id == VerificationCheck.verification_run_id)
            .where(VerificationCheck.regression_test_id.in_(test_ids))
            .order_by(VerificationCheck.created_at.asc(), VerificationCheck.id.asc())
        )
    )
    histories: dict[uuid.UUID, list[dict]] = {}
    for check, phase, run_status in rows:
        assert check.regression_test_id is not None
        histories.setdefault(check.regression_test_id, []).append(
            {
                "phase": phase,
                "run_status": run_status,
                "check_status": check.status,
                "display_name": check.display_name,
                "created_at": _iso(check.created_at),
            }
        )
    return histories
