"""M8-FINISH regression-detail tests: single-test reads with history.

The route-table test runs anywhere; HTTP behavior needs PostgreSQL
(CI) with faked object storage.
"""

import io
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.services import evidence as evidence_service
from app.services import ingestion as ingestion_service
from app.services import investigations as investigation_service
from app.services import jobs as job_service
from app.services import regression_tests as regression_test_service
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
        },
    ).json()["data"]
    return {"workspace": workspace, "project": project, "snapshot": snapshot, "inv": inv}


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


def test_regression_detail_route_present() -> None:
    """Route-table assertion: the M8 detail route exists exactly once."""
    _stub_missing_crypto()
    from app.api import investigations as investigations_api

    found = sorted(
        (sorted(getattr(route, "methods", set())), route.path)
        for route in investigations_api.router.routes
        if getattr(route, "path", "").startswith("/api/v1/regression-tests/")
    )
    assert found == [(["GET"], "/api/v1/regression-tests/{test_id}")]


def test_get_regression_test_detail(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "m8d1")
    created = auth_client.post(
        f"/api/v1/investigations/{env['inv']['id']}/regression-tests",
        json={"title": "Header check", "test_type": "e2e"},
    )
    assert created.status_code == 201
    test_id = created.json()["data"]["id"]

    detail = auth_client.get(f"/api/v1/regression-tests/{test_id}")
    assert detail.status_code == 200
    body = detail.json()["data"]
    assert body["title"] == "Header check"
    assert body["status"] == "proposed"
    assert body["verification_history"] == []


def test_detail_includes_verification_history(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "m8d2")
    session: Session = db_session_factory()
    try:
        claimed = job_service.claim_job(session, "w-m8d", ("investigation",), 60)
        assert claimed is not None
        job_id = uuid.UUID(claimed["id"])
        attempt = investigation_service.start_stage_attempt(
            session,
            job_id=job_id,
            worker_id="w-m8d",
            investigation_id=uuid.UUID(env["inv"]["id"]),
            stage_key="regression_test_creation",
        )
        tests = regression_test_service.create_from_drafts(
            session,
            job_id=job_id,
            worker_id="w-m8d",
            investigation_id=uuid.UUID(env["inv"]["id"]),
            stage_id=uuid.UUID(attempt["id"]),
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
        test_id = uuid.UUID(tests[0]["id"])
        baseline_attempt = investigation_service.start_stage_attempt(
            session,
            job_id=job_id,
            worker_id="w-m8d",
            investigation_id=uuid.UUID(env["inv"]["id"]),
            stage_key="baseline_test_execution",
        )
        run_id = verification_service.start_run(
            session,
            job_id=job_id,
            worker_id="w-m8d",
            investigation_id=uuid.UUID(env["inv"]["id"]),
            project_id=uuid.UUID(env["project"]["id"]),
            patch_id=None,
            snapshot_id=uuid.UUID(env["snapshot"]["id"]),
            stage_id=uuid.UUID(baseline_attempt["id"]),
            phase="baseline",
            runner_image="img",
            runtime_profile={"profile": "static"},
        )
        verification_service.record_check(
            session,
            run_id=run_id,
            check_key="t",
            display_name="T",
            status="failed",
            regression_test_id=test_id,
        )
    finally:
        session.close()

    detail = auth_client.get(f"/api/v1/regression-tests/{test_id}")
    assert detail.status_code == 200
    history = detail.json()["data"]["verification_history"]
    assert [(entry["phase"], entry["check_status"]) for entry in history] == [
        ("baseline", "failed")
    ]


def test_regression_detail_authz_matrix(
    auth_client: TestClient,
    auth_client_factory,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "m8d3")
    created = auth_client.post(
        f"/api/v1/investigations/{env['inv']['id']}/regression-tests",
        json={"title": "t"},
    )
    test_id = created.json()["data"]["id"]

    viewer = auth_client_factory("viewer-m8d@example.com")
    added = auth_client.post(
        f"/api/v1/workspaces/{env['workspace']['id']}/members",
        json={"email": "viewer-m8d@example.com", "role": "viewer"},
    )
    assert added.status_code == 201
    assert viewer.get(f"/api/v1/regression-tests/{test_id}").status_code == 200

    outsider = auth_client_factory("outsider-m8d@example.com")
    assert outsider.get(f"/api/v1/regression-tests/{test_id}").status_code == 404
    assert auth_client.get(f"/api/v1/regression-tests/{uuid.uuid4()}").status_code == 404
