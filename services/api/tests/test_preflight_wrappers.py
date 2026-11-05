"""Scanner wrapper tests (V1): exit semantics and output contracts.

Pure tests: no database, no daemon. Exit-code handling follows the
documented upstream contracts (D63): Semgrep exits 0 on completion
regardless of findings; Gitleaks exits 0 clean / 1 leaks found.
"""

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "services" / "worker"))

from security.scanners import gitleaks, semgrep
from security.scanners.base import ScannerFailure


def _semgrep_doc(results=None, errors=None, version="1.183.0", scanned=None):
    return json.dumps(
        {
            "version": version,
            "results": results if results is not None else [],
            "errors": errors if errors is not None else [],
            "paths": {"scanned": scanned if scanned is not None else ["a.py"]},
        }
    ).encode()


def _sem_result(**over):
    base = {
        "check_id": "meridian-python-eval-exec",
        "path": "a.py",
        "start": {"line": 3, "col": 1},
        "end": {"line": 3, "col": 9},
        "extra": {"message": "no eval", "severity": "ERROR", "lines": "eval(x)"},
    }
    base.update(over)
    return base


def test_semgrep_findings_parse() -> None:
    result = semgrep.parse(0, _semgrep_doc([_sem_result()]), b"", truncated=False)
    assert result.scanner == "semgrep"
    assert len(result.findings) == 1
    assert result.version == "1.183.0"
    assert result.files_scanned == 1
    assert result.errors_count == 0


def test_semgrep_empty_results_is_clean_completion() -> None:
    result = semgrep.parse(0, _semgrep_doc([]), b"", truncated=False)
    assert result.findings == []
    assert result.errors_count == 0


def test_semgrep_errors_counted_not_failed() -> None:
    result = semgrep.parse(
        0, _semgrep_doc([], [{"code": 1}]), b"", truncated=False
    )
    assert result.errors_count == 1


def test_semgrep_nonzero_exit_fails() -> None:
    with pytest.raises(ScannerFailure) as exc:
        semgrep.parse(2, _semgrep_doc([]), b"boom", truncated=False)
    assert exc.value.code == "SEMGREP_FAILED"
    assert not exc.value.retryable


def test_semgrep_oom_is_retryable() -> None:
    with pytest.raises(ScannerFailure) as exc:
        semgrep.parse(137, b"", b"", truncated=False)
    assert exc.value.retryable


def test_semgrep_truncated_is_failure_not_clean() -> None:
    with pytest.raises(ScannerFailure) as exc:
        semgrep.parse(0, _semgrep_doc([]), b"", truncated=True)
    assert exc.value.code == "SCANNER_OUTPUT_TRUNCATED"


def test_semgrep_bad_json_fails() -> None:
    with pytest.raises(ScannerFailure) as exc:
        semgrep.parse(0, b"{nope", b"", truncated=False)
    assert exc.value.code == "SEMGREP_BAD_OUTPUT"


def test_semgrep_missing_results_fails() -> None:
    with pytest.raises(ScannerFailure) as exc:
        semgrep.parse(0, json.dumps({"version": "x"}).encode(), b"", truncated=False)
    assert exc.value.code == "SEMGREP_BAD_OUTPUT"


def test_semgrep_empty_stdout_fails() -> None:
    with pytest.raises(ScannerFailure) as exc:
        semgrep.parse(0, b"  \n ", b"", truncated=False)
    assert exc.value.code == "SEMGREP_EMPTY_OUTPUT"


def test_semgrep_malformed_entry_fails() -> None:
    with pytest.raises(ScannerFailure) as exc:
        semgrep.parse(0, _semgrep_doc(["nope"]), b"", truncated=False)
    assert exc.value.code == "SEMGREP_BAD_OUTPUT"


def _leak(**over):
    base = {
        "RuleID": "aws-access-key",
        "Description": "AWS key",
        "StartLine": 1,
        "EndLine": 1,
        "File": "/work/.env",
        "Secret": "REDACTED",
        "Match": "key=REDACTED",
        "Fingerprint": "fp",
        "Entropy": 3.5,
    }
    base.update(over)
    return base


def test_gitleaks_exit0_empty_array_is_clean() -> None:
    result = gitleaks.parse(0, b"[]", b"", truncated=False)
    assert result.findings == []


def test_gitleaks_exit0_null_and_blank_are_clean() -> None:
    assert gitleaks.parse(0, b"null", b"", truncated=False).findings == []
    assert gitleaks.parse(0, b"  \n", b"", truncated=False).findings == []


def test_gitleaks_exit1_findings_parse() -> None:
    body = json.dumps([_leak()]).encode()
    result = gitleaks.parse(1, body, b"", truncated=False)
    assert len(result.findings) == 1
    assert result.exit_code == 1


def test_gitleaks_exit1_empty_is_contradictory() -> None:
    with pytest.raises(ScannerFailure) as exc:
        gitleaks.parse(1, b"[]", b"", truncated=False)
    assert exc.value.code == "GITLEAKS_CONTRADICTORY"


def test_gitleaks_exit0_findings_is_contradictory() -> None:
    body = json.dumps([_leak()]).encode()
    with pytest.raises(ScannerFailure) as exc:
        gitleaks.parse(0, body, b"", truncated=False)
    assert exc.value.code == "GITLEAKS_CONTRADICTORY"


def test_gitleaks_exit2_fails() -> None:
    with pytest.raises(ScannerFailure) as exc:
        gitleaks.parse(2, b"", b"usage", truncated=False)
    assert exc.value.code == "GITLEAKS_FAILED"


def test_gitleaks_truncated_is_failure_not_clean() -> None:
    with pytest.raises(ScannerFailure) as exc:
        gitleaks.parse(0, b"[]", b"", truncated=True)
    assert exc.value.code == "SCANNER_OUTPUT_TRUNCATED"


def test_gitleaks_bad_json_fails() -> None:
    with pytest.raises(ScannerFailure) as exc:
        gitleaks.parse(1, b"[oops", b"", truncated=False)
    assert exc.value.code == "GITLEAKS_BAD_OUTPUT"


def test_gitleaks_non_array_fails() -> None:
    with pytest.raises(ScannerFailure) as exc:
        gitleaks.parse(1, b'{"a": 1}', b"", truncated=False)
    assert exc.value.code == "GITLEAKS_BAD_OUTPUT"
