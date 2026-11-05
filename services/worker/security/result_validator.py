"""Untrusted scanner-output validation (V1).

Scanner stdout is untrusted input: findings carry repository-controlled
paths, line numbers, and (for secret scanners) credential material.
Every value is validated before normalization, and secret values are
masked before persistence. Error messages never echo secrets.
"""

from __future__ import annotations

import posixpath

MAX_PATH_CHARS = 1024
MAX_EXCERPT_CHARS = 2000
MAX_TEXT_CHARS = 4000


class FindingValidationError(Exception):
    """One finding is malformed. ``code`` is fixed; ``message`` is safe."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _check_str(value: object, field: str, max_chars: int) -> str:
    if not isinstance(value, str) or not value:
        raise FindingValidationError(
            "INVALID_FIELD", f"The finding {field} must be a non-empty string."
        )
    if len(value) > max_chars:
        raise FindingValidationError(
            "FIELD_TOO_LONG", f"The finding {field} exceeds the length limit."
        )
    return value


def validate_rel_path(value: object) -> str:
    """Accept repository-relative posix paths only (no secrets echoed)."""
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        raise FindingValidationError("INVALID_PATH", "The finding path is not a relative path.")
    if value.startswith("/") or (len(value) > 1 and value[1] == ":"):
        raise FindingValidationError("INVALID_PATH", "The finding path must be repository-relative.")
    normalized = posixpath.normpath(value)
    parts = normalized.split("/")
    if normalized in ("", ".") or any(part in ("", ".", "..") for part in parts):
        raise FindingValidationError("INVALID_PATH", "The finding path escapes the repository root.")
    if len(normalized) > MAX_PATH_CHARS:
        raise FindingValidationError("INVALID_PATH", "The finding path is too long.")
    return normalized


def validate_lines(start: object, end: object) -> tuple[int, int]:
    """Line numbers are 1-based ints with end >= start."""
    if isinstance(start, bool) or isinstance(end, bool):
        raise FindingValidationError("INVALID_LINES", "Finding lines must be integers.")
    if not isinstance(start, int) or not isinstance(end, int):
        raise FindingValidationError("INVALID_LINES", "Finding lines must be integers.")
    if start < 1 or end < 1 or end < start:
        raise FindingValidationError("INVALID_LINES", "Finding lines are out of range.")
    return start, end


def truncate_excerpt(text: str) -> tuple[str, bool]:
    """Bound evidence length. Returns (text, truncated)."""
    if len(text) <= MAX_EXCERPT_CHARS:
        return text, False
    return text[:MAX_EXCERPT_CHARS] + "\n[... truncated ...]", True


def validate_text(value: object, field: str) -> str:
    """Short human-readable text (titles, descriptions)."""
    text = _check_str(value, field, MAX_TEXT_CHARS)
    return text.replace("\x00", "")


def mask_secret(value: object, rule_id: str) -> str:
    """Detector-aware masking. Never returns usable credential material.

    Private-key material is fully withheld; short values collapse to a
    marker; longer values keep a small prefix/suffix so the operator
    can locate the finding without recovering the secret.
    """
    if not isinstance(value, str) or not value:
        return "***"
    if value == "REDACTED":
        return value
    lowered_rule = rule_id.lower()
    if "private-key" in lowered_rule or "PRIVATE KEY" in value:
        return "[private key material redacted]"
    compact = value if len(value) <= 64 else value[:64]
    if len(compact) <= 12:
        return "***"
    return f"{compact[:4]}****{compact[-2:]}"
