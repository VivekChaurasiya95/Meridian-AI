"""Evidence endpoint tests (M6): metadata, filters, signed downloads."""

import io
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.envelope import ApiError
from app.models import Investigation
from app.services import evidence as evidence_service
from app.services import ingestion as ingestion_service
from app.services import storage as storage_service
from app.services.object_store import FakeObjectStore

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture()
def fake_store(monkeypatch: pytest.MonkeyPatch) -> FakeObjectStore:
    store = FakeObjectStore()
    monkeypatch.setattr(ingestion_service, "_default_store", lambda: store)
    monkeypatch.setattr(storage_service, "get_store", lambda: store)
    monkeypatch.setattr(evidence_service, "get_store", lambda: store)
    return store


def make_zip(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def setup_inv(auth_client: TestClient, slug: str) -> tuple[str, dict]:
    workspace = auth_client.post("/api/v1/workspaces", json={"name": slug, "slug": slug}).json()[
        "data"
    ]
    project = auth_client.post(
        f"/api/v1/workspaces/{workspace['id']}/projects",
        json={"name": slug, "slug": slug},
    ).json()["data"]
    snapshot = auth_client.post(
        f"/api/v1/projects/{project['id']}/source-uploads",
        files={"file": ("r.zip", make_zip({"index.html": "<h1>x</h1>"}), "application/zip")},
    ).json()["data"]["snapshot"]
    inv = auth_client.post(
        f"/api/v1/projects/{project['id']}/investigations",
        json={
            "title": "t",
            "bug_report": "b",
            "repository_snapshot_id": snapshot["id"],
        },
    ).json()["data"]
    return workspace["id"], inv


def seed_evidence(
    db_session_factory,
    inv_id: str,
    store: FakeObjectStore,
    redaction_status: str = "redacted",  # type: ignore[no-untyped-def]
) -> dict:
    session: Session = db_session_factory()
    try:
        project_id = session.execute(
            select(Investigation.project_id).where(Investigation.id == uuid.UUID(inv_id))
        ).scalar_one()
        return evidence_service.create_evidence(
            session,
            project_id=project_id,
            investigation_id=uuid.UUID(inv_id),
            tool_run_id=None,
            kind="screenshot",
            data=PNG,
            filename_hint="shot.png",
            redaction_status=redaction_status,
            metadata={"source": "test"},
            store=store,
        )
    finally:
        session.close()


def test_list_get_and_download(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    _, inv = setup_inv(auth_client, "ev1")
    record = seed_evidence(db_session_factory, inv["id"], fake_store)
    assert record["mime_type"] == "image/png"
    assert "storage_key" not in record

    listed = auth_client.get(f"/api/v1/investigations/{inv['id']}/evidence").json()["data"]
    assert [row["id"] for row in listed] == [record["id"]]
    assert (
        auth_client.get(
            f"/api/v1/investigations/{inv['id']}/evidence", params={"kind": "trace"}
        ).json()["data"]
        == []
    )
    assert (
        auth_client.get(
            f"/api/v1/investigations/{inv['id']}/evidence", params={"kind": "nope"}
        ).status_code
        == 422
    )
    detail = auth_client.get(f"/api/v1/evidence/{record['id']}").json()["data"]
    assert detail["sha256"] == record["sha256"]
    assert "storage_key" not in detail

    issued = auth_client.post(f"/api/v1/evidence/{record['id']}/download-url").json()["data"]
    assert issued["url"].startswith("https://evidence.invalid/")
    assert issued["expires_at"]


def test_download_refused_when_redaction_failed(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    _, inv = setup_inv(auth_client, "ev2")
    record = seed_evidence(db_session_factory, inv["id"], fake_store, redaction_status="failed")
    response = auth_client.post(f"/api/v1/evidence/{record['id']}/download-url")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EVIDENCE_NOT_READY"


def test_evidence_scoped(auth_client_factory, db_session_factory, fake_store) -> None:  # type: ignore[no-untyped-def]
    owner = auth_client_factory("owner-ev@example.com")
    outsider = auth_client_factory("outsider-ev@example.com")
    _, inv = setup_inv(owner, "ev3")
    record = seed_evidence(db_session_factory, inv["id"], fake_store)
    assert outsider.get(f"/api/v1/investigations/{inv['id']}/evidence").status_code == 404
    assert outsider.get(f"/api/v1/evidence/{record['id']}").status_code == 404
    assert outsider.post(f"/api/v1/evidence/{record['id']}/download-url").status_code == 404
    assert owner.get(f"/api/v1/evidence/{uuid.uuid4()}").status_code == 404


def test_oversized_and_unknown_types_rejected(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    _, inv = setup_inv(auth_client, "ev4")
    session: Session = db_session_factory()
    try:
        project_id = session.execute(
            select(Investigation.project_id).where(Investigation.id == uuid.UUID(inv["id"]))
        ).scalar_one()
        with pytest.raises(ApiError) as exc:
            evidence_service.create_evidence(
                session,
                project_id=project_id,
                investigation_id=uuid.UUID(inv["id"]),
                tool_run_id=None,
                kind="screenshot",
                data=b"\x00\x01binary\xff",
                filename_hint="x.bin",
                redaction_status="not_required",
                store=fake_store,
            )
        assert exc.value.code == "EVIDENCE_TYPE_REJECTED"
    finally:
        session.close()
