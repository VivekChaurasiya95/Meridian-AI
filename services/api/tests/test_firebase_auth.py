"""Firebase social sign-in tests: token verification + session exchange."""

import datetime as dt
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

import app.api.auth as auth_routes
import app.services.firebase_auth as firebase_auth
from app.envelope import ApiError
from app.services.firebase_auth import FirebaseIdentity

SESSION_COOKIE = "meridian_session"
PROJECT_ID = "demo-project"


def _identity(**overrides: object) -> FirebaseIdentity:
    values: dict[str, object] = {
        "uid": "firebase-uid-1",
        "email": "Social@Example.com",
        "email_verified": True,
        "display_name": "Social User",
        "avatar_url": None,
        "sign_in_provider": "google.com",
    }
    values.update(overrides)
    return FirebaseIdentity(**values)  # type: ignore[arg-type]


@pytest.fixture()
def stub_verify(monkeypatch: pytest.MonkeyPatch):
    """Replace the route's token verifier with a canned identity/error."""

    def install(identity: FirebaseIdentity | None = None, error: ApiError | None = None) -> None:
        def fake(_id_token: str) -> FirebaseIdentity:
            if error is not None:
                raise error
            assert identity is not None
            return identity

        monkeypatch.setattr(auth_routes, "verify_firebase_id_token", fake)

    return install


def test_firebase_sign_in_creates_user_and_session(client: TestClient, stub_verify) -> None:
    stub_verify(_identity())
    response = client.post("/api/v1/auth/firebase", json={"id_token": "valid"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["email"] == "social@example.com"
    assert data["display_name"] == "Social User"
    assert data["status"] == "active"
    assert SESSION_COOKIE in response.headers.get("set-cookie", "")
    assert client.get("/api/v1/me").status_code == 200


def test_firebase_sign_in_returns_same_user(client: TestClient, stub_verify) -> None:
    stub_verify(_identity())
    first = client.post("/api/v1/auth/firebase", json={"id_token": "valid"})
    second = client.post("/api/v1/auth/firebase", json={"id_token": "valid"})
    assert first.json()["data"]["id"] == second.json()["data"]["id"]


def test_firebase_sign_in_accepts_github(client: TestClient, stub_verify) -> None:
    stub_verify(
        _identity(
            uid="github-uid-9",
            email="octo@example.com",
            sign_in_provider="github.com",
        )
    )
    response = client.post("/api/v1/auth/firebase", json={"id_token": "valid"})
    assert response.status_code == 200
    assert response.json()["data"]["email"] == "octo@example.com"


def test_firebase_sign_in_links_local_account_by_email(client: TestClient, stub_verify) -> None:
    signup = client.post(
        "/api/v1/auth/signup",
        json={
            "email": "social@example.com",
            "password": "password-1234",
            "display_name": "Local Name",
        },
    )
    assert signup.status_code == 201
    local_id = signup.json()["data"]["id"]
    client.cookies.clear()
    stub_verify(_identity())
    response = client.post("/api/v1/auth/firebase", json={"id_token": "valid"})
    assert response.status_code == 200
    assert response.json()["data"]["id"] == local_id
    # Password login still works for the linked account.
    client.cookies.clear()
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "social@example.com", "password": "password-1234"},
    )
    assert login.status_code == 200


def test_firebase_sign_in_rejects_unverified_email(client: TestClient, stub_verify) -> None:
    stub_verify(_identity(email_verified=False))
    response = client.post("/api/v1/auth/firebase", json={"id_token": "valid"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_REQUIRED"


def test_firebase_sign_in_rejects_missing_email(client: TestClient, stub_verify) -> None:
    stub_verify(_identity(email=None))
    response = client.post("/api/v1/auth/firebase", json={"id_token": "valid"})
    assert response.status_code == 401


def test_firebase_sign_in_rejects_invalid_token(client: TestClient, stub_verify) -> None:
    stub_verify(error=ApiError(401, "AUTH_REQUIRED", "Social sign-in failed."))
    response = client.post("/api/v1/auth/firebase", json={"id_token": "junk"})
    assert response.status_code == 401


def test_firebase_sign_in_reports_unconfigured(client: TestClient, stub_verify) -> None:
    stub_verify(
        error=ApiError(503, "AUTH_PROVIDER_NOT_CONFIGURED", "Social sign-in is not configured.")
    )
    response = client.post("/api/v1/auth/firebase", json={"id_token": "valid"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AUTH_PROVIDER_NOT_CONFIGURED"


# --- Token verification (no database; keys are generated in-test) ---


@pytest.fixture()
def rsa_keys(monkeypatch: pytest.MonkeyPatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        firebase_auth, "_public_keys", lambda: {"test-kid": private_key.public_key()}
    )
    monkeypatch.setattr(
        firebase_auth,
        "get_settings",
        lambda: SimpleNamespace(firebase_project_id=PROJECT_ID),
    )
    return private_key


def _make_token(private_key: object, **overrides: object) -> str:
    now = dt.datetime.now(dt.UTC)
    claims: dict[str, object] = {
        "sub": "uid-123",
        "aud": PROJECT_ID,
        "iss": f"https://securetoken.google.com/{PROJECT_ID}",
        "iat": now,
        "exp": now + dt.timedelta(hours=1),
        "email": "person@example.com",
        "email_verified": True,
        "name": "Person",
        "firebase": {"sign_in_provider": "google.com"},
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-kid"})


def test_verify_accepts_valid_google_token(rsa_keys: object) -> None:
    identity = firebase_auth.verify_firebase_id_token(_make_token(rsa_keys))
    assert identity.uid == "uid-123"
    assert identity.email == "person@example.com"
    assert identity.sign_in_provider == "google.com"


def test_verify_rejects_wrong_audience(rsa_keys: object) -> None:
    with pytest.raises(ApiError) as excinfo:
        firebase_auth.verify_firebase_id_token(_make_token(rsa_keys, aud="someone-else"))
    assert excinfo.value.status_code == 401


def test_verify_rejects_expired_token(rsa_keys: object) -> None:
    past = dt.datetime.now(dt.UTC) - dt.timedelta(hours=2)
    with pytest.raises(ApiError):
        firebase_auth.verify_firebase_id_token(
            _make_token(rsa_keys, iat=past, exp=past + dt.timedelta(minutes=5))
        )


def test_verify_rejects_non_social_provider(rsa_keys: object) -> None:
    with pytest.raises(ApiError):
        firebase_auth.verify_firebase_id_token(
            _make_token(rsa_keys, firebase={"sign_in_provider": "password"})
        )


def test_verify_reports_unconfigured_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        firebase_auth,
        "get_settings",
        lambda: SimpleNamespace(firebase_project_id=""),
    )
    with pytest.raises(ApiError) as excinfo:
        firebase_auth.verify_firebase_id_token("anything")
    assert excinfo.value.status_code == 503
