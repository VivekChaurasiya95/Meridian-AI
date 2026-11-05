"""M7-FINISH hypothesis-review tests: verdicts, history, authz, audit.

Pure schema/route-table/health tests run anywhere; HTTP behavior
needs PostgreSQL (CI) with faked object storage.
"""

import io
import pathlib
import sys
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Investigation
from app.schemas import HypothesisReviewUpdate
from app.services import evidence as evidence_service
from app.services import hypotheses as hypothesis_service
from app.services import ingestion as ingestion_service
from app.services import investigations as investigation_service
from app.services import jobs as job_service
from app.services import storage as storage_service
from app.services.model_gateway import parse_hypotheses
from app.services.object_store import FakeObjectStore

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture()
def fake_store(monkeypatch: pytest.MonkeyPatch) -> FakeObjectStore:
    store = FakeObjectStore()
    monkeypatch.setattr(ingestion_service, "_default_store", lambda: store)
    monkeypatch.setattr(storage_service, "get_store", lambda: store)
    monkeypatch.setattr(evidence_service, "get_store", lambda: store)
    return store


def _setup(auth_client: TestClient, slug: str) -> dict:
    workspace = auth_client.post("/api/v1/workspaces", json={"name": slug, "slug": slug}).json()[
        "data"
    ]
    project = auth_client.post(
        f"/api/v1/workspaces/{workspace['id']}/projects",
        json={"name": slug, "slug": slug},
    ).json()["data"]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("index.html", "<h1>x</h1>")
    snapshot = auth_client.post(
        f"/api/v1/projects/{project['id']}/source-uploads",
        files={"file": ("r.zip", buffer.getvalue(), "application/zip")},
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


def _seed_hypothesis(db_session_factory, inv_id: str, store: FakeObjectStore) -> dict:  # type: ignore[no-untyped-def]
    session: Session = db_session_factory()
    try:
        claimed = job_service.claim_job(session, "w-hrev", ("investigation",), 60)
        assert claimed is not None
        job_id = uuid.UUID(claimed["id"])
        project_id = session.execute(
            select(Investigation.project_id).where(Investigation.id == uuid.UUID(inv_id))
        ).scalar_one()
        record = evidence_service.create_evidence(
            session,
            project_id=project_id,
            investigation_id=uuid.UUID(inv_id),
            tool_run_id=None,
            kind="screenshot",
            data=PNG,
            filename_hint="s.png",
            redaction_status="not_required",
            metadata={},
            store=store,
        )
        attempt = investigation_service.start_stage_attempt(
            session,
            job_id=job_id,
            worker_id="w-hrev",
            investigation_id=uuid.UUID(inv_id),
            stage_key="hypothesis_review",
        )
        tool_id = investigation_service.create_tool_run(
            session,
            job_id=job_id,
            worker_id="w-hrev",
            investigation_id=uuid.UUID(inv_id),
            tool_name="model_hypothesis",
            request_summary={},
            stage_execution_id=uuid.UUID(attempt["id"]),
        )
        drafts = parse_hypotheses(
            {
                "hypotheses": [
                    {
                        "title": "Stale state",
                        "description": "The flag never resets.",
                        "confidence": 0.6,
                        "evidence_refs": [
                            {
                                "evidence_id": record["id"],
                                "relationship": "supports",
                                "note": "shows it",
                            }
                        ],
                    }
                ]
            }
        )
        created = hypothesis_service.propose_hypotheses(
            session,
            job_id=job_id,
            worker_id="w-hrev",
            investigation_id=uuid.UUID(inv_id),
            stage_id=uuid.UUID(attempt["id"]),
            tool_run_id=tool_id,
            drafts=drafts,
        )
        return created[0]
    finally:
        session.close()


def _add_member(auth_client: TestClient, workspace_id: str, email: str, role: str) -> None:
    added = auth_client.post(
        f"/api/v1/workspaces/{workspace_id}/members",
        json={"email": email, "role": role},
    )
    assert added.status_code == 201, added.text


# Pure tests (no sockets, no database).


def test_review_schema_accepts_only_verdict_and_note() -> None:
    assert set(HypothesisReviewUpdate.model_fields) == {"verdict", "note"}
    assert HypothesisReviewUpdate(verdict="useful").note is None
    assert HypothesisReviewUpdate(verdict="needs_evidence", note="n").verdict == "needs_evidence"
    with pytest.raises(ValidationError):
        HypothesisReviewUpdate(verdict="maybe")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        HypothesisReviewUpdate(verdict="useful", note="x" * 501)
    with pytest.raises(ValidationError):
        HypothesisReviewUpdate(verdict="useful", status="supported")  # type: ignore[call-arg]


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


def test_hypothesis_detail_routes_present() -> None:
    """Route-table assertion: detail GET + review PATCH, nothing else new."""
    _stub_missing_crypto()
    from app.api import investigations as investigations_api

    found = sorted(
        (sorted(getattr(route, "methods", set())), route.path)
        for route in investigations_api.router.routes
        if getattr(route, "path", "").startswith("/api/v1/hypotheses/")
    )
    assert found == [
        (["GET"], "/api/v1/hypotheses/{hypothesis_id}"),
        (["PATCH"], "/api/v1/hypotheses/{hypothesis_id}"),
    ]


def test_model_check_reports_configured_state(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.api.health as health_module
    from app.services.model_gateway import ProviderConfig

    monkeypatch.setattr(
        health_module, "resolve_text_provider", lambda: ProviderConfig(configured=False)
    )
    assert health_module.check_model_provider() == "not_configured"
    monkeypatch.setattr(
        health_module,
        "resolve_text_provider",
        lambda: ProviderConfig(configured=True, provider=None),
    )
    assert health_module.check_model_provider() == "ok"

    def _boom() -> ProviderConfig:
        raise RuntimeError("settings broken")

    monkeypatch.setattr(health_module, "resolve_text_provider", _boom)
    assert health_module.check_model_provider() == "unavailable"


def test_retryable_from_covers_flow_and_report_generation() -> None:
    assert (
        frozenset((*investigation_service.STAGE_FLOW_M8, "report_generation"))
        == investigation_service.RETRYABLE_FROM
    )
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "services" / "worker"))
    try:
        from investigation import pipeline as pipeline_module
    finally:
        sys.path.remove(str(pathlib.Path(__file__).resolve().parents[3] / "services" / "worker"))
    assert pipeline_module.FLOW == investigation_service.STAGE_FLOW_M8
    assert pipeline_module.TRAILING_RETRYABLE == ("report_generation",)


# HTTP behavior (PostgreSQL + faked storage).


def test_review_lifecycle_and_history(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "hrev1")
    created = _seed_hypothesis(db_session_factory, env["inv"]["id"], fake_store)
    hyp_id = created["id"]

    listed = auth_client.get(f"/api/v1/investigations/{env['inv']['id']}/hypotheses").json()["data"]
    assert listed[0]["reviews"] == []

    first = auth_client.patch(
        f"/api/v1/hypotheses/{hyp_id}", json={"verdict": "needs_evidence", "note": "Look closer."}
    )
    assert first.status_code == 200, first.text
    assert first.json()["data"]["verdict"] == "needs_evidence"
    assert first.json()["data"]["note"] == "Look closer."

    second = auth_client.patch(f"/api/v1/hypotheses/{hyp_id}", json={"verdict": "useful"})
    assert second.status_code == 200, second.text
    assert second.json()["data"]["note"] is None

    detail = auth_client.get(f"/api/v1/hypotheses/{hyp_id}")
    assert detail.status_code == 200
    reviews = detail.json()["data"]["reviews"]
    # Append-only history, oldest first; the newest review is effective.
    assert [row["verdict"] for row in reviews] == ["needs_evidence", "useful"]
    assert reviews[0]["reviewer_user_id"] is not None

    listed = auth_client.get(f"/api/v1/investigations/{env['inv']['id']}/hypotheses").json()["data"]
    assert [row["verdict"] for row in listed[0]["reviews"]] == ["needs_evidence", "useful"]


def test_review_viewer_read_only(
    auth_client: TestClient,
    auth_client_factory,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "hrev2")
    created = _seed_hypothesis(db_session_factory, env["inv"]["id"], fake_store)
    viewer = auth_client_factory("viewer-hrev@example.com")
    _add_member(auth_client, env["workspace"]["id"], "viewer-hrev@example.com", "viewer")

    refused = viewer.patch(f"/api/v1/hypotheses/{created['id']}", json={"verdict": "useful"})
    assert refused.status_code == 403

    detail = viewer.get(f"/api/v1/hypotheses/{created['id']}")
    assert detail.status_code == 200
    listed = viewer.get(f"/api/v1/investigations/{env['inv']['id']}/hypotheses")
    assert listed.status_code == 200


def test_review_foreign_404(
    auth_client: TestClient,
    auth_client_factory,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "hrev3")
    created = _seed_hypothesis(db_session_factory, env["inv"]["id"], fake_store)
    outsider = auth_client_factory("outsider-hrev@example.com")

    assert outsider.get(f"/api/v1/hypotheses/{created['id']}").status_code == 404
    assert (
        outsider.patch(
            f"/api/v1/hypotheses/{created['id']}", json={"verdict": "useful"}
        ).status_code
        == 404
    )
    missing = str(uuid.uuid4())
    assert auth_client.get(f"/api/v1/hypotheses/{missing}").status_code == 404
    assert (
        auth_client.patch(f"/api/v1/hypotheses/{missing}", json={"verdict": "useful"}).status_code
        == 404
    )


def test_review_validation(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "hrev4")
    created = _seed_hypothesis(db_session_factory, env["inv"]["id"], fake_store)
    hyp_id = created["id"]

    assert (
        auth_client.patch(f"/api/v1/hypotheses/{hyp_id}", json={"verdict": "maybe"}).status_code
        == 422
    )
    assert (
        auth_client.patch(
            f"/api/v1/hypotheses/{hyp_id}", json={"verdict": "useful", "note": "x" * 501}
        ).status_code
        == 422
    )
    blank = auth_client.patch(
        f"/api/v1/hypotheses/{hyp_id}", json={"verdict": "rejected", "note": "   "}
    )
    assert blank.status_code == 200
    assert blank.json()["data"]["note"] is None


def test_review_writes_audit(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "hrev5")
    created = _seed_hypothesis(db_session_factory, env["inv"]["id"], fake_store)
    patched = auth_client.patch(
        f"/api/v1/hypotheses/{created['id']}", json={"verdict": "useful", "note": "Confirmed."}
    )
    assert patched.status_code == 200

    events = auth_client.get(
        f"/api/v1/workspaces/{env['workspace']['id']}/audit-events",
        params={"action": "hypothesis.reviewed"},
    )
    assert events.status_code == 200
    items = events.json()["data"]
    assert len(items) == 1
    assert items[0]["resource_id"] == created["id"]
    assert items[0]["metadata"] == {"verdict": "useful"}
