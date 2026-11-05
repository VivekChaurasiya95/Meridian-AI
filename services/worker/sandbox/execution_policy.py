"""Command execution policy (M5.2.5): allowlisted profiles, argv only.

There is intentionally NO caller-supplied command surface in v1: each
profile carries its exact argv and the orchestrator runs exactly that.
No shell is ever invoked, so no shell string is ever constructed —
``resolve_command`` returns the profile argv unchanged. A future profile
needing constrained arguments must add explicit per-argument validation
here; nothing else in the package may build commands.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .exceptions import SandboxError

MAX_ARGS = 16
MAX_ARG_BYTES = 4096
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 3600
MIN_OUTPUT_BYTES = 1024
MAX_OUTPUT_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class ExecutionPolicy:
    """One approved execution shape. Immutable after construction."""

    profile: str
    image: str
    command: tuple[str, ...]
    workdir: str = "/work"
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: int = 120
    max_output_bytes: int = 1_048_576


def _check_argv(command: tuple[str, ...]) -> None:
    if not command:
        raise SandboxError("EMPTY_COMMAND", "The command argv must not be empty.")
    if len(command) > MAX_ARGS:
        raise SandboxError("COMMAND_TOO_LONG", "The command has too many arguments.")
    for arg in command:
        if not isinstance(arg, str) or not arg:
            raise SandboxError("INVALID_ARGUMENT", "Command arguments must be non-empty strings.")
        if len(arg.encode("utf-8")) > MAX_ARG_BYTES:
            raise SandboxError("ARGUMENT_TOO_LONG", "A command argument is too long.")


def validate_image_ref(image: str) -> str:
    """Accept pinned image tags only. Returns the validated reference."""
    if not isinstance(image, str) or not image or ":" not in image:
        raise SandboxError("INVALID_PROFILE", "The profile must name a pinned image tag.")
    if image.endswith(":latest"):
        raise SandboxError("INVALID_PROFILE", "Floating image tags are not allowed.")
    return image


def _check_profile(policy: ExecutionPolicy) -> None:
    if not policy.profile:
        raise SandboxError("INVALID_PROFILE", "The profile must have a name.")
    validate_image_ref(policy.image)
    if not (MIN_TIMEOUT_SECONDS <= policy.timeout_seconds <= MAX_TIMEOUT_SECONDS):
        raise SandboxError("INVALID_PROFILE", "The timeout is outside the allowed range.")
    if not (MIN_OUTPUT_BYTES <= policy.max_output_bytes <= MAX_OUTPUT_BYTES):
        raise SandboxError("INVALID_PROFILE", "The output cap is outside the allowed range.")
    for key, value in policy.env.items():
        if not key or not isinstance(value, str):
            raise SandboxError("INVALID_PROFILE", "Environment entries must be plain strings.")
    _check_argv(policy.command)


_SMOKE = ExecutionPolicy(
    profile="sandbox_smoke",
    image="python:3.12-slim",
    command=("python", "-c", "print('meridian-sandbox-ok')"),
    timeout_seconds=120,
    max_output_bytes=1_048_576,
)

# Security preflight scanners (V1, D63/D64). Fixed argv, pinned
# images, stdout-JSON contracts. Commands never vary by caller.
_SEMGREP = ExecutionPolicy(
    profile="semgrep_preflight",
    image="semgrep/semgrep:1.183.0",
    command=(
        "semgrep",
        "scan",
        "--config",
        "/work/Meridian.rules",
        "--json",
        "--metrics=off",
        "--disable-version-check",
        "/work",
    ),
    env={"HOME": "/tmp"},
    timeout_seconds=600,
    max_output_bytes=8_388_608,
)

_GITLEAKS = ExecutionPolicy(
    profile="gitleaks_preflight",
    image="zricethezav/gitleaks:v8.30.1",
    command=(
        "gitleaks",
        "dir",
        "/work",
        "--report-format",
        "json",
        "--report-path",
        "-",
        "--redact",
        "--exit-code",
        "1",
    ),
    env={"HOME": "/tmp"},
    timeout_seconds=300,
    max_output_bytes=8_388_608,
)

# Browser reproduction (M6). Fixed argv: the trusted repro script plus a
# server-validated steps file, both baked in as reserved extras. The
# script serves the snapshot on container loopback and drives headless
# Chromium; findings land in /tmp/meridian-out for bounded extraction.
_REPRO = ExecutionPolicy(
    profile="browser_repro",
    # Maintainer-built base (repro-base.Dockerfile): upstream ships the
    # browsers but not the playwright Python package, and per-execution
    # builds are RUN-free, so the pinned package is baked in once here.
    image="meridian/repro-base:1.49.0",
    command=("python", "/work/Meridian.rules/repro.py"),
    env={"HOME": "/tmp", "PLAYWRIGHT_BROWSERS_PATH": "/ms-playwright"},
    timeout_seconds=600,
    max_output_bytes=4_194_304,
)

_PROFILES: dict[str, ExecutionPolicy] = {
    _SMOKE.profile: _SMOKE,
    _SEMGREP.profile: _SEMGREP,
    _GITLEAKS.profile: _GITLEAKS,
    _REPRO.profile: _REPRO,
}


def get_policy(profile: str) -> ExecutionPolicy:
    """Return the validated policy for a known profile name."""
    try:
        policy = _PROFILES[profile]
    except KeyError:
        raise SandboxError(
            "UNKNOWN_PROFILE", f"Unknown execution profile: {profile}."
        ) from None
    _check_profile(policy)
    return policy


def resolve_command(policy: ExecutionPolicy) -> tuple[str, ...]:
    """Return the exact argv to execute. v1 allows zero caller variation."""
    _check_argv(policy.command)
    return policy.command
