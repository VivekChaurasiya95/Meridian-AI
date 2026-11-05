"""Scanner container runner (V1, D64).

Runs one scanner profile in a disposable restricted container on top
of the existing sandbox primitives: same spec controls, same build
hermeticity, same guaranteed cleanup. Differences from smoke are
deliberate and narrow: the FROM line is the scanner image, Semgrep
gets Meridian-owned rules as trusted extra files, and raw scanner
stdout/stderr are NEVER persisted (they carry secret values) — only
counts, versions, and fixed codes reach the database.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sandbox import container_runtime, workspace
from sandbox.container_spec import build_spec
from sandbox.exceptions import SandboxError
from sandbox.execution_policy import get_policy, validate_image_ref
from sandbox.lifecycle import (
    create_execution,
    finish_execution,
    new_execution_id,
    update_cleanup,
)

from security import rules as ruleset
from security.scanners import gitleaks as gitleaks_wrapper
from security.scanners import semgrep as semgrep_wrapper
from security.scanners.base import GITLEAKS, SEMGREP, ScannerFailure, ScannerResult

logger = logging.getLogger("meridian.security.orchestrator")

SCANNER_ORDER = (SEMGREP, GITLEAKS)


@dataclass
class ScannerRun:
    scanner: str
    findings: list[dict[str, Any]] = field(default_factory=list)
    version: str | None = None
    files_scanned: int | None = None
    errors_count: int = 0
    exit_code: int = 0
    duration_ms: int = 0


def _extras_for(scanner: str) -> dict[str, bytes] | None:
    if scanner != SEMGREP:
        return None
    try:
        loaded = ruleset.load_rules()
    except (FileNotFoundError, OSError) as exc:
        raise ScannerFailure(
            "RULESET_MISSING", "The Meridian ruleset is unavailable."
        ) from exc
    return {f"{workspace.RULES_ROOT}/{name}": data for name, data in loaded.items()}


def run_scanner(
    session_factory: Any,
    *,
    scanner: str,
    source_dir: str,
    job_id: uuid.UUID,
    worker_id: str,
    snapshot_id: uuid.UUID,
    attempt: int,
    image_override: str | None = None,
    client: Any = None,
    is_cancelled: Callable[[], bool] | None = None,
    timeout_seconds: int | None = None,
) -> ScannerRun:
    """Run one scanner container over ``source_dir`` to a parsed result.

    Raises ``ScannerFailure`` for scan failures (bad output, nonzero
    unexpected exits) and ``SandboxError`` for infrastructure and
    cancellation outcomes. The execution row is finished and the
    container/image destroyed on every path.
    """
    if scanner == SEMGREP:
        profile_name = "semgrep_preflight"
        parse = semgrep_wrapper.parse
    elif scanner == GITLEAKS:
        profile_name = "gitleaks_preflight"
        parse = gitleaks_wrapper.parse
    else:
        raise ScannerFailure("UNKNOWN_SCANNER", f"Unknown scanner: {scanner}.")
    policy = get_policy(profile_name)
    image = validate_image_ref(image_override) if image_override else policy.image
    extras = _extras_for(scanner)
    limit_seconds = timeout_seconds if timeout_seconds is not None else policy.timeout_seconds

    execution_uuid = uuid.UUID(hex=new_execution_id())
    execution_id = execution_uuid.hex
    with session_factory() as session:
        create_execution(
            session,
            execution_id=execution_uuid,
            job_id=job_id,
            worker_id=worker_id,
            snapshot_id=snapshot_id,
            profile=policy.profile,
            attempt=attempt,
            scanner=scanner,
        )

    container: Any = None
    own_client: Any = client
    image_tag: str | None = None
    cleaned_container = False
    cleaned_image = False

    def _safe_abort() -> bool:
        if is_cancelled is None:
            return False
        try:
            return bool(is_cancelled())
        except Exception as exc:  # noqa: BLE001 — the watch must never break a run
            logger.warning("cancel watch failed execution_id=%s error=%s", execution_id, exc)
            return False

    def _finish(status: str, **kwargs: Any) -> None:
        with session_factory() as session:
            finish_execution(session, execution_uuid, status=status, **kwargs)

    try:
        if own_client is None:
            own_client = container_runtime.get_client()
        context_tar, context_digest = workspace.pack_build_context(
            source_dir, base_image=image, extra_root_files=extras
        )
        image_tag = f"meridian-preflight-{scanner}-{context_digest[:16]}"
        image_id = container_runtime.build_source_image(own_client, context_tar, image_tag)
        logger.info(
            "scanner image built scanner=%s tag=%s image_id=%s", scanner, image_tag, image_id
        )
        spec = build_spec(policy, execution_id, image=image_tag)
        container = container_runtime.create_container(own_client, spec)
        run = container_runtime.run_to_completion(
            container, limit_seconds, should_abort=_safe_abort
        )
        logs = container_runtime.read_logs(container, policy.max_output_bytes)
        cleaned_image = (
            container_runtime.remove_image(own_client, image_tag) == "removed"
        )
        if run["timed_out"]:
            _finish(
                "timed_out",
                exit_code=run["exit_code"],
                timed_out=True,
                duration_ms=run["duration_ms"],
                error_code="COMMAND_TIMEOUT",
                error_message=f"The {scanner} scan exceeded its time limit.",
            )
            raise ScannerFailure(
                "COMMAND_TIMEOUT",
                f"The {scanner} scan exceeded its time limit.",
                retryable=True,
            )
        try:
            parsed: ScannerResult = parse(
                run["exit_code"],
                logs["stdout"],
                logs["stderr"],
                truncated=logs["truncated"],
            )
        except ScannerFailure as exc:
            _finish(
                "failed",
                exit_code=run["exit_code"],
                duration_ms=run["duration_ms"],
                output_truncated=logs["truncated"],
                error_code=exc.code,
                error_message=exc.message,
            )
            raise
        _finish(
            "completed",
            exit_code=run["exit_code"],
            duration_ms=run["duration_ms"],
        )
        return ScannerRun(
            scanner=scanner,
            findings=list(parsed.findings),
            version=parsed.version or image,
            files_scanned=parsed.files_scanned,
            errors_count=parsed.errors_count,
            exit_code=run["exit_code"],
            duration_ms=run["duration_ms"],
        )
    except ScannerFailure:
        raise
    except SandboxError as exc:
        if exc.code == "EXECUTION_CANCELLED":
            _finish("cancelled", error_code=exc.code, error_message=exc.message)
        else:
            _finish("failed", error_code=exc.code, error_message=exc.message)
        raise
    finally:
        if container is not None:
            cleaned_container = container_runtime.destroy_container(container) == "cleaned"
        if image_tag is not None and own_client is not None and not cleaned_image:
            cleaned_image = (
                container_runtime.remove_image(own_client, image_tag) == "removed"
            )
        with session_factory() as session:
            update_cleanup(
                session,
                execution_uuid,
                "cleaned" if (cleaned_container and cleaned_image) else "cleanup_failed",
            )
