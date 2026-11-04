"""Sandbox runtime + workspace tests (M5.2.3-4).

Docker-daemon contact is faked; no test here needs a daemon. The single
DB test reuses the storage-suite helpers to prove the real
materialization path through the workspace module.
"""

import io
import os
import pathlib
import sys
import tarfile
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "services" / "worker"))

from sandbox import container_runtime, workspace
from sandbox.exceptions import SandboxError

from app.models import User
from app.services import ingestion as ingestion_service
from app.services import storage as storage_service
from app.services.object_store import FakeObjectStore

ORIGINAL = {"src/app.py": "print(1)\n", "README.md": "# demo\n"}


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


def _open_session(factory, email: str = "owner@example.com"):  # type: ignore[no-untyped-def]
    session = factory()
    user = session.execute(select(User).where(User.email == email)).scalar_one()
    return session, user


@pytest.fixture(autouse=True)
def fake_store(monkeypatch: pytest.MonkeyPatch) -> FakeObjectStore:
    store = FakeObjectStore()
    monkeypatch.setattr(ingestion_service, "_default_store", lambda: store)
    monkeypatch.setattr(storage_service, "get_store", lambda: store)
    return store


class FakeContainer:
    """Minimal docker-py container surface for runtime tests."""

    def __init__(
        self,
        exit_code: int = 0,
        exit_after: int = 1,
        logs_out: bytes = b"",
        logs_err: bytes = b"",
        remove_fails: bool = False,
    ) -> None:
        self._exit_code = exit_code
        self._exit_after = exit_after
        self._logs_out = logs_out
        self._logs_err = logs_err
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

    def logs(self, stdout: bool = False, stderr: bool = False):  # type: ignore[no-untyped-def]
        out = self._logs_out if stdout else b""
        err = self._logs_err if stderr else b""
        return out + err

    def remove(self, force: bool = False) -> None:
        assert force
        if self._remove_fails:
            raise RuntimeError("daemon refused removal")
        self.removed = True


class FakeImage:
    id = "sha256:fakeimageid"


class FakeImages:
    def __init__(self, fail_build: bool = False, fail_remove: bool = False) -> None:
        self.fail_build = fail_build
        self.fail_remove = fail_remove
        self.built: list = []
        self.removed: list = []

    def build(self, **kwargs):  # type: ignore[no-untyped-def]
        if self.fail_build:
            raise RuntimeError("daemon refused build")
        self.built.append(kwargs)
        return FakeImage(), []

    def remove(self, **kwargs):  # type: ignore[no-untyped-def]
        if self.fail_remove:
            raise RuntimeError("daemon refused image removal")
        self.removed.append(kwargs)


class FakeContainers:
    def __init__(self, container: FakeContainer) -> None:
        self.container = container
        self.created_kwargs: dict = {}

    def create(self, **kwargs):  # type: ignore[no-untyped-def]
        self.created_kwargs = kwargs
        return self.container


class FakeClient:
    def __init__(self, container: FakeContainer) -> None:
        self.containers = FakeContainers(container)
        self.images = FakeImages()
        self.pinged = False

    def ping(self) -> None:
        self.pinged = True


def test_missing_docker_sdk_is_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "docker", None)
    with pytest.raises(SandboxError) as exc_info:
        container_runtime.get_client()
    assert exc_info.value.code == "RUNTIME_NOT_CONFIGURED"


def test_create_forwards_spec_kwargs() -> None:
    container = FakeContainer()
    client = FakeClient(container)
    spec = {"image": "img", "name": "n"}
    assert container_runtime.create_container(client, spec) is container
    assert client.containers.created_kwargs == spec


def test_run_success_returns_exit_code() -> None:
    container = FakeContainer(exit_code=0, exit_after=2)
    result = container_runtime.run_to_completion(container, 30, poll_interval=0.001)
    assert result == {"exit_code": 0, "timed_out": False, "duration_ms": result["duration_ms"]}
    assert container.started and not container.killed


def test_run_nonzero_exit_is_reported_not_raised() -> None:
    container = FakeContainer(exit_code=3, exit_after=1)
    result = container_runtime.run_to_completion(container, 30, poll_interval=0.001)
    assert result["exit_code"] == 3
    assert result["timed_out"] is False


def test_run_timeout_kills_container() -> None:
    container = FakeContainer(exit_after=10**9)
    result = container_runtime.run_to_completion(container, 0.02, poll_interval=0.001)
    assert result["timed_out"] is True
    assert container.killed


def test_run_abort_cancels_execution() -> None:
    container = FakeContainer(exit_after=10**9)
    calls = {"n": 0}

    def abort() -> bool:
        calls["n"] += 1
        return calls["n"] >= 2

    with pytest.raises(SandboxError) as exc_info:
        container_runtime.run_to_completion(
            container, 30, poll_interval=0.001, should_abort=abort
        )
    assert exc_info.value.code == "EXECUTION_CANCELLED"
    assert container.killed


def test_logs_are_bounded_with_marker() -> None:
    container = FakeContainer(logs_out=b"x" * 2000, logs_err=b"e" * 10)
    result = container_runtime.read_logs(container, 100)
    assert result["stdout"].endswith(b"x" * (100 - len(container_runtime.TRUNCATION_MARKER)))
    assert result["stdout"].startswith(container_runtime.TRUNCATION_MARKER)
    assert result["stderr"] == b"e" * 10
    assert result["truncated"] is True
    small = container_runtime.read_logs(FakeContainer(logs_out=b"ok\n"), 100)
    assert small["stdout"] == b"ok\n"
    assert small["truncated"] is False


def test_build_source_image_is_hermetic() -> None:
    client = FakeClient(FakeContainer())
    image_id = container_runtime.build_source_image(client, b"context-tar", "tag-x")
    assert image_id == "sha256:fakeimageid"
    assert len(client.images.built) == 1
    call = client.images.built[0]
    assert call["tag"] == "tag-x"
    assert call["pull"] is False
    assert call["custom_context"] is True
    with pytest.raises(SandboxError) as exc_info:
        container_runtime.build_source_image(client, b"", "tag-x")
    assert exc_info.value.code == "EMPTY_SOURCE"
    client.images.fail_build = True
    with pytest.raises(SandboxError) as exc_info:
        container_runtime.build_source_image(client, b"context-tar", "tag-x")
    assert exc_info.value.code == "IMAGE_BUILD_FAILED"
    assert exc_info.value.retryable is True


def test_remove_image_never_raises() -> None:
    client = FakeClient(FakeContainer())
    assert container_runtime.remove_image(client, "tag-x") == "removed"
    assert client.images.removed[0]["image"] == "tag-x"
    client.images.fail_remove = True
    assert container_runtime.remove_image(client, "tag-x") == "image_cleanup_failed"


def test_destroy_never_raises() -> None:
    assert container_runtime.destroy_container(FakeContainer()) == "cleaned"
    assert container_runtime.destroy_container(FakeContainer(remove_fails=True)) == (
        "cleanup_failed"
    )


def test_workspace_create_destroy_roundtrip(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = workspace.create_workspace()
    assert os.path.isdir(path)
    assert workspace.destroy_workspace(path) is True
    assert not os.path.exists(path)
    assert workspace.destroy_workspace(path) is True


def test_pack_build_context_is_deterministic(tmp_path) -> None:  # type: ignore[no-untyped-def]
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    (src / "sub" / "a.py").write_bytes(b"print(1)\n")
    first, first_digest = workspace.pack_build_context(str(src))
    second, second_digest = workspace.pack_build_context(str(src))
    assert first == second
    assert first_digest == second_digest
    assert len(first_digest) == 64
    import io

    with tarfile.open(fileobj=io.BytesIO(first), mode="r") as tar:
        names = sorted(m.name for m in tar.getmembers())
        assert names[0] == workspace.BUILD_DOCKERFILE_NAME
        assert "sub/a.py" in names
        members = [m for m in tar.getmembers() if m.isfile()]
        assert all(m.mode == 0o644 for m in members)
        assert all(m.uid == 0 and m.gid == 0 for m in members)
        dockerfile = tar.extractfile(workspace.BUILD_DOCKERFILE_NAME)
        assert dockerfile is not None
        body = dockerfile.read().decode("utf-8")
        assert "FROM python:3.12-slim" in body
        assert "USER 65534:65534" in body
        assert "RUN" not in body


def test_pack_build_context_repo_dockerfile_stays_inert_data(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A snapshot root Dockerfile must never become the build file.

    The trusted build instructions live under a reserved name; a
    repository file named exactly ``Dockerfile`` is preserved as inert
    data for /work, even when it carries hostile RUN steps.
    """
    src = tmp_path / "src"
    src.mkdir()
    (src / "Dockerfile").write_bytes(b"FROM python:3.12-slim\nRUN exit 3\n")
    (src / "app.py").write_bytes(b"print(1)\n")
    packed, _digest = workspace.pack_build_context(str(src))
    with tarfile.open(fileobj=io.BytesIO(packed), mode="r") as tar:
        names = [m.name for m in tar.getmembers()]
        assert names.count("Dockerfile") == 1  # the repo file, as data
        assert names.count(workspace.BUILD_DOCKERFILE_NAME) == 1
        trusted = tar.extractfile(workspace.BUILD_DOCKERFILE_NAME)
        assert trusted is not None
        body = trusted.read().decode("utf-8")
        assert "RUN" not in body
        assert "USER 65534:65534" in body
        repo_file = tar.extractfile("Dockerfile")
        assert repo_file is not None
        assert "RUN exit 3" in repo_file.read().decode("utf-8")


def test_pack_build_context_rejects_reserved_root_names(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Reserved build-control names at the context root fail closed."""
    for reserved in (workspace.BUILD_DOCKERFILE_NAME, ".dockerignore"):
        src = tmp_path / reserved.replace(".", "_")
        src.mkdir()
        (src / reserved).write_bytes(b"data\n")
        with pytest.raises(SandboxError) as exc_info:
            workspace.pack_build_context(str(src))
        assert exc_info.value.code == "RESERVED_FILENAME"
    # The same names nested in subdirectories are inert data.
    nested = tmp_path / "nested"
    (nested / "sub").mkdir(parents=True)
    (nested / "sub" / workspace.BUILD_DOCKERFILE_NAME).write_bytes(b"data\n")
    (nested / "sub" / ".dockerignore").write_bytes(b"data\n")
    packed, _digest = workspace.pack_build_context(str(nested))
    with tarfile.open(fileobj=io.BytesIO(packed), mode="r") as tar:
        names = sorted(m.name for m in tar.getmembers())
    assert f"sub/{workspace.BUILD_DOCKERFILE_NAME}" in names
    assert "sub/.dockerignore" in names


def test_build_source_image_pins_trusted_dockerfile_and_no_network() -> None:
    """The daemon must build the reserved file with no build network."""
    client = FakeClient(FakeContainer())
    container_runtime.build_source_image(client, b"context-tar", "tag-x")
    call = client.images.built[0]
    assert call["dockerfile"] == workspace.BUILD_DOCKERFILE_NAME
    assert call["network_mode"] == "none"
    assert call["pull"] is False
    assert call["custom_context"] is True


def test_pack_build_context_enforces_size_cap(tmp_path) -> None:  # type: ignore[no-untyped-def]
    src = tmp_path / "src"
    src.mkdir()
    (src / "big.bin").write_bytes(b"0" * 100)
    with pytest.raises(SandboxError) as exc_info:
        workspace.pack_build_context(str(src), max_bytes=10)
    assert exc_info.value.code == "WORKSPACE_TOO_LARGE"


def test_prepare_source_materializes_real_snapshot(
    auth_client: TestClient,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
    tmp_path,  # type: ignore[no-untyped-def]
) -> None:
    ws = make_workspace(auth_client, "wssrc")
    project = make_project(auth_client, ws["id"], "src")
    snapshot = upload_snapshot(auth_client, project["id"], make_zip(ORIGINAL))
    session, user = _open_session(db_session_factory)
    try:
        dest = tmp_path / "out"
        dest.mkdir()
        result = workspace.prepare_source(
            session, user, uuid.UUID(snapshot["id"]), str(dest), store=fake_store
        )
        packed, digest = workspace.pack_build_context(str(dest))
    finally:
        session.close()
        assert workspace.destroy_workspace(str(tmp_path / "out")) is True
    assert result["files"] == len(ORIGINAL)
    assert len(packed) > 0
    assert len(digest) == 64
