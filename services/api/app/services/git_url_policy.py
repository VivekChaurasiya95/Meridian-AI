"""Pure GitHub URL, ref, and resolved-address policy (Git import slice 1).

This module is the single grammar implementation used by the API (validate
only, no network) and by the trusted worker (re-validate before fetch).
It performs no I/O except through an injectable resolver, imports no
subprocess/git machinery, and never accepts credentials.

Policy (docs/GIT_IMPORT_DESIGN.md §8.1-§8.2): only canonical public
GitHub HTTPS URLs, full-length commit SHAs, conservative branch names,
and globally routable resolved addresses. Anything else fails closed.
"""

import ipaddress
import re
import socket
from dataclasses import dataclass

GITHUB_HOST = "github.com"

_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_REPO_RE = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$")
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


class GitUrlError(Exception):
    """Rejected Git input: ``code`` maps to the API error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class GitHubRepo:
    provider: str
    owner: str
    repo: str
    host: str
    canonical_url: str


def _invalid(message: str) -> GitUrlError:
    return GitUrlError("GIT_URL_INVALID", message)


def parse_github_url(raw: str) -> GitHubRepo:
    """Parse and normalize a public GitHub HTTPS repository URL."""
    if not isinstance(raw, str) or not raw.strip():
        raise _invalid("Enter a GitHub repository URL.")
    value = raw.strip()
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise _invalid("The repository URL is malformed.")
    # Reject scheme-less and non-URL transports before urlparse leniency.
    if "://" not in value:
        raise GitUrlError(
            "GIT_URL_UNSUPPORTED", "Only https://github.com repository URLs are supported."
        )
    scheme, rest = value.split("://", 1)
    if scheme.lower() != "https":
        raise GitUrlError(
            "GIT_URL_UNSUPPORTED", "Only https://github.com repository URLs are supported."
        )
    if "\\" in value or " " in value:
        raise _invalid("The repository URL is malformed.")
    if not value.isascii():
        raise _invalid("The repository URL is malformed.")
    if "?" in rest or "#" in rest:
        raise _invalid("The repository URL must not contain a query or fragment.")
    if "%" in rest:
        raise _invalid("The repository URL must not contain percent-encoding.")

    # Authority is everything before the first path slash.
    authority, _, path = rest.partition("/")
    if "@" in authority:
        raise GitUrlError(
            "GIT_CREDENTIALS_NOT_ALLOWED",
            "Credentials must not be embedded in the repository URL.",
        )
    if authority.startswith("["):
        raise GitUrlError(
            "GIT_HOST_NOT_ALLOWED", "Only github.com repositories are supported in this version."
        )
    if ":" in authority:
        host, _, port = authority.partition(":")
        if port != "443" or not port.isdigit():
            raise GitUrlError("GIT_URL_UNSUPPORTED", "Only the default HTTPS port is supported.")
    else:
        host = authority
    if host.lower() != GITHUB_HOST:
        raise GitUrlError(
            "GIT_HOST_NOT_ALLOWED", "Only github.com repositories are supported in this version."
        )
    if host != host.lower():
        host = host.lower()

    if not path:
        raise _invalid("The repository URL must include an owner and repository name.")
    trimmed = path[:-1] if path.endswith("/") else path
    if trimmed.endswith(".git"):
        trimmed = trimmed[:-4]
    parts = trimmed.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise _invalid("The repository URL must look like https://github.com/owner/repository.")
    owner, repo = parts
    if not _OWNER_RE.fullmatch(owner) or "--" in owner:
        raise _invalid("The repository owner is invalid.")
    if (
        not _REPO_RE.fullmatch(repo)
        or repo in (".", "..")
        or repo.startswith((".", "-"))
        or ".." in repo
    ):
        raise _invalid("The repository name is invalid.")
    return GitHubRepo(
        provider="github",
        owner=owner,
        repo=repo,
        host=GITHUB_HOST,
        canonical_url=f"https://github.com/{owner}/{repo}",
    )


def validate_branch_name(branch: str) -> str:
    """Return a conservative branch name or raise GitUrlError."""
    if not isinstance(branch, str) or not branch:
        raise GitUrlError("GIT_BRANCH_NOT_FOUND", "Enter a branch name.")
    if (
        not _BRANCH_RE.fullmatch(branch)
        or ".." in branch
        or "//" in branch
        or branch.endswith(("/", ".", ".lock"))
        or "@{" in branch
        or "\\" in branch
    ):
        raise GitUrlError("GIT_BRANCH_NOT_FOUND", "The branch name is invalid.")
    return branch


def validate_commit_sha(value: str) -> str:
    """Return a normalized full commit SHA or raise GitUrlError.

    Short SHAs are rejected: pinning must identify exactly one commit.
    """
    if not isinstance(value, str) or not _SHA_RE.fullmatch(value or ""):
        raise GitUrlError(
            "GIT_COMMIT_NOT_FOUND", "Enter a full 40-character commit SHA to pin an exact commit."
        )
    return value.lower()


def is_public_ip(value: str | ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True only for globally routable unicast addresses."""
    try:
        ip = ipaddress.ip_address(value) if isinstance(value, str) else value
    except ValueError:
        return False
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return False
    return bool(ip.is_global)


def validate_resolved_addresses(addresses: list[str]) -> list[str]:
    """Validate resolver output; fail closed on empty or mixed answers."""
    if not addresses:
        raise GitUrlError("GIT_PRIVATE_ADDRESS", "The repository host could not be resolved.")
    normalized: list[str] = []
    for raw in addresses:
        try:
            ip = ipaddress.ip_address(raw)
        except ValueError:
            raise GitUrlError(
                "GIT_PRIVATE_ADDRESS", "The repository host resolved to an invalid address."
            ) from None
        if not is_public_ip(ip):
            raise GitUrlError(
                "GIT_PRIVATE_ADDRESS",
                "The repository host resolved to a non-public address.",
            )
        text = str(ip)
        if text not in normalized:
            normalized.append(text)
    return normalized


def choose_pinned_address(addresses: list[str]) -> str:
    """Validate all answers and return the single address to pin."""
    return validate_resolved_addresses(addresses)[0]


def resolve_public_addresses(
    host: str,
    port: int = 443,
    getaddrinfo_fn: object = socket.getaddrinfo,
) -> list[str]:
    """Resolve via an injectable getaddrinfo and validate every answer.

    The worker pins the first returned address (see design §8.2). Tests
    inject a fake resolver; no test needs real DNS or network.
    """
    if host.lower() != GITHUB_HOST:
        raise GitUrlError(
            "GIT_HOST_NOT_ALLOWED", "Only github.com repositories are supported in this version."
        )
    try:
        infos = getaddrinfo_fn(host, port, 0, socket.SOCK_STREAM)  # type: ignore[operator]
    except (OSError, UnicodeError):
        raise GitUrlError(
            "GIT_PRIVATE_ADDRESS", "The repository host could not be resolved."
        ) from None
    addresses: list[str] = []
    for info in infos or []:
        try:
            sockaddr = info[4]
            addresses.append(str(sockaddr[0]))
        except (IndexError, TypeError):
            continue
    return validate_resolved_addresses(addresses)
