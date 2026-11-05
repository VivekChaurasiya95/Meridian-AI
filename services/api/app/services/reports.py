"""Investigation reports: model-written summaries (M9) + file reports (M10).

M9: one validated model-written summary per generation stage run; the
latest is the investigation's current summary. Trusted-worker-only
writes with job-ownership checks; membership-checked reads.

M10: deterministic downloadable md/html files rendered ONLY from
persisted rows (summary, snapshot id+digest, repro result, evidence
index, hypotheses, patches+approvals, check results, limitations,
timestamps). Bytes are a pure function of investigation state — no
generation timestamp, no report id inside — so regeneration from
unchanged rows is byte-identical. Private MinIO bytes, short-lived
authorized downloads, issuance audited.
"""

import contextlib
import datetime as dt
import hashlib
import html
import os
import tempfile
import uuid
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.envelope import ApiError, access_denied, not_found
from app.models import (
    EvidenceArtifact,
    Hypothesis,
    Investigation,
    InvestigationReport,
    Patch,
    Project,
    Report,
    RepositorySnapshot,
    ToolRun,
    User,
    VerificationCheck,
    VerificationRun,
    WorkspaceMember,
)
from app.services import audit as audit_service
from app.services.activity import db_now, investigation_access
from app.services.investigations import require_job_ownership
from app.services.model_gateway import ReportDraft
from app.services.object_store import MinioObjectStore, ObjectStore, StorageError

REPORT_FORMATS = ("md", "html")
REPORT_STATUSES = ("queued", "running", "ready", "failed", "blocked")
TERMINAL_REPORT_STATUSES = frozenset({"ready", "failed", "blocked"})
MIME_BY_FORMAT = {"md": "text/markdown", "html": "text/html"}
REPORT_GENERATOR = "meridian-reports-v1"
WORKSPACE_LIST_LIMIT = 50
CONTRIBUTOR_ROLES = frozenset({"owner", "admin", "developer"})


def _iso(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.UTC)
    return value.isoformat().replace("+00:00", "Z")


def serialize_report(row: InvestigationReport) -> dict:
    return {
        "id": str(row.id),
        "investigation_id": str(row.investigation_id),
        "title": row.title,
        "summary": row.summary,
        "sections": list(row.sections or []),
        "model": row.model,
        "created_at": _iso(row.created_at),
    }


def create_report(
    session: Session,
    *,
    job_id: uuid.UUID,
    worker_id: str,
    investigation_id: uuid.UUID,
    stage_id: uuid.UUID,
    tool_run_id: uuid.UUID | None,
    model: str,
    draft: ReportDraft,
) -> dict:
    """Persist one validated report draft (trusted worker path)."""
    require_job_ownership(session, job_id, worker_id, investigation_id)
    if not model or len(model) > 128:
        raise ApiError(422, "VALIDATION_ERROR", "The report model label is invalid.")
    row = InvestigationReport(
        id=uuid.uuid4(),
        investigation_id=investigation_id,
        created_by_stage_id=stage_id,
        tool_run_id=tool_run_id,
        title=draft.title,
        summary=draft.summary,
        sections=[{"heading": section.heading, "body": section.body} for section in draft.sections],
        model=model,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return serialize_report(row)


def get_latest_report(session: Session, user: User, investigation_id: uuid.UUID) -> dict:
    """Current report for one investigation (404 when none exists)."""
    inv, _role = investigation_access(session, user, investigation_id)
    row = (
        session.execute(
            select(InvestigationReport)
            .where(InvestigationReport.investigation_id == inv.id)
            .order_by(desc(InvestigationReport.created_at), desc(InvestigationReport.id))
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise not_found("report")
    return serialize_report(row)


def report_count(session: Session, investigation_id: uuid.UUID) -> int:
    """Number of M9 model-written summaries (for investigation detail counts)."""
    return (
        session.execute(
            select(func.count()).where(InvestigationReport.investigation_id == investigation_id)
        )
    ).scalar_one()


# M10 file reports: deterministic md/html rendered from persisted rows.


def serialize_file_report(row: Report) -> dict:
    """Public file-report metadata. The storage key stays server-side."""
    return {
        "id": str(row.id),
        "investigation_id": str(row.investigation_id),
        "project_id": str(row.project_id),
        "patch_id": str(row.patch_id) if row.patch_id else None,
        "verification_run_id": str(row.verification_run_id) if row.verification_run_id else None,
        "format": row.format,
        "status": row.status,
        "digest_sha256": row.digest_sha256,
        "byte_size": row.byte_size,
        "error_code": row.error_code,
        "error_message": row.error_message,
        "created_by": str(row.created_by) if row.created_by else None,
        "created_at": _iso(row.created_at),
    }


def report_key(report_id: uuid.UUID, report_format: str) -> str:
    return f"reports/{report_id}.{report_format}"


def get_store() -> ObjectStore:
    settings = get_settings()
    return MinioObjectStore(
        endpoint_url=settings.s3_endpoint_url,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        region=settings.s3_region,
    )


def build_report_context(session: Session, investigation_id: uuid.UUID) -> dict[str, Any]:
    """Collect the stable persisted state a file report covers (M10).

    Pure read of committed rows: no model calls, no invented values.
    Raises 409 EVIDENCE_NOT_READY when any artifact failed redaction —
    the index must be complete to be honest, so generation refuses
    instead of silently dropping evidence.
    """
    inv = session.get(Investigation, investigation_id)
    if inv is None:
        raise not_found("investigation")
    snapshot: RepositorySnapshot | None = None
    if inv.repository_snapshot_id is not None:
        snapshot = session.get(RepositorySnapshot, inv.repository_snapshot_id)
    repro = (
        session.execute(
            select(ToolRun)
            .where(
                ToolRun.investigation_id == inv.id,
                ToolRun.tool_name == "browser_repro",
                ToolRun.status == "succeeded",
            )
            .order_by(desc(ToolRun.created_at), desc(ToolRun.id))
            .limit(1)
        )
    ).scalar_one_or_none()
    evidence_rows = list(
        session.execute(
            select(EvidenceArtifact)
            .where(EvidenceArtifact.investigation_id == inv.id)
            .order_by(EvidenceArtifact.created_at.asc(), EvidenceArtifact.id.asc())
        ).scalars()
    )
    if any(row.redaction_status == "failed" for row in evidence_rows):
        raise ApiError(
            409,
            "EVIDENCE_NOT_READY",
            "An evidence artifact failed redaction review, so no report can be issued.",
        )
    hypothesis_rows = list(
        session.execute(
            select(Hypothesis)
            .where(Hypothesis.investigation_id == inv.id)
            .order_by(Hypothesis.created_at.asc(), Hypothesis.id.asc())
        ).scalars()
    )
    patch_rows = list(
        session.execute(
            select(Patch)
            .where(Patch.investigation_id == inv.id)
            .order_by(Patch.created_at.asc(), Patch.id.asc())
        ).scalars()
    )
    run_rows = list(
        session.execute(
            select(VerificationRun)
            .where(VerificationRun.investigation_id == inv.id)
            .order_by(VerificationRun.created_at.asc(), VerificationRun.id.asc())
        ).scalars()
    )
    check_rows: list[VerificationCheck] = []
    if run_rows:
        check_rows = list(
            session.execute(
                select(VerificationCheck)
                .where(VerificationCheck.verification_run_id.in_([row.id for row in run_rows]))
                .order_by(VerificationCheck.created_at.asc(), VerificationCheck.id.asc())
            ).scalars()
        )
    checks_by_run: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for check in check_rows:
        checks_by_run.setdefault(check.verification_run_id, []).append(
            {
                "check_key": check.check_key,
                "display_name": check.display_name,
                "status": check.status,
                "exit_code": check.exit_code,
                "duration_ms": check.duration_ms,
            }
        )
    result = dict(repro.result_summary or {}) if repro is not None else None
    limitations = [
        "Static snapshots only: dynamic services outside the snapshot are out of scope.",
        "Statuses describe recorded tool output, never model claims.",
    ]
    if not patch_rows:
        limitations.append("No patch has been proposed for this investigation.")
    if not run_rows:
        limitations.append("No verification run has been recorded.")
    return {
        "generator": REPORT_GENERATOR,
        "investigation": {
            "id": str(inv.id),
            "title": inv.title,
            "status": inv.status,
            "severity": inv.severity,
            "result_summary": inv.result_summary,
            "created_at": _iso(inv.created_at),
            "updated_at": _iso(inv.updated_at),
        },
        "snapshot": (
            {
                "id": str(snapshot.id),
                "tree_digest": snapshot.tree_digest,
                "source_type": snapshot.source_type,
                "commit_sha": snapshot.commit_sha,
            }
            if snapshot is not None
            else None
        ),
        "reproduction": (
            {
                "tool_run_id": str(repro.id),
                "reproduced": result.get("reproduced") if result else None,
                "assertions_total": result.get("assertions_total") if result else None,
                "assertions_passed": result.get("assertions_passed") if result else None,
                "finished_at": _iso(repro.finished_at),
            }
            if repro is not None
            else None
        ),
        "evidence": [
            {
                "id": str(row.id),
                "kind": row.kind,
                "mime_type": row.mime_type,
                "byte_size": row.byte_size,
                "sha256": row.sha256,
                "redaction_status": row.redaction_status,
                "created_at": _iso(row.created_at),
            }
            for row in evidence_rows
        ],
        "hypotheses": [
            {
                "id": str(row.id),
                "title": row.title,
                "description": row.description,
                "confidence": float(row.confidence) if row.confidence is not None else None,
                "status": row.status,
                "created_at": _iso(row.created_at),
            }
            for row in hypothesis_rows
        ],
        "patches": [
            {
                "id": str(row.id),
                "status": row.status,
                "summary": row.summary,
                "diff_sha256": row.diff_sha256,
                "diff_byte_size": row.diff_byte_size,
                "files_changed": list(row.files_changed or []),
                "approval_status": row.approval_status,
                "approved_at": _iso(row.approved_at),
                "applied_at": _iso(row.applied_at),
                "created_at": _iso(row.created_at),
            }
            for row in patch_rows
        ],
        "verification_runs": [
            {
                "id": str(row.id),
                "phase": row.phase,
                "status": row.status,
                "summary": row.summary,
                "finished_at": _iso(row.finished_at),
                "created_at": _iso(row.created_at),
                "checks": checks_by_run.get(row.id, []),
            }
            for row in run_rows
        ],
        "limitations": limitations,
    }


def _md_value(value: Any) -> str:
    if value is None:
        return "none recorded"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def render_report_markdown(context: dict[str, Any]) -> bytes:
    """Render the context as Markdown (pure, deterministic, no invention)."""
    inv = context["investigation"]
    lines = [
        f"# Investigation report: {inv['title']}",
        "",
        f"Generator: {context['generator']}",
        "",
        "## Summary",
        "",
        f"- Investigation: {inv['id']}",
        f"- Status: {inv['status']}",
        f"- Severity: {inv['severity']}",
        f"- Outcome: {_md_value(inv['result_summary'])}",
        f"- Opened: {_md_value(inv['created_at'])}",
        f"- Updated: {_md_value(inv['updated_at'])}",
        "",
        "## Snapshot",
        "",
    ]
    snapshot = context["snapshot"]
    if snapshot is None:
        lines.append("No snapshot is pinned to this investigation.")
    else:
        lines.extend(
            [
                f"- Snapshot: {snapshot['id']}",
                f"- Tree digest: {snapshot['tree_digest']}",
                f"- Source: {snapshot['source_type']}",
                f"- Commit: {_md_value(snapshot['commit_sha'])}",
            ]
        )
    lines.extend(["", "## Reproduction", ""])
    repro = context["reproduction"]
    if repro is None:
        lines.append("No reproduction result has been recorded.")
    else:
        lines.extend(
            [
                f"- Tool run: {repro['tool_run_id']}",
                f"- Reproduced: {_md_value(repro['reproduced'])}",
                f"- Assertions passed: {_md_value(repro['assertions_passed'])}"
                f" of {_md_value(repro['assertions_total'])}",
                f"- Finished: {_md_value(repro['finished_at'])}",
            ]
        )
    lines.extend(["", "## Evidence", ""])
    if not context["evidence"]:
        lines.append("No evidence has been captured.")
    for item in context["evidence"]:
        lines.extend(
            [
                f"### {item['id']}",
                "",
                f"- Kind: {item['kind']}",
                f"- Media: {item['mime_type']} ({item['byte_size']} bytes)",
                f"- SHA-256: {item['sha256']}",
                f"- Redaction: {item['redaction_status']}",
                f"- Captured: {_md_value(item['created_at'])}",
                "",
            ]
        )
    lines.extend(["## Hypotheses", ""])
    if not context["hypotheses"]:
        lines.append("No hypotheses have been proposed.")
    for item in context["hypotheses"]:
        lines.extend(
            [
                f"### {item['title']}",
                "",
                f"- Hypothesis: {item['id']}",
                f"- Status: {item['status']}",
                f"- Confidence: {_md_value(item['confidence'])}",
                "",
                item["description"],
                "",
            ]
        )
    lines.extend(["## Patches", ""])
    if not context["patches"]:
        lines.append("No patches have been proposed.")
    for item in context["patches"]:
        files = ", ".join(str(path) for path in item["files_changed"]) or "none recorded"
        lines.extend(
            [
                f"### {item['id']}",
                "",
                f"- Status: {item['status']}",
                f"- Approval: {item['approval_status']}",
                f"- Diff SHA-256: {item['diff_sha256']}",
                f"- Files: {files}",
                f"- Approved: {_md_value(item['approved_at'])}",
                f"- Applied: {_md_value(item['applied_at'])}",
                "",
                item["summary"],
                "",
            ]
        )
    lines.extend(["## Verification", ""])
    if not context["verification_runs"]:
        lines.append("No verification runs have been recorded.")
    for run in context["verification_runs"]:
        lines.extend(
            [
                f"### {run['id']}",
                "",
                f"- Phase: {run['phase']}",
                f"- Status: {run['status']}",
                f"- Summary: {_md_value(run['summary'])}",
                "",
            ]
        )
        if not run["checks"]:
            lines.extend(["No checks were recorded for this run.", ""])
        for check in run["checks"]:
            lines.append(
                f"- {check['display_name']} [{check['check_key']}]: {check['status']}"
                f" (exit {_md_value(check['exit_code'])})"
            )
        lines.append("")
    lines.extend(["## Limitations", ""])
    for limitation in context["limitations"]:
        lines.append(f"- {limitation}")
    lines.append("")
    return ("\n".join(lines)).encode("utf-8")


def _html_value(value: Any) -> str:
    return html.escape(_md_value(value), quote=True)


def render_report_html(context: dict[str, Any]) -> bytes:
    """Render the context as standalone HTML (pure, deterministic).

    Inline styles only, no external references; every value escaped.
    """
    inv = context["investigation"]
    parts = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{html.escape(str(inv['title']), quote=True)} — investigation report</title>",
        "<style>body{font-family:system-ui,sans-serif;max-width:72ch;margin:2rem auto;"
        "padding:0 1rem;color:#1a1a1a}h1{font-size:1.5rem}h2{font-size:1.2rem;"
        "border-bottom:1px solid #ccc;padding-bottom:.25rem}code{font-size:.85em;"
        "background:#f4f4f4;padding:.1em .3em;border-radius:4px}li{margin:.2rem 0}</style>",
        "</head>",
        "<body>",
        f"<h1>Investigation report: {html.escape(str(inv['title']), quote=True)}</h1>",
        f"<p>Generator: <code>{html.escape(str(context['generator']), quote=True)}</code></p>",
        "<h2>Summary</h2>",
        "<ul>",
        f"<li>Investigation: <code>{inv['id']}</code></li>",
        f"<li>Status: {html.escape(str(inv['status']), quote=True)}</li>",
        f"<li>Severity: {html.escape(str(inv['severity']), quote=True)}</li>",
        f"<li>Outcome: {_html_value(inv['result_summary'])}</li>",
        f"<li>Opened: {_html_value(inv['created_at'])}</li>",
        f"<li>Updated: {_html_value(inv['updated_at'])}</li>",
        "</ul>",
        "<h2>Snapshot</h2>",
    ]
    snapshot = context["snapshot"]
    if snapshot is None:
        parts.append("<p>No snapshot is pinned to this investigation.</p>")
    else:
        parts.extend(
            [
                "<ul>",
                f"<li>Snapshot: <code>{snapshot['id']}</code></li>",
                f"<li>Tree digest: <code>{snapshot['tree_digest']}</code></li>",
                f"<li>Source: {html.escape(str(snapshot['source_type']), quote=True)}</li>",
                f"<li>Commit: {_html_value(snapshot['commit_sha'])}</li>",
                "</ul>",
            ]
        )
    parts.append("<h2>Reproduction</h2>")
    repro = context["reproduction"]
    if repro is None:
        parts.append("<p>No reproduction result has been recorded.</p>")
    else:
        parts.extend(
            [
                "<ul>",
                f"<li>Tool run: <code>{repro['tool_run_id']}</code></li>",
                f"<li>Reproduced: {_html_value(repro['reproduced'])}</li>",
                f"<li>Assertions passed: {_html_value(repro['assertions_passed'])}"
                f" of {_html_value(repro['assertions_total'])}</li>",
                f"<li>Finished: {_html_value(repro['finished_at'])}</li>",
                "</ul>",
            ]
        )
    parts.append("<h2>Evidence</h2>")
    if not context["evidence"]:
        parts.append("<p>No evidence has been captured.</p>")
    for item in context["evidence"]:
        parts.extend(
            [
                f"<h3><code>{item['id']}</code></h3>",
                "<ul>",
                f"<li>Kind: {html.escape(str(item['kind']), quote=True)}</li>",
                f"<li>Media: {html.escape(str(item['mime_type']), quote=True)}"
                f" ({item['byte_size']} bytes)</li>",
                f"<li>SHA-256: <code>{item['sha256']}</code></li>",
                f"<li>Redaction: {html.escape(str(item['redaction_status']), quote=True)}</li>",
                f"<li>Captured: {_html_value(item['created_at'])}</li>",
                "</ul>",
            ]
        )
    parts.append("<h2>Hypotheses</h2>")
    if not context["hypotheses"]:
        parts.append("<p>No hypotheses have been proposed.</p>")
    for item in context["hypotheses"]:
        parts.extend(
            [
                f"<h3>{html.escape(str(item['title']), quote=True)}</h3>",
                "<ul>",
                f"<li>Hypothesis: <code>{item['id']}</code></li>",
                f"<li>Status: {html.escape(str(item['status']), quote=True)}</li>",
                f"<li>Confidence: {_html_value(item['confidence'])}</li>",
                "</ul>",
                f"<p>{html.escape(str(item['description']), quote=True)}</p>",
            ]
        )
    parts.append("<h2>Patches</h2>")
    if not context["patches"]:
        parts.append("<p>No patches have been proposed.</p>")
    for item in context["patches"]:
        files = ", ".join(html.escape(str(path), quote=True) for path in item["files_changed"])
        parts.extend(
            [
                f"<h3><code>{item['id']}</code></h3>",
                "<ul>",
                f"<li>Status: {html.escape(str(item['status']), quote=True)}</li>",
                f"<li>Approval: {html.escape(str(item['approval_status']), quote=True)}</li>",
                f"<li>Diff SHA-256: <code>{item['diff_sha256']}</code></li>",
                f"<li>Files: {files or 'none recorded'}</li>",
                f"<li>Approved: {_html_value(item['approved_at'])}</li>",
                f"<li>Applied: {_html_value(item['applied_at'])}</li>",
                "</ul>",
                f"<p>{html.escape(str(item['summary']), quote=True)}</p>",
            ]
        )
    parts.append("<h2>Verification</h2>")
    if not context["verification_runs"]:
        parts.append("<p>No verification runs have been recorded.</p>")
    for run in context["verification_runs"]:
        parts.extend(
            [
                f"<h3><code>{run['id']}</code></h3>",
                "<ul>",
                f"<li>Phase: {html.escape(str(run['phase']), quote=True)}</li>",
                f"<li>Status: {html.escape(str(run['status']), quote=True)}</li>",
                f"<li>Summary: {_html_value(run['summary'])}</li>",
                "</ul>",
            ]
        )
        if not run["checks"]:
            parts.append("<p>No checks were recorded for this run.</p>")
        else:
            parts.append("<ul>")
            for check in run["checks"]:
                parts.append(
                    f"<li>{html.escape(str(check['display_name']), quote=True)}"
                    f" [{html.escape(str(check['check_key']), quote=True)}]:"
                    f" {html.escape(str(check['status']), quote=True)}"
                    f" (exit {_html_value(check['exit_code'])})</li>"
                )
            parts.append("</ul>")
    parts.append("<h2>Limitations</h2>")
    parts.append("<ul>")
    for limitation in context["limitations"]:
        parts.append(f"<li>{html.escape(str(limitation), quote=True)}</li>")
    parts.append("</ul>")
    parts.extend(["</body>", "</html>", ""])
    return ("\n".join(parts)).encode("utf-8")


def render_context(context: dict[str, Any], report_format: str) -> bytes:
    """Render one context in the requested format (pure dispatch)."""
    if report_format == "md":
        return render_report_markdown(context)
    if report_format == "html":
        return render_report_html(context)
    raise ApiError(422, "VALIDATION_ERROR", "The report format is not supported.")


def _generate(session: Session, row: Report, store: ObjectStore | None) -> dict:
    """Render one queued/running row and store its bytes (sync core).

    Shared by the API request path and the worker handler: transitions
    running → ready on success, running → blocked on redaction failure
    (409), running → failed on storage failure (503). The row keeps its
    terminal state so history shows what happened.
    """
    if row.status not in ("queued", "running"):
        raise ApiError(409, "INVALID_STATE", "The report is already finished.")
    if row.format not in REPORT_FORMATS:
        raise ApiError(422, "VALIDATION_ERROR", "The report format is not supported.")
    row.status = "running"
    row.error_code = None
    row.error_message = None
    session.commit()
    try:
        context = build_report_context(session, row.investigation_id)
    except ApiError as exc:
        if exc.code == "EVIDENCE_NOT_READY":
            row.status = "blocked"
            row.error_code = exc.code
            row.error_message = exc.message
            session.commit()
        raise
    payload = render_context(context, row.format)
    digest = hashlib.sha256(payload).hexdigest()
    key = report_key(row.id, row.format)
    settings = get_settings()
    active_store = store or get_store()
    fd, tmp_path = tempfile.mkstemp(prefix="meridian-report-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
        byte_size = active_store.put_file(
            settings.s3_evidence_bucket, key, tmp_path, content_type=MIME_BY_FORMAT[row.format]
        )
    except StorageError as exc:
        row.status = "failed"
        row.error_code = exc.code
        row.error_message = exc.message
        session.commit()
        raise ApiError(503, exc.code, exc.message) from exc
    finally:
        with contextlib.suppress(OSError):
            os.remove(tmp_path)
    row.status = "ready"
    row.digest_sha256 = digest
    row.storage_key = key
    row.byte_size = byte_size
    session.commit()
    session.refresh(row)
    return serialize_file_report(row)


def request_report(
    session: Session,
    user: User,
    investigation_id: uuid.UUID,
    report_format: str,
    store: ObjectStore | None = None,
) -> dict:
    """Queue and synchronously generate one NEW file report (M10).

    History is append-only: every request is a fresh row; nothing is
    overwritten. Generation is deterministic and container-free (pure
    render of persisted rows), so the API completes it in-request like
    ingestion — the worker handler covers queued rows for async legs.
    """
    inv, role = investigation_access(session, user, investigation_id)
    if role not in CONTRIBUTOR_ROLES:
        raise access_denied()
    if report_format not in REPORT_FORMATS:
        raise ApiError(422, "VALIDATION_ERROR", "The report format is not supported.")
    latest_patch = (
        session.execute(
            select(Patch.id)
            .where(Patch.investigation_id == inv.id)
            .order_by(desc(Patch.created_at), desc(Patch.id))
            .limit(1)
        )
    ).scalar_one_or_none()
    latest_run = (
        session.execute(
            select(VerificationRun.id)
            .where(VerificationRun.investigation_id == inv.id)
            .order_by(desc(VerificationRun.created_at), desc(VerificationRun.id))
            .limit(1)
        )
    ).scalar_one_or_none()
    row = Report(
        id=uuid.uuid4(),
        investigation_id=inv.id,
        project_id=inv.project_id,
        patch_id=latest_patch,
        verification_run_id=latest_run,
        format=report_format,
        status="queued",
        created_by=user.id,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return _generate(session, row, store)


def generate_pending(
    session: Session,
    investigation_id: uuid.UUID,
    store: ObjectStore | None = None,
) -> list[dict]:
    """Generate every queued file report for one investigation (worker).

    Best-effort per row: each result carries its terminal state, so one
    redaction-blocked report never stops its siblings.
    """
    rows = list(
        session.execute(
            select(Report)
            .where(Report.investigation_id == investigation_id, Report.status == "queued")
            .order_by(Report.created_at.asc(), Report.id.asc())
        ).scalars()
    )
    results = []
    for row in rows:
        try:
            results.append(_generate(session, row, store))
        except ApiError:
            session.refresh(row)
            results.append(serialize_file_report(row))
    return results


def list_reports(
    session: Session, user: User, investigation_id: uuid.UUID, limit: int = 50
) -> list[dict]:
    """Newest-first file reports for one investigation (capped, security T5)."""
    inv, _role = investigation_access(session, user, investigation_id)
    rows = list(
        session.execute(
            select(Report)
            .where(Report.investigation_id == inv.id)
            .order_by(desc(Report.created_at), desc(Report.id))
            .limit(limit)
        ).scalars()
    )
    return [serialize_file_report(row) for row in rows]


def list_workspace_reports(
    session: Session, user: User, workspace_id: uuid.UUID, limit: int = WORKSPACE_LIST_LIMIT
) -> list[dict]:
    """Newest-first file reports across one workspace (capped, for /app/reports)."""
    role = (
        session.execute(
            select(WorkspaceMember.role).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if role is None:
        raise not_found("workspace")
    rows = list(
        session.execute(
            select(Report)
            .join(Project, Project.id == Report.project_id)
            .where(Project.workspace_id == workspace_id)
            .order_by(desc(Report.created_at), desc(Report.id))
            .limit(min(max(limit, 1), WORKSPACE_LIST_LIMIT))
        ).scalars()
    )
    return [serialize_file_report(row) for row in rows]


def get_report(session: Session, user: User, report_id: uuid.UUID) -> dict:
    """One file report's metadata. Keys stay server-side; 404 for foreign."""
    row = (
        session.execute(
            select(Report)
            .join(Project, Project.id == Report.project_id)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Project.workspace_id)
            .where(Report.id == report_id, WorkspaceMember.user_id == user.id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise not_found("report")
    return serialize_file_report(row)


def issue_download_url(
    session: Session,
    user: User,
    report_id: uuid.UUID,
    request_id: str,
    store: ObjectStore | None = None,
) -> dict:
    """Authorize and mint a short-lived report download URL (audited).

    Ready reports only: blocked rows answer 409 (redaction failed), and
    a fresh redaction failure after generation also refuses — fail
    closed rather than serving a stale index.
    """
    found = (
        session.execute(
            select(Report, Project.workspace_id)
            .join(Project, Project.id == Report.project_id)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Project.workspace_id)
            .where(Report.id == report_id, WorkspaceMember.user_id == user.id)
        )
    ).one_or_none()
    if found is None:
        raise not_found("report")
    row, workspace_id = found
    assert isinstance(row, Report)
    if row.status == "blocked":
        raise ApiError(
            409, "EVIDENCE_NOT_READY", "This report is blocked: an artifact failed redaction."
        )
    if row.status != "ready" or row.storage_key is None:
        raise ApiError(409, "REPORT_NOT_READY", "This report is not ready for download.")
    failed = (
        session.execute(
            select(EvidenceArtifact.id)
            .where(
                EvidenceArtifact.investigation_id == row.investigation_id,
                EvidenceArtifact.redaction_status == "failed",
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    if failed is not None:
        raise ApiError(
            409, "EVIDENCE_NOT_READY", "An artifact failed redaction review after generation."
        )
    settings = get_settings()
    active_store = store or get_store()
    assert row.storage_key is not None
    try:
        url = active_store.generate_download_url(
            settings.s3_evidence_bucket, row.storage_key, settings.evidence_download_ttl_seconds
        )
    except StorageError as exc:
        raise ApiError(503, exc.code, exc.message) from exc
    audit_service.append_audit(
        session,
        workspace_id=workspace_id,
        actor_type="user",
        action=audit_service.ACTION_REPORT_DOWNLOAD_ISSUED,
        resource_type="report",
        resource_id=row.id,
        actor=user,
        request_id=request_id,
        metadata={"format": row.format, "byte_size": row.byte_size},
    )
    expires_at = db_now(session) + dt.timedelta(seconds=settings.evidence_download_ttl_seconds)
    return {"url": url, "expires_at": _iso(expires_at)}
