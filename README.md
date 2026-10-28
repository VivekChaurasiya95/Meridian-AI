# Meridian AI — Clarity for complex engineering

Meridian AI is an AI-assisted software debugging and reliability platform. It turns a
developer's bug report into a structured, evidence-backed investigation: reproduce,
capture evidence, hypothesize, propose regression tests, review a patch, verify, report.

> **Milestone 1 status (this checkout):** working foundation only — premium app shell,
> FastAPI backend, PostgreSQL migrations, health probes, and end-to-end workspace
> management (the first persistent resource). The investigation pipeline
> (execution, browser reproduction, AI reasoning, patches, verification) arrives in
> later milestones. The UI never presents unbuilt stages as real.

## Repository layout

```text
apps/web/            Next.js frontend (App Router, TypeScript, Tailwind v4)
services/api/        FastAPI backend (app/*) with co-located tests
services/orchestrator/  (M4+) investigation state machine — not yet built
services/worker/        (M5+) isolated execution worker — not yet built
migrations/          Alembic migrations (PostgreSQL, versioned)
docs/DECISIONS.md    Working architecture decision log
public/              Product specifications (source of truth; never edited)
```

Spec authority: `SECURITY.md` > PRD > `ARCHITECTURE.md`/`API.md` > `DATABASE.md` >
`DESIGN_SYSTEM.md` > `IMPLEMENTATION_PLAN.md`. Conflicts and resolutions live in
[docs/DECISIONS.md](docs/DECISIONS.md).

## Prerequisites

- Node.js ≥ 20.9 and npm
- Python ≥ 3.12 and pip
- Docker (for PostgreSQL), or a local PostgreSQL 16

## Quickstart

```powershell
# 1. Environment
Copy-Item .env.example .env

# 2. Database (creates the `meridian` database; add `meridian_test` for tests)
docker compose up -d db
# first time only:
docker exec meridian-db-1 psql -U meridian -d meridian -c "CREATE DATABASE meridian_test;"

# 3. Backend
cd services/api
pip install -e ".[dev]"
cd ../..
alembic upgrade head
uvicorn app.main:app --app-dir services/api --host 127.0.0.1 --port 8000
# -> http://127.0.0.1:8000/health/live

# 4. Frontend (new terminal, from repo root)
cd apps/web
npm install
npm run dev
# -> http://localhost:3000      landing
# -> http://localhost:3000/app  workspace home (live API data)
```

Or run Postgres + API together: `docker compose up --build` (web still runs locally).

## Checks

```powershell
# Backend (from services/api)
ruff check . ; ruff format --check .
mypy app
pytest                                   # DB tests need TEST_DATABASE_URL up

# Frontend (from apps/web)
npm run lint
npm run typecheck
npm run build
npx playwright install --with-deps chromium   # first time only
npm run e2e
```

## API surface (M1)

- `GET /health/live` → `{"status":"ok"}` (no auth, no DB)
- `GET /health/ready` → `{"status":"ready","checks":{…}}` or `503`
- `POST /api/v1/workspaces` `{name, slug}` → `201`
- `GET /api/v1/workspaces?limit&cursor` → paginated envelope
- `GET /api/v1/workspaces/{id}` → workspace + caller role
- `PATCH /api/v1/workspaces/{id}` `{name}` → owner/admin only

All `/api/v1` responses use `{data, request_id}` / `{error, request_id}`.
Authentication arrives in M2; M1 uses an explicit local-developer identity
(see `services/api/app/api/deps.py` and `docs/DECISIONS.md` D3).

## License

MIT — see [LICENSE](LICENSE).
