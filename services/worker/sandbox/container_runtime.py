"""Docker runtime wrapper (M5.2.6): sliced waits, bounded logs, cleanup.

All functions take an explicit client/container object — never a global —
so unit tests inject fakes and no test needs a daemon. Timeouts and
cancellation are first-class outcomes, never hangs: ``run_to_completion``
polls in slices, kills on timeout, and asks a caller-provided abort
callback (later: job cancellation / lease loss) on every slice.
"""

from __future__ import annotations

import io
import re
import tarfile
import time
from typing import Any, Callable

from .exceptions import SandboxError
from .workspace import BUILD_DOCKERFILE_NAME

TRUNCATION_MARKER = b"[... earlier output truncated ...]\n"

# Trusted build limits (M5.3): the fixed Dockerfile has no RUN steps, so
# builds do negligible work (COPY + metadata) — these bound the builder
# against pathological contexts. CPU shares and CPU sets are deliberately
# not set: shares are not a quota and pinning is platform-fragile. PID
# and disk quotas are not expressible on builds; the 256MB context cap
# and RUN-free Dockerfile are the operative controls there.
BUILD_MEMORY_BYTES = 512 * 1024 * 1024
BUILD_TIMEOUT_SECONDS = 300


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


def build_source_image(
    client: Any,
    context_tar: bytes,
    tag: str,
    *,
    memory_bytes: int = BUILD_MEMORY_BYTES,
    timeout_seconds: int = BUILD_TIMEOUT_SECONDS,
) -> str:
    """Build the per-execution source image from a build-context tarball.

    The build is hermetic: the context carries a fixed Dockerfile (under
    a reserved name, never the default ``Dockerfile``) with no RUN steps,
    the base image is never pulled (it must already exist locally), the
    build itself has no network, and builder containers get a memory cap
    plus a client-side timeout. Returns the built image id.
    """
    if not context_tar or not tag:
        raise SandboxError("EMPTY_SOURCE", "There is no source to transfer.")
    if memory_bytes <= 0 or timeout_seconds <= 0:
        raise SandboxError("INVALID_LIMITS", "Build limits must be positive.")
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
            container_limits={"memory": memory_bytes, "memswap": memory_bytes},
            timeout=timeout_seconds,
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


def create_output_volume(client: Any, name: str, labels: dict) -> Any:
    """Create one per-execution named output volume (M6 repro deliverables).

    Named volumes (never host binds) survive container stop, unlike the
    /tmp tmpfs — container file outputs are unreadable otherwise.
    """
    try:
        return client.volumes.create(name=name, labels=dict(labels))
    except Exception as exc:
        raise SandboxError(
            "VOLUME_CREATE_FAILED",
            "The output volume could not be created.",
            retryable=True,
        ) from exc


def remove_volume(client: Any, name: str) -> str:
    """Remove an output volume. Never raises: returns the cleanup status."""
    try:
        volume = client.volumes.get(name)
        volume.remove(force=True)
        return "removed"
    except Exception:
        try:
            return "removed" if _volume_missing(client, name) else "volume_cleanup_failed"
        except Exception:
            return "volume_cleanup_failed"


def _volume_missing(client: Any, name: str) -> bool:
    try:
        client.volumes.get(name)
    except Exception as exc:
        return type(exc).__name__ == "NotFound"
    return False


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


_ARTIFACT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}")


def read_files(
    container: Any,
    path: str,
    *,
    max_files: int,
    max_file_bytes: int,
    max_total_bytes: int,
) -> dict:
    """Read a container output directory via get_archive (M6).

    Returns {"files": {name: bytes}, "skipped": n}. Only flat regular
    files with safe names are returned; anything else is counted in
    ``skipped``. Every bound fails closed — oversized or overcounted
    output is an error, never a silent truncation.
    """
    if max_files <= 0 or max_file_bytes <= 0 or max_total_bytes <= 0:
        raise SandboxError("INVALID_LIMITS", "Artifact caps must be positive.")
    if not path or not path.startswith("/"):
        raise SandboxError("INVALID_PATH", "The artifact path must be absolute.")
    try:
        stream, _stat = container.get_archive(path)
    except Exception as exc:
        if type(exc).__name__ == "NotFound":
            raise SandboxError(
                "OUTPUT_NOT_FOUND", "The execution produced no output.", False
            ) from exc
        raise SandboxError(
            "ARTIFACT_READ_FAILED", "Sandbox output files could not be read.", True
        ) from exc
    chunks: list[bytes] = []
    total = 0
    try:
        for chunk in stream:
            if not isinstance(chunk, bytes):
                continue
            total += len(chunk)
            if total > max_total_bytes + 1024 * 1024:
                raise SandboxError(
                    "OUTPUT_TOO_LARGE", "Sandbox output exceeds the size limit.", False
                )
            chunks.append(chunk)
    except SandboxError:
        raise
    except Exception as exc:
        raise SandboxError(
            "ARTIFACT_READ_FAILED", "Sandbox output files could not be read.", True
        ) from exc
    files: dict[str, bytes] = {}
    skipped = 0
    data_total = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(b"".join(chunks))) as tar:
            for member in tar.getmembers():
                name = (member.name or "").rsplit("/", 1)[-1]
                if not member.isfile() or not _ARTIFACT_NAME.fullmatch(name):
                    skipped += 1
                    continue
                if member.size > max_file_bytes:
                    raise SandboxError(
                        "OUTPUT_FILE_TOO_LARGE",
                        f"An output file exceeds the size limit: {name}.",
                        False,
                    )
                reader = tar.extractfile(member)
                if reader is None:
                    skipped += 1
                    continue
                content = reader.read()
                data_total += len(content)
                if data_total > max_total_bytes:
                    raise SandboxError(
                        "OUTPUT_TOO_LARGE", "Sandbox output exceeds the size limit.", False
                    )
                if len(files) >= max_files:
                    raise SandboxError(
                        "OUTPUT_TOO_MANY_FILES", "Too many output files.", False
                    )
                if name in files:
                    skipped += 1
                    continue
                files[name] = content
    except SandboxError:
        raise
    except Exception as exc:
        raise SandboxError(
            "ARTIFACT_READ_FAILED", "Sandbox output could not be parsed.", True
        ) from exc
    return {"files": files, "skipped": skipped}


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
