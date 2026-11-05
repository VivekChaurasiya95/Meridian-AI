"""M9 verification-engine tests: verdicts, reruns, adoption, comparison.

Pure verdict/schema/route-table tests run anywhere; HTTP and worker
service tests need PostgreSQL (CI) with faked object storage.
"""

import io
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.envelope import ApiError
from app.models import VerificationRun
from app.schemas import VerificationRunCreate
from app.services import evidence as evidence_service
from app.services import ingestion as ingestion_service
from app.services import investigations as investigation_service
from app.services import jobs as job_service
from app.services import storage as storage_service
from app.services import verification as verification_service
from app.services.model_gateway import RegressionTestDraft
from app.services.object_store import FakeObjectStore


@pytest.fixture()
def fake_store(monkeypatch: pytest.MonkeyPatch) -> FakeObjectStore:
    store = FakeObjectStore()
    monkeypatch.setattr(ingestion_service, "_default_store", lambda: store)
    monkeypatch.setattr(storage_service, "get_store", lambda: store)
    monkeypatch.setattr(evidence_service, "get_store", lambda: store)
    return store


def _setup(auth_client: TestClient, slug: str) -> dict:
    workspace = auth_client.post("/api/v1/workspaces", json={"name": slug, "slug": slug}).json()[
        "data"
    ]
    project = auth_client.post(
        f"/api/v1/workspaces/{workspace['id']}/projects",
        json={"name": slug, "slug": slug},
    ).json()["data"]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("index.html", "<h1>x</h1>")
    snapshot = auth_client.post(
        f"/api/v1/projects/{project['id']}/source-uploads",
        files={"file": ("r.zip", buffer.getvalue(), "application/zip")},
    ).json()["data"]["snapshot"]
    inv = auth_client.post(
        f"/api/v1/projects/{project['id']}/investigations",
        json={
            "title": "t",
            "bug_report": "b",
            "repository_snapshot_id": snapshot["id"],
            "reproduction_context": {
                "route": "/",
                "steps": [{"action": "assert_text", "selector": "h1", "text": "x"}],
            },
        },
    ).json()["data"]
    return {"workspace": workspace, "project": project, "snapshot": snapshot, "inv": inv}


def _claim(db_session_factory, worker: str = "w-m9"):  # type: ignore[no-untyped-def]
    session: Session = db_session_factory()
    try:
        claimed = job_service.claim_job(session, worker, ("investigation",), 60)
        assert claimed is not None
        return claimed
    finally:
        session.close()


def _stage_id(db_session_factory, claimed, inv_id: str, key: str) -> uuid.UUID:  # type: ignore[no-untyped-def]
    session: Session = db_session_factory()
    try:
        attempt = investigation_service.start_stage_attempt(
            session,
            job_id=uuid.UUID(claimed["id"]),
            worker_id="w-m9",
            investigation_id=uuid.UUID(inv_id),
            stage_key=key,
        )
        return uuid.UUID(attempt["id"])
    finally:
        session.close()


def _make_runnable(db_session_factory, fake_store, claimed, env, title: str = "T") -> dict:  # type: ignore[no-untyped-def]
    from app.services import regression_tests as regression_test_service

    stage_id = _stage_id(db_session_factory, claimed, env["inv"]["id"], "regression_test_creation")
    session: Session = db_session_factory()
    try:
        created = regression_test_service.create_from_drafts(
            session,
            job_id=uuid.UUID(claimed["id"]),
            worker_id="w-m9",
            investigation_id=uuid.UUID(env["inv"]["id"]),
            stage_id=stage_id,
            tool_run_id=None,
            project_id=uuid.UUID(env["project"]["id"]),
            drafts=[
                RegressionTestDraft(
                    title=title,
                    description=None,
                    test_type="e2e",
                    file_path="tests/t.spec",
                    test_name="t",
                    steps=({"action": "assert_text", "selector": "h1", "text": "x"},),
                )
            ],
            store=fake_store,
        )
        return created[0]
    finally:
        session.close()


def _start_run(db_session_factory, claimed, env, stage_id: uuid.UUID, phase: str):  # type: ignore[no-untyped-def]
    session: Session = db_session_factory()
    try:
        return verification_service.start_run(
            session,
            job_id=uuid.UUID(claimed["id"]),
            worker_id="w-m9",
            investigation_id=uuid.UUID(env["inv"]["id"]),
            project_id=uuid.UUID(env["project"]["id"]),
            patch_id=None,
            snapshot_id=uuid.UUID(env["snapshot"]["id"]),
            stage_id=stage_id,
            phase=phase,
            runner_image="img",
            runtime_profile={"profile": "static"},
        )
    finally:
        session.close()


# Pure verdict matrix (no sockets, no database).


def test_verdict_all_pass() -> None:
    assert verification_service.derive_verdict(["passed", "passed"]) == "passed"
    assert verification_service.derive_verdict(["passed"]) == "passed"


def test_verdict_required_fail_fails() -> None:
    assert verification_service.derive_verdict(["passed", "failed"]) == "failed"
    assert verification_service.derive_verdict(["failed"]) == "failed"
    assert verification_service.derive_verdict(["timed_out"]) == "timed_out"


def test_verdict_blocked_only_blocked() -> None:
    assert verification_service.derive_verdict(["blocked"]) == "blocked"
    assert verification_service.derive_verdict(["blocked", "skipped"]) == "blocked"
    assert verification_service.derive_verdict(["passed", "blocked"]) == "blocked"


def test_verdict_zero_executed_never_passes() -> None:
    assert verification_service.derive_verdict([]) == "inconclusive"
    assert verification_service.derive_verdict(["skipped", "skipped"]) == "inconclusive"
    assert verification_service.derive_verdict(["queued"]) == "inconclusive"


def test_verdict_withheld_pass() -> None:
    assert verification_service.derive_verdict(["passed", "skipped"]) == "inconclusive"
    assert verification_service.derive_verdict(["passed", "inconclusive"]) == "inconclusive"
    assert verification_service.derive_verdict(["passed", "cancelled"]) == "inconclusive"


def test_verdict_unknown_fails_closed() -> None:
    assert verification_service.derive_verdict(["passed", "bogus"]) == "inconclusive"


def test_rerun_schema_accepts_only_selection() -> None:
    assert set(VerificationRunCreate.model_fields) == {"selected_check_keys"}
    assert VerificationRunCreate().selected_check_keys is None
    assert VerificationRunCreate(selected_check_keys=[]).selected_check_keys == []
    with pytest.raises(ValidationError):
        VerificationRunCreate(status="passed")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        VerificationRunCreate(selected_check_keys=["a"], extra="nope")  # type: ignore[call-arg]


def _stub_missing_crypto() -> None:
    """Sandbox shim: stub crypto imports only when they are missing.

    CI installs the full dependency set; this sandbox venv lacks
    PyJWT/cryptography with no network to install them. The router
    import needs them present but never calls them, so bare stubs
    unblock the pure route-table test only.
    """
    import sys
    import types

    try:
        import jwt  # noqa: F401
    except ModuleNotFoundError:
        sys.modules.setdefault("jwt", types.ModuleType("jwt"))
    try:
        from cryptography.x509 import load_pem_x509_certificate  # noqa: F401
    except ModuleNotFoundError:
        package = types.ModuleType("cryptography")
        package.__path__ = []  # type: ignore[attr-defined]
        sys.modules.setdefault("cryptography", package)
        x509 = types.ModuleType("cryptography.x509")
        x509.load_pem_x509_certificate = lambda *args, **kwargs: None  # type: ignore[attr-defined]
        sys.modules.setdefault("cryptography.x509", x509)


def test_no_user_route_sets_passed() -> None:
    """Route-table assertion: the rerun route takes no status/verdict field."""
    _stub_missing_crypto()
    from app.api import verification as verification_api

    posts = [
        route
        for route in verification_api.router.routes
        if "POST" in getattr(route, "methods", set())
    ]
    assert [route.path for route in posts] == [
        "/api/v1/investigations/{investigation_id}/verification-runs"
    ]


# HTTP rerun behavior (PostgreSQL + faked storage).


def test_rerun_creates_new_run_and_preserves_history(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "m9r1")
    inv_id = env["inv"]["id"]
    claimed = _claim(db_session_factory)
    first = _make_runnable(db_session_factory, fake_store, claimed, env, "First")
    second = _make_runnable(db_session_factory, fake_store, claimed, env, "Second")

    rerun = auth_client.post(f"/api/v1/investigations/{inv_id}/verification-runs", json={})
    assert rerun.status_code == 201, rerun.text
    body = rerun.json()["data"]
    assert body["status"] == "queued"
    assert body["checks"] == []
    assert body["runtime_profile"]["selected_check_keys"] == [first["id"], second["id"]]
    assert [item["display_name"] for item in body["runtime_profile"]["planned_checks"]] == [
        "First",
        "Second",
    ]

    subset = auth_client.post(
        f"/api/v1/investigations/{inv_id}/verification-runs",
        json={"selected_check_keys": [second["id"]]},
    )
    assert subset.status_code == 201, subset.text
    assert subset.json()["data"]["runtime_profile"]["selected_check_keys"] == [second["id"]]
    assert subset.json()["data"]["id"] != body["id"]

    listed = auth_client.get(f"/api/v1/investigations/{inv_id}/verification-runs")
    assert listed.status_code == 200
    runs = listed.json()["data"]
    assert [run["id"] for run in runs] == [subset.json()["data"]["id"], body["id"]]
    assert all(run["status"] == "queued" for run in runs)


def test_rerun_validates_selection(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "m9r2")
    inv_id = env["inv"]["id"]
    claimed = _claim(db_session_factory)
    runnable = _make_runnable(db_session_factory, fake_store, claimed, env)
    manual = auth_client.post(
        f"/api/v1/investigations/{inv_id}/regression-tests", json={"title": "Manual idea"}
    ).json()["data"]

    malformed = auth_client.post(
        f"/api/v1/investigations/{inv_id}/verification-runs",
        json={"selected_check_keys": ["not-a-uuid"]},
    )
    assert malformed.status_code == 422
    foreign = auth_client.post(
        f"/api/v1/investigations/{inv_id}/verification-runs",
        json={"selected_check_keys": [str(uuid.uuid4())]},
    )
    assert foreign.status_code == 404
    unusable = auth_client.post(
        f"/api/v1/investigations/{inv_id}/verification-runs",
        json={"selected_check_keys": [manual["id"]]},
    )
    assert unusable.status_code == 422
    unknown_field = auth_client.post(
        f"/api/v1/investigations/{inv_id}/verification-runs",
        json={"selected_check_keys": [runnable["id"]], "status": "passed"},
    )
    assert unknown_field.status_code == 422


def test_rerun_refused_without_runnable_tests(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "m9r3")
    rerun = auth_client.post(
        f"/api/v1/investigations/{env['inv']['id']}/verification-runs", json={}
    )
    assert rerun.status_code == 409


def test_rerun_authz(
    auth_client: TestClient,
    auth_client_factory,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "m9r4")
    inv_id = env["inv"]["id"]
    claimed = _claim(db_session_factory)
    _make_runnable(db_session_factory, fake_store, claimed, env)

    viewer = auth_client_factory("viewer@example.com")
    added = auth_client.post(
        f"/api/v1/workspaces/{env['workspace']['id']}/members",
        json={"email": "viewer@example.com", "role": "viewer"},
    )
    assert added.status_code == 201
    assert viewer.get(f"/api/v1/investigations/{inv_id}/verification-runs").status_code == 200
    assert viewer.get(f"/api/v1/investigations/{inv_id}/verification-comparison").status_code == 200
    forbidden = viewer.post(f"/api/v1/investigations/{inv_id}/verification-runs", json={})
    assert forbidden.status_code == 403

    outsider = auth_client_factory("outsider@example.com")
    assert (
        outsider.post(f"/api/v1/investigations/{inv_id}/verification-runs", json={}).status_code
        == 404
    )
    assert outsider.get(f"/api/v1/investigations/{inv_id}/verification-comparison").status_code == (
        404
    )


def test_stale_completion_refused(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "m9s1")
    claimed = _claim(db_session_factory)
    stage_id = _stage_id(db_session_factory, claimed, env["inv"]["id"], "baseline_test_execution")
    run_id = _start_run(db_session_factory, claimed, env, stage_id, "baseline")
    session: Session = db_session_factory()
    try:
        verification_service.record_check(
            session, run_id=run_id, check_key="t1", display_name="T1", status="passed"
        )
        verification_service.finish_run(session, run_id=run_id, status="passed", summary="ok")
        try:
            verification_service.finish_run(session, run_id=run_id, status="failed", summary="late")
        except ApiError as exc:
            assert exc.code == "INVALID_TRANSITION"
        else:
            raise AssertionError("expected INVALID_TRANSITION")
        try:
            verification_service.record_check(
                session, run_id=run_id, check_key="t2", display_name="T2", status="passed"
            )
        except ApiError as exc:
            assert exc.code == "INVALID_STATE"
        else:
            raise AssertionError("expected INVALID_STATE")
        try:
            verification_service.record_check(
                session,
                run_id=uuid.uuid4(),
                check_key="t9",
                display_name="T9",
                status="passed",
            )
        except ApiError as exc:
            assert exc.code == "RESOURCE_NOT_FOUND"
        else:
            raise AssertionError("expected RESOURCE_NOT_FOUND")
        row = session.get(VerificationRun, run_id)
        assert row is not None and row.status == "passed"
    finally:
        session.close()


def test_comparison_baseline_vs_post(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "m9c1")
    inv_id = env["inv"]["id"]
    claimed = _claim(db_session_factory)
    test = _make_runnable(db_session_factory, fake_store, claimed, env)
    baseline_stage = _stage_id(db_session_factory, claimed, inv_id, "baseline_test_execution")
    baseline_id = _start_run(db_session_factory, claimed, env, baseline_stage, "baseline")
    session: Session = db_session_factory()
    try:
        verification_service.record_check(
            session,
            run_id=baseline_id,
            check_key=test["id"],
            display_name=test["title"],
            status="failed",
            regression_test_id=uuid.UUID(test["id"]),
            exit_code=1,
        )
        verification_service.finish_run(session, run_id=baseline_id, status="failed", summary="bug")
    finally:
        session.close()

    compared = auth_client.get(f"/api/v1/investigations/{inv_id}/verification-comparison")
    assert compared.status_code == 200
    rows = compared.json()["data"]
    assert [(row["title"], row["baseline"]["check_status"], row["post_patch"]) for row in rows] == [
        ("T", "failed", None)
    ]

    post_stage = _stage_id(db_session_factory, claimed, inv_id, "post_patch_verification")
    post_id = _start_run(db_session_factory, claimed, env, post_stage, "post_patch")
    session = db_session_factory()
    try:
        verification_service.record_check(
            session,
            run_id=post_id,
            check_key=test["id"],
            display_name=test["title"],
            status="passed",
            regression_test_id=uuid.UUID(test["id"]),
            exit_code=0,
        )
        verification_service.finish_run(session, run_id=post_id, status="passed", summary="fixed")
    finally:
        session.close()

    compared = auth_client.get(f"/api/v1/investigations/{inv_id}/verification-comparison")
    rows = compared.json()["data"]
    assert [
        (row["baseline"]["check_status"], row["post_patch"]["check_status"]) for row in rows
    ] == [("failed", "passed")]


def test_worker_adopts_queued_plan(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "m9a1")
    inv_id = env["inv"]["id"]
    claimed = _claim(db_session_factory)
    first = _make_runnable(db_session_factory, fake_store, claimed, env, "First")
    _make_runnable(db_session_factory, fake_store, claimed, env, "Second")
    queued = auth_client.post(
        f"/api/v1/investigations/{inv_id}/verification-runs",
        json={"selected_check_keys": [first["id"]]},
    )
    assert queued.status_code == 201
    queued_id = uuid.UUID(queued.json()["data"]["id"])

    stage_id = _stage_id(db_session_factory, claimed, inv_id, "baseline_test_execution")
    session: Session = db_session_factory()
    try:
        adopted = verification_service.adopt_queued_run(
            session,
            job_id=uuid.UUID(claimed["id"]),
            worker_id="w-m9",
            investigation_id=uuid.UUID(inv_id),
            project_id=uuid.UUID(env["project"]["id"]),
            patch_id=None,
            snapshot_id=uuid.UUID(env["snapshot"]["id"]),
            stage_id=stage_id,
            phase="baseline",
            runner_image="img",
            runtime_profile={"profile": "static", "runner": "browser_repro"},
        )
        assert adopted is not None
        assert adopted["run_id"] == queued_id
        assert adopted["selected_check_keys"] == [first["id"]]
        assert adopted["planned_total"] == 1
        row = session.get(VerificationRun, queued_id)
        assert row is not None
        assert row.status == "running"
        assert row.phase == "baseline"
        assert row.created_by_stage_id == stage_id
        assert (
            verification_service.adopt_queued_run(
                session,
                job_id=uuid.UUID(claimed["id"]),
                worker_id="w-m9",
                investigation_id=uuid.UUID(inv_id),
                project_id=uuid.UUID(env["project"]["id"]),
                patch_id=None,
                snapshot_id=uuid.UUID(env["snapshot"]["id"]),
                stage_id=stage_id,
                phase="baseline",
                runner_image="img",
                runtime_profile={},
            )
            is None
        )
    finally:
        session.close()


def test_plan_checks_labels(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "m9p1")
    claimed = _claim(db_session_factory)
    runnable = _make_runnable(db_session_factory, fake_store, claimed, env)
    auth_client.post(
        f"/api/v1/investigations/{env['inv']['id']}/regression-tests", json={"title": "M"}
    )
    session: Session = db_session_factory()
    try:
        plan = verification_service.plan_checks(session, uuid.UUID(env["inv"]["id"]))
    finally:
        session.close()
    assert plan["profiles"] == ["static"]
    assert plan["test_count"] == 2
    assert plan["runnable_count"] == 1
    assert [(check["check_key"], check["runnable"]) for check in plan["required_checks"]] == [
        (runnable["id"], True),
        (plan["required_checks"][1]["check_key"], False),
    ]
