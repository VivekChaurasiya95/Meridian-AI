"""File-report generation (M10, worker side): queued rows to bytes.

Renders each queued ``reports`` row from persisted rows only and
stores the bytes privately. Deterministic content — the same
investigation state always yields the same bytes — and fail-closed:
a redaction-failed artifact blocks its report (409 state) instead of
producing a silently incomplete index. Never finalizes the
investigation; that belongs to the verification gate.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.envelope import ApiError
from app.services import investigations as investigation_service
from app.services import reports as report_service
from investigation import InvestigationAbort, InvestigationFailure

logger = logging.getLogger("meridian.investigation.reporting")


def generate_pending_reports(
    session_factory: Any,
    job_id: uuid.UUID,
    worker_id: str,
    investigation_id: uuid.UUID,
    *,
    store: Any = None,
) -> dict:
    """Generate every queued file report for one investigation.

    Requires job ownership like every other worker write path. Each
    row resolves independently to ready/blocked/failed; the summary
    counts them honestly without inventing content.
    """
    try:
        with session_factory() as session:
            investigation_service.require_job_ownership(
                session, job_id, worker_id, investigation_id
            )
    except ApiError as exc:
        if exc.code in ("LEASE_LOST", "JOB_SUPERSEDED"):
            raise InvestigationAbort() from exc
        raise InvestigationFailure(exc.code, exc.message, False) from exc
    try:
        with session_factory() as session:
            results = report_service.generate_pending(session, investigation_id, store)
    except ApiError as exc:
        if exc.code in ("LEASE_LOST", "JOB_SUPERSEDED"):
            raise InvestigationAbort() from exc
        raise InvestigationFailure(exc.code, exc.message, False) from exc
    counts: dict[str, int] = {}
    for item in results:
        status = str(item.get("status", "unknown"))
        counts[status] = counts.get(status, 0) + 1
    logger.info(
        "reports generated investigation_id=%s counts=%s", investigation_id, counts
    )
    return {
        "outcome": "completed",
        "report_count": len(results),
        "report_ids": [str(item["id"]) for item in results],
        "counts": counts,
    }
