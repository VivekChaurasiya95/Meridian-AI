"""Workspace endpoint tests (API.md §6.3): envelope, authz, pagination."""

import uuid

from fastapi.testclient import TestClient


def test_create_workspace_returns_201_envelope(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/v1/workspaces",
        json={"name": "Product Engineering", "slug": "product-engineering"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["request_id"].startswith("req_")
    assert response.headers["X-Request-ID"] == body["request_id"]
    data = body["data"]
    assert data["name"] == "Product Engineering"
    assert data["slug"] == "product-engineering"
    assert data["role"] == "owner"
    uuid.UUID(data["id"])
    assert data["created_at"].endswith("Z")


def test_create_workspace_rejects_duplicate_slug(auth_client: TestClient) -> None:
    auth_client.post("/api/v1/workspaces", json={"name": "A", "slug": "dupe"})
    response = auth_client.post("/api/v1/workspaces", json={"name": "B", "slug": "dupe"})
    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "RESOURCE_CONFLICT"
    assert body["request_id"].startswith("req_")


def test_create_workspace_validates_input(auth_client: TestClient) -> None:
    response = auth_client.post("/api/v1/workspaces", json={"name": "  ", "slug": "Bad Slug!"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    fields = {detail["field"] for detail in body["error"]["details"]}
    assert {"name", "slug"} <= fields


def test_create_workspace_rejects_unknown_fields(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/v1/workspaces", json={"name": "A", "slug": "a", "role": "owner"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_list_workspaces_paginates_with_cursor(auth_client: TestClient) -> None:
    for slug in ("ws-one", "ws-two", "ws-three"):
        created = auth_client.post("/api/v1/workspaces", json={"name": slug, "slug": slug})
        assert created.status_code == 201

    first = auth_client.get("/api/v1/workspaces", params={"limit": 2})
    assert first.status_code == 200
    first_body = first.json()
    assert len(first_body["data"]) == 2
    assert first_body["page"] == {"limit": 2, "next_cursor": first_body["page"]["next_cursor"]}
    assert first_body["page"]["next_cursor"]
    # Newest first.
    assert first_body["data"][0]["slug"] == "ws-three"

    second = auth_client.get(
        "/api/v1/workspaces",
        params={"limit": 2, "cursor": first_body["page"]["next_cursor"]},
    )
    assert second.status_code == 200
    second_body = second.json()
    assert [item["slug"] for item in second_body["data"]] == ["ws-one"]
    assert second_body["page"]["next_cursor"] is None


def test_list_workspaces_rejects_bad_cursor(auth_client: TestClient) -> None:
    response = auth_client.get("/api/v1/workspaces", params={"cursor": "not-a-cursor"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_get_workspace_returns_role(auth_client: TestClient) -> None:
    created = auth_client.post("/api/v1/workspaces", json={"name": "A", "slug": "a"}).json()
    response = auth_client.get(f"/api/v1/workspaces/{created['data']['id']}")
    assert response.status_code == 200
    assert response.json()["data"]["role"] == "owner"


def test_get_workspace_hides_unknown_ids(auth_client: TestClient) -> None:
    response = auth_client.get(f"/api/v1/workspaces/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_patch_workspace_renames_for_owner(auth_client: TestClient) -> None:
    created = auth_client.post("/api/v1/workspaces", json={"name": "Old", "slug": "old"}).json()
    workspace_id = created["data"]["id"]
    response = auth_client.patch(f"/api/v1/workspaces/{workspace_id}", json={"name": "New"})
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "New"


def test_patch_workspace_forbids_viewer(auth_client: TestClient, migrated_db: str) -> None:
    from sqlalchemy import create_engine, text

    created = auth_client.post("/api/v1/workspaces", json={"name": "A", "slug": "a"}).json()
    workspace_id = created["data"]["id"]

    engine = create_engine(migrated_db)
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE workspace_members SET role = 'viewer' WHERE workspace_id = :id"),
            {"id": workspace_id},
        )
    engine.dispose()

    response = auth_client.patch(f"/api/v1/workspaces/{workspace_id}", json={"name": "Nope"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ACCESS_DENIED"
