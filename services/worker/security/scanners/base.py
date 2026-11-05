"""Shared scanner-result shape (V1).

Wrappers turn (exit code, stdout, stderr, truncated) into a result or
raise ``ScannerFailure``. Failure messages carry fixed codes and
counts only — never scanner output, which may hold secrets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SEMGREP = "semgrep"
GITLEAKS = "gitleaks"


class ScannerFailure(Exception):
    """Operational scan failure (not a finding). Fail-closed by default."""

    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


@dataclass
class ScannerResult:
    scanner: str
    findings: list[dict[str, Any]] = field(default_factory=list)
    version: str | None = None
    files_scanned: int | None = None
    errors_count: int = 0
    exit_code: int = 0


def check_truncated(scanner: str, truncated: bool) -> None:
    """Truncated JSON cannot be trusted: loud failure, never clean."""
    if truncated:
        raise ScannerFailure(
            "SCANNER_OUTPUT_TRUNCATED",
            f"The {scanner} output exceeded its cap and cannot be trusted.",
        )
