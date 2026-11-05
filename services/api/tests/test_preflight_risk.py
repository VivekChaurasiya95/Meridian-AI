"""Risk policy tests (V1): status matrix and honest summaries.

Pure tests. Scanner failures are never hidden behind low findings,
and `no findings` never becomes `safe`.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "services" / "worker"))

from security.models.finding import NormalizedFinding
from security.models.report import ScannerOutcome
from security.risk_policy import evaluate


def _finding(severity: str) -> NormalizedFinding:
    return NormalizedFinding(
        id="f" * 32,
        scanner="semgrep",
        rule_id="r",
        category="general",
        severity=severity,
        confidence="high",
        title="t",
        description="d",
        path="a.py",
        start_line=1,
        end_line=1,
        excerpt="",
        excerpt_truncated=False,
        redacted=False,
        fingerprint="fp",
    )


def _ok(scanner: str) -> ScannerOutcome:
    return ScannerOutcome(scanner=scanner, status="completed", findings=1)


def _failed(scanner: str) -> ScannerOutcome:
    return ScannerOutcome(scanner=scanner, status="failed", error_code="X")


def test_no_findings_completes_not_safe_claim() -> None:
    status, summary = evaluate(
        [], {"semgrep": _ok("semgrep"), "gitleaks": _ok("gitleaks")}
    )
    assert status == "completed"
    assert summary.total == 0
    assert summary.by_severity["high"] == 0


def test_low_and_medium_complete() -> None:
    status, _ = evaluate(
        [_finding("low"), _finding("medium")], {"semgrep": _ok("semgrep")}
    )
    assert status == "completed"


def test_high_requires_review() -> None:
    status, summary = evaluate([_finding("high")], {"semgrep": _ok("semgrep")})
    assert status == "review_required"
    assert summary.by_severity["high"] == 1


def test_critical_requires_review() -> None:
    status, _ = evaluate([_finding("critical")], {"gitleaks": _ok("gitleaks")})
    assert status == "review_required"


def test_one_scanner_failed_is_partial() -> None:
    status, summary = evaluate(
        [_finding("low")],
        {"semgrep": _ok("semgrep"), "gitleaks": _failed("gitleaks")},
    )
    assert status == "partial"
    assert summary.to_json()["scanners"]["gitleaks"]["status"] == "failed"


def test_all_scanners_failed_is_failed() -> None:
    status, _ = evaluate(
        [], {"semgrep": _failed("semgrep"), "gitleaks": _failed("gitleaks")}
    )
    assert status == "failed"


def test_failure_beats_low_findings() -> None:
    status, _ = evaluate(
        [_finding("low")], {"semgrep": _failed("semgrep")}
    )
    assert status == "failed"


def test_cancelled_without_completion() -> None:
    outcome = ScannerOutcome(scanner="semgrep", status="cancelled")
    status, _ = evaluate([], {"semgrep": outcome})
    assert status == "cancelled"


def test_summary_versions_shape() -> None:
    outcome = ScannerOutcome(scanner="semgrep", status="completed", version="1.183.0")
    _, summary = evaluate([], {"semgrep": outcome})
    assert summary.versions_json() == {"semgrep": "1.183.0"}
    assert summary.to_json()["scanners"]["semgrep"]["findings"] == 0
