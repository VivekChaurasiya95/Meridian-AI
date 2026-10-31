# Meridian AI — Clarity for complex engineering

Meridian AI is an AI-assisted software debugging and reliability platform. It turns a
developer's bug report into a structured, evidence-backed investigation: reproduce,
capture evidence, hypothesize, propose regression tests, review a patch, verify, report.

> **Milestone 2 status (this checkout):** app shell with brand system, session
> authentication (signup/login/logout, `/me`), and workspace management with
> membership roles — all backed by PostgreSQL. Project onboarding and the
> investigation pipeline (execution, browser reproduction, AI reasoning, patches,
> verification) arrive in later milestones. The UI never presents unbuilt stages
> as real.

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
uvicorn app.main:app --app-dir services/api --host 127.0.0.1 --port 8010
# -> http://127.0.0.1:8010/health/live

# 4. Frontend (new terminal, from repo root)
cd apps/web
npm install
npm run dev
# -> http://localhost:3010      landing
# -> http://localhost:3010/app  workspace home (live API data)
```

Or run Postgres + API together: `docker compose up --build` (web still runs locally).

### Social sign-in (Google/GitHub via Firebase, optional)

Password auth works with zero setup. To enable the Google/GitHub buttons:

1. In the [Firebase console](https://console.firebase.google.com), create a
   project (or use an existing one), then **Authentication -> Sign-in
   method**: enable **Google** and **GitHub**. For GitHub, create a GitHub
   OAuth App (GitHub Settings -> Developer settings) with authorization
   callback URL `https://<your-project-id>.firebaseapp.com/__/auth/handler`
   and paste its client ID/secret into Firebase.
2. **Authentication -> Settings -> Authorized domains**: add `localhost`.
3. **Project settings -> Your apps -> Web**: register a web app and copy
   its config values.
4. Put the web config in `apps/web/.env.local` (`NEXT_PUBLIC_FIREBASE_*`,
   see `.env.example`) and set `FIREBASE_PROJECT_ID` in the repo-root
   `.env`. Restart both servers. The API needs only the project ID; tokens
   are verified against Google's public certs, so no service-account key
   is stored anywhere.

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

## API surface (M2)

- `GET /health/live` → `{"status":"ok"}` (no auth, no DB)
- `GET /health/ready` → `{"status":"ready","checks":{…}}` or `503`
- `POST /api/v1/auth/signup` `{email, password, display_name}` → `201` + session cookie
- `POST /api/v1/auth/login` `{email, password}` → `200` + session cookie
- `POST /api/v1/auth/firebase` `{id_token}` → `200` + session cookie (Google/GitHub via Firebase; `503` if `FIREBASE_PROJECT_ID` is unset)
- `POST /api/v1/auth/logout` → `204`, clears the cookie
- `GET /api/v1/me` → current profile; `PATCH /api/v1/me` `{display_name}`
- `POST /api/v1/workspaces` `{name, slug}` → `201`
- `GET /api/v1/workspaces?limit&cursor` → paginated envelope
- `GET /api/v1/workspaces/{id}` → workspace + caller role
- `PATCH /api/v1/workspaces/{id}` `{name}` → owner/admin only
- `GET|POST /api/v1/workspaces/{id}/members` → list (members) / add by email (owner/admin)
- `PATCH|DELETE /api/v1/workspaces/{id}/members/{user_id}` → roles, removal

All `/api/v1` responses use `{data, request_id}` / `{error, request_id}`.
Sessions travel in the `meridian_session` HttpOnly cookie (`SameSite=Lax`) or
as `Bearer` tokens; see `docs/DECISIONS.md` D17–D20.

## License

MIT — see [LICENSE](LICENSE).
