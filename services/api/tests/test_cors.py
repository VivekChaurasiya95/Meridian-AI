"""CORS preflight wiring for browser calls (no database needed).

The web client talks to the API cross-origin (3010 -> 8010) with
``Content-Type: application/json`` on every request and ``Idempotency-Key``
on investigation creation, so each triggers a preflight. A rejected
preflight surfaces in the browser as a CORS failure with no usable error,
so the allowlist must cover every header the client sends.
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture(scope="module")
def cors_client():  # type: ignore[no-untyped-def]
    with TestClient(create_app()) as test_client:
        yield test_client


def _preflight_headers(method: str, *headers: str) -> dict[str, str]:
    value = {
        "Origin": "http://localhost:3010",
        "Access-Control-Request-Method": method,
    }
    if headers:
        value["Access-Control-Request-Headers"] = ", ".join(headers)
    return value


def test_list_preflight_allows_browser_get(cors_client: TestClient) -> None:
    response = cors_client.options(
        f"/api/v1/projects/{uuid.uuid4()}/investigations",
        headers=_preflight_headers("GET", "content-type"),
    )
    assert response.status_code == 200, response.text


def test_create_preflight_allows_idempotency_key(cors_client: TestClient) -> None:
    response = cors_client.options(
        f"/api/v1/projects/{uuid.uuid4()}/investigations",
        headers=_preflight_headers("POST", "content-type", "idempotency-key"),
    )
    assert response.status_code == 200, response.text
