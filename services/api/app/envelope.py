"""API envelope helpers and typed application errors (API.md §4.1–§4.2)."""

import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi.responses import JSONResponse

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9_.\-]{1,64}")


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex[:26]}"


def normalize_request_id(value: str | None) -> str:
    """Honor a sane client-provided ID; otherwise generate one."""
    if value and _REQUEST_ID_PATTERN.fullmatch(value):
        return value
    return new_request_id()


def ok(data: Any, request_id: str, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"data": data, "request_id": request_id},
        headers={REQUEST_ID_HEADER: request_id},
    )


def paged(
    items: list[Any], limit: int, next_cursor: str | None, request_id: str
) -> JSONResponse:
    return JSONResponse(
        status_code=200,
        content={
            "data": items,
            "page": {"limit": limit, "next_cursor": next_cursor},
            "request_id": request_id,
        },
        headers={REQUEST_ID_HEADER: request_id},
    )


@dataclass
class ApiError(Exception):
    """Typed application error rendered as the §4.2 problem envelope."""

    status_code: int
    code: str
    message: str
    details: list[dict[str, str]] = field(default_factory=list)

    def response(self, request_id: str) -> JSONResponse:
        return JSONResponse(
            status_code=self.status_code,
            content={
                "error": {
                    "code": self.code,
                    "message": self.message,
                    "details": self.details,
                },
                "request_id": request_id,
            },
            headers={REQUEST_ID_HEADER: request_id},
        )


def not_found(resource: str = "resource") -> ApiError:
    # 404 doubles as "hidden": existence of unauthorized resources is not leaked.
    return ApiError(404, "RESOURCE_NOT_FOUND", f"The requested {resource} was not found.")


def access_denied() -> ApiError:
    return ApiError(403, "ACCESS_DENIED", "The caller lacks permission for this action.")
