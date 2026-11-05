"""Assessment read-API tests (V1): fake store, real Postgres.

Endpoints serve sanitized persisted data only. Seeds go through the
service layer (already-sanitized records, as the worker produces);
retrieval enforces workspace membership with 404s for foreign rows.
"""

import io
import json
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select

from app.models import User
from app.services import ingestion as ingestion_service
from app.services import security_assessments as assessment_service
from app.services import storage as storage_service
from app.services.object_store import FakeObjectStore

CODE = {"src/app.py": "print(1)\n"}
OTHER = {"src/other.py": "print(2)\n"}


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


def _record(scanner: str, rule: str, severity: str, path: str) -> dict:
    return {
        "id": uuid.uuid4(),
        "fingerprint": f"fp-{scanner}-{rule}-{path}",
        "scanner": scanner,
        "rule_id": rule,
        "severity": severity,
        "confidence": "high",
        "category": "credentials" if scanner == "gitleaks" else "general",
        "title": f"{rule} title",
        "description": f"{rule} description",
        "location": {"path": path, "start_line": 1, "end_line": 1},
        "evidence": {"excerpt": "REDACTED", "redacted": True, "truncated": False},
    }


def _seed(db_session, workspace_id: str, project_id: str, upload: dict, records: list[dict]):  # type: ignore[no-untyped-def]
    assessment = assessment_service.get_or_create_assessment(
        db_session,
        job_id=uuid.UUID(upload["preflight"]["job_id"]),
        workspace_id=uuid.UUID(workspace_id),
        project_id=uuid.UUID(project_id),
        snapshot_id=uuid.UUID(upload["snapshot"]["id"]),
        policy_version="preflight-v1",
        ruleset_version="preflight-v1",
    )
    assessment_service.store_assessment_result(
        db_session,
        assessment.id,
        status="review_required",
        summary={"by_severity": {"high": len(records)}, "total": len(records)},
        scanner_versions={"semgrep": "1.183.0"},
        records=records,
    )
    return assessment


def test_get_assessment_detail(
    auth_client: TestClient, fake_store: FakeObjectStore, db_session
) -> None:  # type: ignore[no-untyped-def]
    workspace = make_workspace(auth_client, "wapi")
    project = make_project(auth_client, workspace["id"], "api")
    upload = upload_data(auth_client, project["id"], make_zip(CODE))
    assessment = _seed(
        db_session,
        workspace["id"],
        project["id"],
        upload,
        [_record("semgrep", "r1", "high", "src/app.py")],
    )
    response = auth_client.get(f"/api/v1/security-assessments/{assessment.id}")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["snapshot_id"] == upload["snapshot"]["id"]
    assert data["status"] == "review_required"
    assert data["generation"] == 1
    blob = json.dumps(data).lower()
    for token in ("snapshots/", "security_storage", "minio", "secret_key"):
        assert token not in blob


def test_snapshot_latest_assessment(
    auth_client: TestClient, fake_store: FakeObjectStore, db_session
) -> None:  # type: ignore[no-untyped-def]
    workspace = make_workspace(auth_client, "wsnap")
    project = make_project(auth_client, workspace["id"], "snap")
    first = upload_data(auth_client, project["id"], make_zip(CODE))
    second = upload_data(auth_client, project["id"], make_zip(OTHER))
    _seed(db_session, workspace["id"], project["id"], first, [])

    response = auth_client.get(f"/api/v1/snapshots/{first['snapshot']['id']}/security-assessment")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["snapshot_id"] == first["snapshot"]["id"]

    missing = auth_client.get(f"/api/v1/snapshots/{second['snapshot']['id']}/security-assessment")
    assert missing.status_code == 404, missing.text

    ghost = auth_client.get(f"/api/v1/snapshots/{uuid.uuid4()}/security-assessment")
    assert ghost.status_code == 404, ghost.text


def test_project_list_paginates(
    auth_client: TestClient, fake_store: FakeObjectStore, db_session
) -> None:  # type: ignore[no-untyped-def]
    workspace = make_workspace(auth_client, "wlist")
    project = make_project(auth_client, workspace["id"], "listed")
    first = upload_data(auth_client, project["id"], make_zip(CODE))
    second = upload_data(auth_client, project["id"], make_zip(OTHER))
    _seed(db_session, workspace["id"], project["id"], first, [])
    _seed(db_session, workspace["id"], project["id"], second, [])

    base = f"/api/v1/projects/{project['id']}/security-assessments"
    page1 = auth_client.get(base, params={"limit": 1})
    assert page1.status_code == 200, page1.text
    body1 = page1.json()
    assert len(body1["data"]) == 1
    assert body1["page"]["next_cursor"]
    page2 = auth_client.get(base, params={"limit": 1, "cursor": body1["page"]["next_cursor"]})
    assert page2.status_code == 200, page2.text
    body2 = page2.json()
    assert len(body2["data"]) == 1
    assert body2["data"][0]["id"] != body1["data"][0]["id"]
    assert body2["page"]["next_cursor"] is None

    bad_cursor = auth_client.get(base, params={"cursor": "nope"})
    assert bad_cursor.status_code == 422, bad_cursor.text


def test_findings_filters(auth_client: TestClient, fake_store: FakeObjectStore, db_session) -> None:  # type: ignore[no-untyped-def]
    workspace = make_workspace(auth_client, "wfind")
    project = make_project(auth_client, workspace["id"], "find")
    upload = upload_data(auth_client, project["id"], make_zip(CODE))
    _seed(
        db_session,
        workspace["id"],
        project["id"],
        upload,
        [
            _record("semgrep", "r-high", "high", "src/app.py"),
            _record("gitleaks", "aws-key", "high", ".env"),
            _record("semgrep", "r-low", "low", "src/other.py"),
        ],
    )
    assessment_id = assessment_service.get_snapshot_assessment(
        db_session,
        db_session.execute(select(User).where(User.email == "owner@example.com")).scalar_one(),
        uuid.UUID(upload["snapshot"]["id"]),
    )["id"]
    base = f"/api/v1/security-assessments/{assessment_id}/findings"

    all_items = auth_client.get(base).json()["data"]
    assert len(all_items) == 3

    low = auth_client.get(base, params={"severity": "low"}).json()["data"]
    assert [item["rule_id"] for item in low] == ["r-low"]

    leaks = auth_client.get(base, params={"scanner": "gitleaks"}).json()["data"]
    assert [item["rule_id"] for item in leaks] == ["aws-key"]

    creds = auth_client.get(base, params={"category": "credentials"}).json()["data"]
    assert len(creds) == 1

    src = auth_client.get(base, params={"path_prefix": "src/"}).json()["data"]
    assert len(src) == 2

    bad = auth_client.get(base, params={"severity": "bogus"})
    assert bad.status_code == 422, bad.text


def test_foreign_workspace_rows_are_hidden(
    auth_client_factory, fake_store: FakeObjectStore, db_session
) -> None:  # type: ignore[no-untyped-def]
    owner = auth_client_factory("owner-sec@example.com")
    other = auth_client_factory("other-sec@example.com")
    workspace = make_workspace(owner, "wsec")
    project = make_project(owner, workspace["id"], "secp")
    upload = upload_data(owner, project["id"], make_zip(CODE))
    assessment = _seed(
        db_session,
        workspace["id"],
        project["id"],
        upload,
        [_record("semgrep", "r1", "high", "src/app.py")],
    )
    assert other.get(f"/api/v1/security-assessments/{assessment.id}").status_code == 404
    assert other.get(f"/api/v1/security-assessments/{assessment.id}/findings").status_code == 404
    assert (
        other.get(f"/api/v1/snapshots/{upload['snapshot']['id']}/security-assessment").status_code
        == 404
    )
    assert other.get(f"/api/v1/projects/{project['id']}/security-assessments").status_code == 404


def test_retry_reuses_assessment_row(
    auth_client: TestClient, fake_store: FakeObjectStore, db_session
) -> None:  # type: ignore[no-untyped-def]
    workspace = make_workspace(auth_client, "wretry")
    project = make_project(auth_client, workspace["id"], "retry")
    upload = upload_data(auth_client, project["id"], make_zip(CODE))

    def _get_or_create():  # type: ignore[no-untyped-def]
        return assessment_service.get_or_create_assessment(
            db_session,
            job_id=uuid.UUID(upload["preflight"]["job_id"]),
            workspace_id=uuid.UUID(workspace["id"]),
            project_id=uuid.UUID(project["id"]),
            snapshot_id=uuid.UUID(upload["snapshot"]["id"]),
            policy_version="preflight-v1",
            ruleset_version="preflight-v1",
        )

    first = _get_or_create()
    assessment_service.store_assessment_result(
        db_session,
        first.id,
        status="failed",
        summary={},
        scanner_versions={},
        records=[_record("semgrep", "r1", "high", "src/app.py")],
    )
    second = _get_or_create()
    assert second.id == first.id
    assert second.generation == 1
    assert second.status == "running"
    findings, _ = assessment_service.list_findings(
        db_session,
        db_session.execute(select(User).where(User.email == "owner@example.com")).scalar_one(),
        first.id,
        25,
        None,
    )
    assert findings == []
