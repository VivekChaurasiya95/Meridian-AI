"""Session auth + /me endpoint tests (D17/D19)."""

from fastapi.testclient import TestClient

SESSION_COOKIE = "meridian_session"


def test_signup_returns_user_and_session_cookie(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "email": "Ada@Example.com",
            "password": "correct-horse-1234",
            "display_name": "Ada",
        },
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["email"] == "ada@example.com"
    assert data["display_name"] == "Ada"
    assert data["status"] == "active"
    assert "password" not in response.text
    set_cookie = response.headers.get("set-cookie", "")
    assert SESSION_COOKIE in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=Lax" in set_cookie or "samesite=lax" in set_cookie.lower()
    # The readable presence flag lets the frontend skip anonymous /me probes.
    assert f"{SESSION_COOKIE}_present=1" in set_cookie


def test_signup_rejects_duplicate_email(client: TestClient) -> None:
    payload = {"email": "dupe@example.com", "password": "password-1234", "display_name": "D"}
    assert client.post("/api/v1/auth/signup", json=payload).status_code == 201
    response = client.post("/api/v1/auth/signup", json=payload)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RESOURCE_CONFLICT"


def test_signup_validates_input(client: TestClient) -> None:
    short_ok = client.post(
        "/api/v1/auth/signup",
        json={"email": "u@example.com", "password": "short", "display_name": "U"},
    )
    assert short_ok.status_code == 201
    empty = client.post(
        "/api/v1/auth/signup",
        json={"email": "e@example.com", "password": "", "display_name": "E"},
    )
    assert empty.status_code == 422
    bad_email = client.post(
        "/api/v1/auth/signup",
        json={"email": "not-an-email", "password": "password-1234", "display_name": "U"},
    )
    assert bad_email.status_code == 422


def test_login_round_trip(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/signup",
        json={"email": "login@example.com", "password": "password-1234", "display_name": "L"},
    )
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "password-1234"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["email"] == "login@example.com"
    me = client.get("/api/v1/me")
    assert me.status_code == 200


def test_login_failures_are_uniform(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/signup",
        json={"email": "real@example.com", "password": "password-1234", "display_name": "R"},
    )
    wrong_password = client.post(
        "/api/v1/auth/login",
        json={"email": "real@example.com", "password": "wrong-password"},
    )
    unknown_email = client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "wrong-password"},
    )
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json()["error"]["code"] == "AUTH_REQUIRED"
    assert wrong_password.json()["error"] == unknown_email.json()["error"]


def test_login_rate_limited_after_repeated_failures(client: TestClient) -> None:
    for _ in range(11):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "flood@example.com", "password": "wrong-password"},
        )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"


def test_me_requires_auth(client: TestClient) -> None:
    response = client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_me_returns_profile(auth_client: TestClient) -> None:
    response = auth_client.get("/api/v1/me")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["email"] == "owner@example.com"
    assert set(data) == {"id", "display_name", "email", "status"}


def test_patch_me_updates_display_name(auth_client: TestClient) -> None:
    response = auth_client.patch("/api/v1/me", json={"display_name": "New Name"})
    assert response.status_code == 200
    assert response.json()["data"]["display_name"] == "New Name"


def test_patch_me_rejects_privileged_fields(auth_client: TestClient) -> None:
    response = auth_client.patch("/api/v1/me", json={"display_name": "X", "status": "disabled"})
    assert response.status_code == 422


def test_logout_revokes_session(auth_client: TestClient) -> None:
    assert auth_client.get("/api/v1/me").status_code == 200
    response = auth_client.post("/api/v1/auth/logout")
    assert response.status_code == 204
    assert auth_client.get("/api/v1/me").status_code == 401


def test_cookie_mutation_without_origin_is_refused(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/signup",
        json={"email": "csrf@example.com", "password": "password-1234", "display_name": "C"},
    )
    # Raw client sends no Origin header: unsafe cookie-authenticated call fails.
    refused = client.post("/api/v1/workspaces", json={"name": "X", "slug": "x"})
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "ACCESS_DENIED"
    # Safe methods are unaffected.
    assert client.get("/api/v1/me").status_code == 200
    # Matching Origin is accepted.
    allowed = client.post(
        "/api/v1/workspaces",
        json={"name": "X", "slug": "x"},
        headers={"Origin": "http://localhost:3000"},
    )
    assert allowed.status_code == 201


def test_bearer_token_auth_without_origin(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/signup",
        json={"email": "api@example.com", "password": "password-1234", "display_name": "A"},
    )
    token = client.cookies.get(SESSION_COOKIE)
    assert token
    client.cookies.clear()
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/me", headers=headers).status_code == 200
    created = client.post("/api/v1/workspaces", json={"name": "B", "slug": "b"}, headers=headers)
    assert created.status_code == 201
    assert client.get("/api/v1/me", headers={"Authorization": "Bearer bogus"}).status_code == 401
