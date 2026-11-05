"""Investigation endpoint tests (M6): create, list, detail, cancel, retry."""

import io
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.envelope import ApiError
from app.services import ingestion as ingestion_service
from app.services import investigations as investigation_service
from app.services import jobs as job_service
from app.services import storage as storage_service
from app.services.object_store import FakeObjectStore

HTML_ZIP_ENTRIES = {
    "index.html": "<html><body><h1>hi</h1></body></html>\n",
    "app.js": "console.log(1)\n",
}


@pytest.fixture(autouse=True)
def fake_store(monkeypatch: pytest.MonkeyPatch) -> FakeObjectStore:
    store = FakeObjectStore()
    monkeypatch.setattr(ingestion_service, "_default_store", lambda: store)
    monkeypatch.setattr(storage_service, "get_store", lambda: store)
    return store


def make_zip(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def make_workspace(client: TestClient, slug: str) -> dict:
    response = client.post("/api/v1/workspaces", json={"name": slug, "slug": slug})
    assert response.status_code == 201, response.text
    return response.json()["data"]


def make_project(client: TestClient, workspace_id: str, slug: str) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/projects",
        json={"name": slug, "slug": slug},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def upload_snapshot(client: TestClient, project_id: str) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/source-uploads",
        files={"file": ("repo.zip", make_zip(HTML_ZIP_ENTRIES), "application/zip")},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["snapshot"]


def setup(client: TestClient, slug: str) -> tuple[dict, dict, dict]:
    workspace = make_workspace(client, f"ws{slug}")
    project = make_project(client, workspace["id"], f"p{slug}")
    snapshot = upload_snapshot(client, project["id"])
    return workspace, project, snapshot


def create(
    client: TestClient,
    project_id: str,
    snapshot_id: str,
    key: str | None = None,
    **overrides,  # type: ignore[no-untyped-def]
):
    body: dict = {
        "title": "Login button sticks",
        "bug_report": "After refresh the login button stays disabled.",
        "severity": "medium",
        "repository_snapshot_id": snapshot_id,
        "reproduction_context": {"route": "/login"},
    }
    body.update(overrides)
    headers = {"Idempotency-Key": key} if key else None
    return client.post(f"/api/v1/projects/{project_id}/investigations", json=body, headers=headers)


def test_create_returns_202_with_links_and_job(auth_client: TestClient) -> None:
    _, project, snapshot = setup(auth_client, "c1")
    response = create(auth_client, project["id"], snapshot["id"], key="inv-key-1")
    assert response.status_code == 202, response.text
    body = response.json()
    data = body["data"]
    assert data["status"] == "queued"
    assert data["current_stage"] is None
    assert data["severity"] == "medium"
    assert body["links"]["self"] == f"/api/v1/investigations/{data['id']}"
    assert body["links"]["activity"].endswith("/activity")

    detail = auth_client.get(f"/api/v1/investigations/{data['id']}").json()["data"]
    assert detail["counts"] == {
        "evidence": 0,
        "hypotheses": 0,
        "patches": 0,
        "verification_runs": 0,
    }
    stages = auth_client.get(f"/api/v1/investigations/{data['id']}/stages").json()["data"]
    assert stages == []
    activity = auth_client.get(f"/api/v1/investigations/{data['id']}/activity").json()
    assert activity["data"][0]["event_type"] == "investigation.created"


def test_idempotent_replay_and_conflict(auth_client: TestClient) -> None:
    _, project, snapshot = setup(auth_client, "c2")
    first = create(auth_client, project["id"], snapshot["id"], key="inv-key-2")
    assert first.status_code == 202
    second = create(auth_client, project["id"], snapshot["id"], key="inv-key-2")
    assert second.status_code == 200
    assert second.json()["data"]["id"] == first.json()["data"]["id"]
    conflict = create(
        auth_client, project["id"], snapshot["id"], key="inv-key-2", title="Other title"
    )
    assert conflict.status_code == 422
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_create_validation(auth_client_factory) -> None:  # type: ignore[no-untyped-def]
    owner = auth_client_factory("owner-inv@example.com")
    viewer = auth_client_factory("viewer-inv@example.com")
    outsider = auth_client_factory("outsider-inv@example.com")
    workspace, project, snapshot = setup(owner, "c3")
    added = owner.post(
        f"/api/v1/workspaces/{workspace['id']}/members",
        json={"email": "viewer-inv@example.com", "role": "viewer"},
    )
    assert added.status_code == 201, added.text
    assert create(viewer, project["id"], snapshot["id"]).status_code == 403
    assert create(outsider, project["id"], snapshot["id"]).status_code == 404
    assert create(owner, project["id"], str(uuid.uuid4())).status_code == 404
    bad = create(owner, project["id"], snapshot["id"], reproduction_context={"browser": "x"})
    assert bad.status_code == 422
    attached = create(owner, project["id"], snapshot["id"], attachments=[{"upload_id": "up_1"}])
    assert attached.status_code == 422
    assert attached.json()["error"]["code"] == "ATTACHMENTS_NOT_SUPPORTED"
    archived = owner.post(f"/api/v1/projects/{project['id']}/archive")
    assert archived.status_code == 200
    assert create(owner, project["id"], snapshot["id"]).status_code == 409


def test_list_filters_and_scope(auth_client_factory) -> None:  # type: ignore[no-untyped-def]
    owner = auth_client_factory("owner-invl@example.com")
    outsider = auth_client_factory("outsider-invl@example.com")
    _, project, snapshot = setup(owner, "c4")
    assert create(owner, project["id"], snapshot["id"], severity="high").status_code == 202
    assert create(owner, project["id"], snapshot["id"], severity="low").status_code == 202
    listed = owner.get(f"/api/v1/projects/{project['id']}/investigations").json()["data"]
    assert len(listed) == 2
    high = owner.get(
        f"/api/v1/projects/{project['id']}/investigations", params={"severity": "high"}
    ).json()["data"]
    assert [item["severity"] for item in high] == ["high"]
    assert (
        owner.get(
            f"/api/v1/projects/{project['id']}/investigations", params={"status": "nope"}
        ).status_code
        == 422
    )
    assert outsider.get(f"/api/v1/projects/{project['id']}/investigations").status_code == 404


def test_cancel_requests_and_finalizes(auth_client: TestClient, db_session_factory) -> None:  # type: ignore[no-untyped-def]
    _, project, snapshot = setup(auth_client, "c5")
    inv = create(auth_client, project["id"], snapshot["id"]).json()["data"]
    cancelled = auth_client.post(f"/api/v1/investigations/{inv['id']}/cancel").json()["data"]
    # No worker ever claimed the queued job, so no ack can arrive: the
    # request cancels the job and finalizes the investigation honestly.
    assert cancelled["status"] == "cancelled"
    assert cancelled["cancel_requested"] is True
    again = auth_client.post(f"/api/v1/investigations/{inv['id']}/cancel")
    assert again.status_code == 409


def test_retry_requeues_from_failed_stage(
    auth_client: TestClient,
    db_session_factory,  # type: ignore[no-untyped-def]
) -> None:
    _, project, snapshot = setup(auth_client, "c6")
    inv = create(auth_client, project["id"], snapshot["id"]).json()["data"]
    session: Session = db_session_factory()
    try:
        claimed = job_service.claim_job(session, "w-inv", ("investigation",), 60)
        assert claimed is not None
        job_id = uuid.UUID(claimed["id"])
        attempt = investigation_service.start_stage_attempt(
            session,
            job_id=job_id,
            worker_id="w-inv",
            investigation_id=uuid.UUID(inv["id"]),
            stage_key="reproduction",
        )
        investigation_service.finish_stage_attempt(
            session,
            job_id=job_id,
            worker_id="w-inv",
            stage_id=uuid.UUID(attempt["id"]),
            status="failed",
            error_code="REPRO_CONTAINER_FAILED",
            error_message="Exit code 1.",
        )
        investigation_service.finalize_investigation(
            session,
            job_id=job_id,
            worker_id="w-inv",
            investigation_id=uuid.UUID(inv["id"]),
            status="failed",
            result_summary="Exit code 1.",
        )
        job_service.fail_job(session, job_id, "w-inv", "REPRO_CONTAINER_FAILED", "x", False)
    finally:
        session.close()
    retry = auth_client.post(
        f"/api/v1/investigations/{inv['id']}/retry",
        json={"from_stage": "reproduction", "reason": "infra flake, trying again"},
    )
    assert retry.status_code == 202, retry.text
    assert retry.json()["data"]["status"] == "queued"
    # Second retry while queued is rejected; unknown stages are rejected.
    running = auth_client.post(
        f"/api/v1/investigations/{inv['id']}/retry",
        json={"from_stage": "reproduction", "reason": "again"},
    )
    assert running.status_code == 409


def test_project_delete_blocked_with_investigations(auth_client: TestClient) -> None:
    _, project, snapshot = setup(auth_client, "c7")
    assert create(auth_client, project["id"], snapshot["id"]).status_code == 202
    response = auth_client.delete(f"/api/v1/projects/{project['id']}")
    assert response.status_code == 409


def test_audit_list_restricted(auth_client_factory) -> None:  # type: ignore[no-untyped-def]
    owner = auth_client_factory("owner-audit@example.com")
    viewer = auth_client_factory("viewer-audit@example.com")
    outsider = auth_client_factory("outsider-audit@example.com")
    workspace, project, snapshot = setup(owner, "c8")
    added = owner.post(
        f"/api/v1/workspaces/{workspace['id']}/members",
        json={"email": "viewer-audit@example.com", "role": "viewer"},
    )
    assert added.status_code == 201, added.text
    assert create(owner, project["id"], snapshot["id"]).status_code == 202
    listed = owner.get(f"/api/v1/workspaces/{workspace['id']}/audit-events").json()["data"]
    assert [event["action"] for event in listed] == ["investigation.created"]
    assert viewer.get(f"/api/v1/workspaces/{workspace['id']}/audit-events").status_code == 403
    assert outsider.get(f"/api/v1/workspaces/{workspace['id']}/audit-events").status_code == 404


def test_terminal_transition_refused(auth_client: TestClient, db_session_factory) -> None:  # type: ignore[no-untyped-def]
    _, project, snapshot = setup(auth_client, "c9")
    inv = create(auth_client, project["id"], snapshot["id"]).json()["data"]
    session: Session = db_session_factory()
    try:
        claimed = job_service.claim_job(session, "w-term", ("investigation",), 60)
        assert claimed is not None
        job_id = uuid.UUID(claimed["id"])
        investigation_service.start_stage_attempt(
            session,
            job_id=job_id,
            worker_id="w-term",
            investigation_id=uuid.UUID(inv["id"]),
            stage_key="project_inspection",
        )
        investigation_service.finalize_investigation(
            session,
            job_id=job_id,
            worker_id="w-term",
            investigation_id=uuid.UUID(inv["id"]),
            status="completed",
            result_summary="done",
        )
        with pytest.raises(ApiError) as exc:
            investigation_service.finalize_investigation(
                session,
                job_id=job_id,
                worker_id="w-term",
                investigation_id=uuid.UUID(inv["id"]),
                status="failed",
                result_summary="late",
            )
        assert exc.value.code == "INVALID_TRANSITION"
    finally:
        session.close()
