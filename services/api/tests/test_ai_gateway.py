"""AI gateway tests (Slices 2-3, 8): routing, budgets, redaction.

Pure unit tests with mocked transports. No live Meta key required.
"""

import pytest

from app.ai import (
    TASK_DOCUMENT_SUMMARIZATION,
    TASK_ROOT_CAUSE_ANALYSIS,
    estimate_tokens,
    meta_registry,
    policy_for,
    prepare_context,
    redact_secrets,
    select_model,
    timed_complete,
)
from app.envelope import ApiError
from app.services.model_gateway import FakeModelProvider


def test_task_policies_cover_all_tasks() -> None:
    from app.ai import ALL_TASKS

    for task in ALL_TASKS:
        policy = policy_for(task)
        assert policy.max_input_tokens > 0
        assert policy.max_output_tokens > 0


def test_routing_uses_tier_and_defaults() -> None:
    registry = meta_registry("fast-1", "big-1", "big-1")
    assert select_model(TASK_DOCUMENT_SUMMARIZATION, registry, "big-1").model_id == "fast-1"
    assert select_model(TASK_ROOT_CAUSE_ANALYSIS, registry, "big-1").model_id == "big-1"
    empty = meta_registry("", "", "only-1")
    assert select_model(TASK_ROOT_CAUSE_ANALYSIS, empty, "only-1").model_id == "only-1"


def test_unknown_task_rejected() -> None:
    with pytest.raises(ApiError):
        policy_for("no_such_task")


def test_budget_enforcement_blocks_oversized_context() -> None:
    provider = FakeModelProvider([{"ok": True}])
    big = "x" * 200_000
    with pytest.raises(ApiError) as exc:
        timed_complete(provider, TASK_DOCUMENT_SUMMARIZATION, "sys", big, "report_v1")
    assert exc.value.code == "CONTEXT_TOO_LARGE"


def test_redaction_masks_secrets() -> None:
    leaked = "api_key=supersecret123 and token: abc.def"
    cleaned = redact_secrets(leaked)
    assert "supersecret123" not in cleaned
    assert "[REDACTED]" in cleaned


def test_prepare_context_dedupes_and_bounds() -> None:
    chunks = ["alpha content", "alpha content", "beta content"]
    prepared = prepare_context(chunks, 1000)
    assert prepared.count("alpha content") == 1
    assert estimate_tokens(prepared) <= 1000


def test_meta_providers_fail_closed_when_disabled() -> None:
    from app.ai.providers import require_spark, segment_image

    with pytest.raises(ApiError) as spark_exc:
        require_spark(False, "https://example.invalid/v1", "k", "m")
    assert spark_exc.value.code == "MODEL_PROVIDER_UNAVAILABLE"

    with pytest.raises(ApiError) as sam_exc:
        segment_image(False, "", "", "", "evidence/shot.png")
    assert sam_exc.value.code == "MODEL_PROVIDER_UNAVAILABLE"


def test_timed_complete_returns_validated_result() -> None:
    provider = FakeModelProvider([{"hypotheses": [{"title": "t", "description": "d"}]}])
    result = timed_complete(provider, TASK_ROOT_CAUSE_ANALYSIS, "sys", "user", "hypotheses_v1")
    assert result.document["hypotheses"][0]["title"] == "t"
