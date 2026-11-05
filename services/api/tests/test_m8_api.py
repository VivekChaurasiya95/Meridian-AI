"""M8 API and worker-service tests: regression tests, patches, verification.

HTTP behavior goes through the API; worker-only transitions are
exercised at the service layer with a real claimed job. Object
storage is faked; Postgres is real.
"""

import hashlib
import io
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.envelope import ApiError
from app.models import Patch, RegressionTest, VerificationRun
from app.services import evidence as evidence_service
from app.services import ingestion as ingestion_service
from app.services import investigations as investigation_service
from app.services import jobs as job_service
from app.services import patches as patch_service
from app.services import regression_tests as regression_test_service
from app.services import storage as storage_service
from app.services import verification as verification_service
from app.services.model_gateway import RegressionTestDraft
from app.services.object_store import FakeObjectStore

DIFF = """--- a/index.html
+++ b/index.html
@@ -1 +1 @@
-<h1>x</h1>
+<h1>fixed</h1>
"""


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


def _claim(db_session_factory, worker: str = "w-m8"):  # type: ignore[no-untyped-def]
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
            worker_id="w-m8",
            investigation_id=uuid.UUID(inv_id),
            stage_key=key,
        )
        return uuid.UUID(attempt["id"])
    finally:
        session.close()


def _propose(db_session_factory, fake_store, claimed, env, key="patch_proposal"):  # type: ignore[no-untyped-def]
    stage_id = _stage_id(db_session_factory, claimed, env["inv"]["id"], key)
    session: Session = db_session_factory()
    try:
        return patch_service.create_proposal(
            session,
            job_id=uuid.UUID(claimed["id"]),
            worker_id="w-m8",
            investigation_id=uuid.UUID(env["inv"]["id"]),
            project_id=uuid.UUID(env["project"]["id"]),
            base_snapshot_id=uuid.UUID(env["snapshot"]["id"]),
            stage_id=stage_id,
            tool_run_id=None,
            summary="Fix the header.",
            diff_text=DIFF,
            store=fake_store,
        )
    finally:
        session.close()


def _park(db_session_factory, claimed, inv_id: str) -> None:  # type: ignore[no-untyped-def]
    session: Session = db_session_factory()
    try:
        patch_service.submit_for_approval(
            session,
            job_id=uuid.UUID(claimed["id"]),
            worker_id="w-m8",
            investigation_id=uuid.UUID(inv_id),
        )
        investigation_service.park_for_approval(
            session,
            job_id=uuid.UUID(claimed["id"]),
            worker_id="w-m8",
            investigation_id=uuid.UUID(inv_id),
        )
    finally:
        session.close()


def test_create_and_list_regression_tests(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "m8t1")
    inv_id = env["inv"]["id"]
    created = auth_client.post(
        f"/api/v1/investigations/{inv_id}/regression-tests",
        json={
            "title": "Header check",
            "description": "Manual idea.",
            "test_type": "manual",
            "file_path": "tests/header.md",
            "test_name": "header",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()["data"]
    assert body["status"] == "proposed"
    listed = auth_client.get(f"/api/v1/investigations/{inv_id}/regression-tests")
    assert listed.status_code == 200
    items = listed.json()["data"]
    assert [t["title"] for t in items] == ["Header check"]
    assert items[0]["verification_history"] == []


def test_create_regression_test_rejects_bad_input(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "m8t2")
    inv_id = env["inv"]["id"]
    bad_type = auth_client.post(
        f"/api/v1/investigations/{inv_id}/regression-tests",
        json={"title": "t", "test_type": "fuzz"},
    )
    assert bad_type.status_code == 422
    escape = auth_client.post(
        f"/api/v1/investigations/{inv_id}/regression-tests",
        json={"title": "t", "file_path": "../escape.txt"},
    )
    assert escape.status_code == 422
    empty = auth_client.post(
        f"/api/v1/investigations/{inv_id}/regression-tests", json={"title": "  "}
    )
    assert empty.status_code == 422


def test_regression_tests_hidden_from_outsiders(
    auth_client: TestClient,
    auth_client_factory,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "m8t3")
    outsider = auth_client_factory("outsider@example.com")
    listed = outsider.get(f"/api/v1/investigations/{env['inv']['id']}/regression-tests")
    assert listed.status_code == 404
    created = outsider.post(
        f"/api/v1/investigations/{env['inv']['id']}/regression-tests",
        json={"title": "t"},
    )
    assert created.status_code == 404


def test_create_regression_test_refused_when_terminal(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "m8t4")
    inv_id = env["inv"]["id"]
    cancelled = auth_client.post(f"/api/v1/investigations/{inv_id}/cancel")
    assert cancelled.status_code == 202
    created = auth_client.post(
        f"/api/v1/investigations/{inv_id}/regression-tests", json={"title": "t"}
    )
    assert created.status_code == 409


def test_patch_reads_and_inline_diff(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "m8p1")
    claimed = _claim(db_session_factory)
    created = _propose(db_session_factory, fake_store, claimed, env)
    listed = auth_client.get(f"/api/v1/investigations/{env['inv']['id']}/patches")
    assert listed.status_code == 200
    assert [p["id"] for p in listed.json()["data"]] == [created["id"]]
    one = auth_client.get(f"/api/v1/patches/{created['id']}")
    assert one.status_code == 200
    assert one.json()["data"]["files_changed"] == [
        {"path": "index.html", "change": "modified", "additions": 1, "deletions": 1}
    ]
    diff = auth_client.get(f"/api/v1/patches/{created['id']}/diff")
    assert diff.status_code == 200
    assert diff.json()["data"]["diff_text"] == DIFF


def test_approve_binds_digest_and_queues_application(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "m8p2")
    claimed = _claim(db_session_factory)
    created = _propose(db_session_factory, fake_store, claimed, env)
    _park(db_session_factory, claimed, env["inv"]["id"])
    digest = hashlib.sha256(DIFF.encode()).hexdigest()
    approved = auth_client.post(
        f"/api/v1/patches/{created['id']}/approve",
        json={"diff_sha256": digest, "base_snapshot_id": env["snapshot"]["id"]},
    )
    assert approved.status_code == 202, approved.text
    data = approved.json()["data"]
    assert data["approval_status"] == "approved"
    assert data["application_status"] == "queued"
    session: Session = db_session_factory()
    try:
        row = session.get(Patch, uuid.UUID(created["id"]))
        assert row is not None and row.status == "approved"
        assert row.approval_by is not None
        from app.models import Investigation

        inv = session.get(Investigation, uuid.UUID(env["inv"]["id"]))
        assert inv is not None and inv.status == "queued"
        assert inv.current_stage == "patch_application"
    finally:
        session.close()


def test_approve_rejects_mismatch_and_reapprove(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "m8p3")
    claimed = _claim(db_session_factory)
    created = _propose(db_session_factory, fake_store, claimed, env)
    _park(db_session_factory, claimed, env["inv"]["id"])
    wrong = auth_client.post(
        f"/api/v1/patches/{created['id']}/approve",
        json={"diff_sha256": "0" * 64, "base_snapshot_id": env["snapshot"]["id"]},
    )
    assert wrong.status_code == 422
    # A well-formed but foreign snapshot id still mismatches the binding.
    foreign = auth_client.post(
        f"/api/v1/patches/{created['id']}/approve",
        json={
            "diff_sha256": hashlib.sha256(DIFF.encode()).hexdigest(),
            "base_snapshot_id": str(uuid.uuid4()),
        },
    )
    assert foreign.status_code == 422
    good = auth_client.post(
        f"/api/v1/patches/{created['id']}/approve",
        json={
            "diff_sha256": hashlib.sha256(DIFF.encode()).hexdigest(),
            "base_snapshot_id": env["snapshot"]["id"],
        },
    )
    assert good.status_code == 202
    again = auth_client.post(
        f"/api/v1/patches/{created['id']}/approve",
        json={
            "diff_sha256": hashlib.sha256(DIFF.encode()).hexdigest(),
            "base_snapshot_id": env["snapshot"]["id"],
        },
    )
    assert again.status_code == 409


def test_approve_forbids_developer_and_outsider(
    auth_client: TestClient,
    auth_client_factory,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "m8p4")
    claimed = _claim(db_session_factory)
    created = _propose(db_session_factory, fake_store, claimed, env)
    _park(db_session_factory, claimed, env["inv"]["id"])
    dev = auth_client_factory("dev@example.com")
    added = auth_client.post(
        f"/api/v1/workspaces/{env['workspace']['id']}/members",
        json={"email": "dev@example.com", "role": "developer"},
    )
    assert added.status_code == 201
    body = {
        "diff_sha256": hashlib.sha256(DIFF.encode()).hexdigest(),
        "base_snapshot_id": env["snapshot"]["id"],
    }
    forbidden = dev.post(f"/api/v1/patches/{created['id']}/approve", json=body)
    assert forbidden.status_code == 403
    outsider = auth_client_factory("outsider@example.com")
    missing = outsider.post(f"/api/v1/patches/{created['id']}/approve", json=body)
    assert missing.status_code == 404


def test_reject_and_discard(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "m8p5")
    claimed = _claim(db_session_factory)
    created = _propose(db_session_factory, fake_store, claimed, env)
    no_reason = auth_client.post(f"/api/v1/patches/{created['id']}/reject", json={"reason": "  "})
    assert no_reason.status_code == 422
    # Discard is blocked while the investigation job is still live.
    blocked = auth_client.post(f"/api/v1/patches/{created['id']}/discard")
    assert blocked.status_code == 409
    rejected = auth_client.post(
        f"/api/v1/patches/{created['id']}/reject", json={"reason": "Stale idea."}
    )
    assert rejected.status_code == 200
    assert rejected.json()["data"]["status"] == "rejected"
    # Rejecting again is a no-op conflict, not a second decision.
    again = auth_client.post(f"/api/v1/patches/{created['id']}/reject", json={"reason": "Again."})
    assert again.status_code == 409


def test_discard_after_cancel(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "m8p6")
    claimed = _claim(db_session_factory)
    created = _propose(db_session_factory, fake_store, claimed, env)
    cancelled = auth_client.post(f"/api/v1/investigations/{env['inv']['id']}/cancel")
    assert cancelled.status_code == 202
    discarded = auth_client.post(f"/api/v1/patches/{created['id']}/discard")
    assert discarded.status_code == 200, discarded.text
    assert discarded.json()["data"]["status"] == "discarded"


def test_verification_reads(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "m8v1")
    inv_id = env["inv"]["id"]
    empty = auth_client.get(f"/api/v1/investigations/{inv_id}/verification-runs")
    assert empty.status_code == 200
    assert empty.json()["data"] == []
    missing = auth_client.get(f"/api/v1/verification-runs/{uuid.uuid4()}")
    assert missing.status_code == 404
    claimed = _claim(db_session_factory)
    stage_id = _stage_id(db_session_factory, claimed, inv_id, "baseline_test_execution")
    session: Session = db_session_factory()
    try:
        run_id = verification_service.start_run(
            session,
            job_id=uuid.UUID(claimed["id"]),
            worker_id="w-m8",
            investigation_id=uuid.UUID(inv_id),
            project_id=uuid.UUID(env["project"]["id"]),
            patch_id=None,
            snapshot_id=uuid.UUID(env["snapshot"]["id"]),
            stage_id=stage_id,
            phase="baseline",
            runner_image="img",
            runtime_profile={"profile": "static"},
        )
        verification_service.record_check(
            session,
            run_id=run_id,
            check_key="t1",
            display_name="T1",
            status="passed",
            exit_code=0,
        )
        verification_service.finish_run(session, run_id=run_id, status="passed", summary="ok")
    finally:
        session.close()
    listed = auth_client.get(f"/api/v1/investigations/{inv_id}/verification-runs")
    assert listed.status_code == 200
    runs = listed.json()["data"]
    assert [(r["phase"], r["status"]) for r in runs] == [("baseline", "passed")]
    one = auth_client.get(f"/api/v1/verification-runs/{runs[0]['id']}")
    assert one.status_code == 200
    assert [c["check_key"] for c in one.json()["data"]["checks"]] == ["t1"]


def test_run_cannot_pass_without_executed_checks(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "m8v2")
    claimed = _claim(db_session_factory)
    stage_id = _stage_id(db_session_factory, claimed, env["inv"]["id"], "baseline_test_execution")
    session: Session = db_session_factory()
    try:
        run_id = verification_service.start_run(
            session,
            job_id=uuid.UUID(claimed["id"]),
            worker_id="w-m8",
            investigation_id=uuid.UUID(env["inv"]["id"]),
            project_id=uuid.UUID(env["project"]["id"]),
            patch_id=None,
            snapshot_id=uuid.UUID(env["snapshot"]["id"]),
            stage_id=stage_id,
            phase="baseline",
            runner_image="img",
            runtime_profile={},
        )
        try:
            verification_service.finish_run(
                session, run_id=run_id, status="passed", summary="empty"
            )
        except ApiError as exc:
            assert exc.code == "INVALID_STATE"
        else:
            raise AssertionError("expected INVALID_STATE")
        row = session.get(VerificationRun, run_id)
        assert row is not None and row.status == "running"
    finally:
        session.close()


def test_test_lifecycle_transitions(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "m8w1")
    claimed = _claim(db_session_factory)
    stage_id = _stage_id(db_session_factory, claimed, env["inv"]["id"], "regression_test_creation")
    session: Session = db_session_factory()
    try:
        created = regression_test_service.create_from_drafts(
            session,
            job_id=uuid.UUID(claimed["id"]),
            worker_id="w-m8",
            investigation_id=uuid.UUID(env["inv"]["id"]),
            stage_id=stage_id,
            tool_run_id=None,
            project_id=uuid.UUID(env["project"]["id"]),
            drafts=[
                RegressionTestDraft(
                    title="T",
                    description=None,
                    test_type="e2e",
                    file_path="tests/t.spec",
                    test_name="t",
                    steps=({"action": "assert_text", "selector": "h1", "text": "x"},),
                )
            ],
            store=fake_store,
        )
        test_id = uuid.UUID(created[0]["id"])
        try:
            regression_test_service.transition_test(session, test_id, "post_patch_passed")
        except ApiError as exc:
            assert exc.code == "INVALID_TRANSITION"
        else:
            raise AssertionError("expected INVALID_TRANSITION")
        regression_test_service.transition_test(session, test_id, "baseline_failed")
        owned = regression_test_service.executable_tests(session, uuid.UUID(env["inv"]["id"]))
        assert owned == []
        gated = regression_test_service.gated_tests(session, uuid.UUID(env["inv"]["id"]))
        assert [t.id for t in gated] == [test_id]
        row = session.get(RegressionTest, test_id)
        assert row is not None
        context = regression_test_service.load_artifact_steps(session, row, fake_store)
        assert context["steps"][0]["action"] == "assert_text"
    finally:
        session.close()


def test_patch_worker_guards(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "m8w2")
    claimed = _claim(db_session_factory)
    session: Session = db_session_factory()
    try:
        try:
            patch_service.submit_for_approval(
                session,
                job_id=uuid.UUID(claimed["id"]),
                worker_id="w-m8",
                investigation_id=uuid.UUID(env["inv"]["id"]),
            )
        except ApiError as exc:
            assert exc.code == "PATCH_NOT_PROPOSED"
        else:
            raise AssertionError("expected PATCH_NOT_PROPOSED")
    finally:
        session.close()
    created = _propose(db_session_factory, fake_store, claimed, env)
    session = db_session_factory()
    try:
        first = patch_service.submit_for_approval(
            session,
            job_id=uuid.UUID(claimed["id"]),
            worker_id="w-m8",
            investigation_id=uuid.UUID(env["inv"]["id"]),
        )
        second = patch_service.submit_for_approval(
            session,
            job_id=uuid.UUID(claimed["id"]),
            worker_id="w-m8",
            investigation_id=uuid.UUID(env["inv"]["id"]),
        )
        assert first.id == second.id == uuid.UUID(created["id"])
        try:
            patch_service.mark_verified(
                session,
                job_id=uuid.UUID(claimed["id"]),
                worker_id="w-m8",
                patch_id=first.id,
                passed=True,
            )
        except ApiError as exc:
            assert exc.code == "INVALID_STATE"
        else:
            raise AssertionError("expected INVALID_STATE")
    finally:
        session.close()
