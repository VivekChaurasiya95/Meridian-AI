# Meridian AI — Architecture Decision Records (Working Log)

This file records implementation decisions made while building Meridian AI.
It is **implementation documentation**, separate from the product specifications
in `public/` (which are never edited). Newest decisions go at the end.

Authority order for conflicts: Security > Product outcomes > Architecture/API
contracts > Database spec > Design system > Implementation plan > existing code.

## Spec-vs-spec conflicts resolved (2026-10-28)

| # | Conflict | Resolution |
|---|----------|------------|
| C1 | No "Milestone" concept in specs; Impl-Plan uses 15 Phases + 7 Iterations, PRD uses 6 Phases | The build sequence follows the Milestone 0–10 plan in the project brief. M0 = Impl-Plan Phase 0 + Iteration 0 controls; M1 = Phase 1 shell + Iteration 1 thin slice + PRD Phase 1 skeleton. |
| C2 | Investigation create flow: ARCHITECTURE two-step (`POST` → `POST …/start`, `/events`) vs API.md single `POST` → `202` with `/activity` + `/stages` | API.md governs (it is the contract). Single `POST …/investigations` → `202`; progress via `/activity` and `/stages`. Applies at M4. |
| C3 | Status vocabulary casing: ARCHITECTURE `UPPER_SNAKE` vs API.md lowercase | Lowercase on the wire and in `text CHECK` constraints, per API.md. |
| C4 | Module layout: `services/api/app/…` + `workers/investigation` (ARCH) vs `backend/app/…` (API) vs `services/api\|orchestrator\|worker` (brief §5, Impl-Plan §7) | Brief/Impl-Plan layout: `apps/web`, `services/api`, `services/orchestrator`, `services/worker`, `packages/*`, top-level `migrations/` and `tests/`. |
| C5 | Queue: ARCH "simple worker may suffice" vs API "durable queue/outbox, never FastAPI BackgroundTasks" | API.md governs reliability: DB-backed job table with leases. No broker unless measured need. Applies at M4. |
| C6 | DATABASE §6 ships one full-schema `001_initial`, but §12 requires ordered versioned migrations | Slice by milestone. `001` = identity + tenancy only (`users`, `workspaces`, `workspace_members`). `projects` arrives with M3 ingestion; jobs/stages with M4; never a dead table without a documented owner milestone. |
| C7 | Workspace slug scope: migration uses global UNIQUE; text allows workspace-scoped | Global UNIQUE (matches the migration SQL). |
| C8 | `Idempotency-Key` required on `POST /workspaces`, but `idempotency_keys` is workspace-scoped (`workspace_id NOT NULL`) | M1: key accepted and logged, enforcement deferred to M2 where workspace-scoped creates exist. Natural dedup via globally-unique slug: a retried create returns `409 RESOURCE_CONFLICT`. |
| C9 | `PATCH /hypotheses/{id}` and `reports` table gaps self-flagged in API.md §6.11/§6.15 | Deferred to M7/M10; will add `hypothesis_reviews` and decide `reports` vs `evidence_artifacts(kind='report')` then. |
| C10 | Patch lifecycle vocabulary differs (SECURITY §9.1 vs DATABASE `patches.status`) | DATABASE values are the code contract (lowercase, C3). Applies at M8/M9. |

## Milestone 0–1 decisions

- **D1 — Health paths.** API.md §6.1 lists `GET /health/live` and `GET /health/ready`
  without the `/api/v1` prefix. Implemented at root, unauthenticated, with the
  literal shapes from §6.1 (no `{data,…}` envelope). Liveness never touches the
  database. Readiness returns `503 {"status":"not_ready","checks":{…}}` when a
  critical dependency is down; non-existent M1 subsystems report honestly as
  `"not_configured"`.
- **D2 — Envelope.** All `/api/v1` responses use `{data, request_id}` /
  `{error:{code,message,details}, request_id}`. `X-Request-ID` is honored when
  sane (`[A-Za-z0-9_.-]{1,64}`), otherwise the server generates
  `req_<26 hex>`. Validation failures → `422 VALIDATION_ERROR`; unknown/hidden
  resources → `404 RESOURCE_NOT_FOUND`; slug conflict → `409 RESOURCE_CONFLICT`
  (additive code; the API.md table is non-exhaustive "typical" codes).
- **D3 — Auth deferred to M2.** M1 has no IdP. `get_current_user` resolves a
  provider-side dev identity (`local-dev`) through the same user-scoped service
  layer that M2 will keep; only the identity source changes. Every query is
  still membership-scoped, so tenant isolation is structural from day one.
- **D4 — First persistent resource.** M1 ships workspaces end-to-end
  (`POST/GET/PATCH /api/v1/workspaces…`). `projects` stays schema-only until M3
  (C6). Members endpoints and `GET /me` arrive with real auth in M2.
- **D5 — Pagination.** `GET /workspaces` returns the §4.3 paginated envelope
  (`limit` default 25, max 100; opaque cursor over `(created_at, id)` DESC).
- **D6 — Sync SQLAlchemy.** SQLAlchemy 2.x with `psycopg` (sync) for the MVP;
  async only if measured load justifies it. `pool_pre_ping`, short
  `connect_timeout` on readiness probes.
- **D7 — `updated_at`.** Maintained explicitly by the service layer on update
  (no trigger in `001`, matching the spec SQL).
- **D8 — Frontend tokens.** Tailwind CSS v4 `@theme` tokens generated 1:1 from
  DESIGN_SYSTEM.md. System font stacks only (no webfont download), so builds
  work offline. No full light theme for MVP, per the design spec.
- **D9 — Test layout.** Unit/service tests co-located (`services/api/tests`,
  `apps/web/e2e`); top-level `tests/` is reserved for later cross-service
  integration/security suites. API DB tests run real Alembic migrations against
  `TEST_DATABASE_URL` and skip loudly (never silently) when PostgreSQL is
  unreachable. Landing-page Playwright smoke only in M1; app-flow e2e at M2+.
- **D10 — Lease TTL (forward, M4).** `locked_at/locked_by/heartbeat_at` with a
  60s default TTL and expired-lease reclaim. Recorded now so M4 has no new
  decision.
- **D11 — Polling first.** 2–3s then 5–10s + backoff per API.md §7; no SSE in M1.
- **D12 — Toolchain pins.** Node ≥ 20.9; Next.js 15, React 19, Tailwind v4,
  `framer-motion` 12 (stable documented API), `lucide-react`; Python ≥ 3.12,
  FastAPI 0.11x, Pydantic v2, SQLAlchemy 2.0, Alembic, `psycopg[binary]`,
  PostgreSQL 16. `ruff` (lint+format), `mypy`, `pytest`, `eslint`.
- **D13 — No execution surface in M1.** No repo commands, no shell, no runner,
  no model calls. The API process cannot execute untrusted code by construction.
- **D14 — Secrets.** Only `.env.example` is committed. `DATABASE_URL` is
  required at startup; nothing prints secret values.

- **D15 — Dependency pins are lower bounds.** Upper bounds rot fast (observed:
  FastAPI 0.139 and eslint 9.39 exist where older caps would have excluded
  them). Only the SQLAlchemy `2.x` line is capped, where a major-line change is
  known-risky. Verified-against versions are recorded in session reports, not
  in pins.
- **D16 — Two-tier API tests.** `tests/test_unit.py` is pure (no sockets, no
  DB) and runs everywhere, including locked-down sandboxes. HTTP/DB tests
  (`test_health.py`, `test_workspaces.py`, `test_request_id.py`) need loopback
  sockets + PostgreSQL and run on dev machines and CI. Known warning (not an
  error): current starlette deprecates `httpx`-backed TestClient in favor of
  `httpx2`; kept `httpx` until the new API is verified.

- **D17 — M2 ships first-party session auth (resolves O1 for now).** Email +
  password (bcrypt via pre-hash, `local` auth provider) with opaque
  server-side sessions. Rationale: no IdP credentials exist or are verifiable
  in this environment, and the specs explicitly permit first-party sessions.
  Reversible: `users(auth_provider, provider_subject)` stays IdP-shaped, so a
  hosted OIDC provider can be added later as another provider + routes without
  migrating existing rows. No custom crypto: bcrypt, `secrets`, SHA-256 token
  hashes only.
- **D18 — Member management contract (M2).** `POST …/members {email, role}`
  adds an *existing* active user by email (case-insensitive); unknown email →
  `404`. This satisfies "don't let callers add arbitrary users by guessing
  UUIDs" without building email invitations. Roles assignable: `admin`,
  `developer`, `viewer` only — `owner` is immutable in M2 (no transfer flow
  yet). Any member may list; only owner/admin may add/change/remove; the last
  owner can never be removed or demoted. List items:
  `{user_id, email, display_name, role, joined_at}`.
- **D19 — Session transport.** `meridian_session` HttpOnly cookie (`SameSite=Lax`,
  `Secure` in prod, 24h absolute expiry) is primary for the browser;
  `Authorization: Bearer <opaque-token>` hits the same session store for API
  clients and tests. CORS allows credentials for the exact configured origin
  (never wildcard). Cookie-authenticated unsafe methods (POST/PATCH/DELETE)
  must carry an `Origin`/`Referer` matching the allowlist.
- **D20 — Login rate limiting (M2).** Single-process sliding window: 10 failed
  attempts per (IP, email) per 10 minutes → `429 RATE_LIMITED`. Documented as
  dev-scale; a shared store arrives with horizontal scaling.

- **D21 — Light mode ships (user-directed).** Overrides the design spec's
  "no full light theme for MVP": user explicitly requested it. Light tokens
  are the `:root` default, dark stays in `.dark`; `next-themes` (class
  strategy, default dark, no system tracking) persists the choice. A toggle
  lives in the landing header and app topbar.
- **D22 — Loopback hostname tolerance.** The web client swaps `localhost` ↔
  `127.0.0.1` between the configured API base and the page host (pure
  `resolveApiBase`, e2e-covered) so the session cookie stays same-site
  whichever spelling the user opens. CORS/origin defaults allow both
  spellings on ports 3000/3010. Non-loopback hosts are never rewritten.
- **D23 — Session presence flag.** Signup/login set a readable
  `meridian_session_present=1` cookie (no secret) alongside the HttpOnly
  session cookie; logout clears both. The frontend skips the `/me` probe when
  the flag is absent, eliminating benign 401s for anonymous visitors.
- **D24 — Adopted libraries: next-themes + Radix.** Menus moved from a
  hand-rolled dropdown to `@radix-ui/react-dropdown-menu` (focus/keyboard
  correctness); theming uses `next-themes`. Other hand-built primitives stay:
  they already meet the design system, and churning them adds risk without
  benefit.
- **D25 — Local port map (user-owned).** This checkout runs web :3010, API
  :8010, Postgres :5435, MinIO :9010/:9011. Compose, env template, configs,
  and docs follow that map; the API still honors `API_PORT`/`CORS_*` env.
- **D26 — Firebase social sign-in (Google/GitHub), additive to D17.**
  `POST /api/v1/auth/firebase {id_token}` verifies the Firebase ID token
  server-side (RS256 against Google's published securetoken certs; only
  `FIREBASE_PROJECT_ID` is configured — no service-account secret) and then
  issues the same D19 session cookie as password login. Only
  `google.com`/`github.com` sign-in providers are accepted. Users are
  `auth_provider='firebase'`, `provider_subject=<Firebase UID>`; a verified
  email matching an existing account signs into that account instead of
  duplicating it. Unverified or missing emails are rejected. Password auth
  is unchanged.

## Open items (carried forward)

- O1 (M2): decided — first-party sessions now (D17); hosted OIDC remains a
  future additive provider (issuer/audience TBD then).
- O2 (M3): ZIP-first ingestion confirmed by default; Git-provider timing open.
- O3 (M4): Queue stays PG-backed unless load proves otherwise.
- O4 (M7): `META_API_KEY`/`META_MODEL_ID`, structured-output/tool-call format,
  image-input support — must be spiked against the live provider; deterministic
  test doubles until then.
- O5 (M3+): Object-store product, signed-URL TTL, retention windows.
