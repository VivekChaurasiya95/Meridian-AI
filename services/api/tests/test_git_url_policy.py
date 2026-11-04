"""Pure unit tests for Git URL/ref/address policy (no DB, no network).

DNS is always faked through the injectable resolver (design §9).
"""

import socket

import pytest

from app.config import Settings
from app.services.git_url_policy import (
    GitUrlError,
    choose_pinned_address,
    is_public_ip,
    parse_github_url,
    resolve_public_addresses,
    validate_branch_name,
    validate_commit_sha,
    validate_resolved_addresses,
)


def code_of(raw: str) -> str:
    with pytest.raises(GitUrlError) as exc_info:
        parse_github_url(raw)
    return exc_info.value.code


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("https://github.com/owner/repository", "https://github.com/owner/repository"),
        ("https://github.com/owner/repository.git", "https://github.com/owner/repository"),
        ("https://github.com/owner/repository/", "https://github.com/owner/repository"),
        ("https://github.com/Owner/Repo.Name_1-x", "https://github.com/Owner/Repo.Name_1-x"),
        ("HTTPS://GITHUB.COM/owner/repository", "https://github.com/owner/repository"),
        ("https://github.com:443/owner/repository", "https://github.com/owner/repository"),
        ("  https://github.com/owner/repository  ", "https://github.com/owner/repository"),
        ("https://github.com/a/b", "https://github.com/a/b"),
    ],
)
def test_valid_urls_normalize(raw: str, canonical: str) -> None:
    repo = parse_github_url(raw)
    assert repo.provider == "github"
    assert repo.host == "github.com"
    assert repo.canonical_url == canonical
    assert "@" not in repo.canonical_url and "://" in repo.canonical_url


@pytest.mark.parametrize(
    "raw",
    [
        "http://github.com/owner/repository",
        "ssh://git@github.com/owner/repository",
        "git://github.com/owner/repository",
        "file:///etc/passwd",
        "ext::sh -c id",
        "git@github.com:owner/repository.git",
        "ftp://github.com/owner/repository",
        "github.com/owner/repository",
        "//github.com/owner/repository",
    ],
)
def test_unsupported_transports_rejected(raw: str) -> None:
    assert code_of(raw) == "GIT_URL_UNSUPPORTED"


@pytest.mark.parametrize(
    "raw",
    [
        "https://gitlab.com/owner/repository",
        "https://github.com.evil.example/owner/repository",
        "https://notgithub.com/owner/repository",
        "https://127.0.0.1/owner/repository",
        "https://[::1]/owner/repository",
        "https://localhost/owner/repository",
        "https://192.168.1.10/owner/repository",
        "https://169.254.169.254/latest/meta-data",
        "https://metadata.google.internal/owner/repository",
        "https://github.com./owner/repository",
    ],
)
def test_non_github_hosts_rejected(raw: str) -> None:
    assert code_of(raw) == "GIT_HOST_NOT_ALLOWED"


@pytest.mark.parametrize(
    "raw",
    [
        "https://user:pass@github.com/owner/repository",
        "https://token@github.com/owner/repository",
        "https://user@github.com/owner/repository",
    ],
)
def test_embedded_credentials_rejected(raw: str) -> None:
    assert code_of(raw) == "GIT_CREDENTIALS_NOT_ALLOWED"


@pytest.mark.parametrize(
    "raw",
    [
        "https://github.com:22/owner/repository",
        "https://github.com:8443/owner/repository",
        "https://github.com:abc/owner/repository",
        "https://github.com:/owner/repository",
    ],
)
def test_arbitrary_ports_rejected(raw: str) -> None:
    assert code_of(raw) == "GIT_URL_UNSUPPORTED"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "https://github.com",
        "https://github.com/",
        "https://github.com/owner",
        "https://github.com/owner/",
        "https://github.com/owner/repo/extra",
        "https://github.com/owner/repo?tab=readme",
        "https://github.com/owner/repo#readme",
        "https://github.com/owner%2frepo",
        "https://github.com/-owner/repo",
        "https://github.com/owner-/repo",
        "https://github.com/ow--ner/repo",
        "https://github.com//repo",
        "https://github.com/owner//",
        "https://github.com/../repo",
        "https://github.com/owner/..",
        "https://github.com/owner/.repo",
        "https://github.com/owner/-repo",
        "https://github.com/owner/re po",
        "https://github.com/own er/repo",
        "https://github.com\\owner\\repo",
        "https://github.com/owner/repo\\",
        "https://github.com/" + "o" * 40 + "/repo",
        "https://github.com/owner/" + "r" * 101,
    ],
)
def test_malformed_urls_rejected(raw: str) -> None:
    assert code_of(raw) in ("GIT_URL_INVALID", "GIT_URL_UNSUPPORTED", "GIT_HOST_NOT_ALLOWED")


@pytest.mark.parametrize(
    ("branch", "ok"),
    [
        ("main", True),
        ("feature/git-import", True),
        ("release/1.2.x", True),
        ("a", True),
        ("", False),
        ("-main", False),
        ("feat..ure", False),
        ("feature/", False),
        ("feature.", False),
        ("feature.lock", False),
        ("feature//x", False),
        ("feature@{1}", False),
        ("feature\\x", False),
        (" feature", False),
        ("x" * 257, False),
    ],
)
def test_branch_validation(branch: str, ok: bool) -> None:
    if ok:
        assert validate_branch_name(branch) == branch
    else:
        with pytest.raises(GitUrlError) as exc_info:
            validate_branch_name(branch)
        assert exc_info.value.code == "GIT_BRANCH_NOT_FOUND"


def test_commit_sha_must_be_full() -> None:
    assert validate_commit_sha("A" * 40) == "a" * 40
    assert validate_commit_sha("0123456789abcdef0123456789abcdef01234567") == (
        "0123456789abcdef0123456789abcdef01234567"
    )
    for bad in ("abc123", "g" * 40, "a" * 39, "a" * 41, "", "a" * 40 + " "):
        with pytest.raises(GitUrlError) as exc_info:
            validate_commit_sha(bad)
        assert exc_info.value.code == "GIT_COMMIT_NOT_FOUND"


@pytest.mark.parametrize(
    ("ip", "public"),
    [
        ("140.82.121.3", True),  # github.com shape (public unicast)
        ("8.8.8.8", True),
        ("2606:4700:4700::1111", True),
        ("127.0.0.1", False),
        ("10.0.0.5", False),
        ("172.16.0.9", False),
        ("192.168.1.1", False),
        ("169.254.169.254", False),
        ("100.64.0.1", False),
        ("0.0.0.0", False),
        ("224.0.0.1", False),
        ("240.0.0.1", False),
        ("::1", False),
        ("fe80::1", False),
        ("fc00::1", False),
        ("fd12:3456::1", False),
        ("::", False),
        ("ff02::1", False),
        ("not-an-ip", False),
        ("", False),
    ],
)
def test_is_public_ip(ip: str, public: bool) -> None:
    assert is_public_ip(ip) is public


def test_mixed_dns_answers_fail_closed() -> None:
    with pytest.raises(GitUrlError) as exc_info:
        validate_resolved_addresses(["140.82.121.3", "127.0.0.1"])
    assert exc_info.value.code == "GIT_PRIVATE_ADDRESS"
    with pytest.raises(GitUrlError):
        validate_resolved_addresses([])
    with pytest.raises(GitUrlError):
        choose_pinned_address(["10.1.2.3"])
    assert choose_pinned_address(["140.82.121.3", "140.82.121.3"]) == "140.82.121.3"


def fake_getaddrinfo(addresses: list[str]):  # type: ignore[no-untyped-def]
    def _fake(host: str, port: int, family: int, socktype: int):  # type: ignore[no-untyped-def]
        return [(socket.AF_INET, socktype, 6, "", (ip, port)) for ip in addresses]

    return _fake


def test_resolve_with_fake_dns_public() -> None:
    resolved = resolve_public_addresses(
        "github.com", getaddrinfo_fn=fake_getaddrinfo(["140.82.121.3"])
    )
    assert resolved == ["140.82.121.3"]


def test_resolve_rebinding_to_private_fails() -> None:
    # Validate-time answer was public; fetch-time answer is loopback.
    with pytest.raises(GitUrlError) as exc_info:
        resolve_public_addresses("github.com", getaddrinfo_fn=fake_getaddrinfo(["127.0.0.1"]))
    assert exc_info.value.code == "GIT_PRIVATE_ADDRESS"


def test_resolve_rejects_non_github_before_dns() -> None:
    called = False

    def _spy(host: str, port: int, family: int, socktype: int):  # type: ignore[no-untyped-def]
        nonlocal called
        called = True
        return []

    with pytest.raises(GitUrlError) as exc_info:
        resolve_public_addresses("localhost", getaddrinfo_fn=_spy)
    assert exc_info.value.code == "GIT_HOST_NOT_ALLOWED"
    assert called is False


def test_resolve_dns_failure_is_safe_error() -> None:
    def _boom(host: str, port: int, family: int, socktype: int):  # type: ignore[no-untyped-def]
        raise OSError("name resolution failed")

    with pytest.raises(GitUrlError) as exc_info:
        resolve_public_addresses("github.com", getaddrinfo_fn=_boom)
    assert exc_info.value.code == "GIT_PRIVATE_ADDRESS"
    assert "OSError" not in exc_info.value.message


def test_git_import_config_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost:5432/db")
    settings = Settings()  # type: ignore[call-arg]
    assert settings.git_import_timeout_seconds == 120
    assert settings.git_import_max_file_bytes == 25 * 1024 * 1024
    assert settings.git_import_max_attempts == 2
