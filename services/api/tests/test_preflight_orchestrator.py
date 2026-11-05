"""Preflight execution tests (V1): fake daemon, real Postgres.

The container daemon is faked; everything else is real — upload,
dual materialization, execution rows, stages, assessment persistence,
and cleanup. Scanner stdout fixtures are synthetic and masked.
"""

import glob
import io
import json
import os
import pathlib
import sys
import tarfile
import tempfile
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "services" / "worker"))

from sandbox.exceptions import SandboxError
from security import preflight as preflight_module
from security.orchestrator import run_scanner
from security.preflight import PreflightFailure, run_preflight
from security.scanners.base import ScannerFailure

from app.models import JobStage, SandboxExecution, SecurityAssessment, SecurityFinding
from app.services import ingestion as ingestion_service
from app.services import jobs as job_service
from app.services import storage as storage_service
from app.services.object_store import FakeObjectStore

ENTRIES = {
    "src/app.py": "import subprocess\nsubprocess.run('ls', shell=True)\n",
    ".env": "API_KEY=synthetic-test-value\n",
}

SEMGREP_DOC = {
    "version": "1.183.0",
    "results": [
        {
            "check_id": "meridian-python-subprocess-shell",
            "path": "/work/src/app.py",
            "start": {"line": 2, "col": 1},
            "end": {"line": 2, "col": 20},
            "extra": {
                "message": "shell=True danger",
                "severity": "ERROR",
                "lines": "subprocess.run('ls', shell=True)",
                "metadata": {"category": "injection", "confidence": "HIGH"},
            },
        }
    ],
    "errors": [],
    "paths": {"scanned": ["src/app.py"]},
}

GITLEAKS_DOC = [
    {
        "RuleID": "generic-api-key",
        "Description": "Generic API key",
        "StartLine": 1,
        "EndLine": 1,
        "File": "/work/.env",
        "Secret": "REDACTED",
        "Match": "API_KEY=REDACTED",
        "Fingerprint": "fp-1",
    }
]


class FakeContainer:
    def __init__(self, exit_code=0, exit_after=1, logs_out=b"", logs_err=b""):  # type: ignore[no-untyped-def]
        self._exit_code = exit_code
        self._exit_after = exit_after
        self._logs_out = logs_out
        self._logs_err = logs_err
        self.labels: dict = {}
        self._polls = 0
        self.started = False
        self.removed = False
        self.attrs = {"State": {"Status": "created", "ExitCode": 0}}

    def start(self) -> None:
        self.started = True
        self.attrs["State"]["Status"] = "running"

    def reload(self) -> None:
        self._polls += 1
        if self._polls >= self._exit_after:
            self.attrs["State"]["Status"] = "exited"
            self.attrs["State"]["ExitCode"] = self._exit_code

    def kill(self) -> None:
        self.attrs["State"]["Status"] = "exited"
        self.attrs["State"]["ExitCode"] = 137

    def logs(self, stdout=False, stderr=False):  # type: ignore[no-untyped-def]
        return (self._logs_out if stdout else b"") + (self._logs_err if stderr else b"")

    def remove(self, force: bool = False) -> None:
        assert force
        self.removed = True


class FakeContainers:
    def __init__(self, available) -> None:  # type: ignore[no-untyped-def]
        self.available = list(available)
        self.created_kwargs: list = []

    def create(self, **kwargs):  # type: ignore[no-untyped-def]
        self.created_kwargs.append(kwargs)
        return self.available.pop(0) if self.available else FakeContainer()

    def list(self, all=False, filters=None):  # type: ignore[no-untyped-def]
        return []


class FakeImage:
    id = "sha256:fakeimageid"


class FakeImages:
    def __init__(self) -> None:
        self.built: list = []
        self.removed: list = []

    def build(self, **kwargs):  # type: ignore[no-untyped-def]
        kwargs["fileobj"].seek(0)
        kwargs["context_bytes"] = kwargs["fileobj"].read()
        self.built.append(kwargs)
        return FakeImage(), []

    def remove(self, **kwargs):  # type: ignore[no-untyped-def]
        self.removed.append(kwargs)


class FakeClient:
    def __init__(self, containers) -> None:  # type: ignore[no-untyped-def]
        self.containers = FakeContainers(containers)
        self.images = FakeImages()

    def ping(self) -> None:
        return None


def make_zip(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def make_workspace(client: TestClient, slug: str) -> dict:
    response = client.post("/api/v1/workspaces", json={"name": slug, "slug": slug})
    assert response.status_code == 201, response.text
    return response.json()["data"]


def make_project(client: TestClient, workspace_id: str, slug: str) -> dict:
    response = client.post(
        f"/api/v1/workspaces/{workspace_id}/projects",
        json={"name": slug, "slug": slug},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def upload_data(client: TestClient, project_id: str, data: bytes) -> dict:
    response = client.post(
        f"/api/v1/projects/{project_id}/source-uploads",
        files={"file": ("repo.zip", data, "application/zip")},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


@pytest.fixture()
def db_session(migrated_db: str):  # type: ignore[no-untyped-def]
    engine = create_engine(migrated_db)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def db_session_factory(migrated_db: str):  # type: ignore[no-untyped-def]
    engine = create_engine(migrated_db)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    engine.dispose()


@pytest.fixture(autouse=True)
def fake_store(monkeypatch: pytest.MonkeyPatch) -> FakeObjectStore:
    store = FakeObjectStore()
    monkeypatch.setattr(ingestion_service, "_default_store", lambda: store)
    monkeypatch.setattr(storage_service, "get_store", lambda: store)
    return store


def _setup(auth_client: TestClient, slug: str):  # type: ignore[no-untyped-def]
    workspace = make_workspace(auth_client, f"wx{slug}")
    project = make_project(auth_client, workspace["id"], f"px{slug}")
    data = upload_data(auth_client, project["id"], make_zip(ENTRIES))
    return workspace, project, data


def _claim(db_session: Session, worker_id: str = "w-pre"):  # type: ignore[no-untyped-def]
    claimed = job_service.claim_job(db_session, worker_id, ("security_preflight",), 60)
    assert claimed is not None
    return claimed


def _sandboxes() -> set:
    return set(glob.glob(os.path.join(tempfile.gettempdir(), "meridian-sandbox-src-*")))


def _sem_container() -> FakeContainer:
    return FakeContainer(
        exit_code=0, exit_after=2, logs_out=json.dumps(SEMGREP_DOC).encode()
    )


def _leak_container() -> FakeContainer:
    return FakeContainer(
        exit_code=1, exit_after=2, logs_out=json.dumps(GITLEAKS_DOC).encode()
    )


def _exec_rows(db_session: Session, job_id: str):  # type: ignore[no-untyped-def]
    return (
        db_session.execute(
            select(SandboxExecution).where(
                SandboxExecution.job_id == uuid.UUID(job_id)
            )
        )
        .scalars()
        .all()
    )


def test_full_run_completes_and_persists(
    auth_client: TestClient,
    db_session: Session,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
) -> None:
    _workspace, _project, data = _setup(auth_client, "full")
    claimed = _claim(db_session)
    before = _sandboxes()
    client = FakeClient([_sem_container(), _leak_container()])
    result = run_preflight(
        db_session_factory, claimed, "w-pre", client=client, store=fake_store
    )

    assert result["status"] == "review_required"
    assert result["snapshot_id"] == data["snapshot"]["id"]
    assert result["summary"]["by_severity"]["high"] == 2

    assessment = db_session.execute(
        select(SecurityAssessment).where(
            SecurityAssessment.id == uuid.UUID(result["assessment_id"])
        )
    ).scalar_one()
    assert assessment.status == "review_required"
    assert assessment.generation == 1
    assert assessment.ruleset_version == "preflight-v1"
    assert assessment.scanner_versions["semgrep"] == "1.183.0"

    findings = (
        db_session.execute(
            select(SecurityFinding).where(
                SecurityFinding.assessment_id == assessment.id
            )
        )
        .scalars()
        .all()
    )
    assert len(findings) == 2
    blob = json.dumps([{"t": f.title, "e": f.evidence} for f in findings])
    assert "synthetic-test-value" not in blob
    leak = next(f for f in findings if f.scanner == "gitleaks")
    assert leak.evidence["redacted"] is True
    assert leak.location["path"] == ".env"

    rows = _exec_rows(db_session, claimed["id"])
    assert sorted(row.scanner for row in rows) == ["gitleaks", "semgrep"]
    for row in rows:
        assert row.status == "completed"
        assert row.stdout is None and row.stderr is None
        assert row.cleanup_status == "cleaned"
    sem_row = next(row for row in rows if row.scanner == "semgrep")
    assert sem_row.exit_code == 0
    leak_row = next(row for row in rows if row.scanner == "gitleaks")
    assert leak_row.exit_code == 1

    stages = {
        row.stage_key: row.status
        for row in db_session.execute(
            select(JobStage).where(JobStage.job_id == uuid.UUID(claimed["id"]))
        ).scalars()
    }
    for key in (
        "validate_snapshot",
        "prepare_scan_input",
        "semgrep_scan",
        "gitleaks_scan",
        "normalize_findings",
        "apply_risk_policy",
        "persist_assessment",
        "cleanup",
    ):
        assert stages[key] == "completed", key

    assert len(client.images.removed) == 2
    assert _sandboxes() == before


def test_scanner_build_uses_trusted_image_and_rules(
    auth_client: TestClient,
    db_session: Session,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
) -> None:
    _workspace, _project, _data = _setup(auth_client, "build")
    claimed = _claim(db_session)
    client = FakeClient([_sem_container(), _leak_container()])
    run_preflight(db_session_factory, claimed, "w-pre", client=client, store=fake_store)

    assert len(client.images.built) == 2
    sem_build = client.images.built[0]
    assert sem_build["dockerfile"] == "Meridian.Dockerfile"
    assert sem_build["network_mode"] == "none"
    assert sem_build["pull"] is False
    with tarfile.open(fileobj=io.BytesIO(sem_build["context_bytes"]), mode="r") as tar:
        names = tar.getnames()
        dockerfile = tar.extractfile("Meridian.Dockerfile").read().decode()  # type: ignore[union-attr]
    assert dockerfile.startswith("FROM semgrep/semgrep:1.183.0\n")
    assert "RUN" not in dockerfile
    assert "Meridian.rules/python-security.yml" in names
    assert "src/app.py" in names
    assert ".env" not in names

    leak_build = client.images.built[1]
    with tarfile.open(fileobj=io.BytesIO(leak_build["context_bytes"]), mode="r") as tar:
        names = tar.getnames()
        dockerfile = tar.extractfile("Meridian.Dockerfile").read().decode()  # type: ignore[union-attr]
    assert dockerfile.startswith("FROM zricethezav/gitleaks:v8.30.1\n")
    assert ".env" in names
    assert not any(name.startswith("Meridian.rules") for name in names)

    for kwargs in client.containers.created_kwargs:
        assert kwargs["user"] == "65534:65534"
        assert kwargs["read_only"] is True
        assert kwargs["network_mode"] == "none"
        assert "volumes" not in kwargs


def test_partial_when_one_scanner_fails(
    auth_client: TestClient,
    db_session: Session,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
) -> None:
    _workspace, _project, _data = _setup(auth_client, "part")
    claimed = _claim(db_session)
    bad_leak = FakeContainer(exit_code=1, exit_after=1, logs_out=b"[oops")
    client = FakeClient([_sem_container(), bad_leak])
    result = run_preflight(
        db_session_factory, claimed, "w-pre", client=client, store=fake_store
    )
    assert result["status"] == "partial"
    assert result["summary"]["scanners"]["gitleaks"]["status"] == "failed"
    assert result["summary"]["scanners"]["gitleaks"]["error_code"] == "GITLEAKS_BAD_OUTPUT"
    findings = (
        db_session.execute(
            select(SecurityFinding).where(
                SecurityFinding.assessment_id == uuid.UUID(result["assessment_id"])
            )
        )
        .scalars()
        .all()
    )
    assert len(findings) == 1 and findings[0].scanner == "semgrep"


def test_all_scanners_failed_fails_job(
    auth_client: TestClient,
    db_session: Session,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
) -> None:
    _workspace, _project, data = _setup(auth_client, "fail")
    claimed = _claim(db_session)
    bad_sem = FakeContainer(exit_code=0, exit_after=1, logs_out=b"{oops")
    bad_leak = FakeContainer(exit_code=2, exit_after=1, logs_out=b"")
    client = FakeClient([bad_sem, bad_leak])
    with pytest.raises(PreflightFailure) as exc:
        run_preflight(db_session_factory, claimed, "w-pre", client=client, store=fake_store)
    assert exc.value.code == "SEMGREP_BAD_OUTPUT"
    assert not exc.value.retryable
    assessment = db_session.execute(
        select(SecurityAssessment).where(
            SecurityAssessment.snapshot_id == uuid.UUID(data["snapshot"]["id"])
        )
    ).scalar_one()
    assert assessment.status == "failed"


def test_retry_reuses_assessment_and_execution_attempts(
    auth_client: TestClient,
    db_session: Session,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
) -> None:
    _workspace, _project, _data = _setup(auth_client, "retry")
    claimed = _claim(db_session)
    first_client = FakeClient([_sem_container(), _leak_container()])
    first = run_preflight(
        db_session_factory, claimed, "w-pre", client=first_client, store=fake_store
    )
    claimed["attempts"] = 2
    second_client = FakeClient([_sem_container(), _leak_container()])
    second = run_preflight(
        db_session_factory, claimed, "w-pre", client=second_client, store=fake_store
    )
    assert second["assessment_id"] == first["assessment_id"]
    rows = _exec_rows(db_session, claimed["id"])
    assert sorted((row.attempt, row.scanner) for row in rows) == [
        (1, "gitleaks"),
        (1, "semgrep"),
        (2, "gitleaks"),
        (2, "semgrep"),
    ]
    findings = (
        db_session.execute(
            select(SecurityFinding).where(
                SecurityFinding.assessment_id == uuid.UUID(first["assessment_id"])
            )
        )
        .scalars()
        .all()
    )
    assert len(findings) == 2


def test_cancel_marks_assessment_cancelled(
    auth_client: TestClient,
    db_session: Session,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
) -> None:
    _workspace, _project, data = _setup(auth_client, "cancel")
    claimed = _claim(db_session)
    client = FakeClient([_sem_container(), _leak_container()])
    with pytest.raises(PreflightFailure) as exc:
        run_preflight(
            db_session_factory, claimed, "w-pre", client=client, store=fake_store,
            is_cancelled=lambda: True,
        )
    assert exc.value.code == "EXECUTION_CANCELLED"
    assessment = db_session.execute(
        select(SecurityAssessment).where(
            SecurityAssessment.snapshot_id == uuid.UUID(data["snapshot"]["id"])
        )
    ).scalar_one()
    assert assessment.status == "cancelled"


def test_finding_cap_keeps_highest_severity(
    auth_client: TestClient,
    db_session: Session,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    _workspace, _project, _data = _setup(auth_client, "cap")
    claimed = _claim(db_session)
    monkeypatch.setattr(
        preflight_module, "get_settings", lambda: SimpleNamespace(preflight_max_findings=1)
    )
    client = FakeClient([_sem_container(), _leak_container()])
    result = run_preflight(
        db_session_factory, claimed, "w-pre", client=client, store=fake_store
    )
    assert result["summary"]["persisted"] == 1
    assert result["summary"]["dropped"] == 1
    assert result["summary"]["total"] == 2


def test_run_scanner_rejects_unknown_scanner_and_bad_image(
    db_session_factory,  # type: ignore[no-untyped-def]
    tmp_path,
) -> None:
    with pytest.raises(ScannerFailure):
        run_scanner(
            db_session_factory, scanner="nmap", source_dir=str(tmp_path),
            job_id=uuid.uuid4(), worker_id="w", snapshot_id=uuid.uuid4(), attempt=1,
        )
    with pytest.raises(SandboxError) as exc:
        run_scanner(
            db_session_factory, scanner="semgrep", source_dir=str(tmp_path),
            job_id=uuid.uuid4(), worker_id="w", snapshot_id=uuid.uuid4(), attempt=1,
            image_override="evil:latest",
        )
    assert exc.value.code == "INVALID_PROFILE"


def test_run_scanner_timeout_is_retryable(
    auth_client: TestClient,
    db_session: Session,
    db_session_factory,  # type: ignore[no-untyped-def]
    fake_store: FakeObjectStore,
    tmp_path,
) -> None:
    _workspace, _project, data = _setup(auth_client, "timeout")
    claimed = _claim(db_session)
    (tmp_path / "a.py").write_text("x\n")
    container = FakeContainer(exit_code=0, exit_after=10**9)
    client = FakeClient([container])
    with pytest.raises(ScannerFailure) as exc:
        run_scanner(
            db_session_factory, scanner="gitleaks", source_dir=str(tmp_path),
            job_id=uuid.UUID(claimed["id"]), worker_id="w",
            snapshot_id=uuid.UUID(data["snapshot"]["id"]), attempt=1,
            client=client, timeout_seconds=1,
        )
    assert exc.value.code == "COMMAND_TIMEOUT"
    assert exc.value.retryable


def test_run_scanner_needs_claimed_job(db_session_factory, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from security.preflight import run_preflight as entry

    job = {
        "id": str(uuid.uuid4()),
        "workspace_id": str(uuid.uuid4()),
        "attempts": 0,
        "job_type": "security_preflight",
        "payload": {"snapshot_id": str(uuid.uuid4())},
    }
    with pytest.raises(PreflightFailure) as exc:
        entry(db_session_factory, job, "w")
    assert exc.value.code == "INVALID_JOB"
