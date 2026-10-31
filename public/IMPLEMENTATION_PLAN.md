# Meridian --- Implementation Plan

**File:** `IMPLEMENTATION_PLAN.md`\
**Product:** Meridian --- *Clarity for complex engineering*\
**Planning baseline:** Greenfield build from scratch\
**Version:** 1.0\
**Date:** 28 October 2026\
**Document status:** Working implementation blueprint

------------------------------------------------------------------------

## 1. Executive Summary

Meridian is an AI-assisted software debugging and reliability platform.
It turns a developer's bug report into a structured investigation
supported by reproducible browser behavior, runtime evidence, explicit
hypotheses, regression tests, a reviewable patch, and verification based
on real execution results.

We are building Meridian from scratch as a real software
application---not a static prototype, a chatbot wrapper, or a dashboard
whose statuses are simulated. The product must have a coherent frontend,
backend, database, AI orchestration, isolated execution, evidence
storage, authentication, security controls, testing strategy, and
deployable environments.

This plan combines the responsibilities of:

-   **Senior Product Manager:** scope, user journeys, acceptance
    criteria, prioritization, release gates.
-   **Senior System Designer:** architecture, trust boundaries, service
    contracts, state transitions, reliability.
-   **Senior Full-Stack Engineer:** frontend, backend, API contracts,
    persistence, integration, testing.
-   **Senior AI/GenAI Engineer:** model integration, tool orchestration,
    structured outputs, evaluation, fallback behavior.
-   **Senior UI/UX Designer:** premium product experience, information
    hierarchy, interaction states, responsive design, accessibility.
-   **Multimodal Engineer:** screenshots, browser traces,
    console/network evidence, image attachments, and evidence-grounded
    reasoning.
-   **Security Engineer:** repository trust, sandboxing, tenant
    isolation, approval gates, secrets, and auditability.

The core delivery principle is:

> **Build one complete, secure, observable investigation workflow before
> adding breadth.**

The first release should work end-to-end on a deliberately supported web
stack and a small set of seeded bugs. It should be honest about
uncertainty and unsupported cases. The system must never claim a bug was
reproduced, a patch was applied, or tests passed unless the relevant
operation actually ran and its result was persisted.

------------------------------------------------------------------------

## 2. Product Vision and MVP Definition

### 2.1 Product promise

A developer submits a bug report and project snapshot. Meridian
investigates using deterministic tools and AI-assisted reasoning,
presents evidence and hypotheses, proposes a regression test and minimal
patch, waits for approval, runs verification, and generates a report
that explains what happened.

### 2.2 Primary user journey

1.  User signs in.
2.  User creates or selects a workspace.
3.  User adds a project using a supported onboarding method.
4.  Meridian validates and snapshots the project.
5.  User creates an investigation with a title, description, expected
    behavior, actual behavior, reproduction steps, and optional
    attachments.
6.  Meridian creates a persisted investigation and starts a durable
    background job.
7.  The system inspects the project and selects a supported run profile.
8.  A sandbox starts the application and Playwright attempts
    reproduction.
9.  Browser screenshots, console events, network failures, traces, and
    command outputs are captured as evidence.
10. The AI proposes hypotheses grounded in evidence; the user can
    inspect the supporting and contradicting evidence.
11. Meridian proposes a regression test and executes it against the
    unchanged baseline.
12. The system prepares a minimal patch and shows an isolated diff.
13. The user approves or rejects that exact patch.
14. If approved, the patch is applied to an isolated working copy and
    the verification suite runs.
15. A deterministic verification engine records passed, failed, blocked,
    skipped, timed-out, or inconclusive checks.
16. Meridian generates a report and provides authorized downloads for
    the evidence and diff.

### 2.3 MVP scope

**Must have**

-   Authentication and workspace membership.
-   Project creation and secure source ingestion.
-   Immutable repository snapshots with content hashes.
-   Investigation creation, listing, detail, cancellation, and durable
    stage history.
-   Background job processing and stage-level progress.
-   One supported web-app project profile.
-   Isolated command execution with resource limits.
-   Playwright-based reproduction attempt.
-   Evidence capture and private storage.
-   Muse Spark / Meta Model API adapter, configured through environment
    variables.
-   Schema-validated model outputs and allowlisted tool orchestration.
-   Hypotheses with evidence links and confidence rationale.
-   Regression-test proposal and baseline execution.
-   Patch generation, diff preview, explicit approval/rejection.
-   Post-patch verification based on actual command results.
-   Report generation and authorized report download.
-   Audit trail, structured logs, error handling, and automated tests.
-   Responsive, polished application interface with loading, empty,
    error, blocked, and success states.

**Should have if time permits**

-   Git-provider integration in addition to ZIP onboarding.
-   Multiple predefined project profiles.
-   Rich screenshot and trace viewers.
-   Server-sent events for live progress.
-   Model usage and cost telemetry.
-   Investigation retry from a safe checkpoint.
-   Exportable evidence bundle.

**Not in MVP**

-   Unrestricted support for arbitrary languages and frameworks.
-   Autonomous patch application without approval.
-   Automatic remote pushes, merges, or deployments.
-   Production credentials or direct production access.
-   Arbitrary shell execution selected by the model.
-   Multi-agent complexity without a measured need.
-   Vector search as a default dependency; use deterministic repository
    search first.
-   Claims of guaranteed bug fixing or guaranteed reproduction.

### 2.4 Definition of a successful demo

A clean demo should show one seeded bug going through the full real
workflow:

-   The report is submitted and persisted.
-   The source snapshot is identified.
-   Browser reproduction is attempted and its outcome is visible.
-   Evidence is captured and inspectable.
-   Hypotheses link to real evidence.
-   A regression test is created and actually run.
-   A patch diff is shown before approval.
-   The user approves the exact patch.
-   The post-patch checks execute.
-   The result is derived from check records, not model narration.
-   The final report distinguishes facts, hypotheses, changes, and
    verification limitations.

A second seeded scenario should demonstrate a correct **inconclusive**
or **blocked** outcome. This proves that the system does not fabricate
success.

------------------------------------------------------------------------

## 3. Operating Principles and Engineering Standards

1.  **Evidence before conclusions.** The model may interpret evidence;
    deterministic tools must collect it.
2.  **Persist before reporting progress.** A stage is not complete until
    its state and result are saved.
3.  **Explicit state transitions.** Every stage transition must be
    validated by the backend.
4.  **Human control over changes.** The approved patch is bound to a
    specific base snapshot and diff hash.
5.  **Least privilege.** The execution worker receives only the files,
    network access, and resources needed for its task.
6.  **Fail closed.** Missing authorization, malformed model output,
    invalid state, or unavailable safety checks must not silently
    proceed.
7.  **Reproducibility.** Record snapshot hash, runtime profile, command,
    environment profile, tool version, and execution outcome.
8.  **Traceability.** Every important claim should link to evidence or
    be clearly marked as a hypothesis.
9.  **Truthful verification.** Model output is never the source of truth
    for whether tests passed.
10. **Secure by design.** Repository contents and uploaded documents are
    untrusted inputs.
11. **No fake progress.** UI progress reflects persisted backend stages
    and actual operations.
12. **Accessible premium UX.** Visual polish must not compromise
    contrast, keyboard use, or clear status communication.
13. **Small, reviewable changes.** Keep modules and pull requests
    focused; do not create a monolithic orchestration function.
14. **Test the failure paths.** Timeouts, malformed output, sandbox
    crashes, permission errors, and partial results are first-class
    outcomes.

------------------------------------------------------------------------

## 4. Technical Baseline

Use this as the initial stack unless a discovery spike reveals a
concrete blocker. Keep versions pinned and compatible rather than
upgrading dependencies opportunistically during feature development.

### 4.1 Frontend

-   Next.js with React and TypeScript.
-   App Router and server/client component boundaries used
    intentionally.
-   Tailwind CSS and a small, consistent component system.
-   Accessible primitives for dialogs, menus, tabs, and tooltips.
-   A charting library only where data visualization materially improves
    the investigation.
-   A typed API client generated from or checked against the backend
    OpenAPI contract.
-   Playwright for end-to-end UI tests.
-   A centralized design-token layer based on `DESIGN_SYSTEM.md`.

### 4.2 Backend

-   Python and FastAPI.
-   Pydantic request/response models.
-   SQLAlchemy 2.x or an equivalent typed persistence layer.
-   Alembic for database migrations.
-   PostgreSQL as the source of truth for application and workflow
    state.
-   A durable background-job mechanism. For a minimal first release, use
    a database-backed job table and worker with locking/leases;
    introduce Redis or a dedicated queue only when justified.
-   A dedicated execution worker service that is separate from the API
    process.
-   Playwright browser automation executed only inside the isolated
    worker environment.
-   Git CLI or GitPython for repository inspection and diff operations,
    with subprocess arguments passed safely and commands allowlisted.

### 4.3 AI and multimodal layer

-   A provider adapter for Meta Model API / Muse Spark.
-   Structured Pydantic schemas for all model-produced plans,
    hypotheses, test proposals, and patch explanations.
-   Tool-calling orchestration controlled by backend policy, not by raw
    model-generated shell commands.
-   Explicit timeouts, bounded retries, token/context limits, and usage
    logging.
-   A deterministic evidence packer that chooses relevant files and
    evidence under a budget.
-   Screenshot and trace artifacts referenced by stable evidence IDs.
-   Optional image-capable model calls only when the configured provider
    supports the required image input.
-   Deterministic fallback behavior when the model is unavailable or
    returns invalid output.

**Important:** Confirm current API access, supported model identifiers,
image-input capability, tool-calling format, rate limits, and terms
before committing to a specific provider contract. Keep the provider
behind an adapter so the rest of Meridian does not depend on one
vendor's response format.

### 4.4 Storage and deployment

-   PostgreSQL for structured records.
-   Private object storage for screenshots, traces, logs, attachments,
    reports, and larger evidence artifacts.
-   Local filesystem storage only for local development, behind the same
    storage interface.
-   Environment-based secrets; never commit credentials.
-   Separate development, test, and production configuration.
-   Containerized API and worker services where supported.
-   CI checks for linting, typing, unit tests, migrations, and
    security-sensitive tests.
-   Centralized structured logs with correlation IDs and redaction.

### 4.5 Explicitly defer

-   ChromaDB/vector database until measured repository retrieval needs
    justify it.
-   Kubernetes until operational scale requires it.
-   Complex multi-agent frameworks until a simpler orchestrator proves
    insufficient.
-   WebSockets if polling is enough for the first reliable workflow.
-   Multiple model providers until a provider adapter and evaluation set
    are in place.

------------------------------------------------------------------------

## 5. Target Architecture

### 5.1 Logical components

1.  **Web application:** authentication UI, workspaces, projects,
    investigation workspace, evidence viewer, hypothesis review, patch
    review, verification, reports, settings.
2.  **API service:** authentication/authorization enforcement,
    validation, resource management, job submission, state transitions,
    signed-download authorization, audit records.
3.  **Workflow orchestrator:** advances an investigation through
    validated stages and handles retries, cancellation, timeouts, and
    terminal outcomes.
4.  **Job store/dispatcher:** durably records pending work and supports
    worker leases, retries, and recovery after process restart.
5.  **Execution worker:** runs untrusted repository commands and browser
    automation inside a restricted environment.
6.  **Evidence service:** stores metadata in PostgreSQL and binary
    artifacts in private object storage.
7.  **AI reasoning service:** builds bounded context, invokes the model
    adapter, validates structured output, and records model interactions
    safely.
8.  **Verification engine:** converts command/test execution results
    into deterministic check statuses.
9.  **Report service:** assembles a report from persisted records and
    links to authorized artifacts.
10. **PostgreSQL:** authoritative structured state.
11. **Object storage:** private evidence artifacts and generated
    reports.

### 5.2 Trust boundaries

-   Browser ↔ API: authenticated user traffic; validate all inputs.
-   API ↔ database: service credentials with least privilege.
-   API ↔ object storage: private access; authorize before issuing
    temporary download links.
-   API/orchestrator ↔ model provider: outbound provider requests;
    secrets stay server-side.
-   Orchestrator ↔ worker: typed job contract; no unrestricted command
    interface.
-   Worker ↔ repository code: untrusted code boundary.
-   Worker ↔ network: deny by default; allow only explicitly required
    destinations.
-   Model output ↔ execution policy: untrusted proposal; validate every
    field and map it to an allowlisted operation.
-   Workspace ↔ workspace: strict tenant isolation on every read and
    write.

### 5.3 High-level investigation flow

`User request → API validation → persisted investigation → durable job → snapshot validation → project profile selection → isolated reproduction → evidence capture → AI hypothesis proposal → regression test proposal → baseline test → patch proposal → human approval → isolated patch application → post-patch checks → deterministic verification → report`

At every step, persist input references, output references, status,
timing, error classification, and relevant artifact IDs.

------------------------------------------------------------------------

## 6. State Machine and Outcome Semantics

### 6.1 Main stages

1.  `PROJECT_INSPECTION`
2.  `PLAN_INVESTIGATION`
3.  `REPRODUCTION`
4.  `EVIDENCE_ANALYSIS`
5.  `HYPOTHESIS_REVIEW`
6.  `REGRESSION_TEST_CREATION`
7.  `BASELINE_TEST_EXECUTION`
8.  `PATCH_PROPOSAL`
9.  `AWAITING_USER_APPROVAL`
10. `PATCH_APPLICATION`
11. `POST_PATCH_VERIFICATION`
12. `REPORT_GENERATION`

Terminal states:

-   `COMPLETED`
-   `FAILED`
-   `BLOCKED`
-   `INCONCLUSIVE`
-   `CANCELLED`

A stage may have its own `PENDING`, `RUNNING`, `SUCCEEDED`, `FAILED`,
`BLOCKED`, `SKIPPED`, `TIMED_OUT`, or `INCONCLUSIVE` status, as
appropriate.

### 6.2 Transition requirements

-   Validate every transition against an explicit transition table.
-   Record stage start/end timestamps and duration.
-   Persist a stage result before moving to the next stage.
-   Use idempotency keys for user-triggered creation and retry
    operations.
-   Ensure duplicate worker delivery cannot apply a patch or generate
    duplicate side effects.
-   Treat cancellation as cooperative and bounded; terminate the
    associated worker job where possible.
-   Recover expired worker leases after a crash.
-   Keep retry count and last error classification.
-   Never retry a non-idempotent operation without an explicit safe
    retry policy.

### 6.3 Verification statuses

-   `PASSED`: required configured checks actually ran and passed.
-   `FAILED`: at least one required check ran and failed.
-   `BLOCKED`: required verification could not run because a
    prerequisite or safety gate was not met.
-   `INCONCLUSIVE`: results do not establish pass or failure, such as a
    reproduction that could not be made deterministic.
-   `SKIPPED`: an optional check was intentionally not run; never
    equivalent to pass.
-   `TIMED_OUT`: a configured execution limit was exceeded.

The overall status must be computed from persisted check records and
release policy. The model may explain the result but cannot set the
authoritative verification status.

------------------------------------------------------------------------

## 7. Repository and Workspace Structure

Start with a monorepo so the frontend, backend, contracts, and
infrastructure can evolve together. Keep the worker logically and
operationally isolated even if its code lives in the same repository.

Suggested structure:

``` text
meridian/
├── apps/
│   └── web/                    # Next.js frontend
├── services/
│   ├── api/                    # FastAPI application
│   ├── orchestrator/            # Durable workflow coordination
│   └── worker/                 # Isolated execution worker
├── packages/
│   ├── api-client/              # Typed frontend API client
│   ├── contracts/               # Shared API/schema fixtures where practical
│   └── ui/                      # Shared UI components if justified
├── migrations/                  # Alembic migrations or backend-owned migrations
├── infra/
│   ├── dev/                     # Local development services
│   ├── deployment/              # Deployment definitions
│   └── security/                # Sandbox and policy configuration
├── tests/
│   ├── integration/
│   ├── e2e/
│   ├── security/
│   └── fixtures/
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── DATABASE.md
│   ├── API.md
│   ├── DESIGN_SYSTEM.md
│   ├── SECURITY.md
│   └── IMPLEMENTATION_PLAN.md
├── .env.example
├── .gitignore
├── README.md
└── package/tool configuration files
```

This is a logical layout, not a reason to create empty packages. Add
modules only when there is a real implementation responsibility.

### 7.1 Module boundaries

**Frontend modules** - `app/`: routes and page composition. -
`features/auth/` - `features/workspaces/` - `features/projects/` -
`features/investigations/` - `features/evidence/` -
`features/hypotheses/` - `features/patches/` -
`features/verification/` - `features/reports/` - `components/ui/` -
`lib/api/`, `lib/auth/`, `lib/format/`

**Backend modules** - `auth/` - `workspaces/` - `projects/` -
`repository/` - `investigations/` - `workflow/` - `jobs/` -
`execution/` - `evidence/` - `ai/` - `hypotheses/` -
`regression_tests/` - `patches/` - `verification/` - `reports/` -
`audit/` - `common/`

Keep API route handlers thin. Business rules belong in services/domain
modules. Database access should be explicit and testable. Avoid circular
imports and giant files.

------------------------------------------------------------------------

## 8. Phase-by-Phase Roadmap

The estimates below are directional engineering effort, not a promise of
calendar delivery. Parallel work is possible only after contracts and
dependencies stabilize. For a small student team, prioritize the
critical path over simultaneous feature development.

### Phase 0 --- Discovery, repository bootstrap, and delivery controls

**Goal:** Create a clean, reproducible development foundation.

**Tasks** - \[ \] Confirm the MVP journey, supported stack, onboarding
method, and seeded bug scenarios. - \[ \] Review `PRD.md`,
`ARCHITECTURE.md`, `DATABASE.md`, `API.md`, `DESIGN_SYSTEM.md`, and
`SECURITY.md` together for conflicts. - \[ \] Create the Git repository
and protected main branch. - \[ \] Establish monorepo structure and
contribution conventions. - \[ \] Add `.env.example`; document required
and optional variables. - \[ \] Pin runtime and dependency versions. -
\[ \] Add formatting, linting, static type checks, and test commands. -
\[ \] Add local development configuration for PostgreSQL and
object-storage emulation if selected. - \[ \] Add CI for install, lint,
type-check, tests, migration validation, and build. - \[ \] Create a
decision log for unresolved architecture choices. - \[ \] Create a
threat-model checklist and a definition-of-done template.

**Acceptance criteria** - A new contributor can clone the repository and
follow the README to start the development environment. - No real
secrets are committed. - CI runs on a clean checkout. - All six existing
specifications are linked from the documentation index. - Major
decisions have owners and explicit open questions.

**Exit gate:** Do not build product features until the repository can be
installed, checked, and tested repeatably.

### Phase 1 --- Design foundation and application shell

**Goal:** Establish the premium visual language and real navigation
before adding complex feature screens.

**Tasks** - \[ \] Convert `DESIGN_SYSTEM.md` into CSS variables/design
tokens. - \[ \] Define typography, spacing, borders, surface hierarchy,
focus rings, and status colors. - \[ \] Build reusable buttons, inputs,
text areas, select menus, dialogs, tabs, badges, tooltips, cards,
tables, skeletons, and toast/alert components. - \[ \] Implement
responsive layout primitives and navigation shell. - \[ \] Build landing
page, sign-in/sign-up screens, workspace shell, and
project/investigation navigation placeholders. - \[ \] Implement
loading, empty, error, disabled, and permission-denied states. - \[ \]
Add keyboard navigation, semantic landmarks, and reduced-motion
support. - \[ \] Add visual regression or screenshot baselines for key
viewports.

**Acceptance criteria** - The application is visually consistent with
the design system. - All shared controls have documented states and
accessible labels. - Layout works at narrow mobile, tablet, laptop, and
wide desktop widths. - No page relies on hardcoded fake investigation
data presented as real product state.

**Exit gate:** Design primitives and navigation are stable enough to
build features without duplicating UI patterns.

### Phase 2 --- Backend foundation, identity, and tenancy

**Goal:** Establish secure application identity and workspace ownership.

**Tasks** - \[ \] Create the FastAPI application factory and versioned
`/api/v1` routing. - \[ \] Configure Pydantic settings and environment
validation. - \[ \] Connect PostgreSQL and establish transaction/session
conventions. - \[ \] Add Alembic and the first migration. - \[ \]
Implement health/readiness endpoints without leaking secrets. - \[ \]
Implement authentication using the selected identity strategy. - \[ \]
Verify tokens server-side; do not trust frontend-only route guards. - \[
\] Implement users, workspaces, workspace membership, roles, and
invitations only if needed for MVP. - \[ \] Add authorization
dependencies for workspace-scoped resources. - \[ \] Add request IDs,
structured logs, safe exception handlers, and audit events. - \[ \] Add
rate limits for sensitive endpoints where the deployment supports
them. - \[ \] Add unit and integration tests for authorization and
tenant isolation.

**Acceptance criteria** - Unauthenticated requests cannot access
protected data. - A user cannot access another workspace by changing an
ID in the URL or request body. - Database migrations run from an empty
database. - Logs do not contain tokens, passwords, secrets, or
unredacted sensitive payloads. - Health checks distinguish service
liveness from dependency readiness.

**Exit gate:** Identity and tenancy tests pass before project or
evidence APIs are exposed.

### Phase 3 --- Database model and core CRUD APIs

**Goal:** Implement the authoritative records required for the
investigation lifecycle.

**Tasks** - \[ \] Implement the schema and indexes defined in
`DATABASE.md`. - \[ \] Review uniqueness, foreign keys, cascade
behavior, tenant-scoped queries, and retention. - \[ \] Add
users/workspaces/memberships, projects, repository snapshots,
investigations, stage records, evidence, tool runs, hypotheses,
hypothesis-evidence links, regression tests, patches, verification
runs/checks, activity events, audit events, and idempotency records as
needed by the MVP. - \[ \] Implement workspace and project CRUD APIs. -
\[ \] Implement investigation create/list/detail/cancel endpoints. - \[
\] Implement pagination, filtering, stable ordering, and consistent
error schemas. - \[ \] Implement idempotent investigation creation. - \[
\] Implement activity timeline and stage-status read APIs. - \[ \] Add
API contract tests and generated OpenAPI review. - \[ \] Keep
destructive deletion behavior explicit; do not cascade-delete evidence
unexpectedly.

**Acceptance criteria** - Database constraints enforce core
relationships. - API responses conform to `API.md`. - Pagination does
not leak cross-tenant records. - Duplicate requests with the same
idempotency key do not create duplicate investigations. - Every
important state mutation produces an audit/activity record.

**Exit gate:** Frontend can create and retrieve real workspaces,
projects, and investigations through the API.

### Phase 4 --- Project onboarding and immutable repository snapshots

**Goal:** Safely ingest and identify a project version.

**Tasks** - \[ \] Implement one onboarding path first: validated ZIP
upload or a narrowly scoped Git integration. - \[ \] Enforce file-size,
entry-count, expanded-size, nesting-depth, and processing-time limits. -
\[ \] Reject path traversal, absolute paths, unsafe links,
duplicate/conflicting paths, and suspicious archive entries. - \[ \]
Store uploaded source in a staging area; never extract into the API
application's working directory. - \[ \] Detect the supported project
profile from manifests and lockfiles without running install scripts. -
\[ \] Create an immutable snapshot and calculate a content hash. - \[ \]
Record language/framework/runtime hints and validation warnings. - \[ \]
Keep uploaded secrets from being echoed into logs or AI context; add
basic secret detection and warnings. - \[ \] Create project onboarding
UI with progress, validation summary, and actionable errors. - \[ \] Add
adversarial archive tests and snapshot-integrity tests.

**Acceptance criteria** - A supported fixture can be ingested and
identified deterministically. - Unsafe archives are rejected before
execution. - Snapshot content is immutable and hash-addressable. -
Unsupported projects are marked unsupported with a clear reason. -
Upload failures clean up temporary artifacts safely.

**Exit gate:** A project snapshot can be referenced reliably by every
later stage.

### Phase 5 --- Durable jobs and workflow orchestration

**Goal:** Make investigations survive API and worker restarts.

**Tasks** - \[ \] Implement a durable job table/queue with status,
attempt count, lease expiry, retry policy, and correlation ID. - \[ \]
Implement a worker dispatcher and lease/heartbeat mechanism. - \[ \]
Implement the state transition table and validate all transitions
centrally. - \[ \] Persist stage start, end, status, output references,
and classified errors. - \[ \] Add safe retry from explicitly retryable
stages. - \[ \] Implement cancellation and bounded shutdown behavior. -
\[ \] Prevent duplicate execution and duplicate side effects on
redelivery. - \[ \] Implement recovery of expired leases. - \[ \] Add
concurrency limits per workspace/project and global worker capacity. -
\[ \] Add API polling endpoint for investigation status and stage
history. - \[ \] Build the frontend activity timeline from persisted
state.

**Acceptance criteria** - Restarting the API does not lose queued
work. - Restarting a worker allows a lease to expire and the job to be
recovered. - Duplicate job delivery does not apply the same patch
twice. - Every terminal outcome has a persisted reason. - UI progress is
based on backend state, not a timer or local mock.

**Exit gate:** A no-op investigation can travel through the workflow
engine with durable, testable transitions.

### Phase 6 --- Isolated execution worker and project profiles

**Goal:** Run supported project commands safely outside the API process.

**Tasks** - \[ \] Define a typed job contract between orchestrator and
worker. - \[ \] Create a separate worker service and isolated execution
environment. - \[ \] Enforce CPU, memory, process-count, disk, and
wall-clock limits. - \[ \] Run as a non-root user; do not mount the
Docker socket or host credentials. - \[ \] Use a read-only base
filesystem where feasible and a per-job writable workspace. - \[ \] Deny
outbound network by default; permit only explicitly required
destinations. - \[ \] Apply environment-variable allowlists and prevent
secret inheritance. - \[ \] Define supported runtime images and project
profiles. - \[ \] Allowlist commands and arguments; do not pass
model-generated command strings to a shell. - \[ \] Capture
stdout/stderr with size limits and redaction. - \[ \] Kill process trees
on timeout/cancellation. - \[ \] Record exit code, duration, command
profile, resource outcome, and artifact references. - \[ \] Add sandbox
escape and policy regression tests.

**Acceptance criteria** - The API process never executes repository
code. - A fixture can run an approved command inside the worker. -
Network, CPU, memory, disk, and timeout controls are demonstrably
enforced. - Disallowed commands and unsafe arguments are rejected. -
Worker failure is reported without falsely marking the investigation as
complete.

**Exit gate:** Security review approves the worker threat boundary
before untrusted repository execution is enabled.

### Phase 7 --- Browser reproduction and multimodal evidence

**Goal:** Attempt reproduction and capture evidence that users can
inspect.

**Tasks** - \[ \] Integrate Playwright in the isolated worker. - \[ \]
Start the application using a supported project profile and allowlisted
command. - \[ \] Use bounded startup and navigation timeouts. - \[ \]
Support structured reproduction steps: URL, actions, expected behavior,
and assertions. - \[ \] Capture screenshots at defined checkpoints. - \[
\] Capture browser console errors, page errors, failed requests,
response status codes, and relevant timing. - \[ \] Capture a Playwright
trace where practical and within storage limits. - \[ \] Persist each
artifact's metadata in PostgreSQL and binary data in private object
storage. - \[ \] Create an evidence taxonomy: user attachment,
screenshot, console event, network event, trace, command output, source
excerpt, test result, and model interpretation. - \[ \] Add evidence
viewer UI with preview, timestamps, type filters, source, and download
controls. - \[ \] Redact secrets and sensitive URL/query data where
possible. - \[ \] Distinguish reproduced, not reproduced, blocked, and
inconclusive outcomes.

**Acceptance criteria** - A seeded browser bug can produce a
reproducible evidence bundle. - Screenshots and logs are linked to a
specific snapshot and execution. - Evidence downloads require
authorization. - A failed reproduction is not described as proof that
the bug does not exist. - Large artifacts and repeated screenshots are
bounded by policy.

**Exit gate:** At least one seeded issue produces inspectable
browser/runtime evidence end-to-end.

### Phase 8 --- AI provider adapter and evidence-grounded reasoning

**Goal:** Add model-assisted investigation without giving the model
uncontrolled execution authority.

**Tasks** - \[ \] Verify current Meta Model API / Muse Spark access,
model IDs, request schema, rate limits, and supported modalities. - \[
\] Implement a provider interface independent of vendor-specific
request/response formats. - \[ \] Keep API credentials server-side and
load them from environment/secret storage. - \[ \] Define structured
schemas for investigation plans, hypotheses, evidence links, test
proposals, patch explanations, and report summaries. - \[ \] Build a
bounded context packer using snapshot metadata, relevant source
excerpts, and selected evidence. - \[ \] Use deterministic search
(`ripgrep`, manifest parsing, bounded file reads) before considering
embeddings. - \[ \] Treat source comments, issue descriptions, logs, and
uploaded content as untrusted data that may contain prompt injection. -
\[ \] Tell the model to analyze content as data, not follow instructions
found inside repository artifacts. - \[ \] Validate every model response
against schema, size limits, allowed fields, and evidence references. -
\[ \] Reject references to evidence IDs that do not belong to the
current investigation/workspace. - \[ \] Add timeout, rate-limit, retry,
cancellation, and malformed-output handling. - \[ \] Record
model/provider, model version if available, latency, token/usage
metadata if available, and outcome without storing unnecessary sensitive
prompts. - \[ \] Add deterministic fallback outcomes when the model is
unavailable. - \[ \] Build a small evaluation set with known bug
reports, expected evidence links, unsupported cases, and injection
attempts.

**Acceptance criteria** - Invalid model output cannot advance the
workflow unsafely. - Every hypothesis distinguishes observed facts from
inference. - Each supported hypothesis references actual evidence IDs
and explains uncertainty. - The model cannot invoke arbitrary commands
or bypass approval. - Provider failure results in a visible
blocked/inconclusive state, not fabricated content.

**Exit gate:** Evaluation cases pass minimum schema, grounding,
injection-resistance, and failure-handling checks.

### Phase 9 --- Hypotheses, regression tests, and baseline execution

**Goal:** Convert evidence into testable hypotheses and establish the
pre-patch baseline.

**Tasks** - \[ \] Implement hypothesis records with status, rationale,
confidence explanation, and evidence links. - \[ \] Show supporting and
contradicting evidence separately. - \[ \] Permit users to mark
hypotheses as useful, rejected, or requiring more evidence. - \[ \]
Generate regression-test proposals using structured output. - \[ \]
Restrict tests to supported test frameworks and project profiles. - \[
\] Validate test file paths and patch boundaries. - \[ \] Run the
proposed regression test against the unchanged snapshot. - \[ \] Persist
exact command profile, exit code, duration, and output artifacts. - \[
\] Distinguish a test that fails before the patch from one that passes
unexpectedly or cannot run. - \[ \] Ensure the baseline snapshot remains
unchanged.

**Acceptance criteria** - Hypotheses have evidence links that resolve to
real records. - Proposed tests are reviewed/validated before
execution. - Baseline outcomes are persisted and visible. - The UI does
not claim a regression test reproduces the bug unless execution
demonstrates it. - Failure to establish a useful baseline is represented
accurately.

**Exit gate:** At least one seeded bug has an evidence-linked hypothesis
and a meaningful baseline test result.

### Phase 10 --- Patch generation, diff review, and human approval

**Goal:** Create a minimal, reviewable patch and keep the user in
control.

**Tasks** - \[ \] Generate patch proposals from a bounded source context
and explicit evidence. - \[ \] Apply candidate changes only to a
disposable, isolated working copy. - \[ \] Validate changed paths
against workspace and patch policies. - \[ \] Reject absolute paths,
traversal, binary changes unless explicitly supported, excessive file
counts, and oversized diffs. - \[ \] Compute and persist a base snapshot
hash and patch/diff hash. - \[ \] Display additions, deletions, changed
files, rationale, risk, and linked evidence. - \[ \] Provide approve and
reject actions with clear consequences. - \[ \] Bind approval to the
exact patch hash, base snapshot, and investigation. - \[ \] Revalidate
the hash and state immediately before application. - \[ \] Prevent
duplicate approval requests from applying the patch more than once. - \[
\] Record who approved/rejected and when. - \[ \] Do not push or merge
to a remote repository in the MVP.

**Acceptance criteria** - No patch is applied without explicit user
approval. - The exact approved diff is the diff that gets applied. - A
changed base snapshot invalidates approval and requires review. -
Rejected patches are retained as audit history but not applied. - Patch
application failure is reported clearly and safely.

**Exit gate:** A user can inspect and approve a patch whose base and
content are cryptographically bound to the approval record.

### Phase 11 --- Verification engine and report generation

**Goal:** Produce a trustworthy result from actual post-patch execution.

**Tasks** - \[ \] Run required checks on the patched isolated
workspace. - \[ \] Run the regression test and selected project-profile
checks. - \[ \] Persist every check separately, including command
profile, exit code, duration, output reference, and status. - \[ \]
Compute aggregate verification status using deterministic policy. - \[
\] Distinguish failed, blocked, skipped, timed-out, and inconclusive
checks. - \[ \] Compare baseline and post-patch outcomes where
relevant. - \[ \] Create a report from persisted records---not free-form
model claims alone. - \[ \] Include issue summary, snapshot identity,
reproduction result, evidence index, hypotheses, proposed/approved
changes, check results, limitations, and timestamps. - \[ \] Generate a
downloadable Markdown or HTML report first; add PDF only if it improves
the actual workflow and can be tested reliably. - \[ \] Store report
artifacts privately and authorize every download. - \[ \] Add report
rendering tests for escaped source content and untrusted strings.

**Acceptance criteria** - The aggregate result is reproducible from
persisted verification checks. - Missing or skipped checks never become
a pass. - The report states exactly which checks ran and which did
not. - The report can be regenerated from stored records. - All report
and evidence downloads enforce authorization.

**Exit gate:** The seeded bug completes the
approved-patch-to-verification-to-report journey without invented
results.

### Phase 12 --- Product integration and premium UX completion

**Goal:** Replace disconnected screens with a coherent product
experience.

**Tasks** - \[ \] Connect all screens to real API endpoints. - \[ \]
Implement workspace/project navigation and recent activity. - \[ \]
Build investigation creation and guided input validation. - \[ \] Build
investigation workspace with stage timeline, current activity, evidence,
hypotheses, tests, patch, and verification sections. - \[ \] Implement
polling with sensible intervals, backoff, visibility awareness, and
cleanup. - \[ \] Add retry/cancel actions only where backend semantics
support them. - \[ \] Add informative empty states, loading skeletons,
inline validation, toasts, and recovery guidance. - \[ \] Add responsive
layouts for investigation and diff review. - \[ \] Add accessibility
review, keyboard-only pass, focus management, and contrast checks. - \[
\] Remove all mock data, placeholder success states, and fake progress
from production paths. - \[ \] Add telemetry for key UX errors without
collecting sensitive source contents.

**Acceptance criteria** - A user can complete the primary journey
without developer tools or manual database edits. - Every action has a
clear pending, success, failure, or blocked state. - UI labels match
authoritative backend statuses. - Critical workflows work at laptop and
mobile widths. - No sensitive data is rendered to unauthorized users.

**Exit gate:** A user unfamiliar with the codebase can complete the demo
flow from the UI.

### Phase 13 --- Security hardening, reliability, and release candidate

**Goal:** Prove the product behaves safely under failure and adversarial
input.

**Tasks** - \[ \] Review `SECURITY.md` against the actual
implementation. - \[ \] Test tenant isolation for every resource type
and download route. - \[ \] Test malicious ZIPs, path traversal, symlink
abuse, huge archives, and decompression bombs. - \[ \] Test prompt
injection in bug reports, source comments, logs, README files, and image
OCR/visible text where applicable. - \[ \] Test malformed model output,
tool policy violations, provider timeouts, and rate limits. - \[ \] Test
worker timeout, memory exhaustion, network denial, cancellation, crash,
and lease recovery. - \[ \] Test patch traversal, stale base snapshots,
altered diff hashes, and duplicate approval. - \[ \] Test object-storage
authorization, expired links, content types, and cache policy. - \[ \]
Add dependency and secret scanning in CI. - \[ \] Add database
backup/restore procedure and retention policy. - \[ \] Add operational
runbook for failed jobs, stuck leases, provider outage, and
evidence-storage outage. - \[ \] Load-test bounded concurrency and
measure p50/p95 API latency for key endpoints. - \[ \] Add structured
alerts/health indicators appropriate to the chosen hosting platform. -
\[ \] Complete manual UX and accessibility review.

**Acceptance criteria** - No known critical/high severity issue remains
unresolved for the release scope. - Recovery and failure behavior is
documented and tested. - No untrusted code execution occurs in the API
process. - No false-positive verification pass can be produced by
skipped or missing checks. - Backups and restoration are demonstrated in
a non-production environment.

**Exit gate:** Release checklist signed off by engineering and product
owners.

### Phase 14 --- Demo readiness and controlled release

**Goal:** Deliver a stable, repeatable demonstration and a deployable
MVP.

**Tasks** - \[ \] Prepare at least two seeded fixtures: one fixable bug
and one blocked/inconclusive scenario. - \[ \] Reset fixtures to known
snapshot hashes before each demo. - \[ \] Create a scripted demo
checklist with expected outputs and fallback explanation. - \[ \] Verify
provider credentials and quotas before demo day. - \[ \] Preflight
database, object storage, worker capacity, browser dependencies, and
deployment environment. - \[ \] Verify logs and reports do not leak
secrets. - \[ \] Run the full end-to-end suite from a clean
environment. - \[ \] Record a backup demo video only after the live path
has been tested. - \[ \] Tag the release candidate and document known
limitations. - \[ \] Freeze risky feature work before the deadline;
prioritize fixes to demo blockers.

**Acceptance criteria** - The same seeded scenario can be reset and run
repeatedly. - The primary flow is tested from a clean deployment. - A
provider outage or unsupported project yields an honest fallback
state. - The team can explain the architecture, safety boundaries, and
limitations. - The release includes setup instructions and a concise
known-limitations section.

------------------------------------------------------------------------

## 9. Critical Path and Dependency Map

The implementation should follow this dependency order:

``` text
Repository bootstrap
   ├── Design tokens + application shell
   └── API + database + authentication
          └── Workspace/project/investigation CRUD
                 └── Safe project ingestion + immutable snapshots
                        └── Durable jobs + state machine
                               └── Isolated worker + project profile
                                      └── Browser reproduction + evidence
                                             └── AI adapter + grounded hypotheses
                                                    └── Regression test + baseline
                                                           └── Patch proposal + approval
                                                                  └── Post-patch verification
                                                                         └── Report
                                                                                └── Hardening + release
```

Some design and backend tasks can run in parallel, but AI orchestration
should not become the critical path before persistence, evidence IDs,
worker contracts, and stage semantics are stable.

### Recommended vertical-slice order

1.  User can sign in and create a workspace.
2.  User can create a project and upload a supported fixture.
3.  User can create an investigation and see durable status.
4.  Worker can execute one allowlisted command on the fixture.
5.  Playwright captures one real browser failure.
6.  Model produces a schema-valid, evidence-linked hypothesis.
7.  A regression test runs on the baseline.
8.  Patch diff is generated and reviewed.
9.  User approves and the patch is applied in isolation.
10. Verification runs and the report is generated.

------------------------------------------------------------------------

## 10. API Implementation Workstreams

Use `API.md` as the contract source of truth. Implement only endpoints
needed by the current vertical slice, but preserve consistent naming,
error shapes, and authorization rules.

### Workstream A --- Identity and workspaces

-   Authentication/session validation.
-   Workspace list/create/detail/update.
-   Membership and role checks.
-   Audit events.

### Workstream B --- Projects and snapshots

-   Project CRUD.
-   Upload initialization/completion or Git import.
-   Ingestion status.
-   Snapshot metadata and hash.
-   Project profile detection.

### Workstream C --- Investigations and jobs

-   Create/list/detail/cancel.
-   Durable job dispatch.
-   Stage history and activity timeline.
-   Retry from supported checkpoints.
-   Idempotency and concurrency protection.

### Workstream D --- Evidence

-   Evidence list/detail.
-   Authorized artifact preview/download.
-   Metadata filtering and pagination.
-   Retention and redaction policy.

### Workstream E --- Reasoning and hypotheses

-   Investigation plan proposal.
-   Hypotheses and evidence links.
-   User feedback on hypotheses.
-   Model-call status and failure records.

### Workstream F --- Tests and patches

-   Regression-test proposals.
-   Baseline test runs.
-   Patch proposal and diff metadata.
-   Approval/rejection.
-   Isolated patch application.

### Workstream G --- Verification and reports

-   Verification run and individual check results.
-   Aggregate status.
-   Report creation and retrieval.
-   Authorized report download.

Every endpoint needs: - Authentication and tenant authorization. -
Request/response schema validation. - Consistent error codes. - Audit
behavior for meaningful mutations. - Idempotency for retry-prone
creation/actions. - Tests for expected and forbidden access.

------------------------------------------------------------------------

## 11. AI/GenAI Engineering Plan

### 11.1 Use bounded, explicit reasoning tasks

Avoid sending the entire repository or complete raw logs to the model.
Use separate tasks with narrow inputs and typed outputs:

1.  **Investigation planner:** proposes a small set of permitted
    inspection actions.
2.  **Evidence analyst:** summarizes actual evidence and identifies
    gaps.
3.  **Hypothesis generator:** returns candidate explanations with
    supporting/contradicting evidence IDs.
4.  **Regression-test proposer:** returns a supported test proposal, not
    arbitrary shell commands.
5.  **Patch proposer:** suggests a minimal file change against a fixed
    snapshot.
6.  **Report summarizer:** explains persisted results without changing
    their authoritative statuses.

These are logical roles, not a requirement to run six independent
agents. Start with one orchestrator and a small number of model calls.
Split into separate agents only when evaluation demonstrates a quality
or maintainability benefit.

### 11.2 Model/tool boundary

The model can request a typed operation such as:

-   `inspect_manifest`
-   `search_repository`
-   `read_file_excerpt`
-   `run_supported_profile_check`
-   `navigate_and_capture`
-   `analyze_evidence`
-   `propose_regression_test`
-   `propose_patch`

The backend validates the request and decides whether it is permitted.
The model must not provide an arbitrary executable shell command,
unrestricted URL, filesystem path, or network destination.

### 11.3 Evidence-grounding contract

For each hypothesis, persist: - Hypothesis text. - Evidence IDs
supporting it. - Evidence IDs contradicting it. - Confidence level or
calibrated uncertainty. - Reasoning summary. - Known gaps. -
Model/provider metadata where appropriate.

Reject evidence IDs outside the current investigation. Mark a hypothesis
as unverified until supported by a real observation or test. Do not
confuse a model-generated explanation with a reproduced root cause.

### 11.4 Evaluation before expansion

Create a small fixed evaluation dataset with: - Known fixable bugs. -
Bugs that cannot be reproduced reliably. - Unsupported project
profiles. - Missing dependencies and startup failures. - Contradictory
logs. - Prompt injection in source files and issue descriptions. -
Malformed model responses. - Provider timeout/rate-limit cases. -
Patches that fix one test but break another.

Track at minimum: - Valid structured-output rate. - Evidence-reference
validity rate. - Unsupported claims per investigation. - Correct
blocked/inconclusive rate. - Regression test execution rate. - Patch
application success rate. - Post-patch test pass/fail accuracy. - Cost
and latency per successful investigation.

Do not optimize for "fix rate" alone; that encourages unsafe
overconfidence.

------------------------------------------------------------------------

## 12. Multimodal Evidence Plan

Meridian's multimodal features should improve debugging, not serve as
decoration.

### Inputs

-   User screenshots.
-   Browser screenshots.
-   Playwright traces.
-   Console and page errors.
-   Failed network requests and response metadata.
-   Source excerpts.
-   Command/test output.
-   Optional logs and small text attachments.

### Processing

-   Validate file type and size; do not trust extensions or MIME headers
    alone.
-   Store original artifacts privately.
-   Create safe previews/thumbnails where useful.
-   Extract metadata and timestamps.
-   Redact obvious secrets and sensitive URL/query values.
-   Link each artifact to the snapshot, investigation, stage, and tool
    run.
-   Send only relevant, authorized, size-bounded artifacts to a model
    with verified modality support.
-   Treat OCR text and text visible inside screenshots as untrusted
    input.

### User experience

-   Show artifact type, time, origin, and related stage.
-   Allow users to inspect screenshots and text logs without downloading
    everything.
-   Make trace download/inspection optional if the MVP cannot embed a
    trace viewer reliably.
-   Clearly label model-generated annotations versus raw captured
    evidence.
-   Keep access checks on previews and downloads.

### Acceptance criteria

-   Each artifact has a stable evidence ID and source.
-   Unsupported or oversized files are rejected with clear guidance.
-   Raw evidence is not silently replaced by a model summary.
-   Model interpretation is displayed separately from captured facts.

------------------------------------------------------------------------

## 13. Premium UI/UX Implementation Plan

### 13.1 Product experience principles

-   **Quiet confidence:** polished, restrained interface rather than
    excessive gradients, glow, or decoration.
-   **Evidence-first hierarchy:** show the actual observation before the
    AI interpretation.
-   **Progress clarity:** display the current stage, completed stages,
    next action, and blocked reason.
-   **Human control:** patch review and approval are deliberate,
    high-clarity interactions.
-   **Dense but readable:** technical detail should be scannable without
    hiding important context.
-   **Trustworthy status language:** never use a green success state for
    an unverified claim.
-   **Responsive by design:** complex tables and diffs need thoughtful
    small-screen behavior, not simple overflow.

### 13.2 Primary screens

1.  Landing page.
2.  Sign in / sign up.
3.  Workspace home.
4.  Project list and project overview.
5.  Project onboarding and validation.
6.  Investigation creation.
7.  Investigation workspace.
8.  Evidence viewer.
9.  Hypothesis review.
10. Regression-test and baseline results.
11. Patch review/diff.
12. Approval confirmation.
13. Verification results.
14. Report view/download.
15. Workspace settings and security/audit view, if required by MVP.

### 13.3 Investigation workspace layout

Recommended desktop hierarchy: - Left navigation: workspace, project,
investigations. - Main header: issue title, status, snapshot identity,
key actions. - Stage rail/timeline: current stage and completed/blocked
stages. - Main content: evidence and investigation details. - Side panel
or contextual drawer: hypothesis, selected evidence metadata, and
actions. - Dedicated patch-review layout with changed files and diff. -
Verification summary with individual check statuses and logs.

Avoid placing all content into one giant dashboard. Use progressive
disclosure and direct links between a hypothesis and its evidence.

### 13.4 UI quality gates

-   Every interactive element has hover, focus, active, disabled,
    loading, and error states as relevant.
-   Every list has empty, loading, and failure states.
-   Status is conveyed through text/icon as well as color.
-   Keyboard focus remains visible.
-   Dialogs trap and restore focus correctly.
-   Long paths, filenames, stack traces, and diffs wrap or scroll
    safely.
-   Mobile screens prioritize core status and actions; complex diff
    review may use a dedicated layout.
-   Motion is subtle and respects reduced-motion preferences.
-   Screenshot tests cover core screen states and viewport sizes.

------------------------------------------------------------------------

## 14. Database and Data-Lifecycle Plan

Use `DATABASE.md` as the schema contract, but implement migrations
incrementally as modules are built.

### Rules

-   PostgreSQL is the authoritative source for structured workflow
    state.
-   Evidence binaries live in private object storage; PostgreSQL stores
    metadata and references.
-   Every tenant-owned record must be queryable with workspace
    authorization enforced.
-   Snapshot and patch identities must be immutable.
-   Store timestamps in UTC and render in the user's local timezone.
-   Add indexes based on actual query patterns; avoid unmeasured index
    proliferation.
-   Use foreign keys and unique constraints for integrity, not only
    application checks.
-   Use explicit transaction boundaries around stage transitions and
    related events.
-   Avoid storing full raw model prompts/responses when a compact
    redacted record is sufficient.
-   Define retention/deletion behavior for source snapshots, artifacts,
    and reports.
-   Deletion should not silently break audit requirements; document
    soft-delete and retention semantics.

### Data integrity invariants

-   An investigation references one workspace-authorized project and a
    specific snapshot.
-   Evidence belongs to the correct investigation and stage/tool run
    where applicable.
-   Hypothesis-evidence links cannot cross investigation boundaries.
-   Patch approval binds the actor, patch hash, base snapshot, and
    approval timestamp.
-   Verification checks reference an actual execution record.
-   Aggregate verification status is derived from check records and
    policy.
-   Terminal investigations cannot silently resume without an explicit
    retry/resume operation.

------------------------------------------------------------------------

## 15. Security Work Plan

Treat `SECURITY.md` as a release requirement, not optional
documentation.

### Before executing any repository code

-   Validate the source archive/repository metadata.
-   Create an immutable snapshot.
-   Select a known project profile.
-   Build an isolated worker environment.
-   Apply CPU, memory, disk, process, and wall-clock limits.
-   Apply network egress policy.
-   Remove all application secrets from the worker environment.
-   Pass only the minimum necessary job payload.
-   Record the execution policy/version used.

### Before applying a patch

-   Validate schema and changed paths.
-   Check the base snapshot hash.
-   Enforce diff size and file-count limits.
-   Display the exact diff and its hash.
-   Record explicit human approval.
-   Revalidate the approval and hashes immediately before application.
-   Apply in an isolated copy.
-   Do not push or merge remotely.

### Before release

-   Run tenant-isolation tests.
-   Run archive/path-traversal tests.
-   Run prompt-injection and malformed-output tests.
-   Run patch-integrity tests.
-   Test unauthorized artifact/report downloads.
-   Scan dependencies and secrets.
-   Verify that logs redact credentials and sensitive content.
-   Demonstrate recovery from a worker crash.
-   Review data retention and backup policies.

------------------------------------------------------------------------

## 16. Testing Strategy

Testing is required at every phase. Do not defer all tests to the end.

### 16.1 Unit tests

-   State transition validation.
-   Verification status aggregation.
-   Authorization policy helpers.
-   Pydantic schemas and model-output validation.
-   Archive path validation.
-   Patch path and diff validation.
-   Idempotency behavior.
-   Report escaping/redaction.
-   Evidence-reference validation.

### 16.2 Integration tests

-   API + PostgreSQL.
-   Migration from an empty database.
-   Workspace isolation.
-   Project ingestion + snapshot hash.
-   Job leasing, retry, and crash recovery.
-   Object-storage upload/download authorization.
-   AI provider adapter using deterministic mock responses.
-   Worker command execution with resource limits.
-   Evidence persistence and report regeneration.

### 16.3 End-to-end tests

-   Sign in → workspace → project → investigation.
-   Upload fixture → inspect project → capture browser evidence.
-   Hypothesis → regression test → baseline.
-   Patch proposal → reject path.
-   Patch proposal → approve → apply → verify → report.
-   Provider unavailable → honest blocked/inconclusive result.
-   Unsupported project → clear explanation.
-   User from another workspace denied access.

### 16.4 Security tests

-   ZIP traversal and decompression bomb.
-   Symlink/path abuse.
-   Prompt injection in repository and bug report.
-   Arbitrary command attempt.
-   Malformed tool call and invalid evidence ID.
-   Cross-tenant object access.
-   Stale patch approval and diff-hash mismatch.
-   Duplicate job delivery and duplicate approval.
-   Worker timeout and cancellation.
-   Secret leakage in logs, reports, and UI.

### 16.5 Seeded fixtures

Create version-controlled, synthetic fixtures: - **Fixture A --- Fixable
UI bug:** deterministic behavior, expected screenshot or assertion,
regression test, and small patch. - **Fixture B --- Runtime/network
issue:** known console or failed-request evidence with a constrained
expected diagnosis. - **Fixture C --- Inconclusive case:** issue depends
on unavailable external service or nondeterministic behavior. -
**Fixture D --- Unsafe input:** malicious archive or prompt-injection
content that must be handled safely.

Never use real customer repositories or secrets as demo fixtures.

------------------------------------------------------------------------

## 17. Observability and Operations

### Required metadata

-   Request/correlation ID.
-   Workspace, project, investigation, stage, and job IDs where
    appropriate.
-   Job attempt and worker identity.
-   Stage start/end times and duration.
-   Command profile and exit code.
-   Resource-limit outcome.
-   Artifact IDs, not raw sensitive artifact contents.
-   Model provider/model identifier, latency, and usage metadata when
    available.
-   Classified error code and retryability.

### Required operational views or queries

-   Jobs pending/running/failed/stuck.
-   Expired worker leases.
-   Stage duration and failure rate.
-   Provider error/latency rates.
-   Evidence storage failures.
-   Verification outcomes by check type.
-   Worker resource-limit events.
-   Recent authorization denials and security events.

### Operational playbooks

-   Model provider unavailable or rate-limited.
-   Worker crashes or stops claiming jobs.
-   Job stuck after a lease expires.
-   Database unavailable or migration fails.
-   Object storage unavailable.
-   Report generation fails.
-   Suspected cross-tenant access or secret leakage.
-   A release introduces a false-positive verification result.

------------------------------------------------------------------------

## 18. Team Roles and Parallelization

One person may cover multiple roles, but every responsibility needs a
named owner before implementation begins.

  ---------------------------------------------------------------------------
  Workstream              Primary responsibility      Can parallelize after
  ----------------------- --------------------------- -----------------------
  Product scope and       Product lead                Initial MVP definition
  acceptance criteria                                 

  Design system and       UI/UX + frontend            Design tokens approved
  frontend shell                                      

  API/database/auth       Backend lead                Data model and API
                                                      contracts reviewed

  Repository ingestion    Backend/security            Project snapshot
                                                      contract

  Worker/sandbox          Backend/platform/security   Worker job contract and
                                                      threat model

  AI provider and schemas AI/GenAI lead               Evidence and tool
                                                      contracts stable

  Browser evidence        Automation/multimodal       Worker and storage
                                                      contracts stable

  Patch and verification  Full-stack/AI/platform      Snapshot, worker, and
                                                      approval model stable

  E2E/security validation QA/security                 Vertical slice
                                                      available

  Demo/release            Product + engineering       Seeded workflow
                                                      repeatable
  ---------------------------------------------------------------------------

### Collaboration rules

-   Agree on API and database contracts before parallel feature work.
-   Keep a single source of truth for status enums and schema names.
-   Use small pull requests and review security-sensitive changes.
-   No frontend-only simulation may substitute for a missing backend
    feature.
-   Use fixtures and deterministic mock providers for CI; keep
    real-provider smoke tests separate.
-   Document any deviation from the six specifications and update the
    source document.

------------------------------------------------------------------------

## 19. Backlog Prioritization

### P0 --- Release blockers

-   Auth and tenant isolation.
-   Secure source ingestion and immutable snapshots.
-   Durable workflow state.
-   Isolated worker.
-   Actual reproduction/evidence capture.
-   Model-output validation and evidence grounding.
-   Regression-test execution.
-   Human-approved patch.
-   Deterministic post-patch verification.
-   Report generation.
-   Authorization for artifacts.
-   Core E2E and security tests.

### P1 --- Important quality improvements

-   Better trace viewer.
-   Git-provider integration if ZIP onboarding is the first path.
-   SSE live updates.
-   More project profiles.
-   Retry from selected safe checkpoints.
-   Improved report formatting.
-   Model cost and latency dashboard.
-   Enhanced secret redaction.

### P2 --- Post-MVP

-   Repository embeddings/vector database.
-   More languages and frameworks.
-   Team collaboration and review comments.
-   Remote branch/PR integration.
-   Additional model providers.
-   Advanced evaluation dashboard.
-   Organization-level policies and analytics.
-   Long-running continuous monitoring.

Prioritize by risk reduction and end-to-end value, not by how visually
impressive a feature looks.

------------------------------------------------------------------------

## 20. Release Gates

### Gate A --- Foundation

-   Repository setup reproducible.
-   CI green.
-   Database migration from empty database succeeds.
-   Auth and tenant isolation tests pass.

### Gate B --- Real investigation

-   Project snapshot is immutable.
-   Investigation state is durable.
-   Worker executes an approved profile command.
-   Reproduction captures actual evidence.

### Gate C --- AI-assisted investigation

-   Model outputs validate against schemas.
-   Hypotheses link to real evidence.
-   Prompt injection cannot authorize tools.
-   Provider failure is handled truthfully.

### Gate D --- Controlled patch

-   Regression test runs against baseline.
-   Patch diff is validated and shown.
-   Approval binds to the exact diff and snapshot.
-   Patch application occurs only in isolation.

### Gate E --- Verification and report

-   Required checks run after patch.
-   Aggregate status is derived from persisted results.
-   Report accurately lists checks and limitations.
-   Artifact downloads are authorized.

### Gate F --- Release candidate

-   Full seeded E2E passes.
-   Failure/inconclusive fixture behaves correctly.
-   Security checklist has no unresolved release-blocking issue.
-   Backup/recovery and runbooks are tested.
-   Demo reset and recovery procedures are documented.

A failed gate blocks expansion into the next high-risk capability.

------------------------------------------------------------------------

## 21. Definition of Done

A feature is not done merely because the happy path works on a
developer's machine.

Every feature must satisfy the relevant items below:

-   [ ] Acceptance criteria from the task are met.
-   [ ] API contracts and schema types are updated.
-   [ ] Authorization and tenant boundaries are enforced server-side.
-   [ ] Unit and integration tests are added or updated.
-   [ ] Failure, empty, loading, and blocked states are handled.
-   [ ] Logs are structured and sensitive data is redacted.
-   [ ] Migrations are reversible or a safe recovery path is documented.
-   [ ] Timeouts, retries, and idempotency are considered.
-   [ ] Documentation and `.env.example` are updated.
-   [ ] No secrets or real user data are committed.
-   [ ] No fake progress, fake evidence, or simulated verification is
    present.
-   [ ] Accessibility and responsive behavior are checked for UI
    changes.
-   [ ] Security-sensitive changes receive explicit review.
-   [ ] CI passes on a clean checkout.

------------------------------------------------------------------------

## 22. Initial Engineering Tasks

Use this checklist as the first executable backlog. Create issue tickets
from it and assign an owner and estimate to each.

### Sprint/Iteration 0: Build the foundation

-   [ ] Create the repository and monorepo skeleton.
-   [ ] Add the README with setup, architecture, commands, and current
    limitations.
-   [ ] Add `.env.example` and secret-handling rules.
-   [ ] Add frontend and backend package configuration.
-   [ ] Add formatting, linting, type checking, and tests.
-   [ ] Add local PostgreSQL configuration.
-   [ ] Add CI.
-   [ ] Review all six specifications for inconsistencies.
-   [ ] Decide first source-ingestion path.
-   [ ] Verify the model provider's current API capabilities.
-   [ ] Choose initial deployment and object-storage approach.
-   [ ] Create seeded fixture A and fixture C before building
    orchestration.

### Iteration 1: Thin vertical slice

-   [ ] Build the web shell and one authenticated route.
-   [ ] Build API health/readiness routes.
-   [ ] Connect database and run first migration.
-   [ ] Implement workspace and project creation.
-   [ ] Implement a minimal investigation record and status timeline.
-   [ ] Add a durable no-op job that advances through a small set of
    real states.
-   [ ] Confirm frontend reflects persisted state after refresh.

### Iteration 2: Project snapshot and safe worker

-   [ ] Implement source ingestion and archive validation.
-   [ ] Generate immutable snapshot hashes.
-   [ ] Implement worker job contract.
-   [ ] Run one allowlisted project command in isolation.
-   [ ] Persist execution result and logs.
-   [ ] Add timeout and cancellation tests.

### Iteration 3: Browser evidence

-   [ ] Launch fixture application in the worker.
-   [ ] Execute a reproducible Playwright scenario.
-   [ ] Capture screenshot and console/network evidence.
-   [ ] Store evidence metadata and artifacts.
-   [ ] Render evidence in the frontend.

### Iteration 4: AI reasoning and tests

-   [ ] Implement provider adapter and schema validation.
-   [ ] Produce evidence-linked hypotheses.
-   [ ] Generate a supported regression-test proposal.
-   [ ] Execute baseline test and persist result.
-   [ ] Add provider failure and injection tests.

### Iteration 5: Patch, approval, verification

-   [ ] Produce candidate patch in an isolated workspace.
-   [ ] Validate patch paths and size.
-   [ ] Display diff and hash.
-   [ ] Implement approval/rejection with hash binding.
-   [ ] Apply approved patch in isolation.
-   [ ] Run post-patch checks and compute aggregate status.

### Iteration 6: Report and release readiness

-   [ ] Generate report from persisted records.
-   [ ] Complete main E2E test.
-   [ ] Test inconclusive and blocked outcomes.
-   [ ] Complete security checklist.
-   [ ] Test clean deployment and recovery.
-   [ ] Freeze scope and rehearse demo.

These are sequencing labels, not fixed calendar commitments. Re-plan
based on actual team capacity and discovered risks.

------------------------------------------------------------------------

## 23. Risk Register

  -----------------------------------------------------------------------
  Risk              Impact            Mitigation        Trigger to
                                                        revisit
  ----------------- ----------------- ----------------- -----------------
  Model provider    High              Validate access   First integration
  API/access                          early; use        spike fails
  differs from                        adapter and       
  assumptions                         deterministic     
                                      mocks             

  Arbitrary         High              Narrow stack and  Reproduction
  repositories are                    seeded fixtures   success is
  too difficult to                                      inconsistent
  support                                               

  Untrusted code    Critical          Separate worker,  Any
  escapes execution                   strict sandbox,   sandbox-policy
  boundary                            deny-by-default   failure
                                      network, security 
                                      tests             

  AI invents        High              Schema            Unsupported
  evidence or                         validation,       claims appear in
  overstates root                     evidence IDs,     evals
  cause                               deterministic     
                                      status engine,    
                                      evaluations       

  Patch breaks      High              Baseline and      Regression
  unrelated                           post-patch tests, fixture fails
  behavior                            small diffs,      
                                      human approval    

  Jobs disappear    High              Durable queue/job Lost or stuck job
  after restart                       records, leases,  observed
                                      recovery tests    

  Object storage    Critical          Private buckets,  Any unauthorized
  leaks artifacts                     authorization,    retrieval
                                      short-lived       
                                      links, access     
                                      tests             

  MVP becomes too   High              P0/P1/P2 scope,   Critical path
  broad                               release gates,    slips
                                      defer optional    
                                      services          

  Premium UI        Medium            Build design      Multiple polished
  consumes time                       foundation, then  screens lack APIs
  before workflow                     prioritize real   
  works                               vertical slices   

  Demo depends on   Medium/High       Seeded fixtures,  Provider is
  live external                       provider          unstable near
  services                            preflight, honest demo
                                      fallback scenario 

  Large traces/logs Medium            Size limits,      Storage or
  increase cost                       retention,        latency exceeds
                                      sampling, bounded budget
                                      uploads           

  Security/UX docs  Medium            Update docs with  Repeated
  diverge from code                   contract changes  implementation
                                      and release gates mismatch
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 24. Decisions Required Before Full Implementation

Resolve these during Phase 0; record each decision and rationale in an
ADR.

1.  **Authentication:** choose a hosted identity provider or a secure
    first-party session strategy. Do not implement custom password
    storage casually.
2.  **First onboarding method:** validated ZIP upload or Git-provider
    integration. Choose one for the first vertical slice.
3.  **Execution isolation:** choose the actual runtime/container/VM
    isolation mechanism available in the deployment environment. A
    normal subprocess alone is not a security boundary.
4.  **Object storage:** select local development storage and a
    production private object store.
5.  **Durable jobs:** database-backed jobs for the first release or a
    dedicated queue. The decision must include lease recovery and
    idempotency.
6.  **Model provider:** confirm access to Meta Model API / Muse Spark,
    current request/response schemas, supported image input, quotas, and
    terms.
7.  **Supported runtime:** choose the first Node.js version and the
    exact package-manager/lockfile profiles to support.
8.  **Deployment:** select the initial hosting target for frontend, API,
    worker, PostgreSQL, and private artifacts.
9.  **Retention:** set default retention for uploaded repositories,
    traces, screenshots, logs, and reports.
10. **Demo data:** agree on synthetic fixtures and expected results.

Do not block all engineering on decisions that can be abstracted, but do
not enable untrusted code execution until the isolation decision is real
and tested.

------------------------------------------------------------------------

## 25. What Not to Do

-   Do not ask an AI coding tool to generate the entire platform in one
    giant prompt and accept it without review.
-   Do not create all database tables, UI screens, and agents in a
    single untestable change.
-   Do not build a decorative dashboard before the underlying workflow
    exists.
-   Do not add a vector database simply because the product uses AI.
-   Do not let the model invent terminal commands or directly control
    the host.
-   Do not use mock data in the production investigation path.
-   Do not equate "patch generated" with "bug fixed."
-   Do not equate "test skipped" with "test passed."
-   Do not silently retry destructive actions.
-   Do not log entire source files, secrets, or model payloads by
    default.
-   Do not push or merge code automatically in the MVP.
-   Do not expand the supported framework list before the first profile
    is reliable.
-   Do not hide inconclusive outcomes to make a demo appear more
    impressive.

------------------------------------------------------------------------

## 26. Final Execution Rule

Build Meridian as a sequence of tested, reviewable, production-minded
increments:

1.  **Foundation**
2.  **Identity and data integrity**
3.  **Project snapshot**
4.  **Durable workflow**
5.  **Isolated execution**
6.  **Real browser evidence**
7.  **Evidence-grounded AI reasoning**
8.  **Regression testing**
9.  **Human-approved patch**
10. **Deterministic verification**
11. **Truthful report**
12. **Security and release hardening**

At every phase, preserve the core promise: **Meridian investigates with
evidence, proposes changes under human control, and reports only what
the system actually verified.**
