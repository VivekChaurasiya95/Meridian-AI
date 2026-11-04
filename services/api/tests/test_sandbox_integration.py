"""Sandbox daemon integration tests (M5.2.8): real Docker, real Postgres.

Needs Docker Desktop in Linux-container mode and the smoke image pulled
(``docker pull python:3.12-slim``). Snapshot bytes come from the fake
store — object storage has its own round-trip test; what is proven here
is daemon behavior: isolation flags, timeouts, cancellation, cleanup,
and pruning. Every test destroys its containers in ``finally`` blocks;
execution ids are unique per run so nothing collides.
"""

import io
import os
import pathlib
import sys
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "services" / "worker"))

from sandbox import container_runtime, lifecycle, orchestrator
from sandbox.container_spec import build_spec
from sandbox.exceptions import SandboxError
from sandbox.execution_policy import get_policy

from app.models import SandboxExecution, User
from app.services import ingestion as ingestion_service
from app.services import jobs as job_service
from app.services import storage as storage_service
from app.services.object_store import FakeObjectStore

docker = pytest.importorskip("docker", reason="The Docker SDK is not installed.")

ORIGINAL = {"src/app.py": "print(1)\n", "README.md": "# demo\n"}

# A repository Dockerfile carrying invalid build instructions: if the
# daemon ever selected it as the build file, the build would fail.
# End-to-end success therefore proves the trusted reserved build file
# was used and the repo Dockerfile stayed inert data.
HOSTILE_DOCKERFILE = {
    "Dockerfile": "THIS IS NOT A VALID DOCKERFILE\nRUN exit 3\n",
    "src/app.py": "print(1)\n",
}


@pytest.fixture(scope="session")
def docker_client():  # type: ignore[no-untyped-def]
    try:
        return container_runtime.get_client()
    except SandboxError as exc:
        pytest.skip(f"Docker daemon unavailable: {exc.code}")


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


def make_zip(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _setup_job(auth_client, slug, entries: dict | None = None):  # type: ignore[no-untyped-def]
    response = auth_client.post(
        "/api/v1/workspaces", json={"name": f"ws{slug}", "slug": f"ws{slug}"}
    )
    assert response.status_code == 201, response.text
    workspace_id = response.json()["data"]["id"]
    response = auth_client.post(
        f"/api/v1/workspaces/{workspace_id}/projects",
        json={"name": f"p{slug}", "slug": f"p{slug}"},
    )
    assert response.status_code == 201, response.text
    project_id = response.json()["data"]["id"]
    response = auth_client.post(
        f"/api/v1/projects/{project_id}/source-uploads",
        files={"file": ("repo.zip", make_zip(entries or ORIGINAL), "application/zip")},
    )
    assert response.status_code == 201, response.text
    snapshot = response.json()["data"]["snapshot"]
    response = auth_client.post(
        f"/api/v1/workspaces/{workspace_id}/jobs",
        json={"job_type": "sandbox_smoke", "payload": {"snapshot_id": snapshot["id"]}},
    )
    assert response.status_code == 201, response.text
    return snapshot, response.json()["data"]


def _open_session(factory, email: str = "owner@example.com"):  # type: ignore[no-untyped-def]
    session = factory()
    user = session.execute(select(User).where(User.email == email)).scalar_one()
    return session, user


def _sleep_spec(policy, execution_id: str, seconds: int) -> dict:
    """Test-only spec variant: identical isolation kwargs, sleep command.

    Isolation properties come from the kwargs, not the argv; the smoke
    policy argv cannot sleep, so probes that need a running container use
    this variant and say so.
    """
    return dict(build_spec(policy, execution_id), command=["sleep", str(seconds)])


def test_daemon_smoke_end_to_end(
    auth_client: TestClient,
    db_session: Session,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
    docker_client,  # type: ignore[no-untyped-def]
) -> None:
    _snapshot, _job = _setup_job(auth_client, "it")
    claimed = job_service.claim_job(db_session, "w-it", ("sandbox_smoke",), 120)
    assert claimed is not None
    summary = orchestrator.execute_job(
        db_session_factory, claimed, "w-it", client=docker_client, store=fake_store
    )
    assert summary["exit_code"] == 0
    assert summary["timed_out"] is False
    assert "meridian-sandbox-ok" in summary["stdout_excerpt"]
    assert summary["files"] == len(ORIGINAL)
    assert summary["image_id"].startswith("sha256:")
    assert summary["image_tag"].startswith("meridian-sandbox-src-")
    assert summary["image_removed"] is True

    session = db_session_factory()
    try:
        row = session.get(SandboxExecution, uuid.UUID(hex=summary["execution_id"]))
        assert row is not None
        assert row.status == "completed"
        assert row.cleanup_status == "cleaned"
    finally:
        session.close()

    name = f"meridian-sandbox-{summary['execution_id'][:12]}"
    with pytest.raises(docker.errors.NotFound):
        docker_client.containers.get(name)
    with pytest.raises(docker.errors.ImageNotFound):
        docker_client.images.get(summary["image_tag"])

    done = job_service.complete_job(
        db_session, uuid.UUID(claimed["id"]), "w-it", summary
    )
    assert done["status"] == "completed"


def test_daemon_ignores_repo_dockerfile(
    auth_client: TestClient,
    db_session: Session,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
    docker_client,  # type: ignore[no-untyped-def]
) -> None:
    _snapshot, _job = _setup_job(auth_client, "hd", entries=HOSTILE_DOCKERFILE)
    claimed = job_service.claim_job(db_session, "w-hd", ("sandbox_smoke",), 120)
    assert claimed is not None
    summary = orchestrator.execute_job(
        db_session_factory, claimed, "w-hd", client=docker_client, store=fake_store
    )
    assert summary["exit_code"] == 0
    assert "meridian-sandbox-ok" in summary["stdout_excerpt"]
    assert summary["files"] == len(HOSTILE_DOCKERFILE)
    assert summary["image_removed"] is True
    done = job_service.complete_job(
        db_session, uuid.UUID(claimed["id"]), "w-hd", summary
    )
    assert done["status"] == "completed"


def test_daemon_enforces_isolation(
    docker_client,  # type: ignore[no-untyped-def]
) -> None:
    policy = get_policy("sandbox_smoke")
    execution_id = uuid.uuid4().hex
    spec = _sleep_spec(policy, execution_id, 60)
    container = container_runtime.create_container(docker_client, spec)
    try:
        container.start()
        assert container.attrs["Config"]["User"] == "65534:65534"
        host_config = container.attrs["HostConfig"]
        assert host_config["ReadonlyRootfs"] is True
        assert host_config["Privileged"] is False
        assert set(host_config["CapDrop"]) == {"ALL"}
        assert "no-new-privileges:true" in host_config["SecurityOpt"]
        assert host_config["NetworkMode"] == "none"
        networks = container.attrs["NetworkSettings"]["Networks"]
        assert set(networks) <= {"none"}
        for details in networks.values():
            assert not details.get("IPAddress")
            assert not details.get("Gateway")
        # Functional check: the routing table carries no routes, so no
        # egress is possible regardless of what the config claims.
        code, routes = container.exec_run(["sh", "-c", "cat /proc/net/route"])
        assert code == 0
        assert len(routes.strip().splitlines()) == 1

        code, uid = container.exec_run(["id", "-u"])
        assert code == 0 and uid.strip() == b"65534"

        code, _ = container.exec_run(["sh", "-c", "touch /evil && echo writable"])
        assert code != 0

        code, caps = container.exec_run(["sh", "-c", "grep CapEff /proc/self/status"])
        assert code == 0 and caps.split()[1] == b"0000000000000000"

        code, _ = container.exec_run(["sh", "-c", "ls /var/run/docker.sock"])
        assert code != 0

        code, env = container.exec_run(["env"])
        assert code == 0
        for secret in (b"DATABASE_URL", b"S3_", b"SECRET", b"FIREBASE"):
            assert secret not in env.upper()
    finally:
        assert container_runtime.destroy_container(container) == "cleaned"


def test_daemon_timeout_kills_container(
    docker_client,  # type: ignore[no-untyped-def]
) -> None:
    policy = get_policy("sandbox_smoke")
    container = container_runtime.create_container(
        docker_client, _sleep_spec(policy, uuid.uuid4().hex, 120)
    )
    try:
        result = container_runtime.run_to_completion(container, 3, poll_interval=0.2)
        assert result["timed_out"] is True
        assert result["exit_code"] == 137
    finally:
        assert container_runtime.destroy_container(container) == "cleaned"


def test_daemon_cancel_kills_container(
    docker_client,  # type: ignore[no-untyped-def]
) -> None:
    policy = get_policy("sandbox_smoke")
    container = container_runtime.create_container(
        docker_client, _sleep_spec(policy, uuid.uuid4().hex, 120)
    )
    try:
        calls = {"n": 0}

        def abort() -> bool:
            calls["n"] += 1
            return calls["n"] >= 2

        with pytest.raises(SandboxError) as exc_info:
            container_runtime.run_to_completion(
                container, 120, poll_interval=0.1, should_abort=abort
            )
        assert exc_info.value.code == "EXECUTION_CANCELLED"
    finally:
        assert container_runtime.destroy_container(container) == "cleaned"


def test_daemon_prune_removes_stale(
    docker_client,  # type: ignore[no-untyped-def]
) -> None:
    policy = get_policy("sandbox_smoke")
    stale = container_runtime.create_container(
        docker_client, _sleep_spec(policy, uuid.uuid4().hex, 120)
    )
    live = container_runtime.create_container(
        docker_client, _sleep_spec(policy, uuid.uuid4().hex, 120)
    )
    try:
        stale.start()
        live.start()
        stale_eid = stale.labels["meridian.execution_id"]
        live_eid = live.labels["meridian.execution_id"]
        result = lifecycle.prune_stale_containers(
            docker_client, lambda eid: eid == live_eid
        )
        assert result["kept"] == 1
        assert result["failed"] == 0
        assert result["pruned"] >= 1
        with pytest.raises(docker.errors.NotFound):
            docker_client.containers.get(stale.name)
        assert stale_eid != live_eid
    finally:
        container_runtime.destroy_container(stale)
        container_runtime.destroy_container(live)
