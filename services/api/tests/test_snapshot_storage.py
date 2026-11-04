"""Snapshot content storage tests (M5.1, docs/DECISIONS.md D51).

Object I/O always runs against ``FakeObjectStore`` (autouse fixture):
no MinIO in unit tests. The single MinIO round-trip test at the bottom
is skipped unless ``MERIDIAN_MINIO_TEST=1`` with S3 settings configured.
"""

import hashlib
import io
import json
import os
import tarfile
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.envelope import ApiError
from app.models import RepositorySnapshot, User
from app.services import ingestion as ingestion_service
from app.services import storage as storage_service
from app.services.object_store import FakeObjectStore, StorageError

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


@pytest.fixture(autouse=True)
def fake_store(monkeypatch: pytest.MonkeyPatch) -> FakeObjectStore:
    store = FakeObjectStore()
    monkeypatch.setattr(ingestion_service, "_default_store", lambda: store)
    monkeypatch.setattr(storage_service, "get_store", lambda: store)
    return store


def _only_key(store: FakeObjectStore) -> str:
    assert len(store.objects) == 1
    full = next(iter(store.objects))
    return full.split("/", 1)[1]


def test_upload_stores_private_object_and_marks_ready(
    auth_client: TestClient, fake_store: FakeObjectStore
) -> None:
    workspace = make_workspace(auth_client, "wsst")
    project = make_project(auth_client, workspace["id"], "stored")
    snapshot = upload_snapshot(auth_client, project["id"], make_zip(ORIGINAL))

    assert snapshot["storage_status"] == "ready"
    assert snapshot["storage_bytes"] is not None and snapshot["storage_bytes"] > 0
    assert snapshot["storage_verified_at"] is not None
    assert snapshot["error_code"] is None

    key = _only_key(fake_store)
    assert key.startswith("snapshots/") and key.endswith(".tar")
    assert len(key.rsplit("/", 1)[-1].removesuffix(".tar")) == 64

    # Credential leakage prevention: no storage secrets in the payload.
    blob = json.dumps(snapshot).lower()
    for token in ("minio", "secret", "access_key", "aws_", "endpoint"):
        assert token not in blob


def test_duplicate_content_across_projects_reuses_object(
    auth_client: TestClient, fake_store: FakeObjectStore
) -> None:
    workspace = make_workspace(auth_client, "wsdup")
    first = make_project(auth_client, workspace["id"], "dup-a")
    second = make_project(auth_client, workspace["id"], "dup-b")
    data = make_zip(ORIGINAL)
    one = upload_snapshot(auth_client, first["id"], data)
    two = upload_snapshot(auth_client, second["id"], data)
    assert one["id"] != two["id"]
    assert one["tree_digest"] == two["tree_digest"]
    assert len(fake_store.objects) == 1


def test_verify_endpoint_confirms_ready(auth_client: TestClient) -> None:
    workspace = make_workspace(auth_client, "wsvf")
    project = make_project(auth_client, workspace["id"], "vf")
    snapshot = upload_snapshot(auth_client, project["id"], make_zip(ORIGINAL))
    response = auth_client.post(f"/api/v1/snapshots/{snapshot['id']}/verify")
    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["ok"] is True
    assert body["tree_digest"] == snapshot["tree_digest"]


def test_verify_missing_object_marks_integrity_failed(
    auth_client: TestClient, fake_store: FakeObjectStore
) -> None:
    workspace = make_workspace(auth_client, "wsmis")
    project = make_project(auth_client, workspace["id"], "mis")
    snapshot = upload_snapshot(auth_client, project["id"], make_zip(ORIGINAL))
    fake_store.objects.clear()

    response = auth_client.post(f"/api/v1/snapshots/{snapshot['id']}/verify")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SNAPSHOT_NOT_READY"

    detail = auth_client.get(f"/api/v1/snapshots/{snapshot['id']}").json()["data"]
    assert detail["storage_status"] == "integrity_failed"


def test_corrupted_object_detected_on_verify(
    auth_client: TestClient, fake_store: FakeObjectStore
) -> None:
    workspace = make_workspace(auth_client, "wscor")
    project = make_project(auth_client, workspace["id"], "cor")
    snapshot = upload_snapshot(auth_client, project["id"], make_zip(ORIGINAL))
    full = next(iter(fake_store.objects))
    fake_store.objects[full] = b"tampered-bytes"

    response = auth_client.post(f"/api/v1/snapshots/{snapshot['id']}/verify")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INTEGRITY_FAILED"


def _open_session(factory, email: str = "owner@example.com"):  # type: ignore[no-untyped-def]
    session = factory()
    user = session.execute(select(User).where(User.email == email)).scalar_one()
    return session, user


def test_materialize_round_trip_matches_original(
    auth_client: TestClient,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
    tmp_path,  # type: ignore[no-untyped-def]
) -> None:
    workspace = make_workspace(auth_client, "wsmat")
    project = make_project(auth_client, workspace["id"], "mat")
    snapshot = upload_snapshot(auth_client, project["id"], make_zip(ORIGINAL))

    session, user = _open_session(db_session_factory)
    try:
        dest = tmp_path / "out"
        dest.mkdir()
        result = storage_service.materialize_snapshot(
            session, user, uuid.UUID(snapshot["id"]), str(dest), store=fake_store
        )
    finally:
        session.close()
    assert result["files"] == len(ORIGINAL)
    assert result["tree_digest"] == snapshot["tree_digest"]
    for rel, content in ORIGINAL.items():
        with open(os.path.join(str(dest), *rel.split("/")), encoding="utf-8") as handle:
            assert handle.read() == content


def test_materialize_rejects_traversal_member(
    auth_client: TestClient,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
    tmp_path,  # type: ignore[no-untyped-def]
) -> None:
    workspace = make_workspace(auth_client, "wsevil")
    project = make_project(auth_client, workspace["id"], "evil")
    snapshot = upload_snapshot(auth_client, project["id"], make_zip(ORIGINAL))

    evil = io.BytesIO()
    with tarfile.open(fileobj=evil, mode="w", format=tarfile.PAX_FORMAT) as tar:
        info = tarfile.TarInfo(name="../evil.py")
        info.size = 4
        tar.addfile(info, io.BytesIO(b"x=1\n"))
    evil_bytes = evil.getvalue()
    digest = hashlib.sha256(evil_bytes).hexdigest()
    evil_key = f"snapshots/{digest[:2]}/{digest}.tar"
    bucket = get_settings().s3_repositories_bucket
    fake_store.objects[f"{bucket}/{evil_key}"] = evil_bytes

    session, user = _open_session(db_session_factory)
    try:
        row = session.get(RepositorySnapshot, uuid.UUID(snapshot["id"]))
        assert row is not None
        row.storage_key = evil_key
        session.commit()
        dest = tmp_path / "out"
        dest.mkdir()
        with pytest.raises(ApiError) as exc_info:
            storage_service.materialize_snapshot(
                session, user, uuid.UUID(snapshot["id"]), str(dest), store=fake_store
            )
    finally:
        session.close()
    assert exc_info.value.code == "INTEGRITY_FAILED"


def test_cross_workspace_snapshot_access_is_hidden(
    auth_client_factory,  # type: ignore[no-untyped-def]
) -> None:
    owner = auth_client_factory("owner-x@example.com")
    outsider = auth_client_factory("outsider-x@example.com")
    workspace = make_workspace(owner, "wsx")
    project = make_project(owner, workspace["id"], "x")
    snapshot = upload_snapshot(owner, project["id"], make_zip(ORIGINAL))

    assert outsider.get(f"/api/v1/snapshots/{snapshot['id']}").status_code == 404
    assert outsider.post(f"/api/v1/snapshots/{snapshot['id']}/verify").status_code == 404


def test_storage_outage_returns_503_without_snapshot(
    auth_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    failing = FakeObjectStore(
        fail_with=StorageError("STORAGE_UNAVAILABLE", "Object storage is unavailable.")
    )
    monkeypatch.setattr(ingestion_service, "_default_store", lambda: failing)
    workspace = make_workspace(auth_client, "wsdown")
    project = make_project(auth_client, workspace["id"], "down")
    response = auth_client.post(
        f"/api/v1/projects/{project['id']}/source-uploads",
        files={"file": ("repo.zip", make_zip(ORIGINAL), "application/zip")},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "STORAGE_UNAVAILABLE"

    detail = auth_client.get(f"/api/v1/projects/{project['id']}").json()["data"]
    assert detail["snapshot_count"] == 0


def test_delete_project_removes_unshared_object(
    auth_client: TestClient, fake_store: FakeObjectStore
) -> None:
    workspace = make_workspace(auth_client, "wsdel")
    project = make_project(auth_client, workspace["id"], "del")
    upload_snapshot(auth_client, project["id"], make_zip(ORIGINAL))
    assert len(fake_store.objects) == 1

    response = auth_client.delete(f"/api/v1/projects/{project['id']}")
    assert response.status_code == 204
    assert len(fake_store.objects) == 0


def test_delete_project_keeps_shared_object(
    auth_client: TestClient, fake_store: FakeObjectStore
) -> None:
    workspace = make_workspace(auth_client, "wsshr")
    first = make_project(auth_client, workspace["id"], "shr-a")
    second = make_project(auth_client, workspace["id"], "shr-b")
    data = make_zip(ORIGINAL)
    upload_snapshot(auth_client, first["id"], data)
    upload_snapshot(auth_client, second["id"], data)

    assert auth_client.delete(f"/api/v1/projects/{first['id']}").status_code == 204
    assert len(fake_store.objects) == 1
    assert auth_client.delete(f"/api/v1/projects/{second['id']}").status_code == 204
    assert len(fake_store.objects) == 0


@pytest.mark.skipif(
    os.environ.get("MERIDIAN_MINIO_TEST") != "1",
    reason="MinIO integration needs MERIDIAN_MINIO_TEST=1 with S3 settings configured.",
)
def test_minio_round_trip() -> None:
    pytest.importorskip("boto3", reason="boto3 is not installed; MinIO needs it.")
    from app.services.object_store import MinioObjectStore

    settings = get_settings()
    store = MinioObjectStore(
        endpoint_url=settings.s3_endpoint_url,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        region=settings.s3_region,
    )
    key = "snapshots/it/abcdef1234567890abcdef1234567890abcdef1234567890abcdef12.tar"
    store.put_file(settings.s3_repositories_bucket, key, __file__)
    try:
        assert store.object_exists(settings.s3_repositories_bucket, key)
        with open(__file__, "rb") as handle:
            assert store.get_bytes(settings.s3_repositories_bucket, key) == handle.read()
    finally:
        store.delete_object(settings.s3_repositories_bucket, key)
    assert not store.object_exists(settings.s3_repositories_bucket, key)


def _swap_payload(factory, fake, snapshot_id, payload):  # type: ignore[no-untyped-def]
    """Point a snapshot row at attacker-chosen bytes with a matching key.

    The digest gate passes (key derives from the bytes), so this isolates
    the tar-member validation layer under test.
    """
    digest = hashlib.sha256(payload).hexdigest()
    key = f"snapshots/{digest[:2]}/{digest}.tar"
    bucket = get_settings().s3_repositories_bucket
    fake.objects[f"{bucket}/{key}"] = payload
    session = factory()
    try:
        row = session.get(RepositorySnapshot, uuid.UUID(snapshot_id))
        assert row is not None
        row.storage_key = key
        session.commit()
    finally:
        session.close()


def _build_tar(add):  # type: ignore[no-untyped-def]
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
        add(tar)
    return buffer.getvalue()


def _regular(tar, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def _symlink_tar() -> bytes:
    def add(tar):  # type: ignore[no-untyped-def]
        info = tarfile.TarInfo(name="evil-link.py")
        info.type = tarfile.SYMTYPE
        info.linkname = "src/app.py"
        tar.addfile(info)

    return _build_tar(add)


def _fifo_tar() -> bytes:
    def add(tar):  # type: ignore[no-untyped-def]
        info = tarfile.TarInfo(name="evil-fifo")
        info.type = tarfile.FIFOTYPE
        tar.addfile(info)

    return _build_tar(add)


def _absolute_tar() -> bytes:
    def add(tar):  # type: ignore[no-untyped-def]
        _regular(tar, "/evil.py", b"x = 1\n")

    return _build_tar(add)


def _duplicate_tar() -> bytes:
    def add(tar):  # type: ignore[no-untyped-def]
        _regular(tar, "dup.py", b"first\n")
        _regular(tar, "dup.py", b"second\n")

    return _build_tar(add)


def _two_file_tar() -> bytes:
    def add(tar):  # type: ignore[no-untyped-def]
        _regular(tar, "one.py", b"1\n")
        _regular(tar, "two.py", b"2\n")

    return _build_tar(add)


def _rejects(client, factory, fake, tmp_path, payload):  # type: ignore[no-untyped-def]
    workspace = make_workspace(client, f"ws{uuid.uuid4().hex[:8]}")
    project = make_project(client, workspace["id"], f"p{uuid.uuid4().hex[:8]}")
    snapshot = upload_snapshot(client, project["id"], make_zip(ORIGINAL))
    _swap_payload(factory, fake, snapshot["id"], payload)
    session, user = _open_session(factory)
    try:
        dest = tmp_path / "out"
        dest.mkdir()
        with pytest.raises(ApiError) as exc_info:
            storage_service.materialize_snapshot(
                session, user, uuid.UUID(snapshot["id"]), str(dest), store=fake
            )
    finally:
        session.close()
    assert exc_info.value.code == "INTEGRITY_FAILED"


def test_materialize_rejects_symlink_member(
    auth_client: TestClient,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
    tmp_path,  # type: ignore[no-untyped-def]
) -> None:
    _rejects(auth_client, db_session_factory, fake_store, tmp_path, _symlink_tar())


def test_materialize_rejects_fifo_member(
    auth_client: TestClient,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
    tmp_path,  # type: ignore[no-untyped-def]
) -> None:
    _rejects(auth_client, db_session_factory, fake_store, tmp_path, _fifo_tar())


def test_materialize_rejects_absolute_member(
    auth_client: TestClient,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
    tmp_path,  # type: ignore[no-untyped-def]
) -> None:
    _rejects(auth_client, db_session_factory, fake_store, tmp_path, _absolute_tar())


def test_materialize_rejects_duplicate_paths(
    auth_client: TestClient,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
    tmp_path,  # type: ignore[no-untyped-def]
) -> None:
    _rejects(auth_client, db_session_factory, fake_store, tmp_path, _duplicate_tar())


def test_materialize_rejects_corrupt_tar(
    auth_client: TestClient,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
    tmp_path,  # type: ignore[no-untyped-def]
) -> None:
    _rejects(
        auth_client, db_session_factory, fake_store, tmp_path, b"\x00not-a-tar\xff"
    )


def test_materialize_enforces_file_count_cap(
    auth_client: TestClient,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
    tmp_path,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = get_settings()
    monkeypatch.setattr(
        storage_service,
        "get_settings",
        lambda: base.model_copy(update={"max_archive_files": 1}),
    )
    _rejects(auth_client, db_session_factory, fake_store, tmp_path, _two_file_tar())


def test_materialize_storage_outage_returns_503(
    auth_client: TestClient,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
    tmp_path,  # type: ignore[no-untyped-def]
) -> None:
    workspace = make_workspace(auth_client, "wsout")
    project = make_project(auth_client, workspace["id"], "out")
    snapshot = upload_snapshot(auth_client, project["id"], make_zip(ORIGINAL))
    failing = FakeObjectStore(
        fail_with=StorageError("STORAGE_UNAVAILABLE", "Object storage is unavailable.")
    )
    session, user = _open_session(db_session_factory)
    try:
        dest = tmp_path / "out"
        dest.mkdir()
        with pytest.raises(ApiError) as exc_info:
            storage_service.materialize_snapshot(
                session, user, uuid.UUID(snapshot["id"]), str(dest), store=failing
            )
    finally:
        session.close()
    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "STORAGE_UNAVAILABLE"


def test_list_orphan_keys_detects_unreferenced(
    auth_client: TestClient,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
) -> None:
    workspace = make_workspace(auth_client, "wsorf")
    project = make_project(auth_client, workspace["id"], "orf")
    upload_snapshot(auth_client, project["id"], make_zip(ORIGINAL))
    bucket = get_settings().s3_repositories_bucket
    stray = f"snapshots/zz/{'0' * 64}.tar"
    fake_store.objects[f"{bucket}/{stray}"] = b"leftover"
    session, _user = _open_session(db_session_factory)
    try:
        result = storage_service.list_orphan_keys(session, store=fake_store)
    finally:
        session.close()
    assert result["objects"] == 2
    assert result["orphan_keys"] == [stray]
    assert result["orphan_bytes"] == len(b"leftover")
