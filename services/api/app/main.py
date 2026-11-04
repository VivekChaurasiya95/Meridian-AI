"""FastAPI application factory."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app import __version__
from app.api import auth, git_imports, health, jobs, members, projects, users, workspaces
from app.config import get_settings
from app.envelope import (
    REQUEST_ID_HEADER,
    ApiError,
    new_request_id,
    normalize_request_id,
)

logger = logging.getLogger("meridian.api")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a request ID to every request and response."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = normalize_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response


def _request_id_from(request: Request) -> str:
    return getattr(request.state, "request_id", None) or new_request_id()


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    application = FastAPI(title="Meridian API", version=__version__)
    application.add_middleware(RequestIdMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins(),
        # Required for the HttpOnly session cookie; origins stay explicit,
        # never a wildcard (D19).
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", REQUEST_ID_HEADER],
    )

    @application.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return exc.response(_request_id_from(request))

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(part) for part in error["loc"] if part != "body"),
                "issue": error["msg"],
            }
            for error in exc.errors()
        ]
        return ApiError(
            422, "VALIDATION_ERROR", "The request contains invalid fields.", details
        ).response(_request_id_from(request))

    @application.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = _request_id_from(request)
        logger.exception("Unhandled error (request_id=%s)", request_id)
        return ApiError(500, "INTERNAL_ERROR", "An unexpected internal failure occurred.").response(
            request_id
        )

    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(users.router)
    application.include_router(workspaces.router)
    application.include_router(members.router)
    application.include_router(projects.router)
    application.include_router(git_imports.router)
    application.include_router(jobs.router)
    return application


app = create_app()
