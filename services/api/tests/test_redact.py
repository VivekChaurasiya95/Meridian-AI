"""Secret-redaction tests (M5 hardening): pure, no database needed."""

from app.services.redact import REPLACEMENT, redact_text


def test_none_and_plain_text_pass_through() -> None:
    assert redact_text(None) is None
    assert redact_text("") == ""
    assert redact_text("meridian-sandbox-ok") == "meridian-sandbox-ok"
    # Credential words without a value assignment are prose, not secrets.
    assert redact_text("token expired, request a new password") == (
        "token expired, request a new password"
    )


def test_assignment_forms_redact_value_but_keep_name() -> None:
    assert redact_text("password=hunter2") == f"password={REPLACEMENT}"
    assert redact_text("password: hunter2") == f"password: {REPLACEMENT}"
    assert redact_text('"password": "hunter2"') == f'"password": "{REPLACEMENT}"'
    assert redact_text("api_key='AKIAIOSFODNN7EXAMPLE'") == f"api_key='{REPLACEMENT}'"


def test_unenumerated_credential_name_variant_still_redacted() -> None:
    # Meaning-based classification: any name containing a credential word.
    assert redact_text("clientApiSecret=abc123XYZ") == f"clientApiSecret={REPLACEMENT}"
    assert redact_text("X-Auth-Token: deadbeef") == f"X-Auth-Token: {REPLACEMENT}"


def test_bearer_and_url_password_redacted() -> None:
    assert redact_text("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9") == (
        f"Authorization: Bearer {REPLACEMENT}"
    )
    assert redact_text("postgres://meridian:s3cret@db:5432/meridian") == (
        f"postgres://meridian:{REPLACEMENT}@db:5432/meridian"
    )


def test_token_shapes_and_private_key_redacted() -> None:
    assert redact_text("key AKIAIOSFODNN7EXAMPLE here") == f"key {REPLACEMENT} here"
    assert redact_text("push with ghp_abcdefghij1234567890 now") == f"push with {REPLACEMENT} now"
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA7b\n-----END RSA PRIVATE KEY-----"
    assert redact_text(f"leaked:\n{pem}\ndone") == f"leaked:\n{REPLACEMENT}\ndone"


def test_redaction_is_idempotent() -> None:
    once = redact_text("password=hunter2 and AKIAIOSFODNN7EXAMPLE")
    assert once is not None
    assert redact_text(once) == once
