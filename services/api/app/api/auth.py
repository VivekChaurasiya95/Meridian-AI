"""Session auth routes: signup, login, logout."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.api.deps import DbSession, RequestId, bearer_or_cookie_token, login_limiter
from app.config import get_settings
from app.envelope import ApiError, ok
from app.schemas import FirebaseLoginRequest, LoginRequest, SignupRequest
from app.services import auth as auth_service
from app.services.firebase_auth import verify_firebase_id_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _session_cookie(response: JSONResponse, raw_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.secure_cookies,
    )
    # Readable presence flag (no secret): lets the frontend skip the /me
    # probe entirely for anonymous visitors instead of logging 401s.
    response.set_cookie(
        key=settings.session_cookie_name + "_present",
        value="1",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
        httponly=False,
        samesite="lax",
        secure=settings.secure_cookies,
    )


@router.post("/signup", status_code=201)
def signup(
    payload: SignupRequest, session: DbSession, request_id: RequestId
) -> JSONResponse:
    settings = get_settings()
    data, raw_token = auth_service.signup(session, payload, settings.bcrypt_rounds)
    response = ok(data, request_id, status_code=201)
    _session_cookie(response, raw_token)
    return response


@router.post("/login")
def login(
    payload: LoginRequest, request: Request, session: DbSession, request_id: RequestId
) -> JSONResponse:
    client_host = request.client.host if request.client else "unknown"
    rate_key = f"{client_host}:{payload.email.strip().lower()}"
    data, raw_token = auth_service.login(session, payload, login_limiter(), rate_key)
    response = ok(data, request_id)
    _session_cookie(response, raw_token)
    return response


@router.post("/firebase")
def firebase_login(
    payload: FirebaseLoginRequest,
    request: Request,
    session: DbSession,
    request_id: RequestId,
) -> JSONResponse:
    """Exchange a Firebase ID token (Google/GitHub) for a Meridian session."""
    client_host = request.client.host if request.client else "unknown"
    rate_key = f"firebase:{client_host}"
    limiter = login_limiter()
    if not limiter.allowed(rate_key):
        raise ApiError(429, "RATE_LIMITED", "Too many sign-in attempts. Try again later.")
    try:
        identity = verify_firebase_id_token(payload.id_token)
        data, raw_token = auth_service.firebase_sign_in(session, identity)
    except ApiError as exc:
        if exc.status_code == 401:
            limiter.register_failure(rate_key)
        raise
    limiter.reset(rate_key)
    response = ok(data, request_id)
    _session_cookie(response, raw_token)
    return response


@router.post("/logout", status_code=204)
def logout(request: Request, session: DbSession) -> JSONResponse:
    # Idempotent: unknown or missing tokens still clear both cookies.
    auth_service.logout(session, bearer_or_cookie_token(request))
    settings = get_settings()
    response = JSONResponse(status_code=204, content=None)
    response.delete_cookie(key=settings.session_cookie_name, path="/")
    response.delete_cookie(key=settings.session_cookie_name + "_present", path="/")
    return response
