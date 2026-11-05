"""Normalizer and validator tests (V1): mapping, paths, redaction.

Pure tests. Secret values in fixtures are synthetic and masked; tests
assert masked values never round-trip into normalized findings.
"""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "services" / "worker"))

from security import normalizer
from security.models.finding import fingerprint_of
from security.result_validator import (
    FindingValidationError,
    mask_secret,
    truncate_excerpt,
    validate_lines,
    validate_rel_path,
    validate_text,
)


def test_validate_rel_path_accepts_nested() -> None:
    assert validate_rel_path("src/app.py") == "src/app.py"
    assert validate_rel_path("a/./b.py") == "a/b.py"


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "/abs.py",
        "C:/x.py",
        "../up.py",
        "a/../../up.py",
        "a\\b.py",
        "a\x00b",
        ".",
        "a/" + "x" * 2000 + ".py",
        None,
        42,
    ],
)
def test_validate_rel_path_rejects(bad) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(FindingValidationError):
        validate_rel_path(bad)


def test_validate_lines_ok_and_bad() -> None:
    assert validate_lines(2, 5) == (2, 5)
    for start, end in [(0, 1), (1, 0), (5, 2), (True, 2), ("1", 2), (1.0, 2)]:
        with pytest.raises(FindingValidationError):
            validate_lines(start, end)


def test_truncate_excerpt_bounds() -> None:
    text, cut = truncate_excerpt("small")
    assert (text, cut) == ("small", False)
    big = "x" * 5000
    text, cut = truncate_excerpt(big)
    assert cut and len(text) < len(big) and "truncated" in text


def test_validate_text_rejects_empty_and_nul() -> None:
    with pytest.raises(FindingValidationError):
        validate_text("", "title")
    with pytest.raises(FindingValidationError):
        validate_text(None, "title")
    assert validate_text("a\x00b", "title") == "ab"


def test_mask_secret_private_key_fully_withheld() -> None:
    assert mask_secret("anything", "private-key-rule") == "[private key material redacted]"
    assert (
        mask_secret("-----BEGIN PRIVATE KEY-----\nabc", "generic")
        == "[private key material redacted]"
    )


def test_mask_secret_short_and_empty() -> None:
    assert mask_secret("", "x") == "***"
    assert mask_secret(None, "x") == "***"
    assert mask_secret("short", "x") == "***"


def test_mask_secret_long_keeps_only_prefix_suffix() -> None:
    masked = mask_secret("sk_live_ABCDEFGH12345678", "stripe-key")
    assert masked.startswith("sk_l")
    assert masked.endswith("78")
    assert "ABCDEFGH123456" not in masked


def test_mask_secret_redacted_passthrough() -> None:
    assert mask_secret("REDACTED", "x") == "REDACTED"


def test_strip_scan_root() -> None:
    assert normalizer.strip_scan_root("/work/src/a.py") == "src/a.py"
    assert normalizer.strip_scan_root("src/a.py") == "src/a.py"
    for bad in ("/work", "/work/", "/etc/passwd", "", None):
        with pytest.raises(FindingValidationError):
            normalizer.strip_scan_root(bad)


def _sem_raw(**over):  # type: ignore[no-untyped-def]
    base = {
        "check_id": "meridian-python-eval-exec",
        "path": "/work/src/a.py",
        "start": {"line": 3, "col": 1},
        "end": {"line": 3, "col": 9},
        "extra": {
            "message": "no eval",
            "severity": "ERROR",
            "lines": "eval(user_input)",
            "metadata": {"category": "code-execution", "confidence": "HIGH"},
        },
    }
    base.update(over)
    return base


def test_normalize_semgrep_full_mapping() -> None:
    finding = normalizer.normalize_semgrep(_sem_raw())
    assert finding.scanner == "semgrep"
    assert finding.rule_id == "meridian-python-eval-exec"
    assert finding.path == "src/a.py"
    assert (finding.start_line, finding.end_line) == (3, 3)
    assert finding.severity == "high"
    assert finding.confidence == "high"
    assert finding.category == "code-execution"
    assert finding.title == "no eval"
    assert finding.excerpt == "eval(user_input)"
    assert finding.redacted is False
    assert finding.fingerprint == fingerprint_of(
        "semgrep", "meridian-python-eval-exec", "src/a.py", 3, 3
    )


@pytest.mark.parametrize(
    "native,expected",
    [("ERROR", "high"), ("error", "high"), ("WARNING", "medium"), ("INFO", "informational")],
)
def test_normalize_semgrep_severity_map(native: str, expected: str) -> None:
    raw = _sem_raw(extra={"message": "m", "severity": native, "lines": ""})
    assert normalizer.normalize_semgrep(raw).severity == expected


def test_normalize_semgrep_unknown_severity_falls_back_medium() -> None:
    raw = _sem_raw(extra={"message": "m", "severity": "CRITICAL", "lines": ""})
    assert normalizer.normalize_semgrep(raw).severity == "medium"


def test_normalize_semgrep_credential_rule_masks_excerpt() -> None:
    raw = _sem_raw(
        check_id="creds-rule",
        extra={
            "message": "m",
            "severity": "ERROR",
            "lines": "password = 's3cr3t-value-123'",
            "metadata": {"category": "credentials"},
        },
    )
    finding = normalizer.normalize_semgrep(raw)
    assert finding.redacted is True
    assert "s3cr3t-value-123" not in finding.excerpt


def test_normalize_semgrep_malformed_rejected() -> None:
    with pytest.raises(FindingValidationError):
        normalizer.normalize_semgrep(_sem_raw(path="/etc/passwd"))
    with pytest.raises(FindingValidationError):
        normalizer.normalize_semgrep(_sem_raw(start={"line": 0}))
    with pytest.raises(FindingValidationError):
        normalizer.normalize_semgrep(_sem_raw(extra="nope"))
    with pytest.raises(FindingValidationError):
        normalizer.normalize_semgrep(_sem_raw(check_id=""))


def _leak_raw(**over):  # type: ignore[no-untyped-def]
    base = {
        "RuleID": "aws-access-key",
        "Description": "AWS access key",
        "StartLine": 4,
        "EndLine": 4,
        "File": "/work/.env",
        "Secret": "AKIAIOSFODNN7EXAMPLE",
        "Match": "key=AKIAIOSFODNN7EXAMPLE",
        "Fingerprint": "upstream-fp",
    }
    base.update(over)
    return base


def test_normalize_gitleaks_masks_and_maps() -> None:
    finding = normalizer.normalize_gitleaks(_leak_raw())
    assert finding.scanner == "gitleaks"
    assert finding.rule_id == "aws-access-key"
    assert finding.path == ".env"
    assert (finding.start_line, finding.end_line) == (4, 4)
    assert finding.severity == "high"
    assert finding.confidence == "high"
    assert finding.category == "credentials"
    assert finding.redacted is True
    assert "AKIAIOSFODNN7EXAMPLE" not in finding.excerpt
    assert "AKIAIOSFODNN7EXAMPLE" not in finding.title
    assert "AKIAIOSFODNN7EXAMPLE" not in finding.description


def test_normalize_gitleaks_private_key_is_critical() -> None:
    finding = normalizer.normalize_gitleaks(
        _leak_raw(RuleID="private-key", Secret="-----BEGIN RSA PRIVATE KEY-----\n...")
    )
    assert finding.severity == "critical"
    assert finding.excerpt == "[private key material redacted]"


def test_normalize_gitleaks_malformed_rejected() -> None:
    with pytest.raises(FindingValidationError):
        normalizer.normalize_gitleaks(_leak_raw(RuleID=""))
    with pytest.raises(FindingValidationError):
        normalizer.normalize_gitleaks(_leak_raw(File="/etc/shadow"))
    with pytest.raises(FindingValidationError):
        normalizer.normalize_gitleaks(_leak_raw(StartLine=0))


def test_fingerprint_stable_and_distinct() -> None:
    first = fingerprint_of("semgrep", "r", "a.py", 1, 2)
    assert first == fingerprint_of("semgrep", "r", "a.py", 1, 2)
    assert first != fingerprint_of("gitleaks", "r", "a.py", 1, 2)
    assert first != fingerprint_of("semgrep", "r", "a.py", 1, 3)
    assert len(first) == 64
