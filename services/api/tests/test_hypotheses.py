"""Hypothesis tests (M7): worker writes, member reads with evidence links."""

import io
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.envelope import ApiError
from app.models import Investigation
from app.services import evidence as evidence_service
from app.services import hypotheses as hypothesis_service
from app.services import ingestion as ingestion_service
from app.services import investigations as investigation_service
from app.services import jobs as job_service
from app.services import storage as storage_service
from app.services.model_gateway import parse_hypotheses
from app.services.object_store import FakeObjectStore

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture(autouse=True)
def fake_store(monkeypatch: pytest.MonkeyPatch) -> FakeObjectStore:
    store = FakeObjectStore()
    monkeypatch.setattr(ingestion_service, "_default_store", lambda: store)
    monkeypatch.setattr(storage_service, "get_store", lambda: store)
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


def seed_proposals(
    db_session_factory,
    inv_id: str,
    store: FakeObjectStore,
    refs: str = "real",  # type: ignore[no-untyped-def]
) -> list[dict]:
    session: Session = db_session_factory()
    try:
        claimed = job_service.claim_job(session, "w-hyp", ("investigation",), 60)
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
            worker_id="w-hyp",
            investigation_id=uuid.UUID(inv_id),
            stage_key="hypothesis_review",
        )
        tool_id = investigation_service.create_tool_run(
            session,
            job_id=job_id,
            worker_id="w-hyp",
            investigation_id=uuid.UUID(inv_id),
            tool_name="model_hypothesis",
            request_summary={},
            stage_execution_id=uuid.UUID(attempt["id"]),
        )
        evidence_id = record["id"] if refs == "real" else str(uuid.uuid4())
        drafts = parse_hypotheses(
            {
                "hypotheses": [
                    {
                        "title": "Stale state",
                        "description": "The flag never resets.",
                        "confidence": 0.6,
                        "evidence_refs": [
                            {
                                "evidence_id": evidence_id,
                                "relationship": "supports",
                                "note": "shows it",
                            }
                        ],
                    }
                ]
            }
        )
        return hypothesis_service.propose_hypotheses(
            session,
            job_id=job_id,
            worker_id="w-hyp",
            investigation_id=uuid.UUID(inv_id),
            stage_id=uuid.UUID(attempt["id"]),
            tool_run_id=tool_id,
            drafts=drafts,
        )
    finally:
        session.close()


def test_propose_and_list_with_links(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = setup_inv(auth_client, "hyp1")
    created = seed_proposals(db_session_factory, env["inv"]["id"], fake_store)
    assert len(created) == 1
    assert created[0]["links"]["evidence"][0]["relationship"] == "supports"
    assert created[0]["confidence"] == 0.6

    listed = auth_client.get(f"/api/v1/investigations/{env['inv']['id']}/hypotheses").json()["data"]
    assert [row["title"] for row in listed] == ["Stale state"]
    assert listed[0]["links"]["evidence"][0]["kind"] == "screenshot"
    detail = auth_client.get(f"/api/v1/investigations/{env['inv']['id']}").json()["data"]
    assert detail["counts"]["hypotheses"] == 1


def test_propose_rejects_unknown_evidence(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = setup_inv(auth_client, "hyp2")
    with pytest.raises(ApiError) as exc:
        seed_proposals(db_session_factory, env["inv"]["id"], fake_store, refs="bogus")
    assert exc.value.code == "MODEL_OUTPUT_INVALID"


def test_propose_refuses_foreign_job(
    auth_client: TestClient,
    db_session_factory,  # type: ignore[no-untyped-def]
) -> None:
    env = setup_inv(auth_client, "hyp3")
    session: Session = db_session_factory()
    try:
        claimed = job_service.claim_job(session, "w-hyp", ("investigation",), 60)
        assert claimed is not None
        drafts = parse_hypotheses(
            {"hypotheses": [{"title": "t", "description": "d", "confidence": None}]}
        )
        with pytest.raises(ApiError) as exc:
            hypothesis_service.propose_hypotheses(
                session,
                job_id=uuid.UUID(claimed["id"]),
                worker_id="impostor",
                investigation_id=uuid.UUID(env["inv"]["id"]),
                stage_id=uuid.uuid4(),
                tool_run_id=None,
                drafts=drafts,
            )
        assert exc.value.code == "LEASE_LOST"
    finally:
        session.close()


def test_hypotheses_scoped(auth_client_factory, db_session_factory, fake_store) -> None:  # type: ignore[no-untyped-def]
    owner = auth_client_factory("owner-hyp@example.com")
    outsider = auth_client_factory("outsider-hyp@example.com")
    env = setup_inv(owner, "hyp4")
    assert outsider.get(f"/api/v1/investigations/{env['inv']['id']}/hypotheses").status_code == 404
    assert owner.get(f"/api/v1/investigations/{uuid.uuid4()}/hypotheses").status_code == 404
    assert owner.get(f"/api/v1/investigations/{env['inv']['id']}/hypotheses").json()["data"] == []
