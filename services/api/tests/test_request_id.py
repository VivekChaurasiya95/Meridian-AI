"""Request-ID propagation (API.md §2.4): honor sane IDs, generate otherwise."""

from fastapi.testclient import TestClient

from app.main import create_app


def test_honors_client_request_id() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health/live", headers={"X-Request-ID": "req_client123"})
    assert response.headers["X-Request-ID"] == "req_client123"


def test_generates_request_id_for_bad_header() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health/live", headers={"X-Request-ID": "bad id!\n"})
    generated = response.headers["X-Request-ID"]
    assert generated.startswith("req_")
    assert generated != "bad id!\n"


def test_error_envelope_carries_request_id(auth_client: TestClient) -> None:
    response = auth_client.get("/api/v1/workspaces/not-a-uuid")
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert body["request_id"] == response.headers["X-Request-ID"]
