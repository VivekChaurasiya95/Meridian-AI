"""Security preflight job entry (V1, D65/D66).

Runs one claimed ``security_preflight`` job end to end: snapshot
verification, assessment row, dual input materialization, the two
scanner containers (independent: one failing never blocks the other),
normalization, risk policy, persistence, and guaranteed cleanup.
Every step is staged; scanners never see credentials; raw scanner
output never leaves this process.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import Any

from app.config import get_settings
from app.envelope import ApiError
from app.services import jobs as job_service
from app.services import projects as project_service
from app.services import security_assessments as assessment_service
from app.services import storage as storage_service
from sandbox import workspace
from sandbox.exceptions import SandboxError

from security import rules as ruleset
from security.models.finding import SEVERITIES, NormalizedFinding, to_record
from security.models.report import ScannerOutcome
from security.normalizer import normalize_gitleaks, normalize_semgrep
from security.orchestrator import SCANNER_ORDER, run_scanner
from security.result_validator import FindingValidationError
from security.risk_policy import evaluate as evaluate_risk
from security.scanners.base import GITLEAKS, SEMGREP, ScannerFailure

logger = logging.getLogger("meridian.security.preflight")

SEVERITY_RANK = {severity: rank for rank, severity in enumerate(SEVERITIES)}


class PreflightFailure(Exception):
    """Job-level preflight failure. Messages carry no secrets."""

    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def _stage(
    session_factory: Any,
    job_id: uuid.UUID,
    worker_id: str,
    key: str,
    status: str,
    **kwargs: Any,
) -> None:
    """Best-effort stage recording: never breaks an execution."""
    try:
        with session_factory() as session:
            job_service.record_stage(session, job_id, worker_id, key, status, **kwargs)
    except ApiError as exc:
        logger.warning("stage record refused job_id=%s code=%s", job_id, exc.code)
    except Exception as exc:  # noqa: BLE001 — observability must never break a run
        logger.warning("stage record failed job_id=%s error=%s", job_id, exc)


def _map_api_error(exc: ApiError) -> PreflightFailure:
    retryable = exc.status_code in (429, 503)
    return PreflightFailure(exc.code, exc.message, retryable)


def _order_for_persistence(findings: list[NormalizedFinding]) -> list[NormalizedFinding]:
    return sorted(
        findings,
        key=lambda item: (
            SEVERITY_RANK.get(item.severity, len(SEVERITY_RANK)),
            item.path,
            item.start_line,
            item.rule_id,
        ),
    )


def run_preflight(
    session_factory: Any,
    job: dict,
    worker_id: str,
    *,
    client: Any = None,
    store: Any = None,
    is_cancelled: Callable[[], bool] | None = None,
    image_overrides: dict[str, str] | None = None,
    timeout_overrides: dict[str, int] | None = None,
) -> dict:
    """Run one claimed ``security_preflight`` job to a persisted result.

    Returns the job-result summary; raises ``PreflightFailure`` (mapped
    to the job lifecycle by the worker) on every other path. The
    assessment row reflects the true outcome — including partial and
    cancelled — and workspaces are destroyed in all cases.
    ``image_overrides``/``timeout_overrides`` are tests-only.
    """
    try:
        job_id = uuid.UUID(str(job["id"]))
        workspace_id = uuid.UUID(str(job["workspace_id"]))
        attempt = int(job.get("attempts", 1))
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise PreflightFailure("INVALID_JOB", "The job record is malformed.") from exc
    if attempt < 1:
        raise PreflightFailure("INVALID_JOB", "Only claimed jobs may execute.")
    if job.get("job_type") != "security_preflight":
        raise PreflightFailure(
            "JOB_TYPE_NOT_IMPLEMENTED", "This entry runs preflight jobs only."
        )
    payload = job.get("payload")
    if not isinstance(payload, dict):
        raise PreflightFailure("INVALID_PAYLOAD", "The job payload must be an object.")
    try:
        snapshot_id = uuid.UUID(str(payload.get("snapshot_id")))
    except (ValueError, TypeError, AttributeError):
        raise PreflightFailure(
            "INVALID_PAYLOAD", "security_preflight needs a snapshot_id."
        ) from None
    scan_profile = payload.get("scan_profile", "initial_preflight")
    policy_version = payload.get("policy_version", "preflight-v1")
    if scan_profile not in job_service.PREFLIGHT_SCAN_PROFILES:
        raise PreflightFailure("INVALID_PAYLOAD", "The scan profile is not supported.")
    if policy_version not in job_service.PREFLIGHT_POLICY_VERSIONS:
        raise PreflightFailure("INVALID_PAYLOAD", "The policy version is not supported.")

    def _safe_abort() -> bool:
        if is_cancelled is None:
            return False
        try:
            return bool(is_cancelled())
        except Exception as exc:  # noqa: BLE001 — the watch must never break a run
            logger.warning("cancel watch failed job_id=%s error=%s", job_id, exc)
            return False

    settings = get_settings()
    max_findings = settings.preflight_max_findings
    assessment_id: uuid.UUID | None = None
    ws_dirs: list[str] = []
    try:
        _stage(session_factory, job_id, worker_id, "validate_snapshot", "running")
        try:
            with session_factory() as session:
                candidate = project_service.get_workspace_snapshot(
                    session, workspace_id, snapshot_id
                )
                project_id = candidate.project_id
                storage_ready = (
                    candidate.storage_status == "ready" and candidate.storage_key
                )
                security_ready = (
                    candidate.security_scan_status == "ready"
                    and candidate.security_storage_key
                )
                if not storage_ready or not security_ready:
                    raise PreflightFailure(
                        "SNAPSHOT_NOT_READY",
                        "The snapshot scan inputs are not stored.",
                    )
        except ApiError as exc:
            _stage(
                session_factory, job_id, worker_id, "validate_snapshot", "failed",
                error_code=exc.code, error_message=exc.message,
            )
            raise _map_api_error(exc) from exc
        _stage(
            session_factory, job_id, worker_id, "validate_snapshot", "completed",
            result_summary={"snapshot_id": str(snapshot_id)},
        )

        try:
            with session_factory() as session:
                assessment = assessment_service.get_or_create_assessment(
                    session,
                    job_id=job_id,
                    workspace_id=workspace_id,
                    project_id=project_id,
                    snapshot_id=snapshot_id,
                    policy_version=policy_version,
                    ruleset_version=ruleset.RULESET_VERSION,
                )
                assessment_id = assessment.id
        except ApiError as exc:
            raise _map_api_error(exc) from exc
        if assessment_id is None:
            raise PreflightFailure(
                "ASSESSMENT_NOT_CREATED", "The assessment row is missing."
            )

        _stage(session_factory, job_id, worker_id, "prepare_scan_input", "running")
        try:
            ws_semgrep = workspace.create_workspace()
            ws_dirs.append(ws_semgrep)
            with session_factory() as session:
                analysis = storage_service.materialize_for_workspace(
                    session, workspace_id, snapshot_id, ws_semgrep, store=store
                )
            ws_gitleaks = workspace.create_workspace()
            ws_dirs.append(ws_gitleaks)
            with session_factory() as session:
                security_input = storage_service.materialize_security_input_for_workspace(
                    session, workspace_id, snapshot_id, ws_gitleaks, store=store
                )
        except ApiError as exc:
            _stage(
                session_factory, job_id, worker_id, "prepare_scan_input", "failed",
                error_code=exc.code, error_message=exc.message,
            )
            raise _map_api_error(exc) from exc
        _stage(
            session_factory, job_id, worker_id, "prepare_scan_input", "completed",
            result_summary={
                "analysis_files": analysis["files"],
                "security_files": security_input["files"],
                "secret_files": security_input["secret_files"],
            },
        )

        sources = {SEMGREP: ws_semgrep, GITLEAKS: ws_gitleaks}
        outcomes: dict[str, ScannerOutcome] = {}
        raw_findings: dict[str, list[dict]] = {}
        first_failure: ScannerFailure | None = None
        for scanner in SCANNER_ORDER:
            stage_key = f"{scanner}_scan"
            _stage(session_factory, job_id, worker_id, stage_key, "running")
            try:
                run = run_scanner(
                    session_factory,
                    scanner=scanner,
                    source_dir=sources[scanner],
                    job_id=job_id,
                    worker_id=worker_id,
                    snapshot_id=snapshot_id,
                    attempt=attempt,
                    image_override=(image_overrides or {}).get(scanner),
                    client=client,
                    is_cancelled=is_cancelled,
                    timeout_seconds=(timeout_overrides or {}).get(scanner),
                )
            except ScannerFailure as exc:
                # Scan-level failure (bad output, unexpected exit): the
                # sibling scanner still runs; independence holds.
                if first_failure is None:
                    first_failure = exc
                outcomes[scanner] = ScannerOutcome(
                    scanner=scanner, status="failed", error_code=exc.code
                )
                _stage(
                    session_factory, job_id, worker_id, stage_key, "failed",
                    error_code=exc.code, error_message=exc.message,
                )
                continue
            except SandboxError as exc:
                # Infrastructure failure (daemon, build, cancel): a shared
                # prerequisite failed, so the run stops here.
                if exc.code == "EXECUTION_CANCELLED":
                    with session_factory() as session:
                        assessment_service.mark_assessment(
                            session, assessment_id, "cancelled"
                        )
                    _stage(session_factory, job_id, worker_id, stage_key, "cancelled")
                    raise PreflightFailure(
                        "EXECUTION_CANCELLED", "The preflight run was cancelled."
                    ) from exc
                _stage(
                    session_factory, job_id, worker_id, stage_key, "failed",
                    error_code=exc.code, error_message=exc.message,
                )
                raise PreflightFailure(exc.code, exc.message, exc.retryable) from exc
            outcomes[scanner] = ScannerOutcome(
                scanner=scanner,
                status="completed",
                findings=len(run.findings),
                files_scanned=run.files_scanned,
                version=run.version,
            )
            raw_findings[scanner] = run.findings
            _stage(
                session_factory, job_id, worker_id, stage_key, "completed",
                result_summary={
                    "findings": len(run.findings),
                    "files_scanned": run.files_scanned,
                    "errors": run.errors_count,
                },
            )
            if _safe_abort():
                break

        if _safe_abort():
            with session_factory() as session:
                assessment_service.mark_assessment(session, assessment_id, "cancelled")
            _stage(session_factory, job_id, worker_id, "cleanup", "completed")
            raise PreflightFailure("EXECUTION_CANCELLED", "The preflight run was cancelled.")

        if not any(outcome.status == "completed" for outcome in outcomes.values()):
            # Nothing usable to persist: fail the job (retrying transient
            # causes) instead of completing with an empty assessment.
            if first_failure is None:
                raise PreflightFailure(
                    "SCANNERS_FAILED", "No scanner completed its run."
                )
            raise PreflightFailure(
                first_failure.code, first_failure.message, first_failure.retryable
            )

        _stage(session_factory, job_id, worker_id, "normalize_findings", "running")
        findings: list[NormalizedFinding] = []
        skipped = 0
        for scanner in SCANNER_ORDER:
            normalize = normalize_semgrep if scanner == SEMGREP else normalize_gitleaks
            for raw in raw_findings.get(scanner, []):
                try:
                    findings.append(normalize(raw))
                except FindingValidationError as exc:
                    skipped += 1
                    logger.warning(
                        "finding skipped scanner=%s code=%s", scanner, exc.code
                    )
        _stage(
            session_factory, job_id, worker_id, "normalize_findings", "completed",
            result_summary={"normalized": len(findings), "skipped": skipped},
        )

        _stage(session_factory, job_id, worker_id, "apply_risk_policy", "running")
        status, summary = evaluate_risk(findings, outcomes)
        summary.skipped_malformed = skipped
        ordered = _order_for_persistence(findings)
        kept = ordered[:max_findings]
        summary.persisted = len(kept)
        summary.dropped = len(ordered) - len(kept)
        _stage(
            session_factory, job_id, worker_id, "apply_risk_policy", "completed",
            result_summary={"status": status, "total": summary.total},
        )

        _stage(session_factory, job_id, worker_id, "persist_assessment", "running")
        records = [to_record(item, assessment_id) for item in kept]
        try:
            with session_factory() as session:
                assessment_service.store_assessment_result(
                    session,
                    assessment_id,
                    status=status,
                    summary=summary.to_json(),
                    scanner_versions=summary.versions_json(),
                    records=records,
                )
        except ApiError as exc:
            _stage(
                session_factory, job_id, worker_id, "persist_assessment", "failed",
                error_code=exc.code, error_message=exc.message,
            )
            raise _map_api_error(exc) from exc
        _stage(
            session_factory, job_id, worker_id, "persist_assessment", "completed",
            result_summary={"status": status, "persisted": len(records)},
        )
        return {
            "assessment_id": str(assessment_id),
            "snapshot_id": str(snapshot_id),
            "status": status,
            "summary": summary.to_json(),
        }
    except PreflightFailure as exc:
        if assessment_id is not None and exc.code not in ("EXECUTION_CANCELLED",):
            try:
                with session_factory() as session:
                    assessment_service.mark_assessment(session, assessment_id, "failed")
            except Exception as mark_exc:  # noqa: BLE001 — best-effort terminal marking
                logger.warning("assessment mark failed error=%s", mark_exc)
        raise
    finally:
        cleaned = True
        for ws_dir in ws_dirs:
            cleaned = workspace.destroy_workspace(ws_dir) and cleaned
        _stage(
            session_factory, job_id, worker_id, "cleanup",
            "completed" if cleaned else "failed",
        )
