# Meridian AI — Work Report & Handoff (M1 → M4 verified)

Paste this whole file to the next AI agent as context. It describes what
Meridian AI is, what has been built and verified through Milestone 4,
the architecture rules you must follow, and the recommended next steps.

## 1. What this project is

Meridian AI is an AI-assisted software debugging and reliability platform.
It turns bug reports into structured, evidence-backed investigations
(reproduce → evidence → hypotheses → tests → patch → verify) with a human
approving every step. Rule: the UI never presents unbuilt stages as real.

**Stack:** Next.js 15 + React 19 + Tailwind v4 + Framer Motion (frontend,
`apps/web`, port 3010) · FastAPI + SQLAlchemy 2.x sync + Alembic +
PostgreSQL 16 (backend, `services/api`, port 8010) · Python worker
(`services/worker`, claims DB jobs) · MinIO (empty bucket, reserved for
M6 evidence) · Docker Compose for db/minio only in practice (see §8).

**Repo layout:** `apps/web/` (App Router), `services/api/app/` (api/,
services/, `main.py`, `config.py`, `models.py`, `schemas.py`,
`envelope.py`, `security.py`), `services/worker/main.py`,
`migrations/versions/`, `public/*.md` (source-of-truth specs),
`docs/DECISIONS.md` (append-only decision log, currently D1–D50),
`UI_UX_DESIGN_SPECIFICATION.md`, `README.md`, `.env` (local, gitignored).

## 2. Non-negotiable conventions (from the specs)

- API envelope: success `{data, request_id}`, paged `{data, page,
  request_id}`, errors `{error: {code, message}, request_id}` with
  `X-Request-ID` header. Codes: VALIDATION_ERROR 422,
  RESOURCE_CONFLICT 409, INVALID_STATE 409, INVALID_TRANSITION 409,
  LEASE_LOST 409, RATE_LIMITED 429, auth errors as documented.
- Auth: opaque `meridian_session` cookie, 24h idle expiry, sliding
  renewal, SHA-256-only token storage, per-user login rate limiting.
- Roles: owner / admin / developer / viewer. Unknown or foreign
  resources answer **404** (never leak existence); role failures 403.
- Pagination: cursor over `(created_at, id)` (or equivalent), `limit`
  clamped to settings. LIKE filters escape `% _ \`. No user strings in
  ORDER BY. Pydantic `extra="forbid"` + allowlisted update fields.
- `public/*.md` are read-only (mirror them, never edit). Migrations are
  raw SQL, append-only (`001_identity_tenancy` →
  `002_local_auth` → `003_projects` → `004_jobs`). Models must mirror
  migration SQL exactly. Frontend: Sage & Bone theme, dark default.

## 3. What is done and VERIFIED (all gates green, outputs observed)

**M1–M2 (prior work):** app shell, session auth (email/password +
Google/GitHub via Firebase), workspaces + role membership, themes,
landing page with FAQ accordion.

**M3 – Project Management (verified):** `projects`,
`repository_snapshots`, `snapshot_files` tables; ZIP upload with
hostile-archive validation (traversal/symlink/bomb/depth/ratio caps,
streaming extract-and-hash to 0700 temp dirs, then cleanup); static
stack inspection (manifests only, never executed, "Not detected" when
absent); immutable snapshots with deterministic digests; CRUD +
archive/unarchive/owner-delete; tree + text-preview reads; pages
`/app/projects`, `/app/projects/new` (3-step wizard, real XHR progress
+ cancel), `/app/projects/[id]` (Overview/Repository/Snapshots/
Settings). Slug unique per workspace (409 on conflict).

**M4 – Durable jobs + hardening (verified live):** `jobs` + `job_stages`
tables; explicit state machines (terminals have no exits);
`SELECT … FOR UPDATE SKIP LOCKED` claiming; DB-time leases/heartbeats
with ownership refusal; exponential backoff + max attempts; idempotent
submit; inline crash recovery (cancelled never requeued, stale
completions refused); real worker loop (heartbeat thread, graceful
shutdown) running only `lifecycle_test` and `manifest_recheck`;
endpoints submit/list/get/cancel/stages (worker transitions are
service-layer, no worker credentials); Jobs page with 5s polling,
stage timelines, cancel, "Run test job"; per-user upload rate limiting;
worker S3 access is read-only repository scope (M5.2; was fully stripped in M4); `/health/ready` probes the real
jobs table. Proven live: a UI-submitted job went queued → running →
completed with stages on the first attempt.

**Executed gate results:** `ruff check .` clean · `mypy app` clean
(`Success: no issues found in 27 source files`) · `pytest -q` fully
green on real Postgres (skips = Firebase-without-credentials only) ·
`npm run lint` / `typecheck` / `build` clean (12/12 pages). Two live
crash bugs were found and fixed along the way (misplaced `.scalars()`,
missing `ArchiveRejected.message`).

## 4. Key decisions to respect (see docs/DECISIONS.md D1–D50)

D20/D45–D50 are load-bearing: dev-scale in-memory rate limiters (fine
for one replica); workers use the service layer, never HTTP; DB time
drives all lease decisions; archive bytes are discarded after
inspection (snapshots keep metadata + file index + small previews);
single-shot 25 MB uploads (sessions deferred); safe job types only
(CHECK-bounded); job lists withhold payloads; `job_stages` rows are
generic — the 12 investigation stage keys are labels only, never
fabricate their results.

## 5. How to run everything (Windows PowerShell, venv at repo root)

```powershell
cd D:\Projects\Meridian-AI
.\.venv\Scripts\Activate.ps1          # needs Python 3.12; pip install -e "services/api[dev]" once
docker compose up -d db
alembic upgrade head                  # from repo root (alembic.ini)
# terminal 1 — API:
uvicorn app.main:app --app-dir services/api --host 127.0.0.1 --port 8010
# terminal 2 — web:  cd apps/web; npm install; npm run dev   # app at http://localhost:3010
# terminal 3 — worker:
$env:WORKER_ID="local-worker-1"; python services/worker/main.py
```

Gates: `cd services/api` → `ruff check .`, `mypy app`, `pytest -q`
(needs Postgres up) · `cd ../../apps/web` → `npm run lint`,
`npm run typecheck`, `npm run build`. Smoke: open
`http://localhost:3010/app/jobs`, press "Run test job", watch it
complete with stages.

## 6. Environment quirks discovered (do not "fix" these as bugs)

- Docker **build** containers here cannot reach PyPI (setuptools
  download fails), so API + worker both run locally; Dockerfiles are
  fine and unchanged. Same root cause would hit any new image build.
- Windows-only test accommodations in
  `services/api/tests/test_archive_security.py`: stdlib `zipfile`
  converts `\` to `/` on write AND read here, so the backslash guard
  is unit-tested directly; POSIX mode bits asserted only off-Windows.
- `.pytest_cache` "Access is denied" warnings are environmental noise.
- `eslint.config.mjs` now ignores `.next/` etc. (was missing).

## 7. Suggested next milestone: M5 — isolated execution worker

Per-job disposable workspaces, CPU/memory/pid/wall-clock limits,
default-deny egress, allowlisted command execution (no shells), then
M6 Playwright reproduction + evidence to MinIO. Do not start M5 work
until its own gates go green the same way. Suggested first question
for the next agent: "Read docs/DECISIONS.md D45–D50 and
services/worker/main.py, then propose the M5 sandbox design before
writing code."

## 8. Current limitations (honest)

No Git sources (option visibly disabled); synchronous ingestion; no
browser automation, evidence pipeline, or AI stages; 5s polling, not
SSE; "New investigation" buttons disabled until the pipeline exists;
MinIO bucket empty and reserved.

## 9. Security Preflight V1 — backend + read APIs (2026-11-04, D61-D67)

Spec: `security.md` (V1 scope confirmed: Semgrep + Gitleaks, dual
artifacts, sandbox profiles, durable job, read APIs; UI/OSV/hardening
deferred). Migration is `008_security_preflight` (doc said 007, which
git import occupies).

Implemented: dual-artifact ingestion (`security_extra` tarball,
`security_*` snapshot fields, read-back verify, mirror optimization
for secret-less uploads); `materialize_security_input_for_workspace`
(policy-based secret verification, worker-only); `security_preflight`
job type end to end (submit validation, idempotent enqueue on ZIP
upload, worker handler, 8 stages); `services/worker/security/`
(wrappers with upstream-verified exit contracts, normalizer with
detector-aware masking, risk policy, ruleset preflight-v1, scanner
runner reusing sandbox primitives with zero stdout persistence);
sandbox profiles `semgrep_preflight`/`gitleaks_preflight` (pinned
`semgrep/semgrep:1.183.0` + `zricethezav/gitleaks:v8.30.1`, trusted
FROM/rules-dir build parameters, `scanner` execution discriminator);
4 read APIs (assessment detail, snapshot latest, project list,
paginated/filtered findings); 97 maintained tests.

Verified in-session: 71 pure unit tests green; ruff clean on all
touched files (22 remaining hits are pre-existing worker regions);
mypy clean on `app` (39 files); API/worker imports + app factory +
migration chain check ok; full suite collects 432 tests.

NOT verified (sandbox blocks loopback TCP to Postgres/MinIO/Docker):
26 DB-backed preflight tests, migration 008 upgrade/downgrade,
real-daemon scanner runs, semgrep rule validation. Required
user-side (unsandboxed PowerShell, repo root):
`$env:TEST_DATABASE_URL='postgresql+psycopg://meridian:meridian@localhost:5435/meridian_test';`
`cd services/api; python -m pytest tests/ -q` (expect 0 failures;
4 pre-existing TestClient tests fail only inside the sandbox);
`alembic upgrade head` + `downgrade -1`/`upgrade head` on a scratch
database for 008; `docker run --rm -v ${PWD}/services/worker/security/rules:/r:ro
semgrep/semgrep:1.183.0 semgrep scan --validate --config /r` for
rules; pull both scanner images before any live preflight job.

Known follow-ups: Security UI (Phase 5 second half), OSV-Scanner
(stub present), git-import snapshot trigger (V1 triggers on ZIP
uploads only), enqueue outbox (enqueue failure currently fails the
upload loudly per D65), repo ignore-file semantics documented as
advisory-only (D67).
