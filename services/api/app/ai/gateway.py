"""Centralized AI gateway (Slices 2-3).

Thin facade over the existing model gateway: task-based routing selects
a verified model + budget, context prep redacts secrets and bounds input,
and every completion is schema-validated by the existing ``parse_*``
validators. Meta Llama is one OpenAI-compatible provider configuration;
when disabled or unconfigured, calls raise ``MODEL_PROVIDER_UNAVAILABLE``
and reasoning stages block honestly (existing behavior preserved).
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

from app.envelope import ApiError

logger = logging.getLogger("meridian.ai")

# Task categories used by pipelines. Keep in sync with worker stages.
TASK_INVESTIGATION_PLANNING = "investigation_planning"
TASK_COMPLEX_REASONING = "complex_reasoning"
TASK_REPOSITORY_ANALYSIS = "repository_analysis"
TASK_SECURITY_INTERPRETATION = "security_interpretation"
TASK_ROOT_CAUSE_ANALYSIS = "root_cause_analysis"
TASK_REMEDIATION_SUGGESTION = "remediation_suggestion"
TASK_REPORT_GENERATION = "report_generation"
TASK_DOCUMENT_SUMMARIZATION = "document_summarization"
TASK_INVESTIGATION_CHAT = "investigation_chat"
TASK_STRUCTURED_EXTRACTION = "structured_extraction"

ALL_TASKS = (
    TASK_INVESTIGATION_PLANNING,
    TASK_COMPLEX_REASONING,
    TASK_REPOSITORY_ANALYSIS,
    TASK_SECURITY_INTERPRETATION,
    TASK_ROOT_CAUSE_ANALYSIS,
    TASK_REMEDIATION_SUGGESTION,
    TASK_REPORT_GENERATION,
    TASK_DOCUMENT_SUMMARIZATION,
    TASK_INVESTIGATION_CHAT,
    TASK_STRUCTURED_EXTRACTION,
)

# Critical tasks never silently fall back to a weaker model.
CRITICAL_TASKS = frozenset(
    {TASK_COMPLEX_REASONING, TASK_ROOT_CAUSE_ANALYSIS, TASK_INVESTIGATION_PLANNING}
)


@dataclass(frozen=True)
class ModelSpec:
    """One registered model candidate (capabilities verified by operator)."""

    model_id: str
    tier: str  # "fast" | "reasoning"
    max_input_tokens: int
    max_output_tokens: int
    supports_json: bool = True
    supports_tools: bool = False
    supports_streaming: bool = False


@dataclass(frozen=True)
class TaskPolicy:
    task: str
    tier: str
    max_input_tokens: int
    max_output_tokens: int
    timeout_seconds: int = 60
    max_attempts: int = 3


# Routing policy: lightweight models for routine work, capable models
# for complex reasoning. Budgets are enforced before every call.
TASK_POLICIES: dict[str, TaskPolicy] = {
    TASK_DOCUMENT_SUMMARIZATION: TaskPolicy(TASK_DOCUMENT_SUMMARIZATION, "fast", 8000, 1500, 45, 3),
    TASK_STRUCTURED_EXTRACTION: TaskPolicy(TASK_STRUCTURED_EXTRACTION, "fast", 8000, 1500, 45, 3),
    TASK_REPOSITORY_ANALYSIS: TaskPolicy(TASK_REPOSITORY_ANALYSIS, "fast", 16000, 2500, 60, 3),
    TASK_SECURITY_INTERPRETATION: TaskPolicy(
        TASK_SECURITY_INTERPRETATION, "reasoning", 16000, 2500, 60, 3
    ),
    TASK_INVESTIGATION_PLANNING: TaskPolicy(
        TASK_INVESTIGATION_PLANNING, "reasoning", 32000, 4000, 90, 3
    ),
    TASK_COMPLEX_REASONING: TaskPolicy(TASK_COMPLEX_REASONING, "reasoning", 32000, 4000, 90, 3),
    TASK_ROOT_CAUSE_ANALYSIS: TaskPolicy(TASK_ROOT_CAUSE_ANALYSIS, "reasoning", 32000, 4000, 90, 3),
    TASK_REMEDIATION_SUGGESTION: TaskPolicy(
        TASK_REMEDIATION_SUGGESTION, "reasoning", 32000, 4000, 90, 3
    ),
    TASK_REPORT_GENERATION: TaskPolicy(TASK_REPORT_GENERATION, "reasoning", 32000, 4000, 90, 3),
    TASK_INVESTIGATION_CHAT: TaskPolicy(TASK_INVESTIGATION_CHAT, "fast", 16000, 2000, 45, 2),
}

_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|password|token|passwd|pwd)\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]+"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END[^-]+-----", re.S),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
)


def redact_secrets(text: str) -> str:
    """Mask credential-shaped substrings before any provider call."""
    out = text
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub("[REDACTED]", out)
    return out


def estimate_tokens(text: str) -> int:
    """Cheap upper-bound estimate (~4 chars/token)."""
    return (len(text) + 3) // 4


def prepare_context(chunks: list[str], max_input_tokens: int) -> str:
    """Deduplicate + bound untrusted context. Repository content is data,
    never instructions: callers must keep it inside the user payload."""
    seen: set[str] = set()
    kept: list[str] = []
    used = 0
    for chunk in chunks:
        clean = redact_secrets(chunk.strip())
        if not clean or clean in seen:
            continue
        seen.add(clean)
        cost = estimate_tokens(clean)
        if used + cost > max_input_tokens:
            break
        kept.append(clean)
        used += cost
    return "\n\n".join(kept)


def policy_for(task: str) -> TaskPolicy:
    policy = TASK_POLICIES.get(task)
    if policy is None:
        raise ApiError(422, "VALIDATION_ERROR", f"Unknown AI task: {task}.")
    return policy


def select_model(task: str, registry: dict[str, ModelSpec], default_model: str) -> ModelSpec:
    """Pick the first registry model matching the task tier.

    Falls back to ``default_model`` so a single-model operator config
    keeps working. Critical tasks keep their reasoning tier.
    """
    policy = policy_for(task)
    for spec in registry.values():
        if spec.tier == policy.tier and spec.model_id:
            return spec
    return ModelSpec(
        model_id=default_model,
        tier=policy.tier,
        max_input_tokens=policy.max_input_tokens,
        max_output_tokens=policy.max_output_tokens,
    )


def meta_registry(
    fast_model: str, reasoning_model: str, default_model: str
) -> dict[str, ModelSpec]:
    """Build the registry from operator-verified model IDs."""
    registry: dict[str, ModelSpec] = {}
    if fast_model:
        registry["fast"] = ModelSpec(fast_model, "fast", 32000, 4096)
    if reasoning_model:
        registry["reasoning"] = ModelSpec(reasoning_model, "reasoning", 128000, 8192)
    if default_model and "fast" not in registry:
        registry["fast"] = ModelSpec(default_model, "fast", 32000, 4096)
    return registry


def timed_complete(provider: object, task: str, system: str, user: str, schema_name: str):  # type: ignore[no-untyped-def]
    """Call the gateway provider with telemetry (no prompt content logged)."""
    policy = policy_for(task)
    if estimate_tokens(system + user) > policy.max_input_tokens:
        raise ApiError(413, "CONTEXT_TOO_LARGE", "The AI context exceeds the task token budget.")
    started = time.monotonic()
    try:
        result = provider.complete_json(system, user, schema_name)  # type: ignore[attr-defined]
    except ApiError:
        logger.warning(
            "ai task failed task=%s schema=%s latency_ms=%d",
            task,
            schema_name,
            int((time.monotonic() - started) * 1000),
        )
        raise
    logger.info(
        "ai task done task=%s model=%s in=%d out=%d attempts=%d latency_ms=%d",
        task,
        result.model,
        result.input_tokens,
        result.output_tokens,
        result.attempts,
        int((time.monotonic() - started) * 1000),
    )
    return result
