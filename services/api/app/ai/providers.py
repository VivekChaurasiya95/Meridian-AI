"""Meta model providers (Spark text + SAM image).

Both providers sit behind the centralized gateway. When disabled or
unconfigured they raise ``MODEL_PROVIDER_UNAVAILABLE`` and pipelines
block honestly. Never log keys or prompt content.
"""

from __future__ import annotations

import logging

from app.config import Settings, get_settings
from app.envelope import ApiError

logger = logging.getLogger("meridian.ai.meta")


def resolve_text_provider(settings: Settings | None = None):  # type: ignore[no-untyped-def]
    """Resolve the text provider: Meta Spark > Meta Llama > existing.

    Returns a ``ProviderConfig``. When nothing is configured the result
    is unconfigured and pipelines block honestly (no fabrication).
    """
    from app.services.model_gateway import (
        HttpModelProvider,
        ProviderConfig,
        get_configured_provider,
    )

    active = settings or get_settings()
    if active.meta_spark_enabled:
        try:
            provider = require_spark(
                True,
                active.meta_spark_base_url,
                active.meta_spark_api_key,
                active.meta_spark_model,
            )
            return ProviderConfig(configured=True, provider=provider)
        except ApiError as exc:
            return ProviderConfig(configured=False, reason=exc.message)
    if active.meta_enabled and active.meta_base_url and active.meta_api_key:
        model = active.meta_model_reasoning or active.meta_model_default
        if model:
            return ProviderConfig(
                configured=True,
                provider=HttpModelProvider(
                    api_base=active.meta_base_url,
                    api_key=active.meta_api_key,
                    model=model,
                    timeout_seconds=active.meta_request_timeout,
                    max_attempts=active.meta_max_retries,
                ),
            )
    return get_configured_provider(active)


def require_spark(enabled: bool, base_url: str, api_key: str, model: str):  # type: ignore[no-untyped-def]
    """Return the existing OpenAI-compatible provider for Meta Spark.

    Spark is invoked through the same chat-completions transport as
    every other provider, so retries, timeouts, and token accounting
    stay in one place.
    """
    from app.services.model_gateway import HttpModelProvider

    if not enabled:
        raise ApiError(503, "MODEL_PROVIDER_UNAVAILABLE", "Meta Spark is disabled.")
    if not base_url or not api_key or not model:
        raise ApiError(503, "MODEL_PROVIDER_UNAVAILABLE", "Meta Spark is not configured.")
    return HttpModelProvider(
        api_base=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=60,
        max_attempts=3,
    )


def segment_image(enabled: bool, base_url: str, api_key: str, model: str, image_ref: str):  # type: ignore[no-untyped-def]
    """Segment one evidence image with Meta SAM (worker-only).

    Validates the request and fails closed until the operator verifies
    the SAM endpoint in provider docs and enables it. No image bytes or
    credentials are logged.
    """
    if not image_ref or len(image_ref) > 2048:
        raise ApiError(422, "VALIDATION_ERROR", "An image reference is required.")
    if not enabled:
        raise ApiError(503, "MODEL_PROVIDER_UNAVAILABLE", "Meta SAM is disabled.")
    if not base_url or not api_key or not model:
        raise ApiError(503, "MODEL_PROVIDER_UNAVAILABLE", "Meta SAM is not configured.")
    # Live SAM call is intentionally not issued here: the worker resolves
    # the evidence artifact, enforces size limits, and posts to the
    # provider endpoint after doc verification.
    logger.info("sam segment requested model=%s ref_len=%d", model, len(image_ref))
    raise ApiError(503, "MODEL_PROVIDER_UNAVAILABLE", "Meta SAM transport is not enabled.")
