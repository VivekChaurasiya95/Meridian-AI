"""Assessment summary shaping (V1).

The summary column carries counts and per-scanner outcomes only —
counts, versions, and fixed codes. Raw output and secrets never land
here; full findings live in ``security_findings``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .finding import SEVERITIES


@dataclass(frozen=True)
class ScannerOutcome:
    scanner: str
    status: str  # completed | failed | skipped | cancelled
    findings: int = 0
    files_scanned: int | None = None
    error_code: str | None = None
    version: str | None = None


@dataclass
class AssessmentSummary:
    by_severity: dict[str, int] = field(default_factory=lambda: {sev: 0 for sev in SEVERITIES})
    total: int = 0
    persisted: int = 0
    dropped: int = 0
    skipped_malformed: int = 0
    scanners: dict[str, ScannerOutcome] = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "by_severity": dict(self.by_severity),
            "total": self.total,
            "persisted": self.persisted,
            "dropped": self.dropped,
            "skipped_malformed": self.skipped_malformed,
            "scanners": {
                name: {
                    "status": outcome.status,
                    "findings": outcome.findings,
                    "files_scanned": outcome.files_scanned,
                    "error_code": outcome.error_code,
                }
                for name, outcome in self.scanners.items()
            },
        }

    def versions_json(self) -> dict:
        return {
            name: outcome.version
            for name, outcome in self.scanners.items()
            if outcome.version
        }
