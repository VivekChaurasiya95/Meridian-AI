"""Investigation pipeline tests (M6): fake daemon, real Postgres.

The container runtime is faked (build/run/archive extraction); the
database, stage machine, evidence indexing, and activity/audit writes
are all real. Daemon-contact behavior stays for the integration stage.
"""

import io
import json
import pathlib
import sys
import tarfile
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "services" / "worker"))

from investigation import InvestigationFailure
from investigation.pipeline import run_investigation

from app.envelope import ApiError
from app.models import (
    ActivityEvent,
    EvidenceArtifact,
    Hypothesis,
    Investigation,
    InvestigationReport,
    InvestigationStage,
    Patch,
    RegressionTest,
    ToolRun,
    VerificationCheck,
    VerificationRun,
)
from app.services import evidence as evidence_service
from app.services import ingestion as ingestion_service
from app.services import investigations as investigation_service
from app.services import jobs as job_service
from app.services import storage as storage_service
from app.services.model_gateway import FakeModelProvider
from app.services.object_store import FakeObjectStore

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
TRACE = b"PK\x03\x04" + b"\x00" * 64


def _out_tar(
    extra: dict[str, bytes] | None = None,
    reproduced: bool = True,
) -> bytes:
    result = {
        "version": 1,
        "reproduced": reproduced,
        "route": "/",
        "assertions": [{"index": 0, "selector": "h1", "passed": reproduced}],
        "failed_step": None,
        "console_errors": 0,
        "failed_requests": 0,
        "trace_omitted": False,
        "playwright_version": "1.49.0",
    }
    files = {
        "result.json": json.dumps(result).encode(),
        "console.json": b"[]",
        "network.json": b"[]",
        "00-init.png": PNG,
        "final.png": PNG,
        "trace.zip": TRACE,
        **(extra or {}),
    }
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(name=f"meridian-out/{name}")
            info.size = len(data)
            info.mtime = 0
            tar.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


class FakeContainer:
    def __init__(self, out_tar: bytes, exit_code: int = 0) -> None:
        self._out_tar = out_tar
        self._exit_code = exit_code
        self.started = False
        self.removed = False
        self.labels: dict = {}
        self.attrs = {"State": {"Status": "created", "ExitCode": 0}}

    def start(self) -> None:
        self.started = True
        self.attrs["State"]["Status"] = "exited"
        self.attrs["State"]["ExitCode"] = self._exit_code

    def reload(self) -> None:
        pass

    def kill(self) -> None:
        self.attrs["State"]["Status"] = "exited"

    def remove(self, force: bool = False) -> None:
        assert force
        self.removed = True

    def logs(self, stdout: bool = False, stderr: bool = False):  # type: ignore[no-untyped-def]
        return b"repro ok\n" if stdout else b""

    def get_archive(self, path):  # type: ignore[no-untyped-def]
        assert path == "/tmp/meridian-out"
        return iter([self._out_tar]), {"name": "meridian-out"}


class FakeContainers:
    def __init__(self, container: FakeContainer) -> None:
        self.container = container
        self.created_kwargs: dict = {}

    def create(self, **kwargs):  # type: ignore[no-untyped-def]
        self.created_kwargs = kwargs
        return self.container

    def list(self, all: bool = False, filters=None):  # type: ignore[no-untyped-def]
        return []


class FakeImages:
    def __init__(self) -> None:
        self.built: list = []
        self.removed: list = []

    def build(self, **kwargs):  # type: ignore[no-untyped-def]
        self.built.append(kwargs)

        class Image:
            id = "sha256:fake"

        return Image(), []

    def remove(self, **kwargs):  # type: ignore[no-untyped-def]
        self.removed.append(kwargs)


class FakeClient:
    def __init__(self, container: FakeContainer) -> None:
        self.containers = FakeContainers(container)
        self.images = FakeImages()

    def ping(self) -> None:
        return None


@pytest.fixture(autouse=True)
def fake_store(monkeypatch: pytest.MonkeyPatch) -> FakeObjectStore:
    store = FakeObjectStore()
    monkeypatch.setattr(ingestion_service, "_default_store", lambda: store)
    monkeypatch.setattr(storage_service, "get_store", lambda: store)
    monkeypatch.setattr(evidence_service, "get_store", lambda: store)
    return store


def make_zip(entries: dict[str, str]) -> bytes:
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def setup_inv(auth_client: TestClient, slug: str, entries: dict[str, str] | None = None) -> dict:
    workspace = auth_client.post("/api/v1/workspaces", json={"name": slug, "slug": slug}).json()[
        "data"
    ]
    project = auth_client.post(
        f"/api/v1/workspaces/{workspace['id']}/projects",
        json={"name": slug, "slug": slug},
    ).json()["data"]
    snapshot = auth_client.post(
        f"/api/v1/projects/{project['id']}/source-uploads",
        files={
            "file": (
                "r.zip",
                make_zip(entries or {"index.html": "<h1>x</h1>", "app.js": "1"}),
                "application/zip",
            )
        },
    ).json()["data"]["snapshot"]
    inv = auth_client.post(
        f"/api/v1/projects/{project['id']}/investigations",
        json={
            "title": "t",
            "bug_report": "b",
            "repository_snapshot_id": snapshot["id"],
            "reproduction_context": {
                "route": "/",
                "steps": [{"action": "assert_text", "selector": "h1", "text": "x"}],
            },
        },
    ).json()["data"]
    return {"workspace": workspace, "project": project, "snapshot": snapshot, "inv": inv}


PATCH_DIFF = """--- a/index.html
+++ b/index.html
@@ -1 +1 @@
-<h1>x</h1>
+<h1>fixed</h1>
"""


def _hypotheses_sample() -> dict:
    return {
        "hypotheses": [
            {
                "title": "Stale flag",
                "description": "The flag never resets.",
                "confidence": 0.5,
                "evidence_refs": [],
            }
        ]
    }


def _tests_sample() -> dict:
    return {
        "tests": [
            {
                "title": "Header shows stale value",
                "description": "Asserts the buggy header text.",
                "test_type": "e2e",
                "file_path": "tests/header.spec",
                "test_name": "header shows stale value",
                "steps": [{"action": "assert_text", "selector": "h1", "text": "x"}],
            }
        ]
    }


def _patch_sample() -> dict:
    return {"summary": "Reset the header flag.", "diff": PATCH_DIFF}


def _tests_sample_two() -> dict:
    first = dict(_tests_sample()["tests"][0])
    second = dict(first)
    second["title"] = "Header shows stale value twice"
    second["test_name"] = "header shows stale value twice"
    return {"tests": [first, second]}


def test_pipeline_completes_with_evidence(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = setup_inv(auth_client, "pipe1")
    inv_id = env["inv"]["id"]
    session: Session = db_session_factory()
    try:
        claimed = job_service.claim_job(session, "w-pipe", ("investigation",), 60)
        assert claimed is not None
    finally:
        session.close()
    client = FakeClient(FakeContainer(_out_tar()))
    fake_model = FakeModelProvider([_hypotheses_sample(), _tests_sample(), _patch_sample()])
    outcome = run_investigation(
        db_session_factory,
        claimed,
        "w-pipe",
        client=client,
        store=fake_store,
        model_provider=fake_model,
    )
    assert outcome["parked"] is True
    assert outcome["status"] == "awaiting_approval"

    session = db_session_factory()
    try:
        stages = list(
            session.execute(
                select(InvestigationStage)
                .where(InvestigationStage.investigation_id == uuid.UUID(inv_id))
                .order_by(InvestigationStage.created_at.asc(), InvestigationStage.id.asc())
            ).scalars()
        )
        assert [(s.stage_key, s.status) for s in stages] == [
            ("project_inspection", "completed"),
            ("reproduction", "completed"),
            ("evidence_analysis", "completed"),
            ("hypothesis_review", "completed"),
            ("regression_test_creation", "completed"),
            ("baseline_test_execution", "completed"),
            ("patch_proposal", "completed"),
            ("awaiting_user_approval", "completed"),
        ]
        hypotheses = list(
            session.execute(
                select(Hypothesis).where(Hypothesis.investigation_id == uuid.UUID(inv_id))
            ).scalars()
        )
        assert [h.title for h in hypotheses] == ["Stale flag"]
        evidence = list(
            session.execute(
                select(EvidenceArtifact).where(
                    EvidenceArtifact.investigation_id == uuid.UUID(inv_id)
                )
            ).scalars()
        )
        # Repro run (6) + test artifact (1) + baseline run (6) + verdict (1).
        assert len(evidence) == 14
        assert {row.kind for row in evidence} == {
            "log",
            "network_summary",
            "screenshot",
            "trace",
            "other",
            "test_output",
        }
        runs = list(
            session.execute(
                select(ToolRun).where(ToolRun.investigation_id == uuid.UUID(inv_id))
            ).scalars()
        )
        assert sorted((run.tool_name, run.status) for run in runs) == [
            ("browser_repro", "succeeded"),
            ("browser_repro", "succeeded"),
            ("model_hypothesis", "succeeded"),
            ("model_patch", "succeeded"),
            ("model_tests", "succeeded"),
        ]
        by_name = {run.tool_name: run for run in runs}
        assert by_name["model_hypothesis"].result_summary["hypothesis_ids"]
        assert by_name["model_tests"].result_summary["test_ids"]
        assert by_name["model_patch"].result_summary["patch_id"]
        first_repro = next(run for run in runs if run.tool_name == "browser_repro")
        assert first_repro.request_summary["steps"][0] == {
            "action": "assert_text",
            "selector": "h1",
            "text": "[provided]",
        }
        events = list(
            session.execute(
                select(ActivityEvent.event_type).where(
                    ActivityEvent.investigation_id == uuid.UUID(inv_id)
                )
            ).scalars()
        )
        assert "investigation.completed" not in events
        assert "investigation.awaiting_approval" in events
        assert "patch.submitted" in events
        inv = session.get(Investigation, uuid.UUID(inv_id))
        assert inv is not None and inv.status == "awaiting_approval"
        assert inv.result_summary is None
        tests = list(
            session.execute(
                select(RegressionTest).where(RegressionTest.investigation_id == uuid.UUID(inv_id))
            ).scalars()
        )
        assert [(t.title, t.status) for t in tests] == [
            ("Header shows stale value", "baseline_failed")
        ]
        patches = list(
            session.execute(
                select(Patch).where(Patch.investigation_id == uuid.UUID(inv_id))
            ).scalars()
        )
        assert len(patches) == 1
        assert patches[0].status == "awaiting_approval"
        assert patches[0].approval_status == "pending"
        assert patches[0].files_changed == [
            {"path": "index.html", "change": "modified", "additions": 1, "deletions": 1}
        ]
        v_runs = list(
            session.execute(
                select(VerificationRun).where(VerificationRun.investigation_id == uuid.UUID(inv_id))
            ).scalars()
        )
        assert [(r.phase, r.status) for r in v_runs] == [("baseline", "failed")]
        checks = list(
            session.execute(
                select(VerificationCheck).where(
                    VerificationCheck.verification_run_id == v_runs[0].id
                )
            ).scalars()
        )
        assert [(c.status, c.exit_code) for c in checks] == [("failed", 1)]
    finally:
        session.close()
    # The container ran the fixed repro argv on a per-execution image.
    created = client.containers.created_kwargs
    assert created["command"] == ["python", "/work/Meridian.rules/repro.py"]
    assert str(created["image"]).startswith("meridian-repro-")
    assert created["network_mode"] == "none"


def test_pipeline_blocks_without_html(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = setup_inv(auth_client, "pipe2", {"notes.txt": "no html here"})
    session: Session = db_session_factory()
    try:
        claimed = job_service.claim_job(session, "w-pipe", ("investigation",), 60)
        assert claimed is not None
    finally:
        session.close()
    client = FakeClient(FakeContainer(_out_tar()))
    try:
        run_investigation(db_session_factory, claimed, "w-pipe", client=client, store=fake_store)
    except InvestigationFailure as exc:
        assert exc.code == "PROFILE_UNSUPPORTED"
    else:
        raise AssertionError("expected PROFILE_UNSUPPORTED")
    session = db_session_factory()
    try:
        inv = session.get(Investigation, uuid.UUID(env["inv"]["id"]))
        assert inv is not None and inv.status == "blocked"
    finally:
        session.close()


def test_pipeline_cancel_unwinds(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = setup_inv(auth_client, "pipe3")
    session: Session = db_session_factory()
    try:
        claimed = job_service.claim_job(session, "w-pipe", ("investigation",), 60)
        assert claimed is not None
    finally:
        session.close()
    client = FakeClient(FakeContainer(_out_tar()))
    outcome = run_investigation(
        db_session_factory,
        claimed,
        "w-pipe",
        client=client,
        store=fake_store,
        is_cancelled=lambda: True,
    )
    assert outcome == {"cancelled": True, "investigation_id": env["inv"]["id"]}
    session = db_session_factory()
    try:
        inv = session.get(Investigation, uuid.UUID(env["inv"]["id"]))
        assert inv is not None and inv.status == "cancelled", inv.status if inv else None
    finally:
        session.close()


def test_pipeline_retry_from_stage(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = setup_inv(auth_client, "pipe4")
    inv_id = uuid.UUID(env["inv"]["id"])
    session: Session = db_session_factory()
    try:
        claimed = job_service.claim_job(session, "w-pipe", ("investigation",), 60)
        assert claimed is not None
        job_id = uuid.UUID(claimed["id"])
        for key in ("project_inspection", "reproduction"):
            attempt = investigation_service.start_stage_attempt(
                session,
                job_id=job_id,
                worker_id="w-pipe",
                investigation_id=inv_id,
                stage_key=key,
            )
            investigation_service.finish_stage_attempt(
                session,
                job_id=job_id,
                worker_id="w-pipe",
                stage_id=uuid.UUID(attempt["id"]),
                status="completed",
                output_summary={},
            )
        tool_id = investigation_service.create_tool_run(
            session,
            job_id=job_id,
            worker_id="w-pipe",
            investigation_id=inv_id,
            tool_name="browser_repro",
            request_summary={},
        )
        investigation_service.finish_tool_run(
            session,
            tool_run_id=tool_id,
            status="succeeded",
            result_summary={"reproduced": False, "assertions_total": 1},
        )
    finally:
        session.close()
    retry_job = dict(claimed)
    retry_job["payload"] = {"investigation_id": str(inv_id), "from_stage": "evidence_analysis"}
    fake_model = FakeModelProvider(
        [
            {"hypotheses": [{"title": "t", "description": "d", "confidence": None}]},
            _tests_sample(),
            _patch_sample(),
        ]
    )
    client = FakeClient(FakeContainer(_out_tar()))
    outcome = run_investigation(
        db_session_factory,
        retry_job,
        "w-pipe",
        client=client,
        store=fake_store,
        model_provider=fake_model,
    )
    assert outcome["parked"] is True
    session = db_session_factory()
    try:
        keys = list(
            session.execute(
                select(InvestigationStage.stage_key).where(
                    InvestigationStage.investigation_id == inv_id
                )
            ).scalars()
        )
        assert sorted(keys) == [
            "awaiting_user_approval",
            "baseline_test_execution",
            "evidence_analysis",
            "hypothesis_review",
            "patch_proposal",
            "project_inspection",
            "regression_test_creation",
            "reproduction",
        ]
        inv = session.get(Investigation, inv_id)
        assert inv is not None and inv.status == "awaiting_approval"
    finally:
        session.close()


def test_stage_ownership_refused(
    auth_client: TestClient,
    db_session_factory,  # type: ignore[no-untyped-def]
) -> None:
    env = setup_inv(auth_client, "pipe5")
    session: Session = db_session_factory()
    try:
        claimed = job_service.claim_job(session, "w-pipe", ("investigation",), 60)
        assert claimed is not None
        try:
            investigation_service.start_stage_attempt(
                session,
                job_id=uuid.UUID(claimed["id"]),
                worker_id="impostor",
                investigation_id=uuid.UUID(env["inv"]["id"]),
                stage_key="reproduction",
            )
        except ApiError as exc:
            assert exc.code == "LEASE_LOST"
        else:
            raise AssertionError("expected LEASE_LOST")
    finally:
        session.close()


def _claim(db_session_factory, worker: str = "w-pipe"):  # type: ignore[no-untyped-def]
    session: Session = db_session_factory()
    try:
        claimed = job_service.claim_job(session, worker, ("investigation",), 60)
        assert claimed is not None
        return claimed
    finally:
        session.close()


def test_review_blocks_without_provider(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = setup_inv(auth_client, "rev1")
    claimed = _claim(db_session_factory)
    client = FakeClient(FakeContainer(_out_tar()))
    try:
        run_investigation(db_session_factory, claimed, "w-pipe", client=client, store=fake_store)
    except InvestigationFailure as exc:
        assert exc.code == "MODEL_NOT_CONFIGURED"
        assert exc.retryable is False
    else:
        raise AssertionError("expected MODEL_NOT_CONFIGURED")
    session: Session = db_session_factory()
    try:
        inv = session.get(Investigation, uuid.UUID(env["inv"]["id"]))
        assert inv is not None and inv.status == "blocked"
        review = session.execute(
            select(InvestigationStage).where(
                InvestigationStage.investigation_id == uuid.UUID(env["inv"]["id"]),
                InvestigationStage.stage_key == "hypothesis_review",
            )
        ).scalar_one()
        assert review.status == "blocked"
    finally:
        session.close()


def test_review_resamples_then_links_evidence(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    from app.models import HypothesisEvidence

    env = setup_inv(auth_client, "rev2")
    inv_id = uuid.UUID(env["inv"]["id"])
    claimed = _claim(db_session_factory)

    def _sample_with_real_ids() -> dict:
        session: Session = db_session_factory()
        try:
            evidence_id = session.execute(
                select(EvidenceArtifact.id)
                .where(EvidenceArtifact.investigation_id == inv_id)
                .order_by(EvidenceArtifact.created_at.asc(), EvidenceArtifact.id.asc())
                .limit(1)
            ).scalar_one()
        finally:
            session.close()
        return {
            "hypotheses": [
                {
                    "title": "Linked cause",
                    "description": "Grounded in captured output.",
                    "confidence": 0.9,
                    "evidence_refs": [
                        {
                            "evidence_id": str(evidence_id),
                            "relationship": "supports",
                            "note": "shows the fault",
                        }
                    ],
                }
            ]
        }

    fake_model = FakeModelProvider(
        [{"not": "hypotheses"}, _sample_with_real_ids, _tests_sample(), _patch_sample()]
    )
    client = FakeClient(FakeContainer(_out_tar()))
    outcome = run_investigation(
        db_session_factory,
        claimed,
        "w-pipe",
        client=client,
        store=fake_store,
        model_provider=fake_model,
    )
    assert outcome["parked"] is True
    assert len(fake_model.calls) == 4
    session: Session = db_session_factory()
    try:
        links = list(session.execute(select(HypothesisEvidence)).scalars())
        assert len(links) == 1
        assert links[0].relationship == "supports"
        run = session.execute(
            select(ToolRun).where(
                ToolRun.investigation_id == inv_id, ToolRun.tool_name == "model_hypothesis"
            )
        ).scalar_one()
        assert run.status == "succeeded"
    finally:
        session.close()


def test_review_provider_outage_stays_running(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = setup_inv(auth_client, "rev3")
    claimed = _claim(db_session_factory)
    fake_model = FakeModelProvider([ApiError(503, "MODEL_PROVIDER_UNAVAILABLE", "down")])
    client = FakeClient(FakeContainer(_out_tar()))
    try:
        run_investigation(
            db_session_factory,
            claimed,
            "w-pipe",
            client=client,
            store=fake_store,
            model_provider=fake_model,
        )
    except InvestigationFailure as exc:
        assert exc.code == "MODEL_PROVIDER_UNAVAILABLE"
        assert exc.retryable is True
    else:
        raise AssertionError("expected provider outage")
    session: Session = db_session_factory()
    try:
        inv = session.get(Investigation, uuid.UUID(env["inv"]["id"]))
        assert inv is not None and inv.status == "running"
    finally:
        session.close()


def _park_first_leg(  # type: ignore[no-untyped-def]
    auth_client, db_session_factory, fake_store, slug
):
    """Run inspection → proposal and park at the approval gate."""
    env = setup_inv(auth_client, slug)
    claimed = _claim(db_session_factory)
    client = FakeClient(FakeContainer(_out_tar()))
    fake_model = FakeModelProvider([_hypotheses_sample(), _tests_sample(), _patch_sample()])
    outcome = run_investigation(
        db_session_factory,
        claimed,
        "w-pipe",
        client=client,
        store=fake_store,
        model_provider=fake_model,
    )
    assert outcome["parked"] is True
    return env, claimed


def test_second_leg_applies_and_verifies(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    import hashlib
    import tempfile

    from app.models import RepositorySnapshot

    env, _claimed = _park_first_leg(auth_client, db_session_factory, fake_store, "gate1")
    inv_id = env["inv"]["id"]
    patches = auth_client.get(f"/api/v1/investigations/{inv_id}/patches").json()["data"]
    assert len(patches) == 1
    patch = patches[0]
    assert patch["status"] == "awaiting_approval"
    expected_digest = hashlib.sha256(PATCH_DIFF.encode()).hexdigest()
    assert patch["diff_sha256"] == expected_digest
    diff = auth_client.get(f"/api/v1/patches/{patch['id']}/diff").json()["data"]
    assert diff["diff_text"] == PATCH_DIFF
    assert diff["truncated"] is False

    approved = auth_client.post(
        f"/api/v1/patches/{patch['id']}/approve",
        json={
            "diff_sha256": expected_digest,
            "base_snapshot_id": env["snapshot"]["id"],
            "note": "Looks right.",
        },
    )
    assert approved.status_code == 202, approved.text
    assert approved.json()["data"]["application_status"] == "queued"

    claimed = _claim(db_session_factory)
    assert uuid.UUID(claimed["id"]) != uuid.UUID(_claimed["id"])
    client = FakeClient(FakeContainer(_out_tar(reproduced=False)))
    outcome = run_investigation(
        db_session_factory, claimed, "w-pipe", client=client, store=fake_store
    )
    assert outcome["status"] == "completed"

    session: Session = db_session_factory()
    try:
        inv = session.get(Investigation, uuid.UUID(inv_id))
        assert inv is not None and inv.status == "completed"
        assert "Patch verified" in (inv.result_summary or "")
        row = session.get(Patch, uuid.UUID(patch["id"]))
        assert row is not None and row.status == "verification_passed"
        assert row.approval_status == "approved"
        assert row.applied_snapshot_id is not None
        applied_id = row.applied_snapshot_id
        snapshot = session.get(RepositorySnapshot, applied_id)
        assert snapshot is not None
        assert snapshot.id != uuid.UUID(env["snapshot"]["id"])
        test = session.execute(
            select(RegressionTest).where(RegressionTest.investigation_id == uuid.UUID(inv_id))
        ).scalar_one()
        assert test.status == "post_patch_passed"
        runs = list(
            session.execute(
                select(VerificationRun)
                .where(VerificationRun.investigation_id == uuid.UUID(inv_id))
                .order_by(VerificationRun.created_at.asc())
            ).scalars()
        )
        assert [(r.phase, r.status) for r in runs] == [
            ("baseline", "failed"),
            ("post_patch", "passed"),
        ]
        assert runs[1].patch_id == row.id
        assert runs[1].repository_snapshot_id == applied_id
        keys = list(
            session.execute(
                select(InvestigationStage.stage_key).where(
                    InvestigationStage.investigation_id == uuid.UUID(inv_id),
                    InvestigationStage.status == "completed",
                )
            ).scalars()
        )
        assert "patch_application" in keys
        assert "post_patch_verification" in keys
        with tempfile.TemporaryDirectory(prefix="meridian-verify-") as tmpdir:
            storage_service.materialize_for_workspace(
                session,
                uuid.UUID(env["workspace"]["id"]),
                applied_id,
                tmpdir,
                store=fake_store,
            )
            with open(pathlib.Path(tmpdir) / "index.html", encoding="utf-8") as handle:
                assert handle.read() == "<h1>fixed</h1>\n"
    finally:
        session.close()


def _report_sample() -> dict:
    return {
        "report": {
            "title": "Header flag fixed",
            "summary": "The stale header flag was reset on submit.",
            "sections": [
                {"heading": "Root cause", "body": "The flag never reset."},
                {
                    "heading": "Verification",
                    "body": "The gated test passes on the patched tree.",
                },
            ],
        }
    }


def _approve_second_leg(auth_client, db_session_factory, env):  # type: ignore[no-untyped-def]
    import hashlib

    inv_id = env["inv"]["id"]
    patches = auth_client.get(f"/api/v1/investigations/{inv_id}/patches").json()["data"]
    assert len(patches) == 1
    expected_digest = hashlib.sha256(PATCH_DIFF.encode()).hexdigest()
    approved = auth_client.post(
        f"/api/v1/patches/{patches[0]['id']}/approve",
        json={
            "diff_sha256": expected_digest,
            "base_snapshot_id": env["snapshot"]["id"],
            "note": "Looks right.",
        },
    )
    assert approved.status_code == 202, approved.text
    return _claim(db_session_factory)


def test_second_leg_writes_report_with_provider(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env, _claimed = _park_first_leg(auth_client, db_session_factory, fake_store, "repw")
    inv_id = env["inv"]["id"]
    claimed = _approve_second_leg(auth_client, db_session_factory, env)
    client = FakeClient(FakeContainer(_out_tar(reproduced=False)))
    fake_model = FakeModelProvider([_report_sample()])
    outcome = run_investigation(
        db_session_factory,
        claimed,
        "w-pipe",
        client=client,
        store=fake_store,
        model_provider=fake_model,
    )
    assert outcome["status"] == "completed"
    assert len(fake_model.calls) == 1
    assert fake_model.calls[0]["schema"] == "report_v1"

    session: Session = db_session_factory()
    try:
        report = session.execute(
            select(InvestigationReport).where(
                InvestigationReport.investigation_id == uuid.UUID(inv_id)
            )
        ).scalar_one()
        assert report.title == "Header flag fixed"
        assert len(report.sections) == 2
        assert report.model == "fake-test"
        stage = session.execute(
            select(InvestigationStage).where(
                InvestigationStage.investigation_id == uuid.UUID(inv_id),
                InvestigationStage.stage_key == "post_patch_verification",
            )
        ).scalar_one()
        assert stage.output_summary["report_status"] == "ready"
        assert stage.output_summary["report_id"] == str(report.id)
    finally:
        session.close()

    response = auth_client.get(f"/api/v1/investigations/{inv_id}/report")
    assert response.status_code == 200, response.text
    assert response.json()["data"]["title"] == "Header flag fixed"


def test_second_leg_skips_report_without_provider(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env, _claimed = _park_first_leg(auth_client, db_session_factory, fake_store, "reps")
    inv_id = env["inv"]["id"]
    claimed = _approve_second_leg(auth_client, db_session_factory, env)
    client = FakeClient(FakeContainer(_out_tar(reproduced=False)))
    outcome = run_investigation(
        db_session_factory, claimed, "w-pipe", client=client, store=fake_store
    )
    assert outcome["status"] == "completed"

    session: Session = db_session_factory()
    try:
        reports = list(
            session.execute(
                select(InvestigationReport).where(
                    InvestigationReport.investigation_id == uuid.UUID(inv_id)
                )
            ).scalars()
        )
        assert reports == []
        stage = session.execute(
            select(InvestigationStage).where(
                InvestigationStage.investigation_id == uuid.UUID(inv_id),
                InvestigationStage.stage_key == "post_patch_verification",
            )
        ).scalar_one()
        assert stage.output_summary["report_status"] == "skipped_no_provider"
        assert stage.output_summary["report_id"] is None
    finally:
        session.close()

    response = auth_client.get(f"/api/v1/investigations/{inv_id}/report")
    assert response.status_code == 404, response.text


def test_failed_verification_fails_honestly(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    import hashlib

    env, _claimed = _park_first_leg(auth_client, db_session_factory, fake_store, "gate2")
    inv_id = env["inv"]["id"]
    patch = auth_client.get(f"/api/v1/investigations/{inv_id}/patches").json()["data"][0]
    approved = auth_client.post(
        f"/api/v1/patches/{patch['id']}/approve",
        json={
            "diff_sha256": hashlib.sha256(PATCH_DIFF.encode()).hexdigest(),
            "base_snapshot_id": env["snapshot"]["id"],
        },
    )
    assert approved.status_code == 202, approved.text
    claimed = _claim(db_session_factory)
    # The bug still reproduces after the patch: the gate must fail.
    client = FakeClient(FakeContainer(_out_tar(reproduced=True)))
    outcome = run_investigation(
        db_session_factory, claimed, "w-pipe", client=client, store=fake_store
    )
    assert outcome["status"] == "failed"
    session: Session = db_session_factory()
    try:
        inv = session.get(Investigation, uuid.UUID(inv_id))
        assert inv is not None and inv.status == "failed"
        assert "failed verification" in (inv.result_summary or "")
        row = session.get(Patch, uuid.UUID(patch["id"]))
        assert row is not None and row.status == "verification_failed"
        test = session.execute(
            select(RegressionTest).where(RegressionTest.investigation_id == uuid.UUID(inv_id))
        ).scalar_one()
        assert test.status == "post_patch_failed"
    finally:
        session.close()


def test_second_leg_resolves_default_stores(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    """Production worker passes store=None; defaults must resolve.

    The fixture points every default at the fake, so this proves the
    apply leg never dereferences a None store (live-probe regression).
    """
    import hashlib

    env, _claimed = _park_first_leg(auth_client, db_session_factory, fake_store, "gate7")
    inv_id = env["inv"]["id"]
    patch = auth_client.get(f"/api/v1/investigations/{inv_id}/patches").json()["data"][0]
    approved = auth_client.post(
        f"/api/v1/patches/{patch['id']}/approve",
        json={
            "diff_sha256": hashlib.sha256(PATCH_DIFF.encode()).hexdigest(),
            "base_snapshot_id": env["snapshot"]["id"],
        },
    )
    assert approved.status_code == 202, approved.text
    claimed = _claim(db_session_factory)
    client = FakeClient(FakeContainer(_out_tar(reproduced=False)))
    outcome = run_investigation(db_session_factory, claimed, "w-pipe", client=client)
    assert outcome["status"] == "completed"
    session: Session = db_session_factory()
    try:
        row = session.get(Patch, uuid.UUID(patch["id"]))
        assert row is not None and row.status == "verification_passed"
        assert row.applied_snapshot_id is not None
    finally:
        session.close()


def test_reject_completes_without_apply(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env, _claimed = _park_first_leg(auth_client, db_session_factory, fake_store, "gate3")
    inv_id = env["inv"]["id"]
    patch = auth_client.get(f"/api/v1/investigations/{inv_id}/patches").json()["data"][0]
    rejected = auth_client.post(
        f"/api/v1/patches/{patch['id']}/reject", json={"reason": "Too risky."}
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["data"]["status"] == "rejected"
    session: Session = db_session_factory()
    try:
        inv = session.get(Investigation, uuid.UUID(inv_id))
        assert inv is not None and inv.status == "completed"
        assert "rejected" in (inv.result_summary or "").lower()
        assert "No changes applied" in (inv.result_summary or "")
        # No application leg was enqueued.
        assert job_service.claim_job(session, "w-pipe", ("investigation",), 60) is None
    finally:
        session.close()


def test_apply_refuses_without_approval(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    from app.services import patches as patch_service

    env, claimed = _park_first_leg(auth_client, db_session_factory, fake_store, "gate4")
    session: Session = db_session_factory()
    try:
        patch = session.execute(
            select(Patch).where(Patch.investigation_id == uuid.UUID(env["inv"]["id"]))
        ).scalar_one()
        assert patch.status == "awaiting_approval"
        try:
            patch_service.mark_applied(
                session,
                job_id=uuid.UUID(claimed["id"]),
                worker_id="w-pipe",
                patch_id=patch.id,
                applied_snapshot_id=uuid.uuid4(),
            )
        except ApiError as exc:
            assert exc.code == "PATCH_NOT_APPROVED"
        else:
            raise AssertionError("expected PATCH_NOT_APPROVED")
    finally:
        session.close()


def test_baseline_runs_many_tests_with_distinct_executions(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    from app.models import SandboxExecution

    env = setup_inv(auth_client, "gate6")
    inv_id = uuid.UUID(env["inv"]["id"])
    claimed = _claim(db_session_factory)
    client = FakeClient(FakeContainer(_out_tar()))
    fake_model = FakeModelProvider([_hypotheses_sample(), _tests_sample_two(), _patch_sample()])
    outcome = run_investigation(
        db_session_factory,
        claimed,
        "w-pipe",
        client=client,
        store=fake_store,
        model_provider=fake_model,
    )
    assert outcome["parked"] is True
    session: Session = db_session_factory()
    try:
        run = session.execute(
            select(VerificationRun).where(
                VerificationRun.investigation_id == inv_id,
                VerificationRun.phase == "baseline",
            )
        ).scalar_one()
        checks = list(
            session.execute(
                select(VerificationCheck).where(VerificationCheck.verification_run_id == run.id)
            ).scalars()
        )
        assert sorted(c.status for c in checks) == ["failed", "failed"]
        executions = list(
            session.execute(
                select(SandboxExecution).where(SandboxExecution.job_id == uuid.UUID(claimed["id"]))
            ).scalars()
        )
        # Repro run plus one execution per baseline test.
        assert len(executions) == 3
        assert sorted(e.run_key for e in executions)[0] == ""
        assert len({e.run_key for e in executions}) == 3
    finally:
        session.close()


def test_baseline_blocks_without_tests(
    auth_client: TestClient,
    db_session_factory,
    fake_store: FakeObjectStore,  # type: ignore[no-untyped-def]
) -> None:
    env = setup_inv(auth_client, "gate5")
    inv_id = uuid.UUID(env["inv"]["id"])
    session: Session = db_session_factory()
    try:
        claimed = job_service.claim_job(session, "w-pipe", ("investigation",), 60)
        assert claimed is not None
        job_id = uuid.UUID(claimed["id"])
        for key in ("project_inspection", "reproduction", "evidence_analysis", "hypothesis_review"):
            attempt = investigation_service.start_stage_attempt(
                session,
                job_id=job_id,
                worker_id="w-pipe",
                investigation_id=inv_id,
                stage_key=key,
            )
            investigation_service.finish_stage_attempt(
                session,
                job_id=job_id,
                worker_id="w-pipe",
                stage_id=uuid.UUID(attempt["id"]),
                status="completed",
                output_summary={"outcome": "completed"} if key == "evidence_analysis" else {},
            )
    finally:
        session.close()
    retry_job = dict(claimed)
    retry_job["payload"] = {
        "investigation_id": str(inv_id),
        "from_stage": "baseline_test_execution",
    }
    try:
        run_investigation(db_session_factory, retry_job, "w-pipe", store=fake_store)
    except InvestigationFailure as exc:
        assert exc.code == "NO_EXECUTABLE_TESTS"
        assert exc.retryable is False
    else:
        raise AssertionError("expected NO_EXECUTABLE_TESTS")
    session = db_session_factory()
    try:
        inv = session.get(Investigation, inv_id)
        assert inv is not None and inv.status == "blocked"
    finally:
        session.close()
