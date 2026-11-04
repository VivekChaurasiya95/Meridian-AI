"""Docker runtime wrapper (M5.2.6): sliced waits, bounded logs, cleanup.

All functions take an explicit client/container object — never a global —
so unit tests inject fakes and no test needs a daemon. Timeouts and
cancellation are first-class outcomes, never hangs: ``run_to_completion``
polls in slices, kills on timeout, and asks a caller-provided abort
callback (later: job cancellation / lease loss) on every slice.
"""

from __future__ import annotations

import io
import time
from typing import Any, Callable

from .exceptions import SandboxError
from .workspace import BUILD_DOCKERFILE_NAME

TRUNCATION_MARKER = b"[... earlier output truncated ...]\n"


def get_client() -> Any:
    """Connect to the local container runtime (Docker Desktop here)."""
    try:
        import docker
    except ImportError:
        raise SandboxError(
            "RUNTIME_NOT_CONFIGURED",
            "The Docker SDK is not installed; sandbox execution is unavailable.",
        ) from None
    try:
        client = docker.from_env()
        client.ping()
        return client
    except Exception as exc:
        raise SandboxError(
            "RUNTIME_UNAVAILABLE",
            "The container runtime is unreachable.",
            retryable=True,
        ) from exc


def create_container(client: Any, spec: dict) -> Any:
    """Create (not start) one container from ``container_spec.build_spec``."""
    try:
        return client.containers.create(**spec)
    except Exception as exc:
        raise SandboxError(
            "CONTAINER_CREATE_FAILED",
            "The sandbox container could not be created.",
            retryable=True,
        ) from exc


def build_source_image(client: Any, context_tar: bytes, tag: str) -> str:
    """Build the per-execution source image from a build-context tarball.

    The build is hermetic: the context carries a fixed Dockerfile (under
    a reserved name, never the default ``Dockerfile``) with no RUN steps,
    the base image is never pulled (it must already exist locally), and
    the build itself has no network. Returns the built image id.
    """
    if not context_tar or not tag:
        raise SandboxError("EMPTY_SOURCE", "There is no source to transfer.")
    try:
        image, _build_logs = client.images.build(
            fileobj=io.BytesIO(context_tar),
            custom_context=True,
            dockerfile=BUILD_DOCKERFILE_NAME,
            tag=tag,
            rm=True,
            forcerm=True,
            pull=False,
            network_mode="none",
            quiet=True,
        )
        return str(image.id)
    except Exception as exc:
        raise SandboxError(
            "IMAGE_BUILD_FAILED", "The sandbox source image could not be built.", True
        ) from exc


def remove_image(client: Any, tag: str) -> str:
    """Remove a source image. Never raises: returns the cleanup status."""
    try:
        client.images.remove(image=tag, force=True, noprune=False)
        return "removed"
    except Exception:
        return "image_cleanup_failed"


def run_to_completion(
    container: Any,
    timeout_seconds: int,
    *,
    poll_interval: float = 0.5,
    should_abort: Callable[[], bool] | None = None,
) -> dict:
    """Start the container and wait in slices. Returns exit/timeout facts.

    Timeout kills the container and returns ``timed_out: True`` (a
    first-class outcome, not an exception). An abort callback returning
    True kills and raises ``EXECUTION_CANCELLED``.
    """
    if timeout_seconds <= 0:
        raise SandboxError("INVALID_TIMEOUT", "The timeout must be positive.")
    try:
        container.start()
    except Exception as exc:
        raise SandboxError(
            "CONTAINER_START_FAILED", "The sandbox container could not start."
        ) from exc
    deadline = time.monotonic() + timeout_seconds
    started = time.monotonic()
    exit_code = 0
    timed_out = False
    while True:
        if should_abort is not None and should_abort():
            _kill_quietly(container)
            raise SandboxError("EXECUTION_CANCELLED", "The execution was cancelled.")
        try:
            container.reload()
            state = container.attrs.get("State", {})
            status = state.get("Status")
        except Exception as exc:
            raise SandboxError(
                "CONTAINER_LOST", "The sandbox container disappeared."
            ) from exc
        if status in ("exited", "dead"):
            exit_code = int(state.get("ExitCode", 0))
            break
        if time.monotonic() >= deadline:
            _kill_quietly(container)
            timed_out = True
            try:
                container.reload()
                exit_code = int(container.attrs.get("State", {}).get("ExitCode", 137))
            except Exception:
                exit_code = 137
            break
        time.sleep(poll_interval)
    return {
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_ms": int((time.monotonic() - started) * 1000),
    }


def read_logs(container: Any, max_bytes: int) -> dict:
    """Fetch bounded stdout/stderr. Keeps the tail (most relevant on failure).

    Streams are fetched with two calls: docker SDK v7 has no ``demux``
    parameter, so there is no supported way to split one combined call.
    """
    if max_bytes <= 0:
        raise SandboxError("INVALID_LIMITS", "The output cap must be positive.")
    try:
        out = container.logs(stdout=True, stderr=False) or b""
        err = container.logs(stdout=False, stderr=True) or b""
    except Exception as exc:
        raise SandboxError("LOGS_FAILED", "Sandbox output could not be read.") from exc
    return {
        "stdout": _bound(out, max_bytes),
        "stderr": _bound(err, max_bytes),
        "truncated": len(out) > max_bytes or len(err) > max_bytes,
    }


def _bound(data: bytes, max_bytes: int) -> bytes:
    if len(data) <= max_bytes:
        return data
    return TRUNCATION_MARKER + data[-(max_bytes - len(TRUNCATION_MARKER)):]


def _kill_quietly(container: Any) -> None:
    try:
        container.kill()
    except Exception:
        pass


def destroy_container(container: Any) -> str:
    """Remove the container. Never raises: returns the cleanup status."""
    try:
        _kill_quietly(container)
        container.remove(force=True)
        return "cleaned"
    except Exception:
        return "cleanup_failed"
