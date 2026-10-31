"""Authentication primitives: password hashing, session tokens, rate limits.

No custom cryptography: bcrypt for passwords (with a SHA-256 pre-hash so long
passwords are safe), `secrets` for token minting, SHA-256 for token storage
hashes. Only hashes ever touch the database or logs — never raw passwords or
raw tokens.
"""

import base64
import hashlib
import secrets
import time
from collections import deque
from collections.abc import Callable
from urllib.parse import urlparse


def hash_password(password: str, rounds: int) -> str:
    """Hash a password for storage. Passwords are never stripped or altered."""
    import bcrypt

    digest = hashlib.sha256(password.encode("utf-8")).digest()
    salt = bcrypt.gensalt(rounds=rounds)
    return bcrypt.hashpw(base64.b64encode(digest), salt).decode("ascii")


def verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time password check. Returns False for malformed hashes."""
    import bcrypt

    try:
        digest = hashlib.sha256(password.encode("utf-8")).digest()
        return bcrypt.checkpw(base64.b64encode(digest), stored_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


def mint_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class SlidingWindowLimiter:
    """Single-process sliding-window rate limiter (dev-scale, see D20).

    Thread-safe enough for the API's purposes (GIL-atomic deque ops).
    A shared store replaces this when the API scales horizontally.
    """

    def __init__(
        self,
        max_attempts: int,
        window_seconds: int,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._max_attempts = max_attempts
        self._window = window_seconds
        self._clock = clock or time.monotonic
        self._hits: dict[str, deque[float]] = {}

    def _prune(self, key: str, now: float) -> deque[float]:
        bucket = self._hits.setdefault(key, deque())
        cutoff = now - self._window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        return bucket

    def allowed(self, key: str) -> bool:
        return len(self._prune(key, self._clock())) < self._max_attempts

    def register_failure(self, key: str) -> None:
        self._prune(key, self._clock()).append(self._clock())

    def reset(self, key: str) -> None:
        self._hits.pop(key, None)


def origin_allowed(
    origin: str | None, referer: str | None, allowed_origins: list[str]
) -> bool:
    """Check an unsafe cookie-authenticated request came from our own frontend.

    Compares scheme://host:port exactly against the CORS allowlist. Missing
    Origin *and* Referer is rejected: browsers always send Origin on
    cross-origin POSTs, and our web client is cross-origin (app ≠ api port).
    """

    def _origin_of(value: str) -> str | None:
        try:
            parsed = urlparse(value)
        except ValueError:
            return None
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            return None
        host = parsed.hostname
        port = f":{parsed.port}" if parsed.port else ""
        return f"{parsed.scheme}://{host}{port}"

    allowed = {_origin_of(a) for a in allowed_origins} - {None}
    if origin:
        return _origin_of(origin) in allowed
    if referer:
        return _origin_of(referer) in allowed
    return False
