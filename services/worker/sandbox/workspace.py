"""Host workspace lifecycle (M5.2.4): temp dir + materialized source.

The trusted orchestrator materializes a READY snapshot into a host
temporary directory (reusing workspace-scoped materialization — the same
byte-level checks as member retrieval), packs it into a deterministic
Docker build context, and removes the directory afterwards. The
execution container is never given MinIO access, host bind mounts, or
``put_archive`` transfers; source bytes cross the boundary only baked
into the per-execution image layer.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import shutil
import tarfile
import tempfile
from typing import TYPE_CHECKING, Any

from .exceptions import SandboxError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models import User

logger = logging.getLogger("meridian.sandbox.workspace")

# Upper bound for packed source: smoke executions stay small, and an
# unbounded build context would let a large snapshot stall the daemon.
SOURCE_MAX_BYTES = 256 * 1024 * 1024

# Reserved name of the trusted build file inside the build context.
# It is deliberately NOT "Dockerfile": a snapshot may legitimately
# contain a root-level file named exactly "Dockerfile", and sharing
# that name would put two Dockerfiles in one context tarball, letting
# repository content control the image build (duplicate tar entries
# resolve last-wins on extraction). The builder is told this exact
# name (see container_runtime.build_source_image), so a repository
# Dockerfile stays inert data copied to /work.
BUILD_DOCKERFILE_NAME = "Meridian.Dockerfile"

# Context-root names that control the image build and therefore can
# never come from snapshot data: the reserved build file itself, and
# ".dockerignore", which the builder would otherwise honor when
# selecting files for COPY. Anything else — including a root-level
# "Dockerfile" — is packed as data. Only exact root matches are
# reserved; the same names nested in subdirectories are inert data.
RESERVED_ROOT_NAMES = frozenset({BUILD_DOCKERFILE_NAME, ".dockerignore"})

# Fixed build-context Dockerfile: pinned base, source owned by the
# non-root execution user, no RUN steps (nothing executes at build time).
BUILD_DOCKERFILE = """\
FROM python:3.12-slim
COPY --chown=65534:65534 . /work
USER 65534:65534
WORKDIR /work
"""


def create_workspace() -> str:
    """Create an isolated host temporary directory for one execution."""
    return tempfile.mkdtemp(prefix="meridian-sandbox-src-")


def destroy_workspace(path: str) -> bool:
    """Remove a workspace directory. Never raises; reports success.

    Idempotent: a missing directory is already clean, so it reports
    success. Only genuine removal failures (permissions, locks) fail.
    """
    try:
        shutil.rmtree(path, ignore_errors=False)
        return True
    except FileNotFoundError:
        return True
    except Exception as exc:
        logger.warning("workspace cleanup failed path=%s error=%s", path, exc)
        return False


def prepare_source(
    session: Session,
    user: User,
    snapshot_id: Any,
    workspace_dir: str,
    store: Any = None,
) -> dict:
    """Materialize a READY snapshot into ``workspace_dir`` (must be empty)."""
    from app.services import storage as storage_service

    if not os.path.isdir(workspace_dir):
        raise SandboxError("INVALID_WORKSPACE", "The workspace directory is missing.")
    return storage_service.materialize_snapshot(
        session, user, snapshot_id, workspace_dir, store=store
    )


def pack_build_context(
    workspace_dir: str, max_bytes: int = SOURCE_MAX_BYTES
) -> tuple[bytes, str]:
    """Pack a materialized tree into a deterministic build-context tarball.

    Returns (context_bytes, sha256_hex). Only regular files are packed,
    with normalized ownership and modes; the fixed Dockerfile is added at
    the context root. Deterministic output means identical snapshots yield
    identical tags, so the daemon layer cache is actually useful.
    """
    entries: list[tuple[str, str, int]] = []
    total = 0
    for root, dirs, files in os.walk(workspace_dir):
        dirs.sort()
        for name in sorted(files):
            full = os.path.join(root, name)
            if not os.path.isfile(full) or os.path.islink(full):
                raise SandboxError(
                    "UNPACKABLE_FILE", f"Not a regular file: {name}."
                )
            rel = os.path.relpath(full, workspace_dir).replace(os.sep, "/")
            if rel in RESERVED_ROOT_NAMES:
                raise SandboxError(
                    "RESERVED_FILENAME",
                    f"Snapshot files must not use the reserved name: {rel}.",
                )
            size = os.path.getsize(full)
            total += size
            if total > max_bytes:
                raise SandboxError(
                    "WORKSPACE_TOO_LARGE", "Packed source exceeds the workspace limit."
                )
            entries.append((rel, full, size))
    dockerfile_bytes = BUILD_DOCKERFILE.encode("utf-8")
    if total + len(dockerfile_bytes) > max_bytes:
        raise SandboxError(
            "WORKSPACE_TOO_LARGE", "Packed source exceeds the workspace limit."
        )
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
        info = tarfile.TarInfo(name=BUILD_DOCKERFILE_NAME)
        info.size = len(dockerfile_bytes)
        info.mtime = 0
        info.uid = 0
        info.gid = 0
        info.uname = ""
        info.gname = ""
        info.mode = 0o644
        tar.addfile(info, io.BytesIO(dockerfile_bytes))
        for rel, full, size in entries:
            info = tarfile.TarInfo(name=rel)
            info.size = size
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mode = 0o644
            with open(full, "rb") as handle:
                tar.addfile(info, handle)
    context = buffer.getvalue()
    return context, hashlib.sha256(context).hexdigest()
