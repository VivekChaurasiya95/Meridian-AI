"""Shared FastAPI dependencies: request ID, DB session, current identity."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.envelope import REQUEST_ID_HEADER, ApiError, normalize_request_id
from app.models import User
from app.security import SlidingWindowLimiter, origin_allowed
from app.services.auth import resolve_session

DbSession = Annotated[Session, Depends(get_db)]

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


@lru_cache(maxsize=1)
def login_limiter() -> SlidingWindowLimiter:
    settings = get_settings()
    return SlidingWindowLimiter(settings.login_max_attempts, settings.login_window_seconds)


@lru_cache(maxsize=1)
def upload_limiter() -> SlidingWindowLimiter:
    settings = get_settings()
    return SlidingWindowLimiter(settings.upload_rate_max, settings.upload_rate_window_seconds)


@lru_cache(maxsize=1)
def write_limiter() -> SlidingWindowLimiter:
    settings = get_settings()
    return SlidingWindowLimiter(settings.write_rate_max, settings.write_rate_window_seconds)


def get_request_id(request: Request) -> str:
    """Resolve the request ID: middleware-attached state first, then header.

    The middleware already honored or generated the ID into request state;
    re-deriving it here would mint a second ID and disagree with the
    X-Request-ID response header.
    """
    state_id = getattr(request.state, "request_id", None)
    if isinstance(state_id, str) and state_id:
        return state_id
    return normalize_request_id(request.headers.get(REQUEST_ID_HEADER))


def bearer_or_cookie_token(request: Request) -> str | None:
    """Extract the session token: Bearer header first, then the session cookie."""
    authorization = request.headers.get("Authorization", "")
    scheme, _, credential = authorization.partition(" ")
    if scheme.lower() == "bearer" and credential.strip():
        return credential.strip()
    cookie_name = get_settings().session_cookie_name
    return request.cookies.get(cookie_name)


def _via_cookie(request: Request) -> bool:
    authorization = request.headers.get("Authorization", "")
    scheme, _, credential = authorization.partition(" ")
    if scheme.lower() == "bearer" and credential.strip():
        return False
    return get_settings().session_cookie_name in request.cookies


def get_current_user(request: Request, session: DbSession) -> User:
    """Resolve the caller from their session token (cookie or Bearer).

    Raises 401 for missing/invalid/expired sessions. Cookie-authenticated
    unsafe methods must additionally prove same-frontend origin (D19).
    """
    token = bearer_or_cookie_token(request)
    if not token:
        raise ApiError(401, "AUTH_REQUIRED", "Authentication is required.")
    user = resolve_session(session, token)
    if user is None:
        raise ApiError(401, "AUTH_REQUIRED", "The session is invalid or expired.")
    if (
        request.method in UNSAFE_METHODS
        and _via_cookie(request)
        and not origin_allowed(
            request.headers.get("Origin"),
            request.headers.get("Referer"),
            get_settings().cors_origins(),
        )
    ):
        raise ApiError(403, "ACCESS_DENIED", "Cross-origin request refused.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
RequestId = Annotated[str, Depends(get_request_id)]
