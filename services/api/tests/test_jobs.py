"""Job endpoint + lifecycle tests (M4): submit, claim, lease, retry, stages."""

import os
import threading
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.envelope import ApiError
from app.services import jobs as job_service


@pytest.fixture()
def db_session():
    engine = create_engine(os.environ["DATABASE_URL"])
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def make_workspace(client: TestClient, slug: str = "ws") -> dict:
    response = client.post("/api/v1/workspaces", json={"name": slug, "slug": slug})
    assert response.status_code == 201, response.text
    return response.json()["data"]


def submit(
    client: TestClient,
    workspace_id: str,
    job_type: str = "lifecycle_test",
    payload: dict | None = None,
    key: str | None = None,
):  # type: ignore[no-untyped-def]
    body: dict = {"job_type": job_type, "payload": payload or {"note": "hi"}}
    if key:
        body["idempotency_key"] = key
    return client.post(f"/api/v1/workspaces/{workspace_id}/jobs", json=body)


def test_submit_and_get_job(auth_client: TestClient) -> None:
    workspace = make_workspace(auth_client)
    response = submit(auth_client, workspace["id"])
    assert response.status_code == 201, response.text
    job = response.json()["data"]
    assert job["status"] == "queued"
    assert job["attempts"] == 0
    assert job["payload"] == {"note": "hi"}

    fetched = auth_client.get(f"/api/v1/jobs/{job['id']}").json()["data"]
    assert fetched["id"] == job["id"]

    listed = auth_client.get(f"/api/v1/workspaces/{workspace['id']}/jobs").json()["data"]
    assert [j["id"] for j in listed] == [job["id"]]
    # List views withhold payloads (D45).
    assert "payload" not in listed[0]


def test_submit_rejects_unknown_type_and_viewer(
    auth_client_factory,  # type: ignore[no-untyped-def]
) -> None:
    owner = auth_client_factory("owner-j@example.com")
    viewer = auth_client_factory("viewer-j@example.com")
    workspace = make_workspace(owner, "wsj")
    added = owner.post(
        f"/api/v1/workspaces/{workspace['id']}/members",
        json={"email": "viewer-j@example.com", "role": "viewer"},
    )
    assert added.status_code == 201, added.text
    assert submit(owner, workspace["id"], job_type="run_anything").status_code == 422
    assert submit(viewer, workspace["id"]).status_code == 403


def test_idempotent_submit_returns_original(auth_client: TestClient) -> None:
    workspace = make_workspace(auth_client)
    first = submit(auth_client, workspace["id"], key="abc-123")
    assert first.status_code == 201
    second = submit(auth_client, workspace["id"], key="abc-123")
    assert second.status_code == 200
    assert second.json()["data"]["id"] == first.json()["data"]["id"]
    listed = auth_client.get(f"/api/v1/workspaces/{workspace['id']}/jobs").json()["data"]
    assert len(listed) == 1


def test_jobs_are_workspace_scoped(auth_client_factory) -> None:  # type: ignore[no-untyped-def]
    owner = auth_client_factory("owner-js@example.com")
    outsider = auth_client_factory("outsider-js@example.com")
    workspace = make_workspace(owner, "wsjs")
    job = submit(owner, workspace["id"]).json()["data"]
    assert outsider.get(f"/api/v1/jobs/{job['id']}").status_code == 404
    assert outsider.get(f"/api/v1/workspaces/{workspace['id']}/jobs").status_code == 404


def test_cancel_transitions(auth_client: TestClient, db_session: Session) -> None:
    workspace = make_workspace(auth_client)
    job = submit(auth_client, workspace["id"]).json()["data"]
    cancelled = auth_client.post(f"/api/v1/jobs/{job['id']}/cancel").json()["data"]
    assert cancelled["status"] == "cancelled"
    # Terminal jobs cannot transition again.
    again = auth_client.post(f"/api/v1/jobs/{job['id']}/cancel")
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "INVALID_TRANSITION"
    # Cancelled jobs are never claimable.
    assert job_service.claim_job(db_session, "w1", ("lifecycle_test",), 60) is None


def test_claim_is_exclusive(auth_client: TestClient, db_session: Session) -> None:
    workspace = make_workspace(auth_client)
    job = submit(auth_client, workspace["id"]).json()["data"]
    claimed = job_service.claim_job(db_session, "worker-a", ("lifecycle_test",), 60)
    assert claimed is not None
    assert claimed["id"] == job["id"]
    assert claimed["status"] == "running"
    assert claimed["attempts"] == 1
    assert claimed["worker_id"] == "worker-a"
    # Second worker sees nothing (row locked / already running unexpired).
    assert job_service.claim_job(db_session, "worker-b", ("lifecycle_test",), 60) is None


def test_concurrent_claim_single_winner(
    auth_client: TestClient, db_session: Session
) -> None:
    workspace = make_workspace(auth_client)
    submit(auth_client, workspace["id"])
    winners: list = []
    barrier = threading.Barrier(2)

    def attempt(worker: str) -> None:
        engine = create_engine(os.environ["DATABASE_URL"])
        factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        session = factory()
        try:
            barrier.wait(timeout=10)
            claimed = job_service.claim_job(session, worker, ("lifecycle_test",), 60)
            if claimed is not None:
                winners.append(worker)
        finally:
            session.close()
            engine.dispose()

    first = threading.Thread(target=attempt, args=("w1",))
    second = threading.Thread(target=attempt, args=("w2",))
    first.start()
    second.start()
    first.join(timeout=30)
    second.join(timeout=30)
    assert len(winners) == 1


def test_lease_expiry_recovers_job(auth_client: TestClient, db_session: Session) -> None:
    workspace = make_workspace(auth_client)
    job = submit(auth_client, workspace["id"]).json()["data"]
    claimed = job_service.claim_job(db_session, "crashed-worker", ("lifecycle_test",), 60)
    assert claimed is not None
    # Simulate a crash: lease in the past, no heartbeat ever again.
    db_session.execute(
        text("UPDATE jobs SET lease_expires_at = now() - interval '1 minute' WHERE id = :id"),
        {"id": job["id"]},
    )
    db_session.commit()
    recovered = job_service.claim_job(db_session, "worker-b", ("lifecycle_test",), 60)
    assert recovered is not None
    assert recovered["id"] == job["id"]
    assert recovered["worker_id"] == "worker-b"
    assert recovered["attempts"] == 2


def test_heartbeat_and_completion_ownership(
    auth_client: TestClient, db_session: Session
) -> None:
    workspace = make_workspace(auth_client)
    job = submit(auth_client, workspace["id"]).json()["data"]
    job_service.claim_job(db_session, "owner-w", ("lifecycle_test",), 60)
    job_id = uuid.UUID(job["id"])
    renewed = job_service.heartbeat_job(db_session, job_id, "owner-w", 60)
    assert renewed["status"] == "running"
    with pytest.raises(ApiError) as exc_info:
        job_service.heartbeat_job(db_session, job_id, "impostor", 60)
    assert exc_info.value.code == "LEASE_LOST"
    done = job_service.complete_job(db_session, job_id, "owner-w", {"echo": "hi"})
    assert done["status"] == "completed"
    assert done["result"] == {"echo": "hi"}
    # Completed jobs never run again.
    assert job_service.claim_job(db_session, "worker-c", ("lifecycle_test",), 60) is None


def test_complete_after_cancel_refused(auth_client: TestClient, db_session: Session) -> None:
    workspace = make_workspace(auth_client)
    job = submit(auth_client, workspace["id"]).json()["data"]
    job_service.claim_job(db_session, "doomed", ("lifecycle_test",), 60)
    auth_client.post(f"/api/v1/jobs/{job['id']}/cancel")
    with pytest.raises(ApiError) as exc_info:
        job_service.complete_job(db_session, uuid.UUID(job["id"]), "doomed", {})
    assert exc_info.value.code == "LEASE_LOST"


def test_retry_backoff_and_max_attempts(
    auth_client: TestClient, db_session: Session
) -> None:
    workspace = make_workspace(auth_client)
    response = auth_client.post(
        f"/api/v1/workspaces/{workspace['id']}/jobs",
        json={"job_type": "lifecycle_test", "payload": {}, "max_attempts": 2},
    )
    assert response.status_code == 201
    job = response.json()["data"]
    job_id = uuid.UUID(job["id"])
    job_service.claim_job(db_session, "w", ("lifecycle_test",), 60)
    retrying = job_service.fail_job(db_session, job_id, "w", "FLAKY", "boom", True)
    assert retrying["status"] == "retry_wait"
    assert retrying["attempts"] == 1
    # Backoff pushes availability into the future; not claimable yet.
    assert job_service.claim_job(db_session, "w2", ("lifecycle_test",), 60) is None
    # Force due and fail the last attempt: FAILED, never requeued.
    db_session.execute(
        text("UPDATE jobs SET available_at = now() - interval '1 minute' WHERE id = :id"),
        {"id": job["id"]},
    )
    db_session.commit()
    job_service.claim_job(db_session, "w2", ("lifecycle_test",), 60)
    final = job_service.fail_job(db_session, job_id, "w2", "FLAKY", "boom", True)
    assert final["status"] == "failed"
    assert final["attempts"] == 2
    assert job_service.claim_job(db_session, "w3", ("lifecycle_test",), 60) is None


def test_stage_lifecycle(auth_client: TestClient, db_session: Session) -> None:
    workspace = make_workspace(auth_client)
    job = submit(auth_client, workspace["id"]).json()["data"]
    job_id = uuid.UUID(job["id"])
    job_service.claim_job(db_session, "stage-w", ("lifecycle_test",), 60)
    first = job_service.record_stage(db_session, job_id, "stage-w", "fetch_manifest", "running")
    assert first["attempt"] == 1
    done = job_service.record_stage(
        db_session, job_id, "stage-w", "fetch_manifest", "completed",
        result_summary={"file_count": 3},
    )
    assert done["status"] == "completed"
    with pytest.raises(ApiError) as exc_info:
        job_service.record_stage(db_session, job_id, "stage-w", "fetch_manifest", "completed")
    assert exc_info.value.code == "INVALID_TRANSITION"
    # Re-running a finished stage opens a new attempt.
    rerun = job_service.record_stage(db_session, job_id, "stage-w", "fetch_manifest", "running")
    assert rerun["attempt"] == 2
    with pytest.raises(ApiError):
        job_service.record_stage(db_session, job_id, "impostor-x", "other", "running")

    stages = auth_client.get(f"/api/v1/jobs/{job['id']}/stages").json()["data"]["stages"]
    assert len(stages) == 2
    assert stages[0]["result_summary"] == {"file_count": 3}
