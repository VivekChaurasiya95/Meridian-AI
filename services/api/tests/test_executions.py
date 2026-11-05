"""Execution read tests (M5): job executions list + detail, tenant-isolated.

Execution rows are written by the worker lifecycle and served to workspace
members with redacted, bounded excerpts. Foreign or unknown ids answer 404.
"""

import pathlib
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "services" / "worker"))

from sandbox import lifecycle

from app.services import jobs as job_service
from app.services.redact import REPLACEMENT


@contextmanager
def _session(migrated_db: str) -> Iterator[Session]:
    engine = create_engine(migrated_db)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def make_workspace(client: TestClient, slug: str) -> dict:
    response = client.post("/api/v1/workspaces", json={"name": slug, "slug": slug})
    assert response.status_code == 201, response.text
    return response.json()["data"]


def submit(client: TestClient, workspace_id: str) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/jobs",
        json={"job_type": "lifecycle_test", "payload": {"note": "exec"}},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def record_finished_execution(db_session: Session, job_id: str) -> uuid.UUID:
    claimed = job_service.claim_job(db_session, "w-exec", ("lifecycle_test",), 60)
    assert claimed is not None and claimed["id"] == job_id
    execution_id = uuid.uuid4()
    lifecycle.create_execution(
        db_session,
        execution_id=execution_id,
        job_id=uuid.UUID(job_id),
        worker_id="w-exec",
        snapshot_id=None,
        profile="sandbox_smoke",
        attempt=claimed["attempts"],
    )
    lifecycle.finish_execution(
        db_session,
        execution_id,
        status="completed",
        exit_code=0,
        duration_ms=120,
        stdout="meridian-sandbox-ok\npassword=hunter2\n",
        stderr="",
    )
    return execution_id


def test_list_and_get_execution(auth_client: TestClient, migrated_db: str) -> None:
    workspace = make_workspace(auth_client, "wsexec")
    job = submit(auth_client, workspace["id"])
    with _session(migrated_db) as session:
        execution_id = record_finished_execution(session, job["id"])

    listed = auth_client.get(f"/api/v1/jobs/{job['id']}/executions").json()["data"]
    assert len(listed["executions"]) == 1
    row = listed["executions"][0]
    assert row["id"] == str(execution_id)
    assert row["job_id"] == job["id"]
    assert row["status"] == "completed"
    assert row["exit_code"] == 0
    assert row["cleanup_status"] == "pending"
    # Secrets in container output never reach API responses.
    assert "hunter2" not in row["stdout_excerpt"]
    assert REPLACEMENT in row["stdout_excerpt"]
    assert row["stdout_chars"] > 0

    detail = auth_client.get(f"/api/v1/executions/{execution_id}").json()["data"]
    assert detail["id"] == str(execution_id)
    assert detail["stdout_excerpt"] == row["stdout_excerpt"]


def test_executions_are_workspace_scoped(
    auth_client_factory,  # type: ignore[no-untyped-def]
    migrated_db: str,
) -> None:
    owner = auth_client_factory("owner-ex@example.com")
    outsider = auth_client_factory("outsider-ex@example.com")
    workspace = make_workspace(owner, "wsexec-s")
    job = submit(owner, workspace["id"])
    assert outsider.get(f"/api/v1/jobs/{job['id']}/executions").status_code == 404
    assert outsider.get(f"/api/v1/executions/{uuid.uuid4()}").status_code == 404
    with _session(migrated_db) as session:
        execution_id = record_finished_execution(session, job["id"])
    assert outsider.get(f"/api/v1/executions/{execution_id}").status_code == 404
