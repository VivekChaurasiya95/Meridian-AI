"""Dual-artifact ingestion tests (V1, D62/D65): fake store, real Postgres.

Uploads build the indexed snapshot plus the security scan input, and
enqueue exactly one preflight job. Secret contents never enter the
index but must survive byte-identical inside the security object.
"""

import io
import tarfile
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select

from app.envelope import ApiError
from app.models import RepositorySnapshot, SnapshotFile, User
from app.services import ingestion as ingestion_service
from app.services import jobs as job_service
from app.services import storage as storage_service
from app.services.object_store import FakeObjectStore

WITH_SECRETS = {
    "src/app.py": "print(1)\n",
    ".env": "API_KEY=synthetic-test-value\n",
    "keys/id_rsa": "PRIVATE KEY FIXTURE\n",
}
PLAIN = {"src/app.py": "print(1)\n", "README.md": "# demo\n"}


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


def upload_data(client: TestClient, project_id: str, data: bytes) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/source-uploads",
        files={"file": ("repo.zip", data, "application/zip")},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


@pytest.fixture()
def db_session(migrated_db: str):  # type: ignore[no-untyped-def]
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(migrated_db)
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


def _snapshot_row(db_session, snapshot_id: str) -> RepositorySnapshot:  # type: ignore[no-untyped-def]
    return db_session.get(RepositorySnapshot, uuid.UUID(snapshot_id))


def test_upload_with_secrets_builds_ready_security_artifact(
    auth_client: TestClient, fake_store: FakeObjectStore, db_session
) -> None:  # type: ignore[no-untyped-def]
    workspace = make_workspace(auth_client, "wsec")
    project = make_project(auth_client, workspace["id"], "sec")
    data = upload_data(auth_client, project["id"], make_zip(WITH_SECRETS))

    assert data["snapshot"]["storage_status"] == "ready"
    assert data["preflight"]["status"] == "queued"
    assert data["preflight"]["job_id"]

    row = _snapshot_row(db_session, data["snapshot"]["id"])
    assert row.security_scan_status == "ready"
    assert row.security_storage_key is not None
    assert row.security_storage_key.startswith("snapshots/security/")
    assert row.security_storage_key != row.storage_key
    assert row.security_content_digest is not None and len(row.security_content_digest) == 64
    assert row.security_storage_bytes is not None and row.security_storage_bytes > 0

    keys = sorted(full.split("/", 1)[1] for full in fake_store.objects)
    assert row.storage_key in keys
    assert row.security_storage_key in keys

    jobs = auth_client.get(f"/api/v1/workspaces/{workspace['id']}/jobs").json()["data"]
    preflight = [job for job in jobs if job["job_type"] == "security_preflight"]
    assert len(preflight) == 1
    assert preflight[0]["id"] == data["preflight"]["job_id"]
    assert preflight[0]["status"] == "queued"


def test_upload_without_secrets_mirrors_main_object(
    auth_client: TestClient, fake_store: FakeObjectStore, db_session
) -> None:  # type: ignore[no-untyped-def]
    workspace = make_workspace(auth_client, "wplain")
    project = make_project(auth_client, workspace["id"], "plain")
    data = upload_data(auth_client, project["id"], make_zip(PLAIN))
    row = _snapshot_row(db_session, data["snapshot"]["id"])
    assert row.security_scan_status == "ready"
    assert row.security_storage_key == row.storage_key
    assert len(fake_store.objects) == 1


def test_secrets_excluded_from_index_but_in_security_object(
    auth_client: TestClient, fake_store: FakeObjectStore, db_session
) -> None:  # type: ignore[no-untyped-def]
    workspace = make_workspace(auth_client, "wsep")
    project = make_project(auth_client, workspace["id"], "sep")
    data = upload_data(auth_client, project["id"], make_zip(WITH_SECRETS))
    snapshot_id = uuid.UUID(data["snapshot"]["id"])

    indexed = {
        row[0]
        for row in db_session.execute(
            select(SnapshotFile.path).where(SnapshotFile.snapshot_id == snapshot_id)
        ).all()
    }
    assert ".env" not in indexed
    assert "keys/id_rsa" not in indexed
    assert "src/app.py" in indexed

    row = _snapshot_row(db_session, data["snapshot"]["id"])
    assert row.security_storage_key is not None
    raw = fake_store.objects[f"meridian-repositories/{row.security_storage_key}"]
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r") as tar:
        names = tar.getnames()
    assert ".env" in names
    assert "keys/id_rsa" in names
    assert "src/app.py" in names


def test_materialize_security_input_round_trip(
    auth_client: TestClient, fake_store: FakeObjectStore, db_session, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    workspace = make_workspace(auth_client, "wmat")
    project = make_project(auth_client, workspace["id"], "mat")
    data = upload_data(auth_client, project["id"], make_zip(WITH_SECRETS))
    dest = tmp_path / "sec"
    dest.mkdir()
    material = storage_service.materialize_security_input_for_workspace(
        db_session, uuid.UUID(workspace["id"]), uuid.UUID(data["snapshot"]["id"]),
        str(dest), store=fake_store,
    )
    assert material["files"] == 3
    assert material["secret_files"] == 2
    assert (dest / ".env").read_text() == "API_KEY=synthetic-test-value\n"
    assert (dest / "src" / "app.py").read_text() == "print(1)\n"


def test_materialize_rejects_tampered_security_object(
    auth_client: TestClient, fake_store: FakeObjectStore, db_session, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    workspace = make_workspace(auth_client, "wtamp")
    project = make_project(auth_client, workspace["id"], "tamp")
    data = upload_data(auth_client, project["id"], make_zip(WITH_SECRETS))
    row = _snapshot_row(db_session, data["snapshot"]["id"])
    assert row.security_storage_key is not None
    full = f"meridian-repositories/{row.security_storage_key}"
    fake_store.objects[full] = b"tampered-bytes"
    dest = tmp_path / "sec"
    dest.mkdir()
    with pytest.raises(ApiError) as exc:
        storage_service.materialize_security_input_for_workspace(
            db_session, uuid.UUID(workspace["id"]), uuid.UUID(data["snapshot"]["id"]),
            str(dest), store=fake_store,
        )
    assert exc.value.code == "INTEGRITY_FAILED"
    db_session.refresh(row)
    assert row.security_scan_status == "integrity_failed"
    assert row.storage_status == "ready"


def test_materialize_rejects_foreign_workspace(
    auth_client_factory, fake_store: FakeObjectStore, db_session, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    owner = auth_client_factory("owner-mat@example.com")
    other = auth_client_factory("other-mat@example.com")
    workspace = make_workspace(owner, "wown")
    project = make_project(owner, workspace["id"], "own")
    data = upload_data(owner, project["id"], make_zip(WITH_SECRETS))
    foreign_ws = make_workspace(other, "wother")["id"]
    dest = tmp_path / "sec"
    dest.mkdir()
    with pytest.raises(ApiError) as exc:
        storage_service.materialize_security_input_for_workspace(
            db_session, uuid.UUID(foreign_ws), uuid.UUID(data["snapshot"]["id"]),
            str(dest), store=fake_store,
        )
    assert exc.value.code == "RESOURCE_NOT_FOUND"


def test_enqueue_preflight_is_idempotent(
    auth_client: TestClient, fake_store: FakeObjectStore, db_session
) -> None:  # type: ignore[no-untyped-def]
    workspace = make_workspace(auth_client, "widem")
    project = make_project(auth_client, workspace["id"], "idem")
    data = upload_data(auth_client, project["id"], make_zip(PLAIN))
    user = db_session.execute(
        select(User).where(User.email == "owner@example.com")
    ).scalar_one()
    first, created_first = job_service.enqueue_security_preflight(
        db_session, user, uuid.UUID(workspace["id"]), uuid.UUID(data["snapshot"]["id"])
    )
    second, created_second = job_service.enqueue_security_preflight(
        db_session, user, uuid.UUID(workspace["id"]), uuid.UUID(data["snapshot"]["id"])
    )
    assert created_first is False  # upload already enqueued it
    assert created_second is False
    assert first["id"] == second["id"] == data["preflight"]["job_id"]


def test_submit_preflight_validates_profile_and_snapshot(auth_client: TestClient) -> None:
    workspace = make_workspace(auth_client, "wval")
    project = make_project(auth_client, workspace["id"], "val")
    data = upload_data(auth_client, project["id"], make_zip(PLAIN))
    base = f"/api/v1/workspaces/{workspace['id']}/jobs"

    bad_profile = auth_client.post(
        base,
        json={
            "job_type": "security_preflight",
            "payload": {
                "snapshot_id": data["snapshot"]["id"],
                "scan_profile": "evil",
                "policy_version": "preflight-v1",
            },
        },
    )
    assert bad_profile.status_code == 422, bad_profile.text

    missing = auth_client.post(
        base,
        json={"job_type": "security_preflight", "payload": {}},
    )
    assert missing.status_code == 422, missing.text

    foreign = auth_client.post(
        base,
        json={
            "job_type": "security_preflight",
            "payload": {"snapshot_id": str(uuid.uuid4())},
        },
    )
    assert foreign.status_code == 404, foreign.text


def test_delete_project_removes_both_objects(
    auth_client: TestClient, fake_store: FakeObjectStore, db_session
) -> None:  # type: ignore[no-untyped-def]
    workspace = make_workspace(auth_client, "wdel")
    project = make_project(auth_client, workspace["id"], "deleteme")
    data = upload_data(auth_client, project["id"], make_zip(WITH_SECRETS))
    row = _snapshot_row(db_session, data["snapshot"]["id"])
    assert row.security_storage_key is not None
    main_full = f"meridian-repositories/{row.storage_key}"
    sec_full = f"meridian-repositories/{row.security_storage_key}"
    assert main_full in fake_store.objects and sec_full in fake_store.objects

    response = auth_client.delete(f"/api/v1/projects/{project['id']}")
    assert response.status_code == 204, response.text
    assert main_full not in fake_store.objects
    assert sec_full not in fake_store.objects


def test_delete_keeps_shared_security_object(
    auth_client: TestClient, fake_store: FakeObjectStore, db_session
) -> None:  # type: ignore[no-untyped-def]
    workspace = make_workspace(auth_client, "wshare")
    first = make_project(auth_client, workspace["id"], "first")
    second = make_project(auth_client, workspace["id"], "second")
    payload = make_zip(WITH_SECRETS)
    upload_data(auth_client, first["id"], payload)
    upload_data(auth_client, second["id"], payload)

    response = auth_client.delete(f"/api/v1/projects/{first['id']}")
    assert response.status_code == 204, response.text
    # Both projects shared both objects: nothing removed yet.
    assert len(fake_store.objects) == 2
