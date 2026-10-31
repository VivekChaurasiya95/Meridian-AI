"""Pure auth unit tests: hashing, tokens, limiter, origin checks, schemas."""

import re

import pytest
from pydantic import ValidationError

from app.schemas import LoginRequest, MemberCreate, SignupRequest
from app.security import (
    SlidingWindowLimiter,
    hash_password,
    hash_session_token,
    mint_session_token,
    origin_allowed,
    verify_password,
)


def test_password_round_trip() -> None:
    stored = hash_password("correct-horse-1234", rounds=4)
    assert stored != "correct-horse-1234"
    assert verify_password("correct-horse-1234", stored) is True
    assert verify_password("wrong-password", stored) is False


def test_password_preserved_verbatim() -> None:
    # Leading/trailing whitespace is part of the secret, never stripped.
    stored = hash_password("  padded-secret-1  ", rounds=4)
    assert verify_password("  padded-secret-1  ", stored) is True
    assert verify_password("padded-secret-1", stored) is False


def test_verify_rejects_malformed_hashes() -> None:
    assert verify_password("anything", "not-a-hash") is False
    assert verify_password("anything", "") is False


def test_long_passwords_supported() -> None:
    long_password = "x" * 200  # Beyond bcrypt's native 72-byte limit.
    stored = hash_password(long_password, rounds=4)
    assert verify_password(long_password, stored) is True


def test_session_token_shape() -> None:
    first, second = mint_session_token(), mint_session_token()
    assert first != second
    hashed = hash_session_token(first)
    assert re.fullmatch(r"[0-9a-f]{64}", hashed)
    assert hash_session_token(first) == hashed  # Deterministic.


def test_signup_schema_policy() -> None:
    assert SignupRequest(
        email="User@Example.com", password="ten-chars1", display_name="U"
    ).password == "ten-chars1"
    with pytest.raises(ValidationError):
        SignupRequest(email="u@e.com", password="short", display_name="U")
    with pytest.raises(ValidationError):
        SignupRequest(email="not-an-email", password="long-enough-1", display_name="U")
    with pytest.raises(ValidationError):
        SignupRequest(
            email="u@e.com", password="long-enough-1", display_name="U", role="owner"
        )


def test_login_schema_requires_password() -> None:
    with pytest.raises(ValidationError):
        LoginRequest(email="u@e.com", password="")
    with pytest.raises(ValidationError):
        MemberCreate(email="u@e.com", role="owner")


def test_limiter_allows_then_blocks() -> None:
    now = [1000.0]
    limiter = SlidingWindowLimiter(3, 60, clock=lambda: now[0])
    assert limiter.allowed("k")
    limiter.register_failure("k")
    limiter.register_failure("k")
    assert limiter.allowed("k")
    limiter.register_failure("k")
    assert not limiter.allowed("k")
    limiter.reset("k")
    assert limiter.allowed("k")


def test_limiter_window_expires() -> None:
    now = [1000.0]
    limiter = SlidingWindowLimiter(1, 60, clock=lambda: now[0])
    limiter.register_failure("k")
    assert not limiter.allowed("k")
    now[0] += 61
    assert limiter.allowed("k")


def test_limiter_keys_are_independent() -> None:
    limiter = SlidingWindowLimiter(1, 60)
    limiter.register_failure("a")
    assert not limiter.allowed("a")
    assert limiter.allowed("b")


def test_origin_check() -> None:
    allowed = ["http://localhost:3000"]
    assert origin_allowed("http://localhost:3000", None, allowed) is True
    assert origin_allowed("http://localhost:3000/", None, allowed) is True
    assert origin_allowed("http://localhost:9999", None, allowed) is False
    assert origin_allowed("https://localhost:3000", None, allowed) is False
    assert origin_allowed("http://evil.com", None, allowed) is False
    assert origin_allowed("garbage", None, allowed) is False
    assert origin_allowed(None, None, allowed) is False
    # Referer fallback when Origin is absent.
    assert origin_allowed(None, "http://localhost:3000/app", allowed) is True
    assert origin_allowed(None, "http://evil.com/", allowed) is False
