"""Sandbox container specification (M5.2.3): restricted Docker kwargs.

``build_spec`` is a pure function returning docker-py create kwargs — no
daemon contact, fully unit-testable. Every SECURITY.md §7.1 baseline
control is pinned here: non-root user, read-only rootfs, bounded tmpfs
for /tmp only, dropped capabilities, no-new-privileges, no privileged
mode, no host namespaces, no mounts/ports/socket, default-deny network
(``none``), CPU/memory/PID limits, and management labels for later
orphan pruning. Anything absent from this dict is denied by omission:
there are deliberately no port, device, or socket keys. A ``volumes``
mapping may be supplied for trusted per-execution named output volumes
only (M6 repro deliverables): never host binds, always removed with the
execution, and reaped by label if the worker dies mid-run.

Source files reach the container baked into a per-execution image (see
``workspace.pack_build_context``), never through ``put_archive``: the
daemon refuses archive extraction into read-only-rootfs containers, and
a bind mount would reintroduce a host surface. ``/work`` therefore comes
from the image layer itself — no tmpfs may shadow it.
"""

from __future__ import annotations

import re

from .exceptions import SandboxError
from .execution_policy import ExecutionPolicy

_EXECUTION_ID_RE = re.compile(r"[0-9a-f]{32}")
_VOLUME_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]*")
_NAME_PREFIX = "meridian-sandbox-"
# Debian/Ubuntu 'nobody': no login, no files owned, present in slim images.
_RUN_UID_GID = "65534:65534"

DEFAULT_NANO_CPUS = 500_000_000  # 0.5 CPU
DEFAULT_MEM_LIMIT = "512m"
DEFAULT_PIDS_LIMIT = 128


def build_spec(
    policy: ExecutionPolicy,
    execution_id: str,
    *,
    image: str | None = None,
    nano_cpus: int = DEFAULT_NANO_CPUS,
    mem_limit: str = DEFAULT_MEM_LIMIT,
    pids_limit: int = DEFAULT_PIDS_LIMIT,
    volumes: dict | None = None,
) -> dict:
    """Build docker-py container-create kwargs for one execution.

    ``image`` overrides the policy base image with the per-execution
    source image tag; the base pinning rules still apply to the policy.
    ``volumes`` is a docker-py volumes mapping for trusted per-execution
    named output volumes (bind mode ``rw`` onto a reserved path); host
    bind sources are never accepted here.
    """
    if not _EXECUTION_ID_RE.fullmatch(execution_id):
        raise SandboxError(
            "INVALID_EXECUTION_ID", "The execution id must be 32 lowercase hex chars."
        )
    if nano_cpus <= 0:
        raise SandboxError("INVALID_LIMITS", "CPU quota must be positive.")
    if not mem_limit or (isinstance(mem_limit, int) and mem_limit <= 0):
        raise SandboxError("INVALID_LIMITS", "Memory limit must be positive.")
    if pids_limit <= 0:
        raise SandboxError("INVALID_LIMITS", "PID limit must be positive.")
    for source in (volumes or {}):
        if not _VOLUME_NAME_RE.fullmatch(source):
            raise SandboxError(
                "INVALID_VOLUME", "Only plain named volumes may be mounted."
            )
    return {
        "image": image or policy.image,
        "volumes": dict(volumes or {}),
        "command": list(policy.command),
        "name": f"{_NAME_PREFIX}{execution_id[:12]}",
        "working_dir": policy.workdir,
        "user": _RUN_UID_GID,
        "read_only": True,
        # Only /tmp is tmpfs: /work comes from the source image layer, and
        # a tmpfs mount there would shadow the transferred files. The
        # uid/gid options let the non-root user write despite read-only root.
        "tmpfs": {
            "/tmp": "rw,uid=65534,gid=65534,mode=1777,size=64m",
        },
        "cap_drop": ["ALL"],
        "security_opt": ["no-new-privileges:true"],
        "network_mode": "none",
        "privileged": False,
        "stdin_open": False,
        "tty": False,
        "nano_cpus": nano_cpus,
        "mem_limit": mem_limit,
        "pids_limit": pids_limit,
        "environment": dict(policy.env),
        "labels": {
            "meridian.managed": "true",
            "meridian.execution_id": execution_id,
            "meridian.profile": policy.profile,
        },
        "detach": True,
    }
