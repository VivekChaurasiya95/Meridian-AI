"""Local authentication service: signup, login, logout, session resolution."""

import datetime as dt
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.envelope import ApiError
from app.models import LocalCredential, User, UserSession
from app.schemas import LoginRequest, SignupRequest
from app.security import (
    SlidingWindowLimiter,
    hash_password,
    hash_session_token,
    mint_session_token,
    verify_password,
)
from app.services.firebase_auth import FIREBASE_PROVIDER, FirebaseIdentity

LOCAL_PROVIDER = "local"


def _serialize_user(user: User) -> dict:
    return {
        "id": str(user.id),
        "display_name": user.display_name,
        "email": user.email,
        "status": user.status,
    }


def _new_session(session: Session, user_id: uuid.UUID) -> str:
    raw_token = mint_session_token()
    now = dt.datetime.now(dt.UTC)
    ttl_hours = get_settings().session_ttl_hours
    session.add(
        UserSession(
            token_hash=hash_session_token(raw_token),
            user_id=user_id,
            created_at=now,
            expires_at=now + dt.timedelta(hours=ttl_hours),
        )
    )
    return raw_token


def signup(session: Session, payload: SignupRequest, bcrypt_rounds: int) -> tuple[dict, str]:
    """Create a local user + credential + first session in one transaction."""
    email = payload.email.strip().lower()
    user_id = uuid.uuid4()
    now = dt.datetime.now(dt.UTC)
    session.add(
        User(
            id=user_id,
            auth_provider=LOCAL_PROVIDER,
            provider_subject=str(user_id),
            email=email,
            display_name=payload.display_name.strip(),
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    try:
        # flush() inserts the user row, so it must sit inside the try:
        # a duplicate local email violates uq_users_local_email here,
        # not at commit time.
        session.flush()
        session.add(
            LocalCredential(
                user_id=user_id,
                password_hash=hash_password(payload.password, bcrypt_rounds),
                created_at=now,
                updated_at=now,
            )
        )
        raw_token = _new_session(session, user_id)
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ApiError(
            409, "RESOURCE_CONFLICT", "An account with this email already exists."
        ) from exc
    user = session.get(User, user_id)
    assert user is not None
    return _serialize_user(user), raw_token


def login(
    session: Session,
    payload: LoginRequest,
    limiter: SlidingWindowLimiter,
    rate_key: str,
) -> tuple[dict, str]:
    """Authenticate with email + password. Failures are uniform (no enumeration)."""
    if not limiter.allowed(rate_key):
        raise ApiError(429, "RATE_LIMITED", "Too many login attempts. Try again later.")
    email = payload.email.strip().lower()
    user = (
        session.execute(
            select(User).where(
                User.auth_provider == LOCAL_PROVIDER,
                User.email == email,
                User.status == "active",
            )
        )
    ).scalar_one_or_none()
    credential = session.get(LocalCredential, user.id) if user else None
    if (
        user is None
        or credential is None
        or not verify_password(payload.password, credential.password_hash)
    ):
        limiter.register_failure(rate_key)
        raise ApiError(401, "AUTH_REQUIRED", "Invalid email or password.")
    limiter.reset(rate_key)
    raw_token = _new_session(session, user.id)
    session.commit()
    return _serialize_user(user), raw_token


def firebase_sign_in(session: Session, identity: FirebaseIdentity) -> tuple[dict, str]:
    """Sign in with a verified Firebase identity (Google/GitHub).

    Returning Firebase users match on (provider, subject). A verified
    email that already belongs to an account signs into that account
    instead of creating a duplicate: one person, one account.
    """
    failed = ApiError(401, "AUTH_REQUIRED", "Social sign-in failed. Try again.")
    if not identity.email or not identity.email_verified:
        raise failed
    email = identity.email.strip().lower()
    user = session.execute(
        select(User).where(
            User.auth_provider == FIREBASE_PROVIDER,
            User.provider_subject == identity.uid,
        )
    ).scalar_one_or_none()
    if user is None:
        user = (
            session.execute(
                select(User).where(func.lower(User.email) == email).order_by(User.created_at)
            )
            .scalars()
            .first()
        )
    if user is None:
        now = dt.datetime.now(dt.UTC)
        user_id = uuid.uuid4()
        session.add(
            User(
                id=user_id,
                auth_provider=FIREBASE_PROVIDER,
                provider_subject=identity.uid,
                email=email,
                display_name=(identity.display_name or email.split("@")[0])[:100],
                avatar_url=identity.avatar_url,
                status="active",
                created_at=now,
                updated_at=now,
            )
        )
        try:
            session.flush()
        except IntegrityError:
            # Concurrent first sign-in won the race; use that row.
            session.rollback()
            user = session.execute(
                select(User).where(
                    User.auth_provider == FIREBASE_PROVIDER,
                    User.provider_subject == identity.uid,
                )
            ).scalar_one_or_none()
            if user is None:
                raise failed from None
        else:
            user = session.get(User, user_id)
    assert user is not None
    if user.status != "active":
        raise failed
    if identity.avatar_url and user.avatar_url != identity.avatar_url:
        user.avatar_url = identity.avatar_url
    raw_token = _new_session(session, user.id)
    session.commit()
    fresh = session.get(User, user.id)
    assert fresh is not None
    return _serialize_user(fresh), raw_token


def logout(session: Session, raw_token: str | None) -> None:
    """Revoke a session. Idempotent: unknown tokens still succeed."""
    if not raw_token:
        return
    row = session.get(UserSession, hash_session_token(raw_token))
    if row is not None and row.revoked_at is None:
        row.revoked_at = dt.datetime.now(dt.UTC)
        session.commit()


def resolve_session(session: Session, raw_token: str) -> User | None:
    """Return the active user for a live, unexpired, unrevoked session token."""
    row = session.get(UserSession, hash_session_token(raw_token))
    if row is None or row.revoked_at is not None:
        return None
    now = dt.datetime.now(dt.UTC)
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=dt.UTC)
    if expires_at <= now:
        return None
    user = session.get(User, row.user_id)
    if user is None or user.status != "active":
        return None
    return user
