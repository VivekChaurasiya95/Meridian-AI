"""Repository-relative path validation (M8): pure, shared.

Test file paths, patch targets, and any future repo-relative input go
through :func:`check_repo_path`. Normalized, relative, bounded, never
under reserved roots — anything else fails closed.
"""

import posixpath

from app.envelope import ApiError

PATH_MAX = 500
RESERVED_ROOTS = ("Meridian.rules/", ".git/")


def check_repo_path(value: object, what: str) -> str:
    """Validate one repo-relative path; return its normalized form."""
    if not isinstance(value, str):
        raise ApiError(422, "VALIDATION_ERROR", f"{what} must be a string.")
    if not 1 <= len(value) <= PATH_MAX:
        raise ApiError(422, "VALIDATION_ERROR", f"{what} is missing or too long.")
    if "\x00" in value:
        raise ApiError(422, "VALIDATION_ERROR", f"{what} is invalid.")
    if value.startswith("/") or value.startswith("\\"):
        raise ApiError(422, "VALIDATION_ERROR", f"{what} must be relative.")
    normalized = posixpath.normpath(value.replace("\\", "/"))
    if normalized in (".", "") or normalized.startswith("../") or "/../" in f"/{normalized}/":
        raise ApiError(422, "VALIDATION_ERROR", f"{what} escapes the repository.")
    for root in RESERVED_ROOTS:
        if normalized == root.rstrip("/") or normalized.startswith(root):
            raise ApiError(422, "VALIDATION_ERROR", f"{what} targets a reserved path.")
    return normalized
