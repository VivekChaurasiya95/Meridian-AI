"""Semgrep CE wrapper (V1, D63).

Contract (upstream docs): ``semgrep scan --json`` prints the result
document to stdout and exits 0 whenever the scan completes, whether
or not findings exist. Any nonzero exit, empty output, or malformed
JSON is an operational failure. Per-file scan ``errors`` are counted
but do not fail the scan on their own.
"""

from __future__ import annotations

import json
from typing import Any

from .base import SEMGREP, ScannerFailure, ScannerResult, check_truncated


def parse(
    exit_code: int,
    stdout: bytes,
    stderr: bytes,
    *,
    truncated: bool,
) -> ScannerResult:
    """Parse one Semgrep container result. Raises ``ScannerFailure``."""
    del stderr  # Diagnostics only; findings and errors come from stdout JSON.
    check_truncated(SEMGREP, truncated)
    if exit_code != 0:
        raise ScannerFailure(
            "SEMGREP_FAILED",
            f"Semgrep exited with code {exit_code}.",
            retryable=exit_code == 137,
        )
    text = stdout.decode("utf-8", errors="replace").strip()
    if not text:
        raise ScannerFailure("SEMGREP_EMPTY_OUTPUT", "Semgrep produced no output.")
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        raise ScannerFailure(
            "SEMGREP_BAD_OUTPUT", "Semgrep output is not valid JSON."
        ) from None
    if not isinstance(document, dict) or not isinstance(document.get("results"), list):
        raise ScannerFailure(
            "SEMGREP_BAD_OUTPUT", "Semgrep output has no results list."
        )
    results = document["results"]
    for item in results:
        if not isinstance(item, dict):
            raise ScannerFailure(
                "SEMGREP_BAD_OUTPUT", "Semgrep results hold a malformed entry."
            )
    errors = document.get("errors", [])
    if not isinstance(errors, list):
        raise ScannerFailure(
            "SEMGREP_BAD_OUTPUT", "Semgrep errors field is malformed."
        )
    version = document.get("version")
    files_scanned: int | None = None
    paths = document.get("paths")
    if isinstance(paths, dict) and isinstance(paths.get("scanned"), list):
        files_scanned = len(paths["scanned"])
    return ScannerResult(
        scanner=SEMGREP,
        findings=list(results),
        version=str(version) if isinstance(version, str) and version else None,
        files_scanned=files_scanned,
        errors_count=len(errors),
        exit_code=exit_code,
    )


def findings_of(result: ScannerResult) -> list[dict[str, Any]]:
    return result.findings
