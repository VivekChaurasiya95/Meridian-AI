<div align="center">

<img src="apps/web/public/brand/meridian-mark.svg" width="72" alt="Meridian AI mark" />

# Meridian AI

[![CI](https://github.com/VivekChaurasiya95/Meridian-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/VivekChaurasiya95/Meridian-AI/actions)
[![License: MIT](https://img.shields.io/github/license/VivekChaurasiya95/Meridian-AI)](LICENSE)
[![Node](https://img.shields.io/badge/node-%3E%3D20.9-339933?logo=node.js&logoColor=white)](apps/web/package.json)
[![Python](https://img.shields.io/badge/python-%3E%3D3.12-3776AB?logo=python&logoColor=white)](services/api/pyproject.toml)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)](https://github.com/VivekChaurasiya95/Meridian-AI/pulls)

<img src="https://readme-typing-svg.herokuapp.com?font=Fira+Code&weight=500&size=21&duration=2800&pause=1200&color=6B7A56&center=true&vCenter=true&width=620&lines=Clarity+for+complex+engineering;Bug+reports+in.+Evidence+out.;Reproduce.+Capture.+Verify." alt="Typing animation: Clarity for complex engineering" />

**An AI-assisted debugging and reliability platform.** Meridian turns a developer's
bug report into a structured, evidence-backed investigation — reproduce, capture
evidence, hypothesize, test, patch, verify, report — with a human approving every step.

[Quickstart](#-getting-started) · [Run the app](#%EF%B8%8F-run-the-application) · [API Reference](#-api-reference) · [Roadmap](#-roadmap) · [Author](#-author)

</div>

---

## 📑 Contents

- [✨ Features](#-features)
- [🎬 Product Tour](#-product-tour)
- [🏗️ Architecture](#-architecture)
- [🧰 Tech Stack](#-tech-stack)
- [🚀 Getting Started](#-getting-started)
- [▶️ Run the Application](#️-run-the-application)
- [🔐 Social Sign-In Setup](#-social-sign-in-setup-optional)
- [🧠 Model Provider Setup](#-model-provider-setup-meta-muse-optional)
- [🗂️ Project Structure](#-project-structure)
- [🔌 API Reference](#-api-reference)
- [⚙️ Configuration](#-configuration)
- [✅ Testing & Quality Gates](#-testing--quality-gates)
- [🛠️ Troubleshooting](#️-troubleshooting)
- [🗺️ Roadmap](#-roadmap)
- [📄 License](#-license)
- [👨‍💻 Author](#-author)

> **Milestone 9 status (this checkout):** everything from Milestone 8, plus
> investigation reports generated at verification time (M9), a security
> preflight pipeline (Semgrep + Gitleaks over isolated snapshots), and Meta
> Muse wiring through the provider gateway. Verification reruns/comparison are
> still ahead. The UI never presents unbuilt stages as real.

Spec authority: `SECURITY.md` > PRD > `ARCHITECTURE.md`/`API.md` > `DATABASE.md` >
`DESIGN_SYSTEM.md` > `IMPLEMENTATION_PLAN.md`. Conflicts and resolutions live in
[docs/DECISIONS.md](docs/DECISIONS.md).

## ✨ Features

| Area | What works today |
|---|---|
| 🖥️ **App shell** | Brand system, warm light/dark themes, landing page with motion design |
| 🔑 **Session auth** | Email/password signup, login, logout, `/me` profile — opaque server-side sessions |
| 🌐 **Social login** | Google and GitHub sign-in via Firebase, exchanged for the same session cookie |
| 🏢 **Workspaces** | Create/rename workspaces, cursor pagination, role-based membership (owner/admin/developer/viewer) |
| 📦 **Projects** | ZIP upload with archive validation, stack inspection, immutable snapshots, repo browser, settings |
| 🔬 **Investigations** | Staged debugging pipeline: reproduce → evidence → hypotheses → tests → patch → verify |
| 🧪 **Hypotheses & tests** | Evidence-grounded hypotheses, regression tests, baseline/post-patch verification |
| 🩹 **Patches** | Unified-diff proposals behind scoped human approval, applied only after approval |
| 📝 **Reports** | Model-written investigation summary at verification time, served per investigation |
| 🛡️ **Security preflight** | Every snapshot scanned by Semgrep + Gitleaks in isolated containers; findings API |
| 🤖 **Meta Muse** | Investigations and reports run on Muse Spark via the provider gateway |
| 🎥 **Product tour** | Animated explainer of the investigation loop, or attach your own demo video |
| 🔬 **Playground** | Interactive desktop scene: feed a file, pick a workflow, watch the agents work |
| 👨‍💻 **Developer page** | Meet-the-developer story, stack, and project highlights |
| ❤️ **Health checks** | Liveness (no DB) and readiness (DB + dependency checks) endpoints |

## 🎬 Product Tour

The landing page ships a **13-second motion explainer** — report → reproduce →
evidence → patch → verify — with play/pause, replay, and per-scene progress.
Prefer your own footage? Set one variable and the section swaps in your video:

```powershell
# apps/web/.env.local — YouTube link or direct .mp4 URL
NEXT_PUBLIC_DEMO_VIDEO_URL=https://www.youtube.com/watch?v=YOUR_VIDEO_ID
```

Restart the web server after changing it.

## 🏗️ Architecture

```mermaid
flowchart LR
    Browser(["Browser"]) --> Web["Next.js 15<br/>:3010"]
    Web --> API["FastAPI<br/>:8010"]
    API --> DB[("PostgreSQL 16<br/>:5435")]
    Web --> Firebase(["Firebase Auth<br/>Google · GitHub"])
    API --> MinIO[("MinIO<br/>:9010 / :9011")]
    API --> Worker["Job worker<br/>durable jobs + sandbox"]
    Worker --> DB
    Worker --> Docker(["Docker<br/>repro + scanners"])
    Worker -. "reasoning stages" .-> Muse(["Meta Muse API<br/>api.meta.ai"])
```

| Service | Tech | Port | Purpose |
|---|---|---|---|
| `web` | Next.js (App Router, TypeScript, Tailwind v4) | 3010 | Landing, auth pages, workspace UI |
| `api` | FastAPI + SQLAlchemy + Alembic | 8010 | REST API, sessions, workspaces, investigations |
| `db` | PostgreSQL 16 | 5435 | Users, sessions, projects, jobs, investigations |
| `minio` | MinIO (S3-compatible) | 9010 / 9011 | Snapshot + evidence object storage, console |
| `worker` | Python job worker | — | Durable jobs, investigation pipeline, sandbox scans |
| `muse` | Meta Model API (external) | — | Reasoning stages + reports (Muse Spark, optional) |

## 🧰 Tech Stack

<p>
  <img src="https://img.shields.io/badge/Next.js-15-black?logo=next.js" alt="Next.js 15" />
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black" alt="React 19" />
  <img src="https://img.shields.io/badge/Tailwind-4-06B6D4?logo=tailwindcss&logoColor=white" alt="Tailwind CSS 4" />
  <img src="https://img.shields.io/badge/Framer_Motion-12-0055FF?logo=framer&logoColor=white" alt="Framer Motion" />
  <img src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/SQLAlchemy-2.0-D71F00?logo=python&logoColor=white" alt="SQLAlchemy 2" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL 16" />
  <img src="https://img.shields.io/badge/Firebase_Auth-FFCA28?logo=firebase&logoColor=black" alt="Firebase Auth" />
  <img src="https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/Playwright-2EAD33?logo=playwright&logoColor=white" alt="Playwright" />
</p>

## 🚀 Getting Started

**Prerequisites:**

| Tool | Version | Notes |
|---|---|---|
| Node.js + npm | ≥ 20.9 | `node --version` to check |
| Python + pip | ≥ 3.12 | `python --version` to check |
| Docker Desktop | current, Linux containers | Hosts PostgreSQL, MinIO, repro/scanner containers |
| Git | any recent | To clone the repo |

Ports `3010`, `8010`, `5435`, `9010`, `9011` must be free (see
[Troubleshooting](#️-troubleshooting) if a port is taken).

**One-time setup** — one terminal, from the repo root:

```powershell
cd D:\Projects\Meridian-AI   # or wherever you cloned it

# 1. Environment files (never commit the real ones)
Copy-Item .env.example .env
# -> open .env and confirm DATABASE_URL / TEST_DATABASE_URL point at localhost:5435

# 2. Python environment + API package
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e "services/api[dev]"

# 3. Infrastructure: PostgreSQL + MinIO (minio-init provisions buckets/policies)
docker compose up -d db minio minio-init

# 4. Test database (first time only) + migrations
docker exec meridian-db-1 psql -U meridian -d meridian -c "CREATE DATABASE meridian_test;"
alembic upgrade head

# 5. Frontend dependencies
cd apps/web
npm install
cd ../..
```

## ▶️ Run the Application

Use one terminal per process, all from the repo root. **Start order matters:**
infrastructure → API → worker → web. Stop everything with `Ctrl+C` in each terminal.

| # | Terminal | Command | Serves |
|---|---|---|---|
| 1 | Infrastructure | `docker compose up db minio` | Postgres :5435, MinIO :9010/:9011 |
| 2 | Backend API | `uvicorn app.main:app --app-dir services/api --host 127.0.0.1 --port 8010` (venv active) | API :8010 |
| 3 | Job worker | `python services/worker/main.py` (venv active, Docker running) | Jobs, investigations, scans |
| 4 | Frontend | `cd apps/web` → `npm run dev` | Web :3010 |

```powershell
# Terminal 1 — infrastructure (leave running)
docker compose up db minio

# Terminal 2 — backend API (leave running)
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --app-dir services/api --host 127.0.0.1 --port 8010
# -> http://127.0.0.1:8010/health/live

# Terminal 3 — job worker (leave running; needs Docker for sandbox jobs)
.\.venv\Scripts\Activate.ps1
$env:WORKER_ID = "local-worker-1"   # optional; defaults to hostname-pid
python services/worker/main.py

# Terminal 4 — frontend (leave running; predev guard cleans stale caches)
cd apps/web
npm run dev
# -> http://localhost:3010            landing
# -> http://localhost:3010/app        workspace home (live API data)
# -> http://localhost:3010/developer  developer story
```

**Verify it's healthy:**

- API liveness: `http://127.0.0.1:8010/health/live` → `{"status":"ok"}`
- API readiness: `http://127.0.0.1:8010/health/ready` → `"model": "ok"` (or
  `"not_configured"` until you add a model key — readiness never fails for that)
- MinIO console: `http://localhost:9011` (dev defaults from compose)
- Then sign up at `http://localhost:3010/signup`, create a workspace + project,
  and upload a ZIP to watch ingestion → snapshot → security preflight run.

Alternative: `docker compose up --build` runs Postgres + MinIO + API + worker
together from images; the web frontend still runs locally via `npm run dev`.

> Host-run API/worker talk to MinIO at `http://localhost:9010` (the compose
> host mapping). If you copied an older `.env`, make sure `S3_ENDPOINT_URL`
> uses port `9010`, not `9000`.

## 🔐 Social Sign-In Setup (optional)

Password auth works with zero setup. To enable the Google/GitHub buttons:

1. In the [Firebase console](https://console.firebase.google.com), create a project
   (or reuse one), then **Authentication → Sign-in method**: enable **Google** and
   **GitHub**. For GitHub, create a GitHub OAuth App (GitHub Settings → Developer
   settings) with authorization callback URL
   `https://<your-project-id>.firebaseapp.com/__/auth/handler`, and paste its
   client ID/secret into Firebase.
2. **Authentication → Settings → Authorized domains**: add `localhost`.
3. **Project settings → Your apps → Web**: register a web app and copy its config.
4. Put the web config in `apps/web/.env.local` (`NEXT_PUBLIC_FIREBASE_*`, see
   `.env.example`) and set `FIREBASE_PROJECT_ID` in the repo-root `.env`. Restart
   both servers. The API needs only the project ID — tokens verify against Google's
   public certs, so no service-account key is stored anywhere.

## 🧠 Model Provider Setup (Meta Muse, optional)

Reasoning stages (hypotheses, reports) call an OpenAI-compatible chat API. Without
a key they block honestly (`MODEL_NOT_CONFIGURED`) instead of emitting output.

1. Create an API key in your Meta developer dashboard.
2. Add it to the repo-root `.env` yourself (never paste secrets into chat/logs):

```dotenv
MODEL_PROVIDER=muse
MODEL_API_BASE=https://api.meta.ai/v1
MODEL_API_KEY=<your-key-here>
MODEL_NAME=muse-spark-1.3
```

3. Restart the API/worker and check `/health/ready` → `"model": "ok"`.

Costs fractions of a cent per investigation. See `docs/DECISIONS.md` D69 for the
verified contract notes.

## 🗂️ Project Structure

```text
apps/web/               Next.js frontend (App Router, TypeScript, Tailwind v4)
├── app/                Routes: landing (/), login, signup, /app, /developer
├── components/         auth · brand · landing · shell · ui · workspaces
├── e2e/                Playwright specs (4 files, 9 cases)
└── public/             Brand art + developer portrait
services/api/           FastAPI backend (app/*) with co-located tests
services/worker/        Durable job worker: investigation pipeline, sandbox, security preflight
migrations/             Alembic migrations (PostgreSQL, versioned; head: 013)
docs/DECISIONS.md       Working architecture decision log
public/                 Product specifications (source of truth; never edited)
```

## 🔌 API Reference

All `/api/v1` responses use the `{data, request_id}` / `{error, request_id}` envelope.
Sessions travel in the `meridian_session` HttpOnly cookie (`SameSite=Lax`) or as
`Bearer` tokens (see `docs/DECISIONS.md` D17–D20).

<details>
<summary><strong>Endpoints (M2 core)</strong></summary>

| Method & path | Purpose | Auth |
|---|---|---|
| `GET /health/live` | `{"status":"ok"}` — no DB touch | — |
| `GET /health/ready` | `{"status":"ready","checks":{…}}` or `503` | — |
| `POST /api/v1/auth/signup` | `{email, password, display_name}` → `201` + session cookie | — |
| `POST /api/v1/auth/login` | `{email, password}` → `200` + session cookie | — |
| `POST /api/v1/auth/firebase` | `{id_token}` (Google/GitHub) → `200` + session cookie; `503` if unconfigured | — |
| `POST /api/v1/auth/logout` | `204`, revokes session, clears cookies | Session |
| `GET /api/v1/me` | Current profile | Session |
| `PATCH /api/v1/me` | `{display_name}` — allowlisted field only | Session |
| `POST /api/v1/workspaces` | `{name, slug}` → `201` | Session |
| `GET /api/v1/workspaces?limit&cursor` | Paginated workspace list | Session |
| `GET /api/v1/workspaces/{id}` | Workspace + caller's role | Member |
| `PATCH /api/v1/workspaces/{id}` | `{name}` | Owner/admin |
| `GET /api/v1/workspaces/{id}/members` | Member list | Member |
| `POST /api/v1/workspaces/{id}/members` | Add existing user `{email, role}` | Owner/admin |
| `PATCH /api/v1/workspaces/{id}/members/{user_id}` | Change role (never demote last owner) | Owner/admin |
| `DELETE /api/v1/workspaces/{id}/members/{user_id}` | Remove member (never the last owner) | Owner/admin |

</details>

Beyond M2 the API covers projects, snapshots, repo browser, jobs, executions,
investigations, hypotheses, evidence, regression tests, patches, verification,
reports, and security assessments — see `API.md` for the full reference.

## ⚙️ Configuration

Copy `.env.example` → `.env` (root, for the API/worker) and create
`apps/web/.env.local` (for the browser — Next.js does not read the root file).
Never commit either.

<details>
<summary><strong>Environment variables</strong></summary>

| Variable | Where | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | root `.env` | `…@localhost:5435/meridian` | API/worker database |
| `TEST_DATABASE_URL` | root `.env` | `…/meridian_test` | Pytest database (never dev) |
| `CORS_ALLOW_ORIGINS` | root `.env` | loopback × ports | Allowed browser origins |
| `SECURE_COOKIES` | root `.env` | `false` | `true` in production (HTTPS) |
| `FIREBASE_PROJECT_ID` | root `.env` | empty (disabled) | Enables `/auth/firebase` |
| `NEXT_PUBLIC_API_URL` | `apps/web/.env.local` | `http://localhost:8010` | API base for the browser |
| `NEXT_PUBLIC_FIREBASE_*` | `apps/web/.env.local` | empty (disabled) | Firebase web config (4 keys) |
| `NEXT_PUBLIC_DEMO_VIDEO_URL` | `apps/web/.env.local` | empty (placeholder) | Landing demo video |
| `S3_ENDPOINT_URL` | root `.env` | `http://localhost:9010` | MinIO S3 API (host mapping) |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | root `.env` | dev defaults | MinIO identity (least privilege per service) |
| `WORKER_ID` | env | hostname-pid | Worker identity in logs/leases |
| `MODEL_PROVIDER` / `MODEL_API_BASE` / `MODEL_API_KEY` / `MODEL_NAME` | root `.env` | unset (blocked honestly) | Reasoning provider (Meta Muse) |

</details>

## ✅ Testing & Quality Gates

Every push runs three CI jobs ([workflow](.github/workflows/ci.yml)): `api`
(lint, typecheck, migrate, pytest), `web` (lint, typecheck, build), and `e2e`
(Playwright, Chromium — no backend required). Run the same gates locally:

```powershell
# Backend (from services/api; needs TEST_DATABASE_URL up on :5435)
ruff check .
mypy app
pytest                                   # full suite, ~603 tests

# Frontend (from apps/web)
npm run lint
npm run typecheck
npm run build
npx playwright install --with-deps chromium   # first time only
npm run e2e
```

Current coverage: **603 backend tests** (auth through investigations, hypotheses,
regression tests, patches, verification, reports, security preflight) and **9 e2e
cases** (landing, auth forms, password toggles, theme, API-base units).

## 🛠️ Troubleshooting

**Port already in use (`EADDRINUSE` / WinError 10048 on 8010 or 3010).**
A previous server is still holding the port. Identify it, then stop only your own
process — never kill processes you don't recognize:

```powershell
Get-NetTCPConnection -LocalPort 8010 -State Listen | ForEach-Object {
  Get-CimInstance Win32_Process -Filter ("ProcessId = " + $_.OwningProcess) |
    Select-Object ProcessId, ExecutablePath, CommandLine
}
```

`TimeWait` rows without a `Listen` row mean the port is free (closing remnants).

**Chunk 404s (`/_next/static/… 404`) after a build.**
A production `.next` is shadowing the dev server. Stop dev (`Ctrl+C`), then:

```powershell
cd apps/web
npm run clean
npm run dev
```

…and hard-refresh (`Ctrl+Shift+R`). Always start dev via `npm run dev` (its
`predev` guard removes production caches); never run `next build` under a live dev
server.

**Webpack `ENOENT … .pack.gz` + forced full reloads.**
`.next` was deleted while the dev server was running, leaving its in-memory cache
index dangling. Same fix: stop the server first, `npm run clean`, start once.

**API can't reach Postgres (`connection refused` on :5435).**
`docker compose up db` must be running first; confirm `DATABASE_URL` uses host port
`5435` (the container-internal `5432` only works between containers).

**Tests hitting the wrong database.**
The suite uses `TEST_DATABASE_URL` exclusively (default `…/meridian_test`, safe).
Never point it at `meridian`. Suite setup/teardown truncates test tables only.

**Sandbox jobs fail immediately.**
The worker needs the Docker daemon (Desktop, Linux containers) plus the pinned
images: `python:3.12-slim`, `semgrep/semgrep:1.183.0`,
`zricethezav/gitleaks:v8.30.1` (`docker pull …` each once).

## 🗺️ Roadmap

- [x] **M1** — App shell, brand system, landing page
- [x] **M2** — Session auth (password + Firebase social), workspaces, membership roles
- [x] **M3** — Project onboarding (ZIP validation, inspection, snapshots), MinIO reserved for M3+ evidence
- [x] **M4** — Durable jobs + leases/recovery + worker (ruff/mypy/pytest + lint/typecheck/build green)
- [x] **M5** — Isolated execution worker (sandbox smoke profile + execution observability; project-specific profiles future)
- [x] **M6** — Investigations, browser reproduction (static profile), evidence + audit
- [x] **M7** — Evidence-grounded hypotheses via a provider adapter (fake default blocks honestly)
- [x] **M8** — Regression tests, baseline/post-patch verification, patch proposals with scoped human approval
- [x] **M9** — Investigation reports, security preflight (Semgrep + Gitleaks), Meta Muse wiring
- [ ] **M10** — Verification reruns/comparison

## 📄 License

MIT — see [LICENSE](LICENSE).

## 👨‍💻 Author

<div align="center">

**Vivek Chaurasiya && Arin Gupta** — Full-stack developer · Creator of Meridian AI

[![GitHub](https://img.shields.io/badge/GitHub-VivekChaurasiya95-181717?logo=github&logoColor=white)](https://github.com/VivekChaurasiya95)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0A66C2?logo=linkedin&logoColor=white)](https://www.linkedin.com/in/vivek-chaurasiya-722037315)
[![Portfolio](https://img.shields.io/badge/Portfolio-Visit-23201C?logo=vercel&logoColor=white)](https://vivek-chaurasiya.vercel.app)

*Designed & built end to end — interface, API, data model, and infrastructure.*

</div>
