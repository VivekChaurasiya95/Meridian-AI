"""Workspace membership tests (API.md §6.4, decision D18)."""

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient

AuthClientFactory = Callable[..., TestClient]


def _create_workspace(client: TestClient, slug: str = "ws") -> str:
    response = client.post("/api/v1/workspaces", json={"name": slug, "slug": slug})
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


def test_add_member_by_email(auth_client_factory: AuthClientFactory) -> None:
    owner = auth_client_factory("owner@example.com", display_name="Owner")
    auth_client_factory("dev@example.com", display_name="Dev")
    workspace_id = _create_workspace(owner)

    response = owner.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"email": "DEV@example.com", "role": "developer"},
    )
    assert response.status_code == 201
    member = response.json()["data"]
    assert member["email"] == "dev@example.com"
    assert member["display_name"] == "Dev"
    assert member["role"] == "developer"
    uuid.UUID(member["user_id"])


def test_add_member_rejects_unknown_and_duplicate(
    auth_client_factory: AuthClientFactory,
) -> None:
    owner = auth_client_factory("owner@example.com")
    workspace_id = _create_workspace(owner)

    unknown = owner.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"email": "ghost@example.com", "role": "viewer"},
    )
    assert unknown.status_code == 404

    auth_client_factory("dev@example.com")
    payload = {"email": "dev@example.com", "role": "viewer"}
    assert owner.post(f"/api/v1/workspaces/{workspace_id}/members", json=payload).status_code == 201
    duplicate = owner.post(f"/api/v1/workspaces/{workspace_id}/members", json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "RESOURCE_CONFLICT"


def test_viewer_cannot_manage_members(auth_client_factory: AuthClientFactory) -> None:
    owner = auth_client_factory("owner@example.com")
    viewer = auth_client_factory("viewer@example.com")
    auth_client_factory("other@example.com")
    workspace_id = _create_workspace(owner)
    owner.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"email": "viewer@example.com", "role": "viewer"},
    )

    add = viewer.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"email": "other@example.com", "role": "viewer"},
    )
    assert add.status_code == 403

    members = viewer.get(f"/api/v1/workspaces/{workspace_id}/members").json()["data"]
    target = (
        next(m for m in members if m["email"] == "other@example.com")
        if any(m["email"] == "other@example.com" for m in members)
        else None
    )
    assert target is None  # The forbidden add really did not happen.


def test_non_member_sees_nothing(auth_client_factory: AuthClientFactory) -> None:
    owner = auth_client_factory("owner@example.com")
    stranger = auth_client_factory("stranger@example.com")
    workspace_id = _create_workspace(owner)
    response = stranger.get(f"/api/v1/workspaces/{workspace_id}/members")
    assert response.status_code == 404


def test_update_member_role(auth_client_factory: AuthClientFactory) -> None:
    owner = auth_client_factory("owner@example.com")
    auth_client_factory("dev@example.com")
    workspace_id = _create_workspace(owner)
    added = owner.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"email": "dev@example.com", "role": "developer"},
    ).json()["data"]

    updated = owner.patch(
        f"/api/v1/workspaces/{workspace_id}/members/{added['user_id']}",
        json={"role": "admin"},
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["role"] == "admin"


def test_owner_role_is_immutable(auth_client_factory: AuthClientFactory) -> None:
    owner = auth_client_factory("owner@example.com")
    workspace_id = _create_workspace(owner)
    owner_id = owner.get("/api/v1/me").json()["data"]["id"]

    response = owner.patch(
        f"/api/v1/workspaces/{workspace_id}/members/{owner_id}",
        json={"role": "admin"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_remove_member_and_last_owner_guard(
    auth_client_factory: AuthClientFactory,
) -> None:
    owner = auth_client_factory("owner@example.com")
    dev = auth_client_factory("dev@example.com")
    workspace_id = _create_workspace(owner)
    added = owner.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"email": "dev@example.com", "role": "developer"},
    ).json()["data"]

    assert (
        owner.delete(f"/api/v1/workspaces/{workspace_id}/members/{added['user_id']}").status_code
        == 204
    )
    assert dev.get(f"/api/v1/workspaces/{workspace_id}").status_code == 404

    owner_id = owner.get("/api/v1/me").json()["data"]["id"]
    last_owner = owner.delete(f"/api/v1/workspaces/{workspace_id}/members/{owner_id}")
    assert last_owner.status_code == 409
    assert last_owner.json()["error"]["code"] == "INVALID_STATE_TRANSITION"


def test_member_can_remove_self(auth_client_factory: AuthClientFactory) -> None:
    owner = auth_client_factory("owner@example.com")
    dev = auth_client_factory("dev@example.com")
    workspace_id = _create_workspace(owner)
    owner.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"email": "dev@example.com", "role": "viewer"},
    )
    dev_id = dev.get("/api/v1/me").json()["data"]["id"]
    assert dev.delete(f"/api/v1/workspaces/{workspace_id}/members/{dev_id}").status_code == 204
    assert dev.get(f"/api/v1/workspaces/{workspace_id}").status_code == 404
