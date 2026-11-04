"""Pure unit tests for the job state machine and retry policy.

No DB, no sockets — they run everywhere (D16 pure tier).
"""

import pytest

from app.envelope import ApiError
from app.services.jobs import (
    JOB_TRANSITIONS,
    STAGE_TRANSITIONS,
    _check_transition,
    backoff_for_attempt,
)


def test_terminal_states_have_no_exits() -> None:
    for status in ("completed", "failed", "cancelled"):
        assert JOB_TRANSITIONS[status] == frozenset()


def test_allowed_job_transitions() -> None:
    assert JOB_TRANSITIONS["queued"] == frozenset({"running", "cancelled"})
    assert JOB_TRANSITIONS["running"] == frozenset(
        {"completed", "retry_wait", "failed", "cancelled"}
    )
    assert JOB_TRANSITIONS["retry_wait"] == frozenset({"queued", "cancelled"})
    # A completed job can never execute again.
    for target in ("running", "queued", "retry_wait", "cancelled", "failed"):
        with pytest.raises(ApiError) as exc_info:
            _check_transition("completed", target)
        assert exc_info.value.code == "INVALID_TRANSITION"


def test_check_transition_accepts_legal_moves() -> None:
    _check_transition("queued", "running")
    _check_transition("running", "retry_wait")
    _check_transition("retry_wait", "queued")
    _check_transition("running", "completed")
    _check_transition("queued", "cancelled")


def test_stage_terminals_have_no_exits() -> None:
    for status in ("completed", "failed", "blocked", "skipped", "cancelled"):
        assert STAGE_TRANSITIONS[status] == frozenset()
    assert STAGE_TRANSITIONS["pending"] == frozenset({"running", "skipped", "cancelled"})
    assert "blocked" in STAGE_TRANSITIONS["running"]


def test_backoff_is_exponential_and_capped() -> None:
    assert backoff_for_attempt(1, 30, 3600) == 30
    assert backoff_for_attempt(2, 30, 3600) == 60
    assert backoff_for_attempt(3, 30, 3600) == 120
    assert backoff_for_attempt(10, 30, 3600) == 3600
    assert backoff_for_attempt(0, 30, 3600) == 30
