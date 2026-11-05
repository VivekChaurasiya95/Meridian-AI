"""Risk policy (V1, security.md section 11).

Turns normalized findings plus per-scanner outcomes into an
assessment status. Scanner failures are never hidden behind low
findings, and `no findings` never becomes `safe` — the status says
what was checked, not what is proven.
"""

from __future__ import annotations

from .models.finding import NormalizedFinding
from .models.report import AssessmentSummary, ScannerOutcome


def evaluate(
    findings: list[NormalizedFinding], scanners: dict[str, ScannerOutcome]
) -> tuple[str, AssessmentSummary]:
    """Return (status, summary) for one finished preflight run."""
    summary = AssessmentSummary(scanners=dict(scanners))
    for finding in findings:
        summary.by_severity[finding.severity] = (
            summary.by_severity.get(finding.severity, 0) + 1
        )
    summary.total = len(findings)
    statuses = {outcome.status for outcome in scanners.values()}
    if "cancelled" in statuses and "completed" not in statuses:
        return "cancelled", summary
    if statuses and statuses <= {"failed"}:
        return "failed", summary
    if "failed" in statuses and "completed" in statuses:
        return "partial", summary
    if summary.by_severity.get("critical", 0) or summary.by_severity.get("high", 0):
        return "review_required", summary
    return "completed", summary
