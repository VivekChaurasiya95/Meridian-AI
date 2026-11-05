"""Normalized finding schema (V1, security.md section 9).

One scanner-independent shape for persistence and API responses.
Fingerprints derive from scanner, rule, and location only — never
from secret values, so equal findings dedup without leaking.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

SEVERITIES = ("critical", "high", "medium", "low", "informational")
CONFIDENCES = ("high", "medium", "low")
SCANNERS = ("semgrep", "gitleaks")


@dataclass(frozen=True)
class NormalizedFinding:
    id: str
    scanner: str
    rule_id: str
    category: str
    severity: str
    confidence: str
    title: str
    description: str
    path: str
    start_line: int
    end_line: int
    excerpt: str
    excerpt_truncated: bool
    redacted: bool
    fingerprint: str


def fingerprint_of(
    scanner: str, rule_id: str, path: str, start_line: int, end_line: int
) -> str:
    """Stable dedup identity. Inputs are validated upstream; no secrets."""
    joined = "\0".join((scanner, rule_id, path, str(start_line), str(end_line)))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def new_finding_id() -> str:
    return uuid.uuid4().hex


def to_record(finding: NormalizedFinding, assessment_id: uuid.UUID) -> dict:
    """Map onto ``security_findings`` columns (location/evidence JSONB)."""
    return {
        "id": uuid.UUID(hex=finding.id),
        "assessment_id": assessment_id,
        "fingerprint": finding.fingerprint,
        "scanner": finding.scanner,
        "rule_id": finding.rule_id,
        "severity": finding.severity,
        "confidence": finding.confidence,
        "category": finding.category,
        "title": finding.title,
        "description": finding.description,
        "location": {
            "path": finding.path,
            "start_line": finding.start_line,
            "end_line": finding.end_line,
        },
        "evidence": {
            "excerpt": finding.excerpt,
            "redacted": finding.redacted,
            "truncated": finding.excerpt_truncated,
        },
    }
