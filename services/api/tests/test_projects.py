"""Project endpoint tests (API.md §6.5-§6.6): CRUD, authz, ingestion."""

import io
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.services import ingestion as ingestion_service
from app.services import storage as storage_service
from app.services.object_store import FakeObjectStore


@pytest.fixture(autouse=True)
def fake_store(monkeypatch: pytest.MonkeyPatch) -> FakeObjectStore:
    """Route all snapshot object I/O to memory: no MinIO in unit tests."""
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


def make_workspace(client: TestClient, slug: str = "ws") -> dict:
    response = client.post("/api/v1/workspaces", json={"name": slug, "slug": slug})
    assert response.status_code == 201, response.text
    return response.json()["data"]


def make_project(client: TestClient, workspace_id: str, slug: str = "proj") -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/projects",
        json={"name": slug, "slug": slug, "description": f"{slug} codebase"},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def upload(client: TestClient, project_id: str, filename: str, data: bytes):  # type: ignore[no-untyped-def]
    return client.post(
        f"/api/v1/projects/{project_id}/source-uploads",
        files={"file": (filename, data, "application/zip")},
    )


DEMO_ZIP = make_zip(
    {
        "package.json": '{"name": "demo", "dependencies": {"react": "19.0.0"}}',
        "package-lock.json": "{}",
        "src/app.js": "console.log(1);\n",
        "README.md": "# demo\n",
    }
)


def test_create_project_returns_201_envelope(auth_client: TestClient) -> None:
    workspace = make_workspace(auth_client)
    project = make_project(auth_client, workspace["id"])
    assert project["name"] == "proj"
    assert project["slug"] == "proj"
    assert project["status"] == "active"
    assert project["source_type"] == "uploaded_archive"
    assert project["role"] == "owner"
    assert project["runtime_profile"] == {}
    assert project["snapshot_count"] == 0
    assert project["latest_snapshot"] is None
    uuid.UUID(project["id"])


def test_create_project_validates_input(auth_client: TestClient) -> None:
    workspace = make_workspace(auth_client)
    response = auth_client.post(
        f"/api/v1/workspaces/{workspace['id']}/projects",
        json={"name": "  ", "slug": "Bad Slug!", "runtime_profile": {"x": 1}},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_project_slug_conflict_is_workspace_scoped(auth_client: TestClient) -> None:
    first = make_workspace(auth_client, "ws-one")
    second = make_workspace(auth_client, "ws-two")
    make_project(auth_client, first["id"], "same")
    conflict = auth_client.post(
        f"/api/v1/workspaces/{first['id']}/projects",
        json={"name": "same", "slug": "same"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "RESOURCE_CONFLICT"
    ok_elsewhere = auth_client.post(
        f"/api/v1/workspaces/{second['id']}/projects",
        json={"name": "same", "slug": "same"},
    )
    assert ok_elsewhere.status_code == 201


def test_viewer_cannot_create_project(auth_client_factory) -> None:  # type: ignore[no-untyped-def]
    owner = auth_client_factory("owner-p@example.com")
    viewer = auth_client_factory("viewer-p@example.com")
    workspace = make_workspace(owner, "wsv")
    added = owner.post(
        f"/api/v1/workspaces/{workspace['id']}/members",
        json={"email": "viewer-p@example.com", "role": "viewer"},
    )
    assert added.status_code == 201, added.text
    response = viewer.post(
        f"/api/v1/workspaces/{workspace['id']}/projects",
        json={"name": "x", "slug": "x"},
    )
    assert response.status_code == 403


def test_developer_can_create_project(auth_client_factory) -> None:  # type: ignore[no-untyped-def]
    owner = auth_client_factory("owner-d@example.com")
    developer = auth_client_factory("dev-d@example.com")
    workspace = make_workspace(owner, "wsd")
    added = owner.post(
        f"/api/v1/workspaces/{workspace['id']}/members",
        json={"email": "dev-d@example.com", "role": "developer"},
    )
    assert added.status_code == 201, added.text
    project = make_project(developer, workspace["id"], "dev-proj")
    assert project["role"] == "developer"


def test_project_access_is_workspace_scoped(auth_client_factory) -> None:  # type: ignore[no-untyped-def]
    owner = auth_client_factory("owner-s@example.com")
    outsider = auth_client_factory("outsider-s@example.com")
    workspace = make_workspace(owner, "wss")
    project = make_project(owner, workspace["id"], "secret")
    assert outsider.get(f"/api/v1/projects/{project['id']}").status_code == 404
    assert outsider.get(f"/api/v1/workspaces/{workspace['id']}/projects").status_code == 404


def test_list_projects_filters_search_sort(auth_client: TestClient) -> None:
    workspace = make_workspace(auth_client, "wsf")
    make_project(auth_client, workspace["id"], "alpha")
    make_project(auth_client, workspace["id"], "beta")
    archived = make_project(auth_client, workspace["id"], "old")
    auth_client.post(f"/api/v1/projects/{archived['id']}/archive")

    active = auth_client.get(
        f"/api/v1/workspaces/{workspace['id']}/projects", params={"status": "active"}
    ).json()["data"]
    assert {p["slug"] for p in active} == {"alpha", "beta"}

    searched = auth_client.get(
        f"/api/v1/workspaces/{workspace['id']}/projects", params={"q": "ALP"}
    ).json()["data"]
    assert [p["slug"] for p in searched] == ["alpha"]

    by_name = auth_client.get(
        f"/api/v1/workspaces/{workspace['id']}/projects", params={"sort": "name", "limit": 2}
    ).json()
    assert [p["slug"] for p in by_name["data"]] == ["alpha", "beta"]
    assert by_name["page"]["next_cursor"]
    second = auth_client.get(
        f"/api/v1/workspaces/{workspace['id']}/projects",
        params={"sort": "name", "limit": 2, "cursor": by_name["page"]["next_cursor"]},
    ).json()
    assert [p["slug"] for p in second["data"]] == ["old"]

    bad = auth_client.get(
        f"/api/v1/workspaces/{workspace['id']}/projects", params={"sort": "nope"}
    )
    assert bad.status_code == 422


def test_update_archive_delete_lifecycle(auth_client_factory) -> None:  # type: ignore[no-untyped-def]
    owner = auth_client_factory("owner-l@example.com")
    developer = auth_client_factory("dev-l@example.com")
    other = auth_client_factory("other-l@example.com")
    workspace = make_workspace(owner, "wsl")
    added = owner.post(
        f"/api/v1/workspaces/{workspace['id']}/members",
        json={"email": "dev-l@example.com", "role": "developer"},
    )
    assert added.status_code == 201, added.text
    project = make_project(owner, workspace["id"], "life")

    updated = owner.patch(
        f"/api/v1/projects/{project['id']}",
        json={"name": "life v2", "description": "renamed"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["name"] == "life v2"

    assert (
        developer.patch(
            f"/api/v1/projects/{project['id']}", json={"name": "hijack", "description": None}
        ).status_code
        == 403
    )
    assert other.get(f"/api/v1/projects/{project['id']}").status_code == 404

    archived = owner.post(f"/api/v1/projects/{project['id']}/archive")
    assert archived.status_code == 200
    assert archived.json()["data"]["status"] == "archived"

    # Developers cannot delete; only the owner can.
    assert developer.delete(f"/api/v1/projects/{project['id']}").status_code == 403
    deleted = owner.delete(f"/api/v1/projects/{project['id']}")
    assert deleted.status_code == 204
    assert owner.get(f"/api/v1/projects/{project['id']}").status_code == 404


def test_unarchive_restores_project(auth_client: TestClient) -> None:
    workspace = make_workspace(auth_client, "wsun")
    project = make_project(auth_client, workspace["id"], "un")
    auth_client.post(f"/api/v1/projects/{project['id']}/archive")
    restored = auth_client.post(f"/api/v1/projects/{project['id']}/unarchive")
    assert restored.status_code == 200
    assert restored.json()["data"]["status"] == "active"


def test_projects_summary_counts_are_real(auth_client: TestClient) -> None:
    workspace = make_workspace(auth_client, "wssum")
    empty = auth_client.get(
        f"/api/v1/workspaces/{workspace['id']}/projects/summary"
    ).json()["data"]
    assert empty == {
        "total": 0,
        "active": 0,
        "archived": 0,
        "snapshots_total": 0,
        "snapshots_recent_7d": 0,
        "needs_attention": 0,
    }
    first = make_project(auth_client, workspace["id"], "one")
    second = make_project(auth_client, workspace["id"], "two")
    auth_client.post(f"/api/v1/projects/{second['id']}/archive")
    assert upload(auth_client, first["id"], "app.zip", DEMO_ZIP).status_code == 201
    summary = auth_client.get(
        f"/api/v1/workspaces/{workspace['id']}/projects/summary"
    ).json()["data"]
    assert summary["total"] == 2
    assert summary["active"] == 1
    assert summary["archived"] == 1
    assert summary["snapshots_total"] == 1
    assert summary["snapshots_recent_7d"] == 1
    assert summary["needs_attention"] == 0


def test_upload_creates_snapshot_and_indexes_files(auth_client: TestClient) -> None:
    workspace = make_workspace(auth_client, "wsup")
    project = make_project(auth_client, workspace["id"], "demo")
    response = upload(auth_client, project["id"], "demo.zip", DEMO_ZIP)
    assert response.status_code == 201, response.text
    body = response.json()["data"]
    snapshot = body["snapshot"]
    assert snapshot["archive_name"] == "demo.zip"
    assert snapshot["archive_size"] == len(DEMO_ZIP)
    assert len(snapshot["tree_digest"]) == 64
    assert body["inspection"]["manifest"]["file_count"] == 4
    assert snapshot["storage_status"] == "ready"
    assert snapshot["storage_bytes"] is not None and snapshot["storage_bytes"] > 0
    assert snapshot["storage_verified_at"] is not None
    assert snapshot["error_code"] is None
    assert [s["key"] for s in body["inspection"]["stages"]] == [
        "received",
        "validated",
        "extracted",
        "inspected",
        "stored",
        "snapshot_created",
    ]

    detail = auth_client.get(f"/api/v1/projects/{project['id']}").json()["data"]
    assert detail["snapshot_count"] == 1
    assert detail["latest_snapshot"]["id"] == snapshot["id"]
    assert detail["runtime_profile"]["frameworks"] == ["React"]
    assert detail["runtime_profile"]["package_manager"] == "npm"

    tree = auth_client.get(
        f"/api/v1/snapshots/{snapshot['id']}/tree", params={"prefix": ""}
    ).json()["data"]
    assert tree["total"] == 4
    assert "src" in tree["directories"]
    assert {entry["path"] for entry in tree["entries"]} >= {"package.json", "README.md"}

    src = auth_client.get(
        f"/api/v1/snapshots/{snapshot['id']}/tree", params={"prefix": "src"}
    ).json()["data"]
    assert [entry["path"] for entry in src["entries"]] == ["src/app.js"]

    preview = auth_client.get(
        f"/api/v1/snapshots/{snapshot['id']}/file", params={"path": "src/app.js"}
    ).json()["data"]
    assert preview["content"] == "console.log(1);\n"
    assert preview["is_text"] is True
    assert preview["truncated"] is False

    listed = auth_client.get(f"/api/v1/projects/{project['id']}/snapshots").json()["data"]
    assert [s["id"] for s in listed] == [snapshot["id"]]


def test_repeated_upload_is_deterministic(
    auth_client: TestClient, fake_store: FakeObjectStore
) -> None:
    workspace = make_workspace(auth_client, "wsdet")
    project = make_project(auth_client, workspace["id"], "det")
    first = upload(auth_client, project["id"], "a.zip", DEMO_ZIP).json()["data"]["snapshot"]
    second = upload(auth_client, project["id"], "b.zip", DEMO_ZIP).json()["data"]["snapshot"]
    assert first["id"] != second["id"]
    assert first["tree_digest"] == second["tree_digest"]
    assert first["storage_status"] == "ready"
    assert second["storage_status"] == "ready"
    assert len(fake_store.objects) == 1


def test_malicious_and_invalid_uploads_rejected(auth_client: TestClient) -> None:
    workspace = make_workspace(auth_client, "wsmal")
    project = make_project(auth_client, workspace["id"], "mal")

    traversal = make_zip({"../../evil.py": "x = 1\n"})
    response = upload(auth_client, project["id"], "evil.zip", traversal)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "ARCHIVE_TRAVERSAL"

    not_zip = upload(auth_client, project["id"], "evil.zip", b"not a zip")
    assert not_zip.status_code == 415

    wrong_ext = upload(auth_client, project["id"], "app.tar.gz", DEMO_ZIP)
    assert wrong_ext.status_code == 415

    # Rejected uploads leave no snapshot behind.
    detail = auth_client.get(f"/api/v1/projects/{project['id']}").json()["data"]
    assert detail["snapshot_count"] == 0


def test_upload_to_archived_project_conflicts(auth_client: TestClient) -> None:
    workspace = make_workspace(auth_client, "wsarc")
    project = make_project(auth_client, workspace["id"], "arc")
    auth_client.post(f"/api/v1/projects/{project['id']}/archive")
    response = upload(auth_client, project["id"], "app.zip", DEMO_ZIP)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE"


def test_snapshots_are_immutable(auth_client: TestClient) -> None:
    workspace = make_workspace(auth_client, "wsimm")
    project = make_project(auth_client, workspace["id"], "imm")
    snapshot = upload(auth_client, project["id"], "a.zip", DEMO_ZIP).json()["data"]["snapshot"]
    assert auth_client.patch(f"/api/v1/snapshots/{snapshot['id']}", json={}).status_code == 405
    assert auth_client.delete(f"/api/v1/snapshots/{snapshot['id']}").status_code == 405
    assert auth_client.get(f"/api/v1/snapshots/{snapshot['id']}").status_code == 200


def test_tree_and_file_guards(auth_client: TestClient) -> None:
    workspace = make_workspace(auth_client, "wsguard")
    project = make_project(auth_client, workspace["id"], "guard")
    snapshot = upload(auth_client, project["id"], "a.zip", DEMO_ZIP).json()["data"]["snapshot"]

    traversal = auth_client.get(
        f"/api/v1/snapshots/{snapshot['id']}/tree", params={"prefix": "../.."}
    )
    assert traversal.status_code == 422

    missing = auth_client.get(
        f"/api/v1/snapshots/{snapshot['id']}/file", params={"path": "nope.py"}
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
