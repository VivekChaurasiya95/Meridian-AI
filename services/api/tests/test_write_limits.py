"""Security T5 tests: write rate limits + bounded reads.

Pure limiter/settings tests run anywhere; HTTP behavior needs
PostgreSQL (CI) with faked object storage.
"""

import io
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.security import SlidingWindowLimiter
from app.services import evidence as evidence_service
from app.services import hypotheses as hypothesis_service
from app.services import ingestion as ingestion_service
from app.services import investigations as investigation_service
from app.services import jobs as job_service
from app.services import reports as report_service
from app.services import storage as storage_service
from app.services import verification as verification_service
from app.services.model_gateway import RegressionTestDraft, parse_hypotheses
from app.services.object_store import FakeObjectStore

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


@pytest.fixture()
def fake_store(monkeypatch: pytest.MonkeyPatch) -> FakeObjectStore:
    store = FakeObjectStore()
    monkeypatch.setattr(ingestion_service, "_default_store", lambda: store)
    monkeypatch.setattr(storage_service, "get_store", lambda: store)
    monkeypatch.setattr(evidence_service, "get_store", lambda: store)
    monkeypatch.setattr(report_service, "get_store", lambda: store)
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


def _claim(db_session_factory, worker: str = "w-wl"):  # type: ignore[no-untyped-def]
    session: Session = db_session_factory()
    try:
        claimed = job_service.claim_job(session, worker, ("investigation",), 60)
        assert claimed is not None
        return claimed
    finally:
        session.close()


def _stage_id(db_session_factory, claimed, inv_id: str, key: str) -> uuid.UUID:  # type: ignore[no-untyped-def]
    session: Session = db_session_factory()
    try:
        attempt = investigation_service.start_stage_attempt(
            session,
            job_id=uuid.UUID(claimed["id"]),
            worker_id="w-wl",
            investigation_id=uuid.UUID(inv_id),
            stage_key=key,
        )
        return uuid.UUID(attempt["id"])
    finally:
        session.close()


def _start_run(db_session_factory, claimed, env, stage_id: uuid.UUID, phase: str):  # type: ignore[no-untyped-def]
    session: Session = db_session_factory()
    try:
        return verification_service.start_run(
            session,
            job_id=uuid.UUID(claimed["id"]),
            worker_id="w-wl",
            investigation_id=uuid.UUID(env["inv"]["id"]),
            project_id=uuid.UUID(env["project"]["id"]),
            patch_id=None,
            snapshot_id=uuid.UUID(env["snapshot"]["id"]),
            stage_id=stage_id,
            phase=phase,
            runner_image="img",
            runtime_profile={"profile": "static"},
        )
    finally:
        session.close()


def _make_runnable(db_session_factory, fake_store, claimed, env, title: str = "T") -> dict:  # type: ignore[no-untyped-def]
    from app.services import regression_tests as regression_test_service

    stage_id = _stage_id(db_session_factory, claimed, env["inv"]["id"], "regression_test_creation")
    session: Session = db_session_factory()
    try:
        created = regression_test_service.create_from_drafts(
            session,
            job_id=uuid.UUID(claimed["id"]),
            worker_id="w-wl",
            investigation_id=uuid.UUID(env["inv"]["id"]),
            stage_id=stage_id,
            tool_run_id=None,
            project_id=uuid.UUID(env["project"]["id"]),
            drafts=[
                RegressionTestDraft(
                    title=title,
                    description=None,
                    test_type="e2e",
                    file_path="tests/t.spec",
                    test_name="t",
                    steps=({"action": "assert_text", "selector": "h1", "text": "x"},),
                )
            ],
            store=fake_store,
        )
        return created[0]
    finally:
        session.close()


def _seed_hypothesis(db_session_factory, env: dict, store: FakeObjectStore) -> dict:  # type: ignore[no-untyped-def]
    session: Session = db_session_factory()
    try:
        claimed = job_service.claim_job(session, "w-wl", ("investigation",), 60)
        assert claimed is not None
        job_id = uuid.UUID(claimed["id"])
        record = evidence_service.create_evidence(
            session,
            project_id=uuid.UUID(env["project"]["id"]),
            investigation_id=uuid.UUID(env["inv"]["id"]),
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
            worker_id="w-wl",
            investigation_id=uuid.UUID(env["inv"]["id"]),
            stage_key="hypothesis_review",
        )
        tool_id = investigation_service.create_tool_run(
            session,
            job_id=job_id,
            worker_id="w-wl",
            investigation_id=uuid.UUID(env["inv"]["id"]),
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
            worker_id="w-wl",
            investigation_id=uuid.UUID(env["inv"]["id"]),
            stage_id=uuid.UUID(attempt["id"]),
            tool_run_id=tool_id,
            drafts=drafts,
        )
        return created[0]
    finally:
        session.close()


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


# Pure limiter/settings tests (no sockets, no database).


def test_write_window_slides_with_fake_clock() -> None:
    now = [1000.0]
    limiter = SlidingWindowLimiter(2, 60, clock=lambda: now[0])
    key = "write:user-1"
    assert limiter.allowed(key)
    limiter.register_failure(key)
    limiter.register_failure(key)
    assert not limiter.allowed(key)
    now[0] += 61
    assert limiter.allowed(key)
    limiter.register_failure(key)
    limiter.reset(key)
    assert limiter.allowed(key)


def test_write_limiter_honors_settings() -> None:
    _stub_missing_crypto()
    from app.api.deps import write_limiter

    write_limiter.cache_clear()
    try:
        settings = get_settings()
        assert settings.write_rate_max == 60
        assert settings.write_rate_window_seconds == 3600
        limiter = write_limiter()
        key = f"write-limit-probe:{uuid.uuid4()}"
        for _ in range(settings.write_rate_max):
            assert limiter.allowed(key)
            limiter.register_failure(key)
        assert not limiter.allowed(key)
    finally:
        write_limiter.cache_clear()


def _tighten(monkeypatch: pytest.MonkeyPatch, module, max_attempts: int = 2) -> None:  # type: ignore[no-untyped-def]
    """Swap one route module onto a tiny limiter (per-test isolation)."""
    limiter = SlidingWindowLimiter(max_attempts, 60)
    monkeypatch.setattr(module, "write_limiter", lambda: limiter)


# HTTP rate-limit behavior (PostgreSQL + faked storage).


def test_rerun_rate_limited_per_user(auth_client_factory, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    _stub_missing_crypto()
    from app.api import verification as verification_api

    _tighten(monkeypatch, verification_api)
    owner = auth_client_factory("rater@example.com")
    other = auth_client_factory("rater-other@example.com")
    env = _setup(owner, "wl1")
    inv_id = env["inv"]["id"]
    # Attempts consume quota even when refused downstream (409 here: no
    # runnable tests), mirroring the upload precedent — validation work
    # is bounded too, not just successful writes.
    assert (
        owner.post(f"/api/v1/investigations/{inv_id}/verification-runs", json={}).status_code == 409
    )
    assert (
        owner.post(f"/api/v1/investigations/{inv_id}/verification-runs", json={}).status_code == 409
    )
    limited = owner.post(f"/api/v1/investigations/{inv_id}/verification-runs", json={})
    assert limited.status_code == 429, limited.text
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
    # A different user still has their own bucket.
    assert (
        other.post(f"/api/v1/investigations/{inv_id}/verification-runs", json={}).status_code == 404
    )


def test_report_create_rate_limited(
    auth_client: TestClient,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_missing_crypto()
    from app.api import reports as reports_api

    _tighten(monkeypatch, reports_api)
    env = _setup(auth_client, "wl2")
    inv_id = env["inv"]["id"]
    first = auth_client.post(f"/api/v1/investigations/{inv_id}/reports", json={"format": "md"})
    assert first.status_code == 201, first.text
    second = auth_client.post(f"/api/v1/investigations/{inv_id}/reports", json={"format": "md"})
    assert second.status_code == 201, second.text
    limited = auth_client.post(f"/api/v1/investigations/{inv_id}/reports", json={"format": "md"})
    assert limited.status_code == 429, limited.text
    assert limited.json()["error"]["code"] == "RATE_LIMITED"


def test_report_download_shares_write_bucket(
    auth_client: TestClient,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_missing_crypto()
    from app.api import reports as reports_api

    _tighten(monkeypatch, reports_api)
    env = _setup(auth_client, "wl3")
    inv_id = env["inv"]["id"]
    report_id = auth_client.post(
        f"/api/v1/investigations/{inv_id}/reports", json={"format": "md"}
    ).json()["data"]["id"]
    first = auth_client.post(f"/api/v1/reports/{report_id}/download-url")
    assert first.status_code == 200, first.text
    # Generation already spent one unit: the shared per-user bucket is out.
    limited = auth_client.post(f"/api/v1/reports/{report_id}/download-url")
    assert limited.status_code == 429, limited.text
    assert limited.json()["error"]["code"] == "RATE_LIMITED"


def test_hypothesis_review_rate_limited(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_missing_crypto()
    from app.api import investigations as investigations_api

    _tighten(monkeypatch, investigations_api)
    env = _setup(auth_client, "wl4")
    hyp_id = _seed_hypothesis(db_session_factory, env, fake_store)["id"]
    first = auth_client.patch(f"/api/v1/hypotheses/{hyp_id}", json={"verdict": "useful"})
    assert first.status_code == 200, first.text
    second = auth_client.patch(f"/api/v1/hypotheses/{hyp_id}", json={"verdict": "rejected"})
    assert second.status_code == 200, second.text
    limited = auth_client.patch(f"/api/v1/hypotheses/{hyp_id}", json={"verdict": "useful"})
    assert limited.status_code == 429, limited.text
    assert limited.json()["error"]["code"] == "RATE_LIMITED"


# HTTP bounded-read behavior (PostgreSQL + faked storage).


def test_verification_runs_list_is_capped(
    auth_client: TestClient,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "wl5")
    inv_id = env["inv"]["id"]
    claimed = _claim(db_session_factory)
    stage_id = _stage_id(db_session_factory, claimed, inv_id, "baseline_test_execution")
    run_ids = [
        str(_start_run(db_session_factory, claimed, env, stage_id, "baseline")) for _ in range(3)
    ]
    default = auth_client.get(f"/api/v1/investigations/{inv_id}/verification-runs")
    assert default.status_code == 200, default.text
    assert [run["id"] for run in default.json()["data"]] == run_ids[::-1]
    assert default.json()["page"]["limit"] == 25
    capped = auth_client.get(
        f"/api/v1/investigations/{inv_id}/verification-runs", params={"limit": 2}
    )
    assert [run["id"] for run in capped.json()["data"]] == run_ids[::-1][:2]
    assert capped.json()["page"]["limit"] == 2
    assert (
        auth_client.get(
            f"/api/v1/investigations/{inv_id}/verification-runs", params={"limit": 101}
        ).status_code
        == 422
    )
    assert (
        auth_client.get(
            f"/api/v1/investigations/{inv_id}/verification-runs", params={"limit": 0}
        ).status_code
        == 422
    )


def test_reports_list_is_capped(
    auth_client: TestClient,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "wl6")
    inv_id = env["inv"]["id"]
    report_ids = [
        auth_client.post(f"/api/v1/investigations/{inv_id}/reports", json={"format": "md"}).json()[
            "data"
        ]["id"]
        for _ in range(3)
    ]
    default = auth_client.get(f"/api/v1/investigations/{inv_id}/reports")
    assert default.status_code == 200, default.text
    assert [row["id"] for row in default.json()["data"]] == report_ids[::-1]
    assert default.json()["page"]["limit"] == 50
    capped = auth_client.get(f"/api/v1/investigations/{inv_id}/reports", params={"limit": 2})
    assert [row["id"] for row in capped.json()["data"]] == report_ids[::-1][:2]
    assert (
        auth_client.get(
            f"/api/v1/investigations/{inv_id}/reports", params={"limit": 101}
        ).status_code
        == 422
    )


def test_comparison_list_is_capped(
    auth_client: TestClient,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = _setup(auth_client, "wl7")
    inv_id = env["inv"]["id"]
    claimed = _claim(db_session_factory)
    for title in ("First", "Second", "Third"):
        _make_runnable(db_session_factory, fake_store, claimed, env, title)
    default = auth_client.get(f"/api/v1/investigations/{inv_id}/verification-comparison")
    assert default.status_code == 200, default.text
    assert [row["title"] for row in default.json()["data"]] == ["First", "Second", "Third"]
    assert default.json()["page"]["limit"] == 25
    capped = auth_client.get(
        f"/api/v1/investigations/{inv_id}/verification-comparison", params={"limit": 2}
    )
    assert [row["title"] for row in capped.json()["data"]] == ["First", "Second"]
    assert (
        auth_client.get(
            f"/api/v1/investigations/{inv_id}/verification-comparison", params={"limit": 101}
        ).status_code
        == 422
    )
