"""Firebase ID-token verification for Google/GitHub social sign-in.

Only the Firebase project ID is configured server-side. Firebase ID tokens
are RS256 JWTs signed by Google, verified here against the public x509
certificates Google publishes for the securetoken service. No
service-account secret is stored on this server. Every verification
failure collapses to one generic 401 so callers learn nothing about
which check failed.
"""

import contextlib
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from cryptography.x509 import load_pem_x509_certificate

from app.config import get_settings
from app.envelope import ApiError

CERTS_URL = (
    "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
)
FIREBASE_PROVIDER = "firebase"
ALLOWED_SIGN_IN_PROVIDERS = frozenset({"google.com", "github.com"})

_cert_cache: dict[str, Any] = {}
_cert_expires_at = 0.0


@dataclass(frozen=True)
class FirebaseIdentity:
    uid: str
    email: str | None
    email_verified: bool
    display_name: str | None
    avatar_url: str | None
    sign_in_provider: str


def _invalid() -> ApiError:
    return ApiError(401, "AUTH_REQUIRED", "Social sign-in failed. Try again.")


def _public_keys() -> dict[str, Any]:
    """Return {kid: public key} from Google's certs, cached per Cache-Control."""
    global _cert_expires_at
    now = time.time()
    if _cert_cache and now < _cert_expires_at:
        return dict(_cert_cache)
    response = httpx.get(CERTS_URL, timeout=10.0)
    response.raise_for_status()
    max_age = 3600
    for part in response.headers.get("Cache-Control", "").split(","):
        part = part.strip()
        if part.startswith("max-age="):
            with contextlib.suppress(ValueError):
                max_age = int(part.split("=", 1)[1])
    keys: dict[str, Any] = {}
    for kid, pem in response.json().items():
        cert = load_pem_x509_certificate(str(pem).encode("utf-8"))
        keys[str(kid)] = cert.public_key()
    _cert_cache.clear()
    _cert_cache.update(keys)
    _cert_expires_at = now + max(max_age, 60)
    return dict(keys)


def verify_firebase_id_token(id_token: str) -> FirebaseIdentity:
    """Verify a Firebase ID token and return the identity it carries."""
    project_id = get_settings().firebase_project_id.strip()
    if not project_id:
        raise ApiError(
            503,
            "AUTH_PROVIDER_NOT_CONFIGURED",
            "Social sign-in is not configured on this server.",
        )
    try:
        kid = jwt.get_unverified_header(id_token).get("kid")
        key = _public_keys().get(kid) if kid else None
        if key is None:
            raise _invalid()
        claims: dict[str, Any] = jwt.decode(
            id_token,
            key,
            algorithms=["RS256"],
            audience=project_id,
            issuer=f"https://securetoken.google.com/{project_id}",
            options={"require": ["exp", "iat", "sub", "aud", "iss"]},
        )
    except ApiError:
        raise
    except Exception:
        raise _invalid() from None

    uid = claims.get("sub")
    if not isinstance(uid, str) or not uid or len(uid) > 128:
        raise _invalid()
    firebase_claim = claims.get("firebase")
    provider = firebase_claim.get("sign_in_provider") if isinstance(firebase_claim, dict) else None
    if provider not in ALLOWED_SIGN_IN_PROVIDERS:
        raise _invalid()
    email = claims.get("email")
    name = claims.get("name")
    picture = claims.get("picture")
    return FirebaseIdentity(
        uid=uid,
        email=email.strip() if isinstance(email, str) and email.strip() else None,
        email_verified=claims.get("email_verified") is True,
        display_name=name.strip() if isinstance(name, str) and name.strip() else None,
        avatar_url=picture if isinstance(picture, str) and picture else None,
        sign_in_provider=str(provider),
    )
