"""Investigation report tests (M9 summaries + M10 file reports).

Pure render/schema/route-table tests run anywhere; HTTP and worker
service tests need PostgreSQL (CI) with faked object storage.
"""

import datetime as dt
import io
import re
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, Report
from app.schemas import ReportCreate
from app.services import evidence as evidence_service
from app.services import ingestion as ingestion_service
from app.services import investigations as investigation_service
from app.services import jobs as job_service
from app.services import reports as report_service
from app.services import storage as storage_service
from app.services.model_gateway import parse_report
from app.services.object_store import FakeObjectStore


@pytest.fixture(autouse=True)
def fake_store(monkeypatch: pytest.MonkeyPatch) -> FakeObjectStore:
    store = FakeObjectStore()
    monkeypatch.setattr(ingestion_service, "_default_store", lambda: store)
    monkeypatch.setattr(storage_service, "get_store", lambda: store)
    monkeypatch.setattr(evidence_service, "get_store", lambda: store)
    monkeypatch.setattr(report_service, "get_store", lambda: store)
    return store


def make_zip(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def setup_inv(auth_client: TestClient, slug: str) -> dict:
    workspace = auth_client.post("/api/v1/workspaces", json={"name": slug, "slug": slug}).json()[
        "data"
    ]
    project = auth_client.post(
        f"/api/v1/workspaces/{workspace['id']}/projects",
        json={"name": slug, "slug": slug},
    ).json()["data"]
    snapshot = auth_client.post(
        f"/api/v1/projects/{project['id']}/source-uploads",
        files={"file": ("r.zip", make_zip({"index.html": "<h1>x</h1>"}), "application/zip")},
    ).json()["data"]["snapshot"]
    inv = auth_client.post(
        f"/api/v1/projects/{project['id']}/investigations",
        json={
            "title": "t",
            "bug_report": "b",
            "repository_snapshot_id": snapshot["id"],
        },
    ).json()["data"]
    return {"workspace": workspace, "project": project, "snapshot": snapshot, "inv": inv}


def seed_reports(db_session_factory, inv_id: str, titles: list[str]) -> list[dict]:  # type: ignore[no-untyped-def]
    session: Session = db_session_factory()
    try:
        claimed = job_service.claim_job(session, "w-rep", ("investigation",), 60)
        assert claimed is not None
        job_id = uuid.UUID(claimed["id"])
        attempt = investigation_service.start_stage_attempt(
            session,
            job_id=job_id,
            worker_id="w-rep",
            investigation_id=uuid.UUID(inv_id),
            stage_key="post_patch_verification",
        )
        tool_id = investigation_service.create_tool_run(
            session,
            job_id=job_id,
            worker_id="w-rep",
            investigation_id=uuid.UUID(inv_id),
            tool_name="model_report",
            request_summary={},
            stage_execution_id=uuid.UUID(attempt["id"]),
        )
        created = []
        for title in titles:
            draft = parse_report(
                {
                    "report": {
                        "title": title,
                        "summary": "Summary.",
                        "sections": [{"heading": "Cause", "body": "Body."}],
                    }
                }
            )
            created.append(
                report_service.create_report(
                    session,
                    job_id=job_id,
                    worker_id="w-rep",
                    investigation_id=uuid.UUID(inv_id),
                    stage_id=uuid.UUID(attempt["id"]),
                    tool_run_id=tool_id,
                    model="fake-test",
                    draft=draft,
                )
            )
        return created
    finally:
        session.close()


def test_create_and_read_latest(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = setup_inv(auth_client, "rep1")
    inv_id = env["inv"]["id"]
    first, second = seed_reports(db_session_factory, inv_id, ["First", "Second"])
    assert first["id"] != second["id"]

    response = auth_client.get(f"/api/v1/investigations/{inv_id}/report")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["id"] == second["id"]
    assert data["title"] == "Second"
    assert data["sections"] == [{"heading": "Cause", "body": "Body."}]
    assert data["model"] == "fake-test"


def test_missing_report_is_404(auth_client: TestClient) -> None:
    env = setup_inv(auth_client, "rep2")
    response = auth_client.get(f"/api/v1/investigations/{env['inv']['id']}/report")
    assert response.status_code == 404, response.text


def test_detail_counts_reports(  # type: ignore[no-untyped-def]
    auth_client: TestClient, db_session_factory
) -> None:
    """Detail counts expose M9 summaries so the UI can skip doomed /report fetches."""
    env = setup_inv(auth_client, "rep-count")
    inv_id = env["inv"]["id"]
    detail = auth_client.get(f"/api/v1/investigations/{inv_id}").json()["data"]
    assert detail["counts"]["reports"] == 0
    seed_reports(db_session_factory, inv_id, ["Only"])
    detail = auth_client.get(f"/api/v1/investigations/{inv_id}").json()["data"]
    assert detail["counts"]["reports"] == 1


def test_foreign_report_is_hidden(auth_client_factory, db_session_factory) -> None:  # type: ignore[no-untyped-def]
    owner = auth_client_factory("owner-rep@example.com")
    other = auth_client_factory("other-rep@example.com")
    env = setup_inv(owner, "rep3")
    seed_reports(db_session_factory, env["inv"]["id"], ["Report"])
    response = other.get(f"/api/v1/investigations/{env['inv']['id']}/report")
    assert response.status_code == 404, response.text


# M10 file reports: pure render/schema/route tests (no sockets, no database).


def _context() -> dict:
    inv_id = "11111111-1111-1111-1111-111111111111"
    snap_id = "22222222-2222-2222-2222-222222222222"
    tree = "a" * 64
    ev_id = "33333333-3333-3333-3333-333333333333"
    ev_sha = "b" * 64
    hyp_id = "44444444-4444-4444-4444-444444444444"
    patch_id = "55555555-5555-5555-5555-555555555555"
    diff = "c" * 64
    run_id = "66666666-6666-6666-6666-666666666666"
    return {
        "generator": report_service.REPORT_GENERATOR,
        "investigation": {
            "id": inv_id,
            "title": "Header renders <b>raw</b>",
            "status": "completed",
            "severity": "high",
            "result_summary": "Patch verified: 1 passing.",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-02T00:00:00Z",
        },
        "snapshot": {
            "id": snap_id,
            "tree_digest": tree,
            "source_type": "uploaded_archive",
            "commit_sha": None,
        },
        "reproduction": {
            "tool_run_id": "77777777-7777-7777-7777-777777777777",
            "reproduced": True,
            "assertions_total": 2,
            "assertions_passed": 2,
            "finished_at": "2026-01-01T01:00:00Z",
        },
        "evidence": [
            {
                "id": ev_id,
                "kind": "test_output",
                "mime_type": "application/json",
                "byte_size": 42,
                "sha256": ev_sha,
                "redaction_status": "not_required",
                "created_at": "2026-01-01T00:30:00Z",
            }
        ],
        "hypotheses": [
            {
                "id": hyp_id,
                "title": "Stale cache",
                "description": "The cache key omits the locale.",
                "confidence": 0.75,
                "status": "supported",
                "created_at": "2026-01-01T02:00:00Z",
            }
        ],
        "patches": [
            {
                "id": patch_id,
                "status": "verification_passed",
                "summary": "Key the cache by locale.",
                "diff_sha256": diff,
                "diff_byte_size": 120,
                "files_changed": ["app/cache.py"],
                "approval_status": "approved",
                "approved_at": "2026-01-01T03:00:00Z",
                "applied_at": "2026-01-01T04:00:00Z",
                "created_at": "2026-01-01T02:30:00Z",
            }
        ],
        "verification_runs": [
            {
                "id": run_id,
                "phase": "post_patch",
                "status": "passed",
                "summary": "1 passing",
                "finished_at": "2026-01-01T05:00:00Z",
                "created_at": "2026-01-01T04:30:00Z",
                "checks": [
                    {
                        "check_key": run_id,
                        "display_name": "Locale header",
                        "status": "passed",
                        "exit_code": 0,
                        "duration_ms": 900,
                    }
                ],
            }
        ],
        "limitations": ["Static snapshots only."],
    }


def _empty_context() -> dict:
    context = _context()
    context["investigation"] = {
        **context["investigation"],
        "status": "running",
        "result_summary": None,
    }
    context["snapshot"] = None
    context["reproduction"] = None
    context["evidence"] = []
    context["hypotheses"] = []
    context["patches"] = []
    context["verification_runs"] = []
    context["limitations"] = ["Static snapshots only."]
    return context


def test_file_render_markdown_byte_identical() -> None:
    first = report_service.render_report_markdown(_context())
    second = report_service.render_report_markdown(_context())
    assert first == second
    assert len(first) > 500
    text = first.decode("utf-8")
    assert "11111111-1111-1111-1111-111111111111" in text
    assert "a" * 64 in text
    assert "b" * 64 in text
    assert "c" * 64 in text
    assert "Locale header" in text


def test_file_render_html_byte_identical_and_escaped() -> None:
    first = report_service.render_report_html(_context())
    second = report_service.render_report_html(_context())
    assert first == second
    text = first.decode("utf-8")
    assert text.startswith("<!DOCTYPE html>")
    assert "&lt;b&gt;raw&lt;/b&gt;" in text
    assert "<b>raw</b>" not in text
    assert "http://" not in text and "https://" not in text


def test_file_render_references_only_persisted_ids() -> None:
    """No-invention: every id/hash token in the bytes comes from the context."""
    context = _context()
    allowed: set[str] = set()
    stack = [context]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, str):
            allowed.add(node)
    for payload in (
        report_service.render_report_markdown(context),
        report_service.render_report_html(context),
    ):
        text = payload.decode("utf-8")
        tokens = set(re.findall(r"[0-9a-f]{8}-[0-9a-f-]{27,35}|[0-9a-f]{64}", text))
        assert tokens, "expected id/hash tokens in the rendered report"
        assert tokens <= allowed, f"rendered tokens outside the context: {tokens - allowed}"
    canary = str(uuid.uuid4())
    assert canary.encode() not in report_service.render_report_markdown(context)
    assert canary.encode() not in report_service.render_report_html(context)


def test_file_render_empty_state_is_honest() -> None:
    text = report_service.render_report_markdown(_empty_context()).decode("utf-8")
    assert "No snapshot is pinned" in text
    assert "No reproduction result has been recorded." in text
    assert "No evidence has been captured." in text
    assert "No hypotheses have been proposed." in text
    assert "No patches have been proposed." in text
    assert "No verification runs have been recorded." in text
    assert "verified" not in text.lower()


def test_report_create_schema_accepts_only_format() -> None:
    assert set(ReportCreate.model_fields) == {"format"}
    assert ReportCreate(format="md").format == "md"
    assert ReportCreate(format="html").format == "html"
    with pytest.raises(ValidationError):
        ReportCreate(format="pdf")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ReportCreate(format="md", status="ready")  # type: ignore[call-arg]


def _stub_missing_crypto() -> None:
    """Sandbox shim: stub crypto imports only when they are missing.

    CI installs the full dependency set; this sandbox venv lacks
    PyJWT/cryptography with no network to install them. The router
    import needs them present but never calls them, so bare stubs
    unblock the pure route-table test only.
    """
    import sys
    import types

    try:
        import jwt  # noqa: F401
    except ModuleNotFoundError:
        sys.modules.setdefault("jwt", types.ModuleType("jwt"))
    try:
        from cryptography.x509 import load_pem_x509_certificate  # noqa: F401
    except ModuleNotFoundError:
        package = types.ModuleType("cryptography")
        package.__path__ = []  # type: ignore[attr-defined]
        sys.modules.setdefault("cryptography", package)
        x509 = types.ModuleType("cryptography.x509")
        x509.load_pem_x509_certificate = lambda *args, **kwargs: None  # type: ignore[attr-defined]
        sys.modules.setdefault("cryptography.x509", x509)


def test_report_routes_table() -> None:
    """Route-table assertion: the M10 surface is exactly five routes."""
    _stub_missing_crypto()
    from app.api import reports as reports_api

    found = sorted(
        (sorted(getattr(route, "methods", set())), route.path)
        for route in reports_api.router.routes
    )
    assert found == [
        (["GET"], "/api/v1/investigations/{investigation_id}/reports"),
        (["GET"], "/api/v1/reports/{report_id}"),
        (["GET"], "/api/v1/workspaces/{workspace_id}/reports"),
        (["POST"], "/api/v1/investigations/{investigation_id}/reports"),
        (["POST"], "/api/v1/reports/{report_id}/download-url"),
    ]


# M10 file reports: HTTP + service behavior (PostgreSQL + faked storage).


def _setup_file(auth_client: TestClient, slug: str) -> dict:
    return setup_inv(auth_client, slug)


def _seed_failed_evidence(db_session_factory, env: dict, fake_store: FakeObjectStore) -> str:  # type: ignore[no-untyped-def]
    session: Session = db_session_factory()
    try:
        created = evidence_service.create_evidence(
            session,
            project_id=uuid.UUID(env["project"]["id"]),
            investigation_id=uuid.UUID(env["inv"]["id"]),
            tool_run_id=None,
            kind="log",
            data=b"leaked-token: abc123",
            filename_hint="run.log",
            redaction_status="failed",
            store=fake_store,
        )
        return str(created["id"])
    finally:
        session.close()


def test_file_report_create_ready_and_download(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    from app.config import get_settings

    env = _setup_file(auth_client, "m10a")
    inv_id = env["inv"]["id"]
    created = auth_client.post(f"/api/v1/investigations/{inv_id}/reports", json={"format": "md"})
    assert created.status_code == 201, created.text
    body = created.json()["data"]
    assert body["status"] == "ready"
    assert body["format"] == "md"
    assert re.fullmatch(r"[0-9a-f]{64}", body["digest_sha256"] or "")
    assert body["byte_size"] and body["byte_size"] > 0
    assert "storage_key" not in body
    assert body["patch_id"] is None
    assert body["verification_run_id"] is None

    listed = auth_client.get(f"/api/v1/investigations/{inv_id}/reports")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()["data"]] == [body["id"]]

    fetched = auth_client.get(f"/api/v1/reports/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["data"]["digest_sha256"] == body["digest_sha256"]

    download = auth_client.post(f"/api/v1/reports/{body['id']}/download-url")
    assert download.status_code == 200, download.text
    payload = download.json()["data"]
    assert payload["url"].startswith("https://")
    expires = dt.datetime.fromisoformat(payload["expires_at"].replace("Z", "+00:00"))
    delta = (expires - dt.datetime.now(dt.UTC)).total_seconds()
    ttl = get_settings().evidence_download_ttl_seconds
    assert 0 < delta <= ttl + 30, f"download URL is not short-lived: {delta}s"

    session: Session = db_session_factory()
    try:
        audit = (
            session.execute(
                select(AuditEvent).where(
                    AuditEvent.action == "report.download_issued",
                    AuditEvent.resource_id == uuid.UUID(body["id"]),
                )
            )
        ).scalar_one_or_none()
        assert audit is not None
    finally:
        session.close()


def test_file_report_regeneration_is_byte_identical(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup_file(auth_client, "m10b")
    inv_id = env["inv"]["id"]
    first = auth_client.post(
        f"/api/v1/investigations/{inv_id}/reports", json={"format": "md"}
    ).json()["data"]
    second = auth_client.post(
        f"/api/v1/investigations/{inv_id}/reports", json={"format": "md"}
    ).json()["data"]
    assert first["id"] != second["id"]
    assert first["status"] == second["status"] == "ready"
    assert first["digest_sha256"] == second["digest_sha256"]
    assert first["byte_size"] == second["byte_size"]
    other = auth_client.post(
        f"/api/v1/investigations/{inv_id}/reports", json={"format": "html"}
    ).json()["data"]
    assert other["digest_sha256"] != first["digest_sha256"]

    listed = auth_client.get(f"/api/v1/investigations/{inv_id}/reports").json()["data"]
    assert [row["id"] for row in listed] == [other["id"], second["id"], first["id"]]


def test_file_report_redaction_failed_blocks(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup_file(auth_client, "m10c")
    inv_id = env["inv"]["id"]
    _seed_failed_evidence(db_session_factory, env, fake_store)
    refused = auth_client.post(f"/api/v1/investigations/{inv_id}/reports", json={"format": "md"})
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "EVIDENCE_NOT_READY"

    listed = auth_client.get(f"/api/v1/investigations/{inv_id}/reports").json()["data"]
    assert len(listed) == 1
    assert listed[0]["status"] == "blocked"
    assert listed[0]["digest_sha256"] is None

    download = auth_client.post(f"/api/v1/reports/{listed[0]['id']}/download-url")
    assert download.status_code == 409
    assert download.json()["error"]["code"] == "EVIDENCE_NOT_READY"


def test_file_report_not_ready_download_refused(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup_file(auth_client, "m10d")
    session: Session = db_session_factory()
    try:
        row = Report(
            id=uuid.uuid4(),
            investigation_id=uuid.UUID(env["inv"]["id"]),
            project_id=uuid.UUID(env["project"]["id"]),
            format="md",
            status="queued",
        )
        session.add(row)
        session.commit()
        report_id = str(row.id)
    finally:
        session.close()
    download = auth_client.post(f"/api/v1/reports/{report_id}/download-url")
    assert download.status_code == 409
    assert download.json()["error"]["code"] == "REPORT_NOT_READY"

    session = db_session_factory()
    try:
        assert (
            report_service.generate_pending(session, uuid.UUID(env["inv"]["id"]))[0]["status"]
            == "ready"
        )
    finally:
        session.close()
    retry = auth_client.post(f"/api/v1/reports/{report_id}/download-url")
    assert retry.status_code == 200, retry.text


def test_file_report_authz(
    auth_client_factory, db_session_factory, fake_store: FakeObjectStore
) -> None:  # type: ignore[no-untyped-def]
    owner = auth_client_factory("owner-m10@example.com")
    viewer_client = auth_client_factory("viewer-m10@example.com")
    stranger = auth_client_factory("stranger-m10@example.com")
    env = _setup_file(owner, "m10e")
    inv_id = env["inv"]["id"]
    workspace_id = env["workspace"]["id"]
    created = owner.post(f"/api/v1/investigations/{inv_id}/reports", json={"format": "md"})
    assert created.status_code == 201, created.text
    report_id = created.json()["data"]["id"]

    added = owner.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"email": "viewer-m10@example.com", "role": "viewer"},
    )
    assert added.status_code == 201, added.text

    viewer_post = viewer_client.post(
        f"/api/v1/investigations/{inv_id}/reports", json={"format": "md"}
    )
    assert viewer_post.status_code == 403
    viewer_list = viewer_client.get(f"/api/v1/investigations/{inv_id}/reports")
    assert viewer_list.status_code == 200
    assert [row["id"] for row in viewer_list.json()["data"]] == [report_id]
    viewer_download = viewer_client.post(f"/api/v1/reports/{report_id}/download-url")
    assert viewer_download.status_code == 200, viewer_download.text

    assert stranger.get(f"/api/v1/investigations/{inv_id}/reports").status_code == 404
    assert stranger.get(f"/api/v1/reports/{report_id}").status_code == 404
    assert (
        stranger.post(f"/api/v1/investigations/{inv_id}/reports", json={"format": "md"}).status_code
        == 404
    )
    assert stranger.post(f"/api/v1/reports/{report_id}/download-url").status_code == 404
    assert stranger.get(f"/api/v1/workspaces/{workspace_id}/reports").status_code == 404

    scoped = owner.get(f"/api/v1/workspaces/{workspace_id}/reports")
    assert scoped.status_code == 200
    assert [row["id"] for row in scoped.json()["data"]] == [report_id]
    unknown = owner.get(f"/api/v1/workspaces/{uuid.uuid4()}/reports")
    assert unknown.status_code == 404


def test_file_report_rejects_bad_format_and_fields(auth_client: TestClient) -> None:
    env = _setup_file(auth_client, "m10f")
    inv_id = env["inv"]["id"]
    bad_format = auth_client.post(
        f"/api/v1/investigations/{inv_id}/reports", json={"format": "pdf"}
    )
    assert bad_format.status_code == 422
    unknown_field = auth_client.post(
        f"/api/v1/investigations/{inv_id}/reports", json={"format": "md", "status": "ready"}
    )
    assert unknown_field.status_code == 422
    missing = auth_client.post(f"/api/v1/investigations/{inv_id}/reports", json={})
    assert missing.status_code == 422
