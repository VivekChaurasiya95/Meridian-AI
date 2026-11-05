# Meridian AI — Implementation Plan (Milestones M1–M10)

All milestones are implemented. Backend, worker, and frontend ship together;
nothing below is aspirational.

- [x] **M1** — App shell, brand system, landing page.
- [x] **M2** — Session auth (password + Firebase social), workspaces, membership roles.
- [x] **M3** — Project onboarding (ZIP validation, inspection, immutable snapshots, content-addressed MinIO storage).
- [x] **M4** — Durable jobs (claim/lease/heartbeat, stages, idempotency) + background worker. GitHub import as worker jobs.
- [x] **M5** — Isolated sandbox execution (network `none`, pinned images) + execution observability.
- [x] **M6** — Investigations, browser reproduction (static profile), evidence artifacts, activity timeline, audit events.
- [x] **M7** — Evidence-grounded hypotheses via the centralized AI gateway (`services/api/app/ai/`). Meta Spark / Meta SAM / Meta Llama plug in as OpenAI-compatible provider configs; disabled by default, fail closed.
- [x] **M8** — Regression tests, baseline/post-patch verification, patch proposals with scoped human approval.
- [x] **M9** — Investigation reports (file generation + downloads), security preflight (Semgrep + Gitleaks + AI interpretation layer).
- [x] **M10** — Verification reruns and baseline-vs-post comparison, in the API (`verification` router) and in the investigation detail UI (`VerificationSection`, with graceful fallback when the endpoint is unavailable).

Conventions: envelope `{data, request_id}` / `{error, request_id}`; workspace-scoped 404s; owner-only deletes; deterministic scanners are the source of findings; model output is schema-validated and never treated as verified evidence.
