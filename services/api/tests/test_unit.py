"""Pure unit tests: no sockets, no database, no network.

These run in any environment (including locked-down sandboxes). HTTP-level
tests live in test_health.py / test_workspaces.py / test_request_id.py and run
where loopback sockets are available (developer machines, CI).
"""

import json
import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.envelope import (
    ApiError,
    access_denied,
    new_request_id,
    normalize_request_id,
    not_found,
    ok,
    paged,
)
from app.schemas import WorkspaceCreate, WorkspaceUpdate
from app.services.workspaces import decode_cursor, encode_cursor


def test_new_request_id_shape() -> None:
    request_id = new_request_id()
    assert request_id.startswith("req_")
    assert len(request_id) == 30


def test_normalize_request_id_honors_sane_values() -> None:
    assert normalize_request_id("req_client123") == "req_client123"
    assert normalize_request_id("a" * 64) == "a" * 64


def test_normalize_request_id_regenerates_insane_values() -> None:
    assert normalize_request_id(None).startswith("req_")
    assert normalize_request_id("").startswith("req_")
    assert normalize_request_id("bad id!").startswith("req_")
    assert normalize_request_id("a" * 65).startswith("req_")


def test_ok_envelope_shape() -> None:
    response = ok({"a": 1}, "req_test", status_code=201)
    assert response.status_code == 201
    assert json.loads(response.body) == {"data": {"a": 1}, "request_id": "req_test"}
    assert response.headers["X-Request-ID"] == "req_test"


def test_paged_envelope_shape() -> None:
    response = paged([{"a": 1}], 25, "cursor-1", "req_test")
    assert json.loads(response.body) == {
        "data": [{"a": 1}],
        "page": {"limit": 25, "next_cursor": "cursor-1"},
        "request_id": "req_test",
    }


def test_error_envelope_shape() -> None:
    response = ApiError(409, "RESOURCE_CONFLICT", "Taken.").response("req_test")
    assert response.status_code == 409
    assert json.loads(response.body) == {
        "error": {"code": "RESOURCE_CONFLICT", "message": "Taken.", "details": []},
        "request_id": "req_test",
    }


def test_error_helpers() -> None:
    assert (not_found().status_code, not_found().code) == (404, "RESOURCE_NOT_FOUND")
    assert (access_denied().status_code, access_denied().code) == (403, "ACCESS_DENIED")


def test_workspace_create_accepts_valid_input() -> None:
    payload = WorkspaceCreate(name="Product Engineering", slug="product-engineering")
    assert payload.name == "Product Engineering"


def test_workspace_create_rejects_bad_slug_and_blank_name() -> None:
    with pytest.raises(ValidationError):
        WorkspaceCreate(name="A", slug="Bad Slug!")
    with pytest.raises(ValidationError):
        WorkspaceCreate(name="   ", slug="a")


def test_workspace_create_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        WorkspaceCreate(name="A", slug="a", role="owner")  # type: ignore[call-arg]


def test_workspace_update_allows_only_name() -> None:
    assert WorkspaceUpdate(name="New").name == "New"
    with pytest.raises(ValidationError):
        WorkspaceUpdate(name="New", slug="new")  # type: ignore[call-arg]


def test_cursor_round_trip() -> None:
    created_at = datetime(2026, 10, 28, 8, 30, tzinfo=UTC)
    workspace_id = uuid.uuid4()
    cursor = encode_cursor(created_at, workspace_id)
    assert decode_cursor(cursor) == (created_at, workspace_id)


def test_cursor_rejects_garbage() -> None:
    assert decode_cursor("not-a-cursor") is None
    assert decode_cursor("") is None


def test_settings_parses_cors_origins() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://u:p@localhost:5432/db",
        cors_allow_origins="http://a:3000, http://b:3000",
    )
    assert settings.cors_origins() == ["http://a:3000", "http://b:3000"]


def test_settings_rejects_non_postgres_url() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="sqlite:///local.db")
