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


def _check_profile(policy: ExecutionPolicy) -> None:
    if not policy.profile or not policy.image or ":" not in policy.image:
        raise SandboxError("INVALID_PROFILE", "The profile must name a pinned image tag.")
    if policy.image.endswith(":latest"):
        raise SandboxError("INVALID_PROFILE", "Floating image tags are not allowed.")
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

_PROFILES: dict[str, ExecutionPolicy] = {
    _SMOKE.profile: _SMOKE,
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
