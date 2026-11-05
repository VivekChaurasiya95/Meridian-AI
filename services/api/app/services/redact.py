"""Secret redaction for untrusted text (M5 hardening).

Execution output, error messages, and other untrusted strings pass through
:func:`redact_text` before persistence or API responses, so leaked
credentials in repository output cannot accumulate in database rows, logs,
or job results.

Classification is meaning-based, not an enumeration of token brands: any
``name: value`` / ``name = value`` pair whose name contains a credential
word (secret, password, token, api key, auth, …) has its value redacted,
whatever the surrounding format. Known high-entropy token shapes (cloud
keys, provider prefixes, PEM blocks, URL passwords) are redacted wherever
they appear, even without a credential name nearby.
"""

from __future__ import annotations

import re

REPLACEMENT = "[REDACTED]"

# A credential-looking assignment key contains one of these words anywhere
# in the name (covers api_key, apiKey, API-KEY, client_secret, authToken…).
_CREDENTIAL_WORDS = (
    r"secret|password|passwd|pwd|token|api[_-]?key|access[_-]?key|auth|credential|private[_-]?key"
)

_ASSIGNMENT_RE = re.compile(
    rf"(?i)(['\"]?[\w.\-]*({_CREDENTIAL_WORDS})[\w.\-]*['\"]?\s*[:=]\s*)(['\"]?)([^\s'\"]+)"
)

_BEARER_RE = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9\-._~+/=]{8,}")

_URL_PASSWORD_RE = re.compile(r"(?i)(\b[a-z][a-z0-9+.\-]*://[^/\s:@]+:)([^/\s@]+)(@)")

_PEM_BLOCK_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----"
)

_AWS_KEY_RE = re.compile(r"\bAKIA[0-9A-Z]{16}\b")


_PROVIDER_TOKEN_RE = re.compile(
    r"\b(?:gh[pousr]_|github_pat_|gho_|xox[baprs]-|sk-(?:live|test)-|sk-)[A-Za-z0-9_\-]{16,}"
)


def redact_text(value: str | None) -> str | None:
    """Redact credential-shaped values. ``None`` passes through as ``None``."""
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    redacted = _PEM_BLOCK_RE.sub(REPLACEMENT, value)
    # Bearer first: `Authorization: Bearer <tok>` must redact the token, not
    # just the `Bearer` prefix the assignment rule would otherwise consume.
    redacted = _BEARER_RE.sub(rf"\1{REPLACEMENT}", redacted)

    def _redact_assignment(match: re.Match[str]) -> str:
        # `Bearer` alone is a scheme marker, not a secret: the bearer rule
        # above already redacted the token that follows it.
        if match.group(4).lower() == "bearer":
            return match.group(0)
        return f"{match.group(1)}{match.group(3)}{REPLACEMENT}"

    redacted = _ASSIGNMENT_RE.sub(_redact_assignment, redacted)
    redacted = _URL_PASSWORD_RE.sub(rf"\1{REPLACEMENT}\3", redacted)
    redacted = _AWS_KEY_RE.sub(REPLACEMENT, redacted)
    redacted = _PROVIDER_TOKEN_RE.sub(REPLACEMENT, redacted)
    return redacted
