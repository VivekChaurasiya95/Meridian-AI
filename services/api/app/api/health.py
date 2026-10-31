"""Liveness and readiness probes (API.md §6.1)."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.db import check_database

router = APIRouter(tags=["system"])


@router.get("/health/live")
def live() -> dict:
    """Process liveness only. No authentication, no dependency checks."""
    return {"status": "ok"}


@router.get("/health/ready")
def ready() -> JSONResponse:
    """Readiness for required dependencies. Response stays sanitized."""
    database_ok = check_database()
    checks = {
        "database": "ok" if database_ok else "unavailable",
        # Honest M1 values: these subsystems do not exist yet (M4/M3).
        "queue": "not_configured",
        "object_storage": "not_configured",
    }
    if not database_ok:
        return JSONResponse(status_code=503, content={"status": "not_ready", "checks": checks})
    return JSONResponse(status_code=200, content={"status": "ready", "checks": checks})
