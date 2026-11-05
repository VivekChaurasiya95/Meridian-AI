"""Evidence pure-helper tests (M6): no database needed."""

from app.services.evidence import redact_json_bytes, sniff_mime


def test_sniff_mime() -> None:
    assert sniff_mime(b"\x89PNG\r\n\x1a\nrest") == "image/png"
    assert sniff_mime(b"\xff\xd8\xffrest") == "image/jpeg"
    assert sniff_mime(b"PK\x03\x04rest") == "application/zip"
    assert sniff_mime(b'{"a": 1}') == "application/json"
    assert sniff_mime(b"  [1, 2]\n") == "application/json"
    assert sniff_mime(b"console output line\n") == "text/plain"
    assert sniff_mime(b"\x00\x01binary\xff") == "application/octet-stream"
    assert sniff_mime(b"{oops") == "text/plain"


def test_redact_json_bytes_redacts_nested_strings() -> None:
    data = b'{"url": "https://x/?token=abc", "items": [{"k": "password=hunter2"}], "n": 3}'
    redacted, changed = redact_json_bytes(data)
    assert changed is True
    assert b"hunter2" not in redacted
    assert b"[REDACTED]" in redacted
    assert b'"n":3' in redacted


def test_redact_json_bytes_fails_closed_on_invalid_input() -> None:
    data = b"\x00\x01not-json"
    assert redact_json_bytes(data) == (data, False)
