# Meridian AI — Meta Llama Integration Plan (Slice 1)

## Current architecture (verified in code)

- Backend: FastAPI in `services/api`. Worker claims durable jobs (`SELECT ... FOR UPDATE SKIP LOCKED`) with leases and heartbeats. No worker HTTP credentials.
- Existing model gateway: `app.services.model_gateway` already provides a `ModelProvider` protocol, `HttpModelProvider` (OpenAI-compatible chat completions, `response_format=json_object`, bounded retries, token/latency accounting), `FakeModelProvider` for tests, and strict validators (`parse_hypotheses`, `parse_regression_tests`, `parse_patch_proposal`, `parse_report`). Reasoning stages block honestly when unconfigured.
- Settings: `app.config.Settings` already has `model_provider`, `model_api_base`, `model_api_key`, `model_name`, `model_timeout_seconds`, `model_max_attempts`. Default `model_provider="fake"` means UNCONFIGURED.
- Pipelines: project intake (ZIP + public GitHub import), snapshots with content-addressed MinIO storage, sandbox execution (allowlisted profiles, network `none`), security preflight (Semgrep + Gitleaks, findings normalized and masked), investigations (M6) with stages/evidence/hypotses/patches/verification.
- Data rules: hypotheses stored separately from evidence. Verification status derives from runner results, never from model claims.

## Decision: extend, do not duplicate

Meta Llama will plug into the existing gateway as another OpenAI-compatible provider configuration. No new parallel AI stack. Business logic keeps calling the gateway; Meta SDKs never leak into services.

## Provider and model notes (verify before enabling)

Meta distributes Llama weights; hosted endpoints are provided by Meta's Llama API and third-party OpenAI-compatible hosts. This integration therefore treats the endpoint as operator configuration (`META_BASE_URL`, `META_API_KEY`, `META_MODEL_*`) and ships **disabled by default**. Before production, confirm the exact model IDs, context windows, JSON/structured output support, function calling, streaming, latency, pricing, and rate limits in the chosen provider's current documentation. Do not enable models whose capability you have not verified.

Recommended routing shape (IDs are operator-verified per provider):

- Fast/extraction tier: small Llama instruct model for summarization, extraction, repository summaries.
- Reasoning tier: larger Llama instruct model for investigation planning, root-cause analysis, report generation.
- Critical reasoning never silently falls back to a weaker model.

## Implementation slices

1. Plan (this file).
2. Centralized gateway: `app/ai/` facade, registry, routing, context prep, redaction, telemetry logging. Reuses `HttpModelProvider`.
3. Task routing policy with per-task budgets/timeouts.
4. Investigation engine: planning/hypotheses/root-cause via gateway with evidence-linked validation.
5. Security interpretation + repository intelligence (post-scanner explanation only).
6. Report generation via `parse_report` with snapshot/policy/model provenance.
7. Investigation chat (evidence-scoped, cited) — only if a chat surface exists; otherwise deferred.
8. Telemetry, UI status, tests, hardening.

## Safety

- Deterministic scanners remain source of truth. Never invent findings, CVEs, or metrics.
- Repository content is untrusted data. System instructions win. Secrets are redacted before any provider call. No credentials, env vars, or session tokens are ever sent.
- No auto-apply of patches. No execution of generated code outside sandbox policy.
- Missing key = provider disabled, app keeps working.

## Verification

- Pure unit tests with mocked HTTP transports. No live key required for the standard suite.
- Gates: `ruff check`, `ruff format --check`, `mypy app`, `pytest` (DB tests use `meridian_test`), web lint/typecheck/build, e2e where applicable.

## Risks / unresolved

- Provider choice (Meta Llama API vs third-party host) determines exact base URL, model IDs, pricing, and rate limits. Operator decision required before enabling.
- Cost depends on input context size; token budgets per task are enforced in routing.
