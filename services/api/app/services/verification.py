"""Verification runs and checks (M8): trusted test execution records.

Only the worker writes runs and checks, and only `passed` comes from
actually executed commands — a run with no executed checks must never
read `passed`. Members read runs with their check detail; nothing here
mutates repository state.
"""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.envelope import ApiError, access_denied, not_found
from app.models import (
    Investigation,
    Project,
    RegressionTest,
    User,
    VerificationCheck,
    VerificationRun,
    WorkspaceMember,
)
from app.services import investigations as investigation_service
from app.services.activity import db_now, investigation_access

RUN_STATUSES = (
    "queued",
    "running",
    "passed",
    "failed",
    "blocked",
    "timed_out",
    "cancelled",
    "inconclusive",
)
RUN_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "cancelled"}),
    "running": frozenset({"passed", "failed", "blocked", "timed_out", "cancelled", "inconclusive"}),
    "passed": frozenset(),
    "failed": frozenset(),
    "blocked": frozenset(),
    "timed_out": frozenset(),
    "cancelled": frozenset(),
    "inconclusive": frozenset(),
}
CHECK_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "skipped", "cancelled"}),
    "running": frozenset(
        {"passed", "failed", "blocked", "timed_out", "skipped", "cancelled", "inconclusive"}
    ),
    "passed": frozenset(),
    "failed": frozenset(),
    "blocked": frozenset(),
    "timed_out": frozenset(),
    "skipped": frozenset(),
    "cancelled": frozenset(),
    "inconclusive": frozenset(),
}
EXECUTED_CHECK = frozenset({"passed", "failed", "timed_out", "inconclusive"})
CHECK_STATUSES = (
    "queued",
    "running",
    "passed",
    "failed",
    "blocked",
    "timed_out",
    "skipped",
    "cancelled",
    "inconclusive",
)

CONTRIBUTOR_ROLES = frozenset({"owner", "admin", "developer"})

# Execution profiles the M9 verifier supports. Static snapshots only,
# mirroring the inspection stage; new profiles extend this tuple.
VERIFICATION_PROFILES = ("static",)

# Regression-test statuses a new run may execute: never-run tests plus
# baseline failures gating a patch. Terminal verdicts (post-patch rows)
# cannot transition again, so they are never selected.
RUNNABLE_TEST_STATUSES = ("created", "baseline_failed")

# Phases the worker may bind a run to (model CHECK parity).
RUN_PHASES = ("baseline", "post_patch", "regression_test", "diagnostic")


def derive_verdict(statuses: list[str]) -> str:
    """Map recorded check statuses to one run status (M9 verdict engine).

    Deterministic and total: any required failure fails the gate, a
    timed-out gate reads timed out, a run with no executed checks never
    passes (blocked-only plans read blocked), and skipped or blocked
    required checks withhold a pass. Unknown statuses fail closed to
    inconclusive instead of passing.
    """
    if any(status == "failed" for status in statuses):
        return "failed"
    if any(status == "timed_out" for status in statuses):
        return "timed_out"
    if any(status not in CHECK_STATUSES for status in statuses):
        return "inconclusive"
    if not any(status in EXECUTED_CHECK for status in statuses):
        if any(status == "blocked" for status in statuses):
            return "blocked"
        return "inconclusive"
    if any(status == "blocked" for status in statuses):
        return "blocked"
    if any(status in ("skipped", "cancelled", "queued", "running") for status in statuses):
        return "inconclusive"
    if any(status == "inconclusive" for status in statuses):
        return "inconclusive"
    return "passed"


def plan_checks(session: Session, investigation_id: uuid.UUID) -> dict:
    """Deterministic check plan: runnable regression tests + profiles.

    Label-only (M9): returns the required checks without writing rows or
    executing anything. Callers persist the plan on a new run
    (``runtime_profile.planned_checks``) or as stage output.
    """
    from app.services import regression_tests as regression_test_service

    rows = list(
        session.execute(
            select(RegressionTest)
            .where(RegressionTest.investigation_id == investigation_id)
            .order_by(RegressionTest.created_at.asc(), RegressionTest.id.asc())
        ).scalars()
    )
    required = []
    for row in rows:
        runnable = (
            row.status in RUNNABLE_TEST_STATUSES
            and row.test_type in regression_test_service.EXECUTABLE_TYPES
            and row.created_artifact_id is not None
        )
        required.append(
            {
                "check_key": str(row.id),
                "display_name": row.title[:300],
                "test_id": str(row.id),
                "status": row.status,
                "runnable": runnable,
            }
        )
    return {
        "required_checks": required,
        "profiles": list(VERIFICATION_PROFILES),
        "test_count": len(rows),
        "runnable_count": sum(1 for check in required if check["runnable"]),
    }


def _iso(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def serialize_check(row: VerificationCheck) -> dict:
    return {
        "id": str(row.id),
        "check_key": row.check_key,
        "display_name": row.display_name,
        "status": row.status,
        "exit_code": row.exit_code,
        "stdout_artifact_id": str(row.stdout_artifact_id) if row.stdout_artifact_id else None,
        "stderr_artifact_id": str(row.stderr_artifact_id) if row.stderr_artifact_id else None,
        "duration_ms": row.duration_ms,
        "started_at": _iso(row.started_at),
        "finished_at": _iso(row.finished_at),
        "created_at": _iso(row.created_at),
    }


def serialize_run(row: VerificationRun, checks: list[dict] | None = None) -> dict:
    data: dict[str, Any] = {
        "id": str(row.id),
        "phase": row.phase,
        "status": row.status,
        "patch_id": str(row.patch_id) if row.patch_id else None,
        "repository_snapshot_id": str(row.repository_snapshot_id),
        "runner_image": row.runner_image,
        "runtime_profile": dict(row.runtime_profile or {}),
        "duration_ms": row.duration_ms,
        "summary": row.summary,
        "started_at": _iso(row.started_at),
        "finished_at": _iso(row.finished_at),
        "created_at": _iso(row.created_at),
    }
    if checks is not None:
        data["checks"] = checks
    return data


def start_run(
    session: Session,
    *,
    job_id: uuid.UUID,
    worker_id: str,
    investigation_id: uuid.UUID,
    project_id: uuid.UUID,
    patch_id: uuid.UUID | None,
    snapshot_id: uuid.UUID,
    stage_id: uuid.UUID,
    phase: str,
    runner_image: str,
    runtime_profile: dict,
) -> uuid.UUID:
    """Open one running verification run (trusted worker path)."""
    investigation_service.require_job_ownership(session, job_id, worker_id, investigation_id)
    if phase not in RUN_PHASES:
        raise ApiError(422, "VALIDATION_ERROR", "The verification phase is not supported.")
    now = db_now(session)
    row = VerificationRun(
        id=uuid.uuid4(),
        investigation_id=investigation_id,
        project_id=project_id,
        patch_id=patch_id,
        repository_snapshot_id=snapshot_id,
        created_by_stage_id=stage_id,
        phase=phase,
        status="running",
        runner_image=runner_image[:500],
        runtime_profile=dict(runtime_profile),
        started_at=now,
        created_at=now,
    )
    session.add(row)
    session.commit()
    return row.id


def record_check(
    session: Session,
    *,
    run_id: uuid.UUID,
    check_key: str,
    display_name: str,
    status: str,
    regression_test_id: uuid.UUID | None = None,
    command_fingerprint: str = "",
    exit_code: int | None = None,
    stdout_artifact_id: uuid.UUID | None = None,
    stderr_artifact_id: uuid.UUID | None = None,
    duration_ms: int | None = None,
) -> dict:
    """Record one terminal check (trusted worker path, upsert by key)."""
    if status not in EXECUTED_CHECK and status not in ("blocked", "skipped", "cancelled"):
        raise ApiError(422, "VALIDATION_ERROR", "The check status is not supported.")
    run = session.get(VerificationRun, run_id)
    if run is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "The verification run was not found.")
    if run.status not in ("queued", "running"):
        raise ApiError(409, "INVALID_STATE", "The verification run is already finished.")
    row = (
        session.execute(
            select(VerificationCheck).where(
                VerificationCheck.verification_run_id == run_id,
                VerificationCheck.check_key == check_key,
            )
        )
    ).scalar_one_or_none()
    now = db_now(session)
    if row is None:
        row = VerificationCheck(
            id=uuid.uuid4(),
            verification_run_id=run_id,
            regression_test_id=regression_test_id,
            check_key=check_key[:200],
            display_name=display_name[:300],
            status=status,
            command_fingerprint=command_fingerprint[:500] or "unspecified",
            exit_code=exit_code,
            stdout_artifact_id=stdout_artifact_id,
            stderr_artifact_id=stderr_artifact_id,
            started_at=now,
            finished_at=now,
            duration_ms=duration_ms,
            created_at=now,
        )
        session.add(row)
    else:
        if status not in CHECK_TRANSITIONS.get(row.status, frozenset()):
            raise ApiError(409, "INVALID_TRANSITION", "The check cannot change.")
        row.status = status
        row.exit_code = exit_code
        row.stdout_artifact_id = stdout_artifact_id
        row.stderr_artifact_id = stderr_artifact_id
        row.finished_at = now
        row.duration_ms = duration_ms
    session.commit()
    session.refresh(row)
    return serialize_check(row)


def finish_run(session: Session, *, run_id: uuid.UUID, status: str, summary: str | None) -> dict:
    """Finish one run. `passed` requires an executed check (never empty)."""
    row = session.get(VerificationRun, run_id)
    if row is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "The verification run was not found.")
    if status not in RUN_TRANSITIONS.get(row.status, frozenset()):
        raise ApiError(409, "INVALID_TRANSITION", "The run cannot change.")
    if status == "passed":
        executed = (
            session.execute(
                select(func.count()).where(
                    VerificationCheck.verification_run_id == run_id,
                    VerificationCheck.status.in_(EXECUTED_CHECK),
                )
            )
        ).scalar_one()
        if not executed:
            raise ApiError(409, "INVALID_STATE", "A run with no executed checks cannot pass.")
    now = db_now(session)
    row.status = status
    row.summary = (summary or "")[:2000] or None
    row.finished_at = now
    if row.started_at is not None:
        row.duration_ms = max(0, int((now - row.started_at).total_seconds() * 1000))
    session.commit()
    session.refresh(row)
    return serialize_run(row)


def create_run(
    session: Session,
    user: User,
    investigation_id: uuid.UUID,
    selected_check_keys: list[str] | None,
) -> dict:
    """Queue one NEW verification run (user rerun path, M9).

    Run history is append-only: this never touches existing runs — every
    rerun is a fresh queued row carrying its check plan as labels. The
    worker adopts the newest queued plan on its next verification leg
    (see ``adopt_queued_run``); only the worker moves runs to terminal.
    """
    inv, role = investigation_access(session, user, investigation_id)
    if role not in CONTRIBUTOR_ROLES:
        raise access_denied()
    if inv.repository_snapshot_id is None:
        raise ApiError(409, "SNAPSHOT_MISSING", "The investigation has no snapshot to verify.")
    plan = plan_checks(session, inv.id)
    by_key = {check["check_key"]: check for check in plan["required_checks"]}
    if selected_check_keys:
        selected: list[str] = []
        for raw in selected_check_keys:
            try:
                test_id = uuid.UUID((raw or "").strip())
            except (ValueError, TypeError, AttributeError):
                raise ApiError(
                    422, "VALIDATION_ERROR", "One of the selected checks is invalid."
                ) from None
            check = by_key.get(str(test_id))
            if check is None:
                raise not_found("regression_test")
            if not check["runnable"]:
                raise ApiError(
                    422,
                    "CHECK_NOT_RUNNABLE",
                    f"One of the selected checks cannot run (test {check['display_name'][:80]}).",
                )
            if str(test_id) not in selected:
                selected.append(str(test_id))
    else:
        selected = [check["check_key"] for check in plan["required_checks"] if check["runnable"]]
    if not selected:
        raise ApiError(
            409, "NO_EXECUTABLE_TESTS", "No runnable regression test is available for a new run."
        )
    now = db_now(session)
    row = VerificationRun(
        id=uuid.uuid4(),
        investigation_id=inv.id,
        project_id=inv.project_id,
        patch_id=None,
        repository_snapshot_id=inv.repository_snapshot_id,
        created_by_stage_id=None,
        phase="regression_test",
        status="queued",
        runner_image=None,
        runtime_profile={
            "requested_by": "user",
            "requested_by_user_id": str(user.id),
            "profiles": list(VERIFICATION_PROFILES),
            "selected_check_keys": selected,
            "planned_checks": [
                {"check_key": key, "display_name": by_key[key]["display_name"]} for key in selected
            ],
        },
        started_at=None,
        finished_at=None,
        duration_ms=None,
        summary=None,
        created_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return serialize_run(row, [])


def adopt_queued_run(
    session: Session,
    *,
    job_id: uuid.UUID,
    worker_id: str,
    investigation_id: uuid.UUID,
    project_id: uuid.UUID,
    patch_id: uuid.UUID | None,
    snapshot_id: uuid.UUID,
    stage_id: uuid.UUID,
    phase: str,
    runner_image: str,
    runtime_profile: dict,
) -> dict | None:
    """Claim the newest user-queued plan for one verification leg (worker).

    Returns the run id plus the requested check subset, or None when no
    queued plan exists (the caller falls back to ``start_run``). Claiming
    binds the run to this leg: stage, snapshot, patch, phase, runner.
    """
    investigation_service.require_job_ownership(session, job_id, worker_id, investigation_id)
    if phase not in RUN_PHASES:
        raise ApiError(422, "VALIDATION_ERROR", "The verification phase is not supported.")
    row = (
        session.execute(
            select(VerificationRun)
            .where(
                VerificationRun.investigation_id == investigation_id,
                VerificationRun.project_id == project_id,
                VerificationRun.status == "queued",
                VerificationRun.created_by_stage_id.is_(None),
            )
            .order_by(VerificationRun.created_at.desc(), VerificationRun.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    profile = dict(row.runtime_profile or {})
    selected = profile.get("selected_check_keys")
    if not isinstance(selected, list) or not all(isinstance(key, str) for key in selected):
        selected = None
    planned = profile.get("planned_checks")
    planned_total = len(planned) if isinstance(planned, list) else None
    now = db_now(session)
    row.status = "running"
    row.created_by_stage_id = stage_id
    row.patch_id = patch_id
    row.repository_snapshot_id = snapshot_id
    row.phase = phase
    row.runner_image = runner_image[:500]
    row.runtime_profile = {
        **profile,
        **dict(runtime_profile),
        "selected_check_keys": selected,
        "adopted_from_queue": True,
    }
    row.started_at = now
    session.commit()
    return {"run_id": row.id, "selected_check_keys": selected, "planned_total": planned_total}


def comparison(session: Session, user: User, investigation_id: uuid.UUID) -> dict:
    """Baseline-vs-post-patch results per regression test (M9)."""
    inv, _role = investigation_access(session, user, investigation_id)
    tests = list(
        session.execute(
            select(RegressionTest)
            .where(RegressionTest.investigation_id == inv.id)
            .order_by(RegressionTest.created_at.asc(), RegressionTest.id.asc())
        ).scalars()
    )
    latest: dict[tuple[uuid.UUID, str], dict] = {}
    if tests:
        rows = list(
            session.execute(
                select(VerificationCheck, VerificationRun.phase, VerificationRun.status)
                .join(VerificationRun, VerificationRun.id == VerificationCheck.verification_run_id)
                .where(
                    VerificationRun.investigation_id == inv.id,
                    VerificationCheck.regression_test_id.in_([test.id for test in tests]),
                )
                .order_by(VerificationCheck.created_at.desc(), VerificationCheck.id.desc())
            )
        )
        for check, phase, run_status in rows:
            assert check.regression_test_id is not None
            key = (check.regression_test_id, phase)
            if key not in latest:
                latest[key] = {
                    "check_status": check.status,
                    "run_status": run_status,
                    "exit_code": check.exit_code,
                    "duration_ms": check.duration_ms,
                    "created_at": _iso(check.created_at),
                }
    return {
        "investigation_id": str(inv.id),
        "tests": [
            {
                "test_id": str(test.id),
                "title": test.title,
                "status": test.status,
                "baseline": latest.get((test.id, "baseline")),
                "post_patch": latest.get((test.id, "post_patch")),
            }
            for test in tests
        ],
    }


def list_runs(session: Session, user: User, investigation_id: uuid.UUID) -> list[dict]:
    """Newest-first runs with their check detail."""
    inv, _role = investigation_access(session, user, investigation_id)
    runs = list(
        session.execute(
            select(VerificationRun)
            .where(VerificationRun.investigation_id == inv.id)
            .order_by(VerificationRun.created_at.desc(), VerificationRun.id.desc())
        ).scalars()
    )
    if not runs:
        return []
    checks = list(
        session.execute(
            select(VerificationCheck)
            .where(VerificationCheck.verification_run_id.in_([row.id for row in runs]))
            .order_by(VerificationCheck.created_at.asc(), VerificationCheck.id.asc())
        ).scalars()
    )
    by_run: dict[uuid.UUID, list[dict]] = {}
    for check in checks:
        by_run.setdefault(check.verification_run_id, []).append(serialize_check(check))
    return [serialize_run(row, by_run.get(row.id, [])) for row in runs]


def get_run(session: Session, user: User, run_id: uuid.UUID) -> dict:
    """One run with checks. 404 for foreign."""
    row = (
        session.execute(
            select(VerificationRun)
            .join(Investigation, Investigation.id == VerificationRun.investigation_id)
            .join(Project, Project.id == Investigation.project_id)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Project.workspace_id)
            .where(VerificationRun.id == run_id, WorkspaceMember.user_id == user.id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise not_found("verification_run")
    checks = list(
        session.execute(
            select(VerificationCheck)
            .where(VerificationCheck.verification_run_id == row.id)
            .order_by(VerificationCheck.created_at.asc(), VerificationCheck.id.asc())
        ).scalars()
    )
    return serialize_run(row, [serialize_check(check) for check in checks])


def run_count(session: Session, investigation_id: uuid.UUID) -> int:
    return (
        session.execute(
            select(func.count()).where(VerificationRun.investigation_id == investigation_id)
        )
    ).scalar_one()
