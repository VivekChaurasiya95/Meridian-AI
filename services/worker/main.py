"""Meridian AI durable job worker (M4).

Claims jobs from PostgreSQL, owns them through leases + heartbeats, and
processes ONLY safe internal job types:

- ``lifecycle_test``: echoes a short caller note back as the result.
- ``manifest_recheck``: recomputes a snapshot tree digest from stored
  file rows (pure database reads) and compares it to the stored digest.

The worker NEVER executes repository code, runs installs or shells,
starts user applications, or launches user-controlled scripts. Internal
transitions call the service layer directly — there are no worker HTTP
credentials (D45). Each service call uses a short-lived session so
transactions stay short.
"""

import logging
import os
import signal
import socket
import sys
import threading
import time
import uuid
from contextlib import contextmanager

# Locate the API package relative to this file, so the worker runs both
# locally (repo checkout) and in the container (/srv/meridian) with no
# PYTHONPATH setup: <root>/services/worker/main.py -> <root>/services/api.
_WORKER_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_WORKER_DIR), "api"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import get_session_factory  # noqa: E402
from app.envelope import ApiError  # noqa: E402
from app.models import RepositorySnapshot, SnapshotFile  # noqa: E402
from app.services import jobs as job_service  # noqa: E402
from app.services.archive_security import ValidatedEntry, compute_tree_digest  # noqa: E402
from sandbox import orchestrator as sandbox_orchestrator  # noqa: E402
from sandbox.exceptions import SandboxError  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("meridian.worker")

SAFE_JOB_TYPES = ("lifecycle_test", "manifest_recheck", "sandbox_smoke")

_stop = False


def handle_exit(signum, frame):  # type: ignore[no-untyped-def]
    global _stop
    logger.info("shutdown signal received; finishing the current job then exiting")
    _stop = True


def worker_identity() -> str:
    return os.getenv("WORKER_ID") or f"{socket.gethostname()}-{os.getpid()}"


@contextmanager
def session_scope():  # type: ignore[no-untyped-def]
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


class JobFailure(Exception):
    def __init__(self, code: str, message: str, retryable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def stage(session: Session, job_id: uuid.UUID, worker_id: str, key: str, status: str, **kwargs) -> None:  # type: ignore[no-untyped-def]
    job_service.record_stage(session, job_id, worker_id, key, status, **kwargs)


def handle_lifecycle_test(session: Session, job: dict, worker_id: str) -> dict:
    note = str(job["payload"].get("note", ""))[:500]
    job_id = uuid.UUID(job["id"])
    stage(session, job_id, worker_id, "setup", "running")
    stage(session, job_id, worker_id, "setup", "completed", result_summary={"worker": worker_id})
    stage(session, job_id, worker_id, "execute", "running")
    stage(
        session,
        job_id,
        worker_id,
        "execute",
        "completed",
        result_summary={"note_length": len(note)},
    )
    return {"echo": note, "worker": worker_id}


def handle_manifest_recheck(session: Session, job: dict, worker_id: str) -> dict:
    job_id = uuid.UUID(job["id"])
    try:
        snapshot_id = uuid.UUID(str(job["payload"].get("snapshot_id")))
    except (ValueError, TypeError, AttributeError):
        raise JobFailure("INVALID_PAYLOAD", "manifest_recheck needs a snapshot_id.", False) from None
    stage(session, job_id, worker_id, "fetch_manifest", "running")
    rows = list(
        session.execute(
            select(SnapshotFile.path, SnapshotFile.size, SnapshotFile.sha256).where(
                SnapshotFile.snapshot_id == snapshot_id
            )
        ).all()
    )
    stored = (
        session.execute(
            select(RepositorySnapshot.tree_digest).where(RepositorySnapshot.id == snapshot_id)
        )
    ).scalar_one_or_none()
    if stored is None:
        stage(
            session, job_id, worker_id, "fetch_manifest", "failed",
            error_code="SNAPSHOT_NOT_FOUND", error_message="The snapshot no longer exists.",
        )
        raise JobFailure("SNAPSHOT_NOT_FOUND", "The snapshot no longer exists.", False)
    stage(
        session, job_id, worker_id, "fetch_manifest", "completed",
        result_summary={"file_count": len(rows)},
    )
    stage(session, job_id, worker_id, "verify_digest", "running")
    digest = compute_tree_digest(
        [ValidatedEntry(path=path, size=size, sha256=digest) for path, size, digest in rows]
    )
    match = digest == stored
    stage(
        session, job_id, worker_id, "verify_digest",
        "completed" if match else "failed",
        result_summary={"match": match, "file_count": len(rows)},
        **({} if match else {"error_code": "DIGEST_MISMATCH", "error_message": "Stored digest differs."}),
    )
    if not match:
        raise JobFailure("DIGEST_MISMATCH", "The stored digest differs from recomputed.", False)
    return {"match": True, "file_count": len(rows), "tree_digest": digest}


def handle_sandbox_smoke(session: Session, job: dict, worker_id: str) -> dict:
    """Run one approved smoke command in a disposable container.

    The orchestrator owns its own short sessions; this handler only maps
    sandbox failures onto the job lifecycle. Lease loss and cancellation
    abort the run through the watch below; completion refusal in
    ``complete_job`` is the final backstop.
    """
    job_id = uuid.UUID(job["id"])

    def abort_on_lease_loss() -> bool:
        try:
            with session_scope() as check:
                return not job_service.is_running_and_owned(check, job_id, worker_id)
        except Exception:
            logger.warning("lease watch failed job_id=%s", job_id)
            return False

    try:
        return sandbox_orchestrator.execute_job(
            get_session_factory(), job, worker_id, is_cancelled=abort_on_lease_loss
        )
    except SandboxError as exc:
        raise JobFailure(exc.code, exc.message, exc.retryable) from None


HANDLERS = {
    "lifecycle_test": handle_lifecycle_test,
    "manifest_recheck": handle_manifest_recheck,
    "sandbox_smoke": handle_sandbox_smoke,
}


def process_job(job: dict, worker_id: str, lease_seconds: int, heartbeat_seconds: int) -> None:
    job_id = uuid.UUID(job["id"])
    lease_lost = threading.Event()

    def beat() -> None:
        while not lease_lost.wait(heartbeat_seconds / 2):
            try:
                with session_scope() as session:
                    job_service.heartbeat_job(session, job_id, worker_id, lease_seconds)
            except ApiError as exc:
                if exc.code == "LEASE_LOST":
                    logger.warning("lease lost during execution job_id=%s", job_id)
                    lease_lost.set()
                else:
                    logger.warning("heartbeat failed job_id=%s code=%s", job_id, exc.code)
            except Exception:
                logger.exception("heartbeat error job_id=%s", job_id)

    heartbeat = threading.Thread(target=beat, name=f"heartbeat-{job_id}", daemon=True)
    heartbeat.start()
    try:
        handler = HANDLERS.get(job["job_type"])
        if handler is None:
            raise JobFailure("JOB_TYPE_NOT_IMPLEMENTED", "This worker cannot run this job type.", False)
        with session_scope() as session:
            result = handler(session, job, worker_id)
        try:
            with session_scope() as session:
                job_service.complete_job(session, job_id, worker_id, result)
        except ApiError as exc:
            logger.warning("completion refused job_id=%s code=%s", job_id, exc.code)
    except JobFailure as failure:
        try:
            with session_scope() as session:
                job_service.fail_job(
                    session, job_id, worker_id, failure.code, failure.message, failure.retryable
                )
        except ApiError as exc:
            logger.warning("failure record refused job_id=%s code=%s", job_id, exc.code)
    except Exception as exc:
        logger.exception("unexpected worker error job_id=%s", job_id)
        try:
            with session_scope() as session:
                job_service.fail_job(session, job_id, worker_id, "WORKER_ERROR", str(exc)[:500], True)
        except ApiError as nested:
            logger.warning("failure record refused job_id=%s code=%s", job_id, nested.code)
    finally:
        lease_lost.set()
        heartbeat.join(timeout=heartbeat_seconds)


def main() -> None:
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    settings = get_settings()
    worker_id = worker_identity()
    lease_seconds = settings.worker_lease_seconds
    heartbeat_seconds = min(settings.worker_heartbeat_seconds, lease_seconds // 2 or 1)
    poll_seconds = settings.worker_poll_seconds
    logger.info(
        "worker starting worker_id=%s lease_s=%d heartbeat_s=%d poll_s=%d",
        worker_id, lease_seconds, heartbeat_seconds, poll_seconds,
    )
    # Fail fast when the database is unreachable (compose depends_on covers it).
    with session_scope() as session:
        job_service.claim_job(session, worker_id, SAFE_JOB_TYPES, lease_seconds)
    while not _stop:
        claimed: dict | None = None
        with session_scope() as session:
            claimed = job_service.claim_job(session, worker_id, SAFE_JOB_TYPES, lease_seconds)
        if claimed is None:
            time.sleep(poll_seconds)
            continue
        process_job(claimed, worker_id, lease_seconds, heartbeat_seconds)
    logger.info("worker stopped worker_id=%s", worker_id)


if __name__ == "__main__":
    main()
