"""AI gateway facade: task routing over the existing model provider.

Business logic calls the facade instead of HTTP or Meta-specific code.
The underlying transport is the existing OpenAI-compatible
``HttpModelProvider``; Meta Llama is selected purely by operator
configuration (base URL, API key, model IDs).
"""

from app.ai.gateway import (
    ALL_TASKS,
    CRITICAL_TASKS,
    TASK_COMPLEX_REASONING,
    TASK_DOCUMENT_SUMMARIZATION,
    TASK_INVESTIGATION_CHAT,
    TASK_INVESTIGATION_PLANNING,
    TASK_REMEDIATION_SUGGESTION,
    TASK_REPORT_GENERATION,
    TASK_REPOSITORY_ANALYSIS,
    TASK_ROOT_CAUSE_ANALYSIS,
    TASK_SECURITY_INTERPRETATION,
    TASK_STRUCTURED_EXTRACTION,
    ModelSpec,
    TaskPolicy,
    estimate_tokens,
    meta_registry,
    policy_for,
    prepare_context,
    redact_secrets,
    select_model,
    timed_complete,
)

__all__ = [
    "ALL_TASKS",
    "CRITICAL_TASKS",
    "TASK_COMPLEX_REASONING",
    "TASK_DOCUMENT_SUMMARIZATION",
    "TASK_INVESTIGATION_CHAT",
    "TASK_INVESTIGATION_PLANNING",
    "TASK_REMEDIATION_SUGGESTION",
    "TASK_REPORT_GENERATION",
    "TASK_REPOSITORY_ANALYSIS",
    "TASK_ROOT_CAUSE_ANALYSIS",
    "TASK_SECURITY_INTERPRETATION",
    "TASK_STRUCTURED_EXTRACTION",
    "ModelSpec",
    "TaskPolicy",
    "estimate_tokens",
    "meta_registry",
    "policy_for",
    "prepare_context",
    "redact_secrets",
    "select_model",
    "timed_complete",
]
