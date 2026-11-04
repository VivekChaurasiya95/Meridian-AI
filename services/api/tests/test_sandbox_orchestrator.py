"""Sandbox orchestrator tests (M5.2.6-8): fake daemon, real Postgres.

The container daemon is faked; everything else is real — API submit
validation, atomic claiming, workspace-scoped materialization against
MinIO-faked storage, execution-row persistence, stages, and cleanup.
Daemon-contact behavior stays for the integration stage.
"""

import glob
import io
import os
import pathlib
import sys
import tempfile
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "services" / "worker"))

from sandbox import lifecycle, orchestrator
from sandbox.exceptions import SandboxError

from app.models import JobStage, SandboxExecution, User
from app.services import ingestion as ingestion_service
from app.services import jobs as job_service
from app.services import storage as storage_service
from app.services.object_store import FakeObjectStore

ORIGINAL = {"src/app.py": "print(1)\n", "README.md": "# demo\n"}


@pytest.fixture()
def db_session():  # type: ignore[no-untyped-def]
    engine = create_engine(os.environ["DATABASE_URL"])
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(autouse=True)
def fake_store(monkeypatch: pytest.MonkeyPatch) -> FakeObjectStore:
    store = FakeObjectStore()
    monkeypatch.setattr(ingestion_service, "_default_store", lambda: store)
    monkeypatch.setattr(storage_service, "get_store", lambda: store)
    return store


class FakeContainer:
    def __init__(  # type: ignore[no-untyped-def]
        self,
        exit_code=0,
        exit_after=1,
        logs_out=b"",
        logs_err=b"",
        labels=None,
        remove_fails=False,
    ):
        self._exit_code = exit_code
        self._exit_after = exit_after
        self._logs_out = logs_out
        self._logs_err = logs_err
        self.labels = dict(labels or {})
        self._remove_fails = remove_fails
        self._polls = 0
        self.started = False
        self.killed = False
        self.removed = False
        self.attrs = {"State": {"Status": "created", "ExitCode": 0}}

    def start(self) -> None:
        self.started = True
        self.attrs["State"]["Status"] = "running"

    def reload(self) -> None:
        self._polls += 1
        if self._polls >= self._exit_after:
            self.attrs["State"]["Status"] = "exited"
            self.attrs["State"]["ExitCode"] = self._exit_code

    def kill(self) -> None:
        self.killed = True
        self.attrs["State"]["Status"] = "exited"
        self.attrs["State"]["ExitCode"] = 137

    def logs(self, stdout=False, stderr=False):  # type: ignore[no-untyped-def]
        out = self._logs_out if stdout else b""
        err = self._logs_err if stderr else b""
        return out + err

    def remove(self, force: bool = False) -> None:
        assert force
        if self._remove_fails:
            raise RuntimeError("daemon refused removal")
        self.removed = True


class FakeContainers:
    def __init__(self, available) -> None:  # type: ignore[no-untyped-def]
        self.available = list(available)
        self.created_kwargs: dict = {}
        self.created: list = []

    def create(self, **kwargs):  # type: ignore[no-untyped-def]
        self.created_kwargs = kwargs
        container = self.available.pop(0) if self.available else FakeContainer()
        self.created.append(container)
        return container

    def list(self, all=False, filters=None):  # type: ignore[no-untyped-def]
        # Daemon-side listing covers pre-existing containers (available)
        # as well as ones created through this client.
        known = list(self.available) + list(self.created)
        wanted = (filters or {}).get("label", "")
        key, _, value = wanted.partition("=")
        return [c for c in known if c.labels.get(key) == value] if key else known


class FakeImage:
    id = "sha256:fakeimageid"


class FakeImages:
    def __init__(self) -> None:
        self.built: list = []
        self.removed: list = []

    def build(self, **kwargs):  # type: ignore[no-untyped-def]
        self.built.append(kwargs)
        return FakeImage(), []

    def remove(self, **kwargs):  # type: ignore[no-untyped-def]
        self.removed.append(kwargs)


class FakeClient:
    def __init__(self, containers) -> None:  # type: ignore[no-untyped-def]
        if isinstance(containers, FakeContainers):
            self.containers = containers
        else:
            self.containers = FakeContainers(containers)
        self.images = FakeImages()

    def ping(self) -> None:
        return None


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


def upload_snapshot(client: TestClient, project_id: str, data: bytes) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/source-uploads",
        files={"file": ("repo.zip", data, "application/zip")},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["snapshot"]


def submit_smoke(client: TestClient, workspace_id: str, snapshot_id: str) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/jobs",
        json={"job_type": "sandbox_smoke", "payload": {"snapshot_id": snapshot_id}},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def _open_session(factory, email: str = "owner@example.com"):  # type: ignore[no-untyped-def]
    session = factory()
    user = session.execute(select(User).where(User.email == email)).scalar_one()
    return session, user


def _sandboxes() -> set:
    return set(glob.glob(os.path.join(tempfile.gettempdir(), "meridian-sandbox-src-*")))


def _setup_job(auth_client, slug):  # type: ignore[no-untyped-def]
    workspace = make_workspace(auth_client, f"ws{slug}")
    project = make_project(auth_client, workspace["id"], f"p{slug}")
    snapshot = upload_snapshot(auth_client, project["id"], make_zip(ORIGINAL))
    job = submit_smoke(auth_client, workspace["id"], snapshot["id"])
    assert job["project_id"] == project["id"]
    return workspace, project, snapshot, job


def _execution_row(db_session_factory, job_id, attempt=1):  # type: ignore[no-untyped-def]
    session = db_session_factory()
    try:
        return (
            session.execute(
                select(SandboxExecution).where(
                    SandboxExecution.job_id == uuid.UUID(job_id),
                    SandboxExecution.attempt == attempt,
                )
            )
        ).scalar_one()
    finally:
        session.close()


def test_smoke_flow_completes_with_fake_daemon(
    auth_client: TestClient,
    db_session: Session,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
) -> None:
    _workspace, _project, snapshot, _job = _setup_job(auth_client, "full")
    claimed = job_service.claim_job(db_session, "w-orch", ("sandbox_smoke",), 60)
    assert claimed is not None
    container = FakeContainer(exit_code=0, exit_after=2, logs_out=b"meridian-sandbox-ok\n")
    client = FakeClient([container])
    before = _sandboxes()
    summary = orchestrator.execute_job(
        db_session_factory, claimed, "w-orch", client=client, store=fake_store
    )
    assert summary["exit_code"] == 0
    assert summary["timed_out"] is False
    assert summary["snapshot_id"] == snapshot["id"]
    assert summary["tree_digest"] == snapshot["tree_digest"]
    assert "meridian-sandbox-ok" in summary["stdout_excerpt"]
    assert summary["image_id"] == "sha256:fakeimageid"
    assert summary["image_tag"].startswith("meridian-sandbox-src-")
    assert summary["image_removed"] is True
    assert container.removed is True
    assert client.images.removed and client.images.removed[0]["image"] == summary["image_tag"]
    assert _sandboxes() == before

    row = _execution_row(db_session_factory, claimed["id"])
    assert row.status == "completed"
    assert row.cleanup_status == "cleaned"
    assert row.exit_code == 0
    assert row.worker_id == "w-orch"

    stages = {
        (stage.stage_key, stage.status)
        for stage in db_session.execute(
            select(JobStage).where(JobStage.job_id == uuid.UUID(claimed["id"]))
        ).scalars()
    }
    assert ("sandbox_prepare", "completed") in stages
    assert ("sandbox_execute", "completed") in stages

    done = job_service.complete_job(db_session, uuid.UUID(claimed["id"]), "w-orch", summary)
    assert done["status"] == "completed"


def test_smoke_nonzero_exit_fails_retryable(
    auth_client: TestClient,
    db_session: Session,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
) -> None:
    _w, _p, _s, _job = _setup_job(auth_client, "nz")
    claimed = job_service.claim_job(db_session, "w-nz", ("sandbox_smoke",), 60)
    assert claimed is not None
    client = FakeClient([FakeContainer(exit_code=3, exit_after=1)])
    with pytest.raises(SandboxError) as exc_info:
        orchestrator.execute_job(
            db_session_factory, claimed, "w-nz", client=client, store=fake_store
        )
    assert exc_info.value.code == "COMMAND_FAILED"
    assert exc_info.value.retryable is True
    row = _execution_row(db_session_factory, claimed["id"])
    assert row.status == "failed"
    assert row.exit_code == 3
    assert row.cleanup_status == "cleaned"


def test_smoke_timeout_kills_and_marks(
    auth_client: TestClient,
    db_session: Session,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
) -> None:
    _w, _p, _s, _job = _setup_job(auth_client, "to")
    claimed = job_service.claim_job(db_session, "w-to", ("sandbox_smoke",), 60)
    assert claimed is not None
    client = FakeClient([FakeContainer(exit_after=10**9)])
    with pytest.raises(SandboxError) as exc_info:
        orchestrator.execute_job(
            db_session_factory,
            claimed,
            "w-to",
            client=client,
            store=fake_store,
            timeout_seconds=1,
        )
    assert exc_info.value.code == "COMMAND_TIMEOUT"
    row = _execution_row(db_session_factory, claimed["id"])
    assert row.status == "timed_out"
    assert row.timed_out is True


def test_cancel_aborts_execution(
    auth_client: TestClient,
    db_session: Session,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
) -> None:
    _w, _p, _s, _job = _setup_job(auth_client, "cx")
    claimed = job_service.claim_job(db_session, "w-cx", ("sandbox_smoke",), 60)
    assert claimed is not None
    container = FakeContainer(exit_after=10**9)
    calls = {"n": 0}

    def abort() -> bool:
        calls["n"] += 1
        return calls["n"] >= 2

    with pytest.raises(SandboxError) as exc_info:
        orchestrator.execute_job(
            db_session_factory,
            claimed,
            "w-cx",
            client=FakeClient([container]),
            store=fake_store,
            is_cancelled=abort,
        )
    assert exc_info.value.code == "EXECUTION_CANCELLED"
    assert container.killed is True
    assert container.removed is True
    row = _execution_row(db_session_factory, claimed["id"])
    assert row.status == "cancelled"


def test_missing_snapshot_rejected_before_container(
    auth_client: TestClient,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
) -> None:
    workspace = make_workspace(auth_client, "wsghost")
    project = make_project(auth_client, workspace["id"], "ghost")
    snapshot = upload_snapshot(auth_client, project["id"], make_zip(ORIGINAL))
    job = submit_smoke(auth_client, workspace["id"], snapshot["id"])
    job["payload"] = {"snapshot_id": str(uuid.uuid4())}
    job["attempts"] = 1
    containers = FakeContainers([])
    with pytest.raises(SandboxError) as exc_info:
        orchestrator.execute_job(
            db_session_factory,
            job,
            "w-ghost",
            client=FakeClient(containers),
            store=fake_store,
        )
    assert exc_info.value.code == "RESOURCE_NOT_FOUND"
    assert exc_info.value.retryable is False
    assert containers.created == []


def test_cross_workspace_snapshot_rejected(
    auth_client: TestClient,
    db_session: Session,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
) -> None:
    _w, _p, _snapshot, job = _setup_job(auth_client, "xa")
    other = make_workspace(auth_client, "wsxb")
    job["workspace_id"] = other["id"]
    claimed = job_service.claim_job(db_session, "w-x", ("sandbox_smoke",), 60)
    assert claimed is not None
    claimed["workspace_id"] = other["id"]
    job = claimed
    containers = FakeContainers([])
    with pytest.raises(SandboxError) as exc_info:
        orchestrator.execute_job(
            db_session_factory,
            job,
            "w-x",
            client=FakeClient(containers),
            store=fake_store,
        )
    assert exc_info.value.code == "RESOURCE_NOT_FOUND"
    assert containers.created == []


def test_unknown_profile_rejected_without_row(
    auth_client: TestClient,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
) -> None:
    _w, _p, snapshot, job = _setup_job(auth_client, "up")
    job["payload"] = {"snapshot_id": snapshot["id"], "profile": "npm_install"}
    job["attempts"] = 1
    containers = FakeContainers([])
    with pytest.raises(SandboxError) as exc_info:
        orchestrator.execute_job(
            db_session_factory,
            job,
            "w-u",
            client=FakeClient(containers),
            store=fake_store,
        )
    assert exc_info.value.code == "UNKNOWN_PROFILE"
    assert containers.created == []
    session = db_session_factory()
    try:
        count = (
            session.execute(
                select(SandboxExecution).where(SandboxExecution.job_id == uuid.UUID(job["id"]))
            )
        ).all()
    finally:
        session.close()
    assert count == []


def test_retry_new_attempt_new_row_duplicate_refused(
    auth_client: TestClient,
    db_session: Session,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
) -> None:
    _w, _p, _s, _job = _setup_job(auth_client, "rt")
    claimed = job_service.claim_job(db_session, "w-rt", ("sandbox_smoke",), 60)
    assert claimed is not None
    first = orchestrator.execute_job(
        db_session_factory,
        claimed,
        "w-rt",
        client=FakeClient([FakeContainer()]),
        store=fake_store,
    )
    assert first["exit_code"] == 0
    claimed["attempts"] = 2
    second = orchestrator.execute_job(
        db_session_factory,
        claimed,
        "w-rt",
        client=FakeClient([FakeContainer()]),
        store=fake_store,
    )
    assert second["exit_code"] == 0
    claimed["attempts"] = 1
    with pytest.raises(SandboxError) as exc_info:
        orchestrator.execute_job(
            db_session_factory,
            claimed,
            "w-rt",
            client=FakeClient([FakeContainer()]),
            store=fake_store,
        )
    assert exc_info.value.code == "DUPLICATE_EXECUTION"


def test_prune_removes_stale_containers(
    auth_client: TestClient,
    db_session: Session,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
) -> None:
    _w, _p, snapshot, _job = _setup_job(auth_client, "pr")
    claimed = job_service.claim_job(db_session, "w-pr", ("sandbox_smoke",), 60)
    assert claimed is not None
    job_id = uuid.UUID(claimed["id"])
    live_id = uuid.uuid4().hex
    stale_id = uuid.uuid4().hex
    session = db_session_factory()
    try:
        lifecycle.create_execution(
            session,
            execution_id=uuid.UUID(hex=live_id),
            job_id=job_id,
            worker_id="w-pr",
            snapshot_id=uuid.UUID(snapshot["id"]),
            profile="sandbox_smoke",
            attempt=claimed["attempts"],
        )
        lifecycle.create_execution(
            session,
            execution_id=uuid.UUID(hex=stale_id),
            job_id=job_id,
            worker_id="w-pr",
            snapshot_id=uuid.UUID(snapshot["id"]),
            profile="sandbox_smoke",
            attempt=claimed["attempts"] + 1,
        )
        lifecycle.finish_execution(
            session,
            uuid.UUID(hex=stale_id),
            status="failed",
            error_code="COMMAND_FAILED",
            error_message="boom",
        )
    finally:
        session.close()
    live = FakeContainer(labels={"meridian.managed": "true", "meridian.execution_id": live_id})
    stale = FakeContainer(labels={"meridian.managed": "true", "meridian.execution_id": stale_id})
    ghost = FakeContainer(labels={"meridian.managed": "true", "meridian.execution_id": "b" * 32})
    plain = FakeContainer(labels={})
    client = FakeClient(FakeContainers([live, stale, ghost, plain]))

    def is_live(execution_id: str) -> bool:
        check = db_session_factory()
        try:
            return lifecycle.is_execution_live(check, uuid.UUID(hex=execution_id))
        finally:
            check.close()

    result = lifecycle.prune_stale_containers(client, is_live)
    assert result == {
        "pruned": 2,
        "kept": 1,
        "failed": 0,
        "pruned_ids": sorted([stale_id, "b" * 32]),
    }
    assert live.removed is False
    assert stale.removed is True
    assert ghost.removed is True
    assert plain.removed is False


def test_is_running_and_owned(auth_client: TestClient, db_session: Session) -> None:
    workspace = make_workspace(auth_client, "wsown")
    project = make_project(auth_client, workspace["id"], "own")
    snapshot = upload_snapshot(auth_client, project["id"], make_zip(ORIGINAL))
    job = submit_smoke(auth_client, workspace["id"], snapshot["id"])
    job_id = uuid.UUID(job["id"])
    claimed = job_service.claim_job(db_session, "w-own", ("sandbox_smoke",), 60)
    assert claimed is not None
    assert job_service.is_running_and_owned(db_session, job_id, "w-own") is True
    assert job_service.is_running_and_owned(db_session, job_id, "someone-else") is False
    db_session.execute(
        text("UPDATE jobs SET lease_expires_at = now() - interval '1 minute' WHERE id = :id"),
        {"id": str(job_id)},
    )
    assert job_service.is_running_and_owned(db_session, job_id, "w-own") is False
    reclaimed = job_service.claim_job(db_session, "w-own", ("sandbox_smoke",), 60)
    assert reclaimed is not None
    assert job_service.is_running_and_owned(db_session, job_id, "w-own") is True
    done = job_service.complete_job(db_session, job_id, "w-own", {"ok": True})
    assert done["status"] == "completed"
    assert job_service.is_running_and_owned(db_session, job_id, "w-own") is False


def _live_execution(db_session_factory, job_id, worker, snapshot_id, attempt):  # type: ignore[no-untyped-def]
    execution_id = uuid.uuid4().hex
    session = db_session_factory()
    try:
        lifecycle.create_execution(
            session,
            execution_id=uuid.UUID(hex=execution_id),
            job_id=uuid.UUID(job_id),
            worker_id=worker,
            snapshot_id=uuid.UUID(snapshot_id),
            profile="sandbox_smoke",
            attempt=attempt,
        )
    finally:
        session.close()
    return execution_id


def _managed_container(execution_id: str) -> FakeContainer:
    return FakeContainer(labels={"meridian.managed": "true", "meridian.execution_id": execution_id})


def _cleanup_status(db_session_factory, execution_id: str):  # type: ignore[no-untyped-def]
    session = db_session_factory()
    try:
        row = session.get(SandboxExecution, uuid.UUID(hex=execution_id))
        return row.cleanup_status if row is not None else None
    finally:
        session.close()


def test_recovery_keeps_live_prunes_stale_and_marks_rows(
    auth_client: TestClient,
    db_session: Session,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
) -> None:
    _w, _p, snapshot, _job = _setup_job(auth_client, "rc")
    claimed = job_service.claim_job(db_session, "w-rc", ("sandbox_smoke",), 60)
    assert claimed is not None
    live_id = _live_execution(
        db_session_factory, claimed["id"], "w-rc", snapshot["id"], claimed["attempts"]
    )
    stale_id = _live_execution(
        db_session_factory, claimed["id"], "w-rc", snapshot["id"], claimed["attempts"] + 1
    )
    session = db_session_factory()
    try:
        lifecycle.finish_execution(
            session,
            uuid.UUID(hex=stale_id),
            status="failed",
            error_code="COMMAND_FAILED",
            error_message="boom",
        )
    finally:
        session.close()
    live = _managed_container(live_id)
    stale = _managed_container(stale_id)
    ghost = _managed_container("c" * 32)
    client = FakeClient(FakeContainers([live, stale, ghost]))

    result = lifecycle.recover_orphans(db_session_factory, client)

    assert result["pruned"] == 2
    assert result["kept"] == 1
    assert result["failed"] == 0
    assert result["pruned_ids"] == sorted([stale_id, "c" * 32])
    assert live.removed is False
    assert stale.removed is True
    assert ghost.removed is True
    assert _cleanup_status(db_session_factory, live_id) == "pending"
    assert _cleanup_status(db_session_factory, stale_id) == "cleaned"


def test_recovery_reclaimed_job_is_stale(
    auth_client: TestClient,
    db_session: Session,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
) -> None:
    _w, _p, snapshot, _job = _setup_job(auth_client, "rk")
    claimed = job_service.claim_job(db_session, "w-a", ("sandbox_smoke",), 60)
    assert claimed is not None
    old_id = _live_execution(
        db_session_factory, claimed["id"], "w-a", snapshot["id"], claimed["attempts"]
    )
    db_session.execute(
        text("UPDATE jobs SET lease_expires_at = now() - interval '1 minute' WHERE id = :id"),
        {"id": claimed["id"]},
    )
    db_session.commit()
    reclaimed = job_service.claim_job(db_session, "w-b", ("sandbox_smoke",), 60)
    assert reclaimed is not None and reclaimed["worker_id"] == "w-b"
    container = _managed_container(old_id)

    result = lifecycle.recover_orphans(db_session_factory, FakeClient(FakeContainers([container])))

    assert result["pruned"] == 1
    assert container.removed is True
    assert _cleanup_status(db_session_factory, old_id) == "cleaned"


def test_recovery_prunes_rowless_malformed_keeps_unlabeled(
    auth_client: TestClient,
    db_session: Session,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
) -> None:
    _w, _p, _s, _job = _setup_job(auth_client, "rm")
    ghost = _managed_container("d" * 32)
    malformed = _managed_container("!!!not-hex!!!")
    plain = FakeContainer(labels={})
    client = FakeClient(FakeContainers([ghost, malformed, plain]))

    result = lifecycle.recover_orphans(db_session_factory, client)

    assert result["pruned"] == 2
    assert result["pruned_ids"] == sorted(["d" * 32, "!!!not-hex!!!"])
    assert ghost.removed is True
    assert malformed.removed is True
    assert plain.removed is False


def test_recovery_idempotent(
    auth_client: TestClient,
    db_session: Session,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
) -> None:
    _w, _p, snapshot, _job = _setup_job(auth_client, "ri")
    claimed = job_service.claim_job(db_session, "w-ri", ("sandbox_smoke",), 60)
    assert claimed is not None
    stale_id = _live_execution(
        db_session_factory, claimed["id"], "w-ri", snapshot["id"], claimed["attempts"]
    )
    session = db_session_factory()
    try:
        lifecycle.finish_execution(
            session,
            uuid.UUID(hex=stale_id),
            status="failed",
            error_code="COMMAND_FAILED",
            error_message="boom",
        )
    finally:
        session.close()
    containers = FakeContainers([_managed_container(stale_id)])
    client = FakeClient(containers)
    first = lifecycle.recover_orphans(db_session_factory, client)
    assert first["pruned"] == 1
    # Model daemon truth: destroyed containers vanish from later listings.
    containers.available = [c for c in containers.available if not c.removed]
    second = lifecycle.recover_orphans(db_session_factory, client)
    assert second == {"pruned": 0, "kept": 0, "failed": 0, "pruned_ids": []}


def test_recovery_db_outage_keeps_containers(
    auth_client: TestClient,
    db_session: Session,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
) -> None:
    _w, _p, snapshot, _job = _setup_job(auth_client, "ro")
    claimed = job_service.claim_job(db_session, "w-ro", ("sandbox_smoke",), 60)
    assert claimed is not None
    stale_id = _live_execution(
        db_session_factory, claimed["id"], "w-ro", snapshot["id"], claimed["attempts"]
    )
    session = db_session_factory()
    try:
        lifecycle.finish_execution(
            session,
            uuid.UUID(hex=stale_id),
            status="failed",
            error_code="COMMAND_FAILED",
            error_message="boom",
        )
    finally:
        session.close()
    container = _managed_container(stale_id)

    def broken_factory():  # type: ignore[no-untyped-def]
        raise RuntimeError("database unreachable")

    result = lifecycle.recover_orphans(broken_factory, FakeClient(FakeContainers([container])))

    assert result["pruned"] == 0
    assert result["kept"] == 1
    assert container.removed is False
