"""Health endpoint tests (API.md §6.1)."""

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.main import create_app


def test_live_reports_ok_without_dependencies() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_ready_when_database_is_up(client: TestClient) -> None:
    # Readiness probes DATABASE_URL (the app's own database), while `client`
    # talks to TEST_DATABASE_URL. Both live on the same server in dev/CI.
    from app.db import check_database

    if not check_database():
        import pytest

        pytest.skip("DATABASE_URL is unreachable; start Postgres (see README).")
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "ok"


def test_ready_reports_not_ready_when_database_is_down(monkeypatch: MonkeyPatch) -> None:
    import app.api.health as health_module

    monkeypatch.setattr(health_module, "check_database", lambda: False)
    with TestClient(create_app()) as client:
        response = client.get("/health/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"] == "unavailable"
    # Sanitized: no connection strings, hostnames, or driver errors leak out.
    assert "meridian" not in response.text.lower().replace("not_ready", "")
    assert "psycopg" not in response.text.lower()
