"""Finding normalizer (V1, security.md section 9).

Maps scanner-native findings onto ``NormalizedFinding``. Malformed
single findings raise ``FindingValidationError`` (the orchestrator
skips and counts them); secrets are masked before they can persist.
"""

from __future__ import annotations

from typing import Any

from .models.finding import NormalizedFinding, fingerprint_of, new_finding_id
from .result_validator import (
    FindingValidationError,
    mask_secret,
    truncate_excerpt,
    validate_lines,
    validate_rel_path,
    validate_text,
)

SCAN_ROOT = "/work"

SEMGREP_SEVERITY = {"INFO": "informational", "WARNING": "medium", "ERROR": "high"}
SEMGREP_CONFIDENCE = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}


def _rule_id(value: object, fallback: str) -> str:
    if isinstance(value, str) and value and len(value) <= 256:
        return value
    if fallback:
        return fallback
    raise FindingValidationError("INVALID_RULE", "The finding rule id is missing.")


def strip_scan_root(value: object) -> str:
    """Relativize container-absolute scan paths, then validate.

    Scanners run with workdir/target ``/work``; findings may report
    ``/work/app.py`` or ``app.py`` depending on the tool. Anything that
    is not under the scan root (or relative already) is rejected.
    """
    if not isinstance(value, str) or not value:
        raise FindingValidationError("INVALID_PATH", "The finding path is missing.")
    if value == SCAN_ROOT or value == SCAN_ROOT + "/":
        raise FindingValidationError("INVALID_PATH", "The finding path is the scan root.")
    if value.startswith(SCAN_ROOT + "/"):
        return validate_rel_path(value[len(SCAN_ROOT) + 1 :])
    return validate_rel_path(value)


def _title_of(message: str, rule_id: str) -> str:
    first_line = message.splitlines()[0] if message.strip() else rule_id
    return first_line[:200] if len(first_line) > 200 else first_line


def normalize_semgrep(raw: dict[str, Any]) -> NormalizedFinding:
    """Normalize one Semgrep result entry."""
    rule_id = _rule_id(raw.get("check_id"), "")
    path = strip_scan_root(raw.get("path"))
    start = raw.get("start") if isinstance(raw.get("start"), dict) else {}
    end = raw.get("end") if isinstance(raw.get("end"), dict) else {}
    start_line, end_line = validate_lines(start.get("line"), end.get("line"))
    extra = raw.get("extra")
    if not isinstance(extra, dict):
        raise FindingValidationError("INVALID_FIELD", "The Semgrep extra block is malformed.")
    message = extra.get("message") if isinstance(extra.get("message"), str) else ""
    severity = SEMGREP_SEVERITY.get(str(extra.get("severity", "")).upper(), "medium")
    metadata = extra.get("metadata") if isinstance(extra.get("metadata"), dict) else {}
    confidence = SEMGREP_CONFIDENCE.get(
        str(metadata.get("confidence", "")).upper(), "medium"
    )
    category = metadata.get("category") if isinstance(metadata.get("category"), str) else ""
    category = category[:64] if category else "general"
    lines = extra.get("lines") if isinstance(extra.get("lines"), str) else ""
    credential_rule = category == "credentials" or "secret" in rule_id.lower()
    if credential_rule:
        excerpt, truncated = truncate_excerpt(mask_secret(lines, rule_id))
        redacted = True
    else:
        excerpt, truncated = truncate_excerpt(lines)
        redacted = False
    title = validate_text(_title_of(message, rule_id), "title")
    description = validate_text(message or rule_id, "description")
    finding_id = new_finding_id()
    return NormalizedFinding(
        id=finding_id,
        scanner="semgrep",
        rule_id=rule_id,
        category=category,
        severity=severity,
        confidence=confidence,
        title=title,
        description=description,
        path=path,
        start_line=start_line,
        end_line=end_line,
        excerpt=excerpt,
        excerpt_truncated=truncated,
        redacted=redacted,
        fingerprint=fingerprint_of("semgrep", rule_id, path, start_line, end_line),
    )


def _gitleaks_severity(rule_id: str) -> str:
    if "private-key" in rule_id.lower():
        return "critical"
    return "high"


def normalize_gitleaks(raw: dict[str, Any]) -> NormalizedFinding:
    """Normalize one Gitleaks report entry. Evidence is always masked."""
    rule_id = _rule_id(raw.get("RuleID"), "")
    path = strip_scan_root(raw.get("File"))
    start_line, end_line = validate_lines(raw.get("StartLine"), raw.get("EndLine"))
    description_raw = raw.get("Description")
    description_text = description_raw if isinstance(description_raw, str) else ""
    secret = raw.get("Secret")
    match = raw.get("Match")
    secret_text = secret if isinstance(secret, str) and secret else ""
    if not secret_text and isinstance(match, str):
        secret_text = match
    excerpt, truncated = truncate_excerpt(mask_secret(secret_text, rule_id))
    title = validate_text(_title_of(description_text, rule_id), "title")
    description = validate_text(description_text or rule_id, "description")
    finding_id = new_finding_id()
    return NormalizedFinding(
        id=finding_id,
        scanner="gitleaks",
        rule_id=rule_id,
        category="credentials",
        severity=_gitleaks_severity(rule_id),
        confidence="high",
        title=title,
        description=description,
        path=path,
        start_line=start_line,
        end_line=end_line,
        excerpt=excerpt,
        excerpt_truncated=truncated,
        redacted=True,
        fingerprint=fingerprint_of("gitleaks", rule_id, path, start_line, end_line),
    )
