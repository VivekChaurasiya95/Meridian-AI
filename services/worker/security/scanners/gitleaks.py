"""Gitleaks wrapper (V1, D63).

Contract (upstream source + docs): ``gitleaks dir /work
--report-format json --report-path - --redact --exit-code 1`` prints a
JSON finding array to stdout (``-`` selects stdout). Exit 0 means no
leaks; exit 1 (the configured leak code) means leaks were found; any
other exit is an operational failure. An empty report parses as ``[]``
or ``null``; an exit code that contradicts the report is a failure,
never a clean bill.
"""

from __future__ import annotations

import json
from typing import Any

from .base import GITLEAKS, ScannerFailure, ScannerResult, check_truncated


def parse(
    exit_code: int,
    stdout: bytes,
    stderr: bytes,
    *,
    truncated: bool,
) -> ScannerResult:
    """Parse one Gitleaks container result. Raises ``ScannerFailure``."""
    del stderr  # Diagnostics only; the report arrives on stdout.
    check_truncated(GITLEAKS, truncated)
    if exit_code not in (0, 1):
        raise ScannerFailure(
            "GITLEAKS_FAILED",
            f"Gitleaks exited with code {exit_code}.",
            retryable=exit_code == 137,
        )
    text = stdout.decode("utf-8", errors="replace").strip()
    if not text or text == "null":
        findings: list[Any] = []
    else:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            raise ScannerFailure(
                "GITLEAKS_BAD_OUTPUT", "Gitleaks output is not valid JSON."
            ) from None
        if parsed is None:
            findings = []
        elif not isinstance(parsed, list):
            raise ScannerFailure(
                "GITLEAKS_BAD_OUTPUT", "Gitleaks output is not a finding array."
            )
        else:
            findings = parsed
    for item in findings:
        if not isinstance(item, dict):
            raise ScannerFailure(
                "GITLEAKS_BAD_OUTPUT", "Gitleaks results hold a malformed entry."
            )
    if exit_code == 0 and findings:
        raise ScannerFailure(
            "GITLEAKS_CONTRADICTORY",
            "Gitleaks exited clean but reported findings.",
        )
    if exit_code == 1 and not findings:
        raise ScannerFailure(
            "GITLEAKS_CONTRADICTORY",
            "Gitleaks signaled leaks but reported none.",
        )
    return ScannerResult(
        scanner=GITLEAKS,
        findings=list(findings),
        exit_code=exit_code,
    )


def findings_of(result: ScannerResult) -> list[dict[str, Any]]:
    return result.findings
