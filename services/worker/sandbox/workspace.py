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
from .execution_policy import validate_image_ref

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
# never come from snapshot data: the reserved build file itself,
# ".dockerignore" (which the builder would otherwise honor when
# selecting files for COPY), and the trusted rules directory (which
# would collide with Meridian-owned scanner configuration). Anything
# else — including a root-level "Dockerfile" — is packed as data.
# Exact root matches are reserved, as is anything under the rules
# directory; the same names nested elsewhere are inert data.
RULES_ROOT = "Meridian.rules"
RESERVED_ROOT_NAMES = frozenset({BUILD_DOCKERFILE_NAME, ".dockerignore", RULES_ROOT})

# Trusted base images may only come from sandbox profiles (validated
# pin format); payloads never select them. This default serves smoke.
DEFAULT_BASE_IMAGE = "python:3.12-slim"

# Fixed build-context Dockerfile template: pinned base, source owned
# by the non-root execution user, no RUN steps (nothing executes at
# build time). Only the FROM line is ever parameterized, and only with
# a validated profile image.
BUILD_DOCKERFILE_TEMPLATE = """\
FROM {base}
COPY --chown=65534:65534 . /work
USER 65534:65534
WORKDIR /work
"""
BUILD_DOCKERFILE = BUILD_DOCKERFILE_TEMPLATE.format(base=DEFAULT_BASE_IMAGE)

# Trusted extra files (Meridian-owned scanner rules) are small and few.
MAX_EXTRA_FILES = 16
MAX_EXTRA_FILE_BYTES = 1024 * 1024


def _dockerfile_for(base_image: str) -> bytes:
    return BUILD_DOCKERFILE_TEMPLATE.format(base=validate_image_ref(base_image)).encode("utf-8")


def _check_extra_name(name: str) -> str:
    """Extra files live under the rules root with safe basenames only."""
    if not name.startswith(RULES_ROOT + "/"):
        raise SandboxError(
            "RESERVED_FILENAME", f"Extra files must live under {RULES_ROOT}/."
        )
    rest = name[len(RULES_ROOT) + 1 :]
    if (
        not rest
        or "/" in rest
        or "\\" in rest
        or "\x00" in rest
        or rest in (".", "..")
        or len(rest) > 128
    ):
        raise SandboxError("RESERVED_FILENAME", "Extra file names must be safe basenames.")
    return name


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
    workspace_dir: str,
    max_bytes: int = SOURCE_MAX_BYTES,
    *,
    base_image: str | None = None,
    extra_root_files: dict[str, bytes] | None = None,
) -> tuple[bytes, str]:
    """Pack a materialized tree into a deterministic build-context tarball.

    Returns (context_bytes, sha256_hex). Only regular files are packed,
    with normalized ownership and modes; the fixed Dockerfile is added at
    the context root. Deterministic output means identical snapshots yield
    identical tags, so the daemon layer cache is actually useful.

    ``base_image`` overrides the FROM line with a validated profile
    image (scanner builds; None or "" keeps the smoke default);
    ``extra_root_files`` adds trusted
    Meridian-owned files (scanner rules) under the reserved rules
    directory. Both are trusted-caller-only: payloads never supply
    them, and snapshot data can never collide with them.
    """
    dockerfile_bytes = _dockerfile_for(base_image or DEFAULT_BASE_IMAGE)
    extras = dict(extra_root_files or {})
    if len(extras) > MAX_EXTRA_FILES:
        raise SandboxError("WORKSPACE_TOO_LARGE", "Too many trusted extra files.")
    for name, data in extras.items():
        _check_extra_name(name)
        if not isinstance(data, bytes) or not data or len(data) > MAX_EXTRA_FILE_BYTES:
            raise SandboxError("INVALID_EXTRAS", "Trusted extra files must be bounded bytes.")
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
            if rel in RESERVED_ROOT_NAMES or rel.startswith(RULES_ROOT + "/"):
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
    extras_bytes = sum(len(data) for data in extras.values())
    if total + len(dockerfile_bytes) + extras_bytes > max_bytes:
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
        if extras:
            dir_info = tarfile.TarInfo(name=RULES_ROOT)
            dir_info.type = tarfile.DIRTYPE
            dir_info.mtime = 0
            dir_info.uid = 0
            dir_info.gid = 0
            dir_info.uname = ""
            dir_info.gname = ""
            dir_info.mode = 0o755
            tar.addfile(dir_info)
            for name in sorted(extras):
                data = extras[name]
                file_info = tarfile.TarInfo(name=name)
                file_info.size = len(data)
                file_info.mtime = 0
                file_info.uid = 0
                file_info.gid = 0
                file_info.uname = ""
                file_info.gname = ""
                file_info.mode = 0o644
                tar.addfile(file_info, io.BytesIO(data))
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
