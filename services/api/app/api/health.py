"""Liveness and readiness probes (API.md §6.1)."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import get_settings
from app.db import check_database, get_engine
from app.services.object_store import MinioObjectStore

router = APIRouter(tags=["system"])


@router.get("/health/live")
def live() -> dict:
    """Process liveness only. No authentication, no dependency checks."""
    return {"status": "ok"}


def check_job_queue() -> str:
    """Durable job table readability: ok / not_configured / unavailable.

    Never raises and never leaks connection details. ``not_configured``
    means the M4 migration has not been applied; ``unavailable`` means
    the database itself is unreachable (reported separately).
    """
    try:
        engine = get_engine()
        with engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM jobs LIMIT 1"))
        return "ok"
    except Exception as exc:
        message = str(exc).lower()
        if "undefined_table" in message or 'relation "jobs" does not exist' in message:
            return "not_configured"
        return "unavailable"


def check_object_storage() -> str:
    """Repositories bucket reachability: ok / not_configured / unavailable.

    Never raises and never leaks endpoints or credentials.
    ``not_configured`` means the S3 client library is missing;
    ``unavailable`` means MinIO itself is unreachable. The bucket is
    created on demand so its absence alone is not a failure.
    """
    try:
        settings = get_settings()
        store = MinioObjectStore(
            endpoint_url=settings.s3_endpoint_url,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            region=settings.s3_region,
        )
        store.ensure_bucket(settings.s3_repositories_bucket)
        return "ok"
    except ModuleNotFoundError:
        # The S3 client library (boto3) is not installed here.
        return "not_configured"
    except Exception:
        return "unavailable"


@router.get("/health/ready")
def ready() -> JSONResponse:
    """Readiness for required dependencies. Response stays sanitized."""
    database_ok = check_database()
    checks = {
        "database": "ok" if database_ok else "unavailable",
        # The M4 jobs table is the durable queue: readable means configured.
        "queue": check_job_queue() if database_ok else "unavailable",
        # M5.1 persists snapshot content to the private repositories bucket.
        "object_storage": check_object_storage() if database_ok else "unavailable",
    }
    if not database_ok:
        return JSONResponse(status_code=503, content={"status": "not_ready", "checks": checks})
    return JSONResponse(status_code=200, content={"status": "ready", "checks": checks})
