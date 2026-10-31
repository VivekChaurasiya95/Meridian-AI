# Meridian --- System Architecture

**Document version:** 1.0\
**Status:** Proposed architecture for MVP\
**Related document:** `PRD.md`\
**Product:** Meridian --- Evidence-driven AI software investigation
platform

------------------------------------------------------------------------

## 1. Purpose

This document defines Meridian's proposed system architecture: the major
components, responsibilities, boundaries, data flows, AI orchestration,
execution model, security controls, and deployment approach.

The architecture prioritizes a small, testable MVP that can complete one
investigation end to end. It intentionally avoids premature
microservices and unrestricted autonomous execution.

### Architectural objective

Given a supported web project and a bug report, Meridian should be able
to:

1.  Inspect the project.
2.  Plan a bounded investigation using Meta Muse Spark.
3.  Attempt to reproduce the failure in a controlled environment.
4.  collect runtime evidence.
5.  Generate evidence-backed root-cause hypotheses.
6.  Propose a regression test and code patch.
7.  Require user approval before applying the patch.
8.  Run the required verification checks.
9.  Produce a traceable report that clearly states what was and was not
    verified.

Meridian must never claim a fix is verified merely because a model
generated a plausible explanation or patch.

------------------------------------------------------------------------

## 2. Architectural Principles

1.  **Modular monolith first:** Use a single FastAPI application and a
    separate execution worker before considering service decomposition.
2.  **Explicit workflow state:** Use a finite state machine rather than
    an unconstrained agent loop.
3.  **Model proposes; tools establish facts:** The model plans and
    interprets. Deterministic tools inspect files, execute tests,
    collect logs, and report exit codes.
4.  **Least privilege:** Each component receives only the permissions
    required for its task.
5.  **Isolated execution:** Untrusted project code must never run inside
    the web API process.
6.  **Human approval:** Patches require explicit user approval before
    application/export.
7.  **Evidence provenance:** Store the source, timestamp, stage, and
    integrity metadata for evidence artifacts.
8.  **Bounded work:** Limit retries, execution time, model calls, input
    size, and artifact size.
9.  **Honest outcomes:** Preserve `blocked`, `failed`, and
    `inconclusive` states; never silently turn them into success.
10. **Incremental scope:** Support one known web stack and controlled
    repositories first.

------------------------------------------------------------------------

## 3. System Context

### 3.1 Actors

-   **Developer:** Creates projects and investigations, reviews
    evidence, approves or rejects patches, and downloads reports.
-   **Web client:** Displays projects, investigation progress, evidence,
    diffs, and verification results.
-   **Meridian API:** Authenticates requests, validates inputs, manages
    records, and exposes application endpoints.
-   **Investigation orchestrator:** Advances the investigation state
    machine and invokes approved tools and model calls.
-   **Meta Model API:** Provides Muse Spark reasoning and structured
    tool-call proposals, subject to current API access and model
    capabilities.
-   **Execution worker:** Runs approved setup/test/browser tasks in an
    isolated workspace.
-   **PostgreSQL:** Stores users/workspaces/projects/investigations and
    structured results.
-   **Object storage:** Stores source archives and larger logs,
    screenshots, traces, and report artifacts.

### 3.2 System context diagram

``` text
┌─────────────────────────┐
│       Developer         │
└────────────┬────────────┘
             │ HTTPS
             ▼
┌─────────────────────────┐
│     Meridian Web UI     │
│ Next.js / TypeScript    │
└────────────┬────────────┘
             │ REST API
             ▼
┌─────────────────────────┐
│       Meridian API      │
│ FastAPI / Auth / Policy │
└──────┬──────────┬───────┘
       │          │
       ▼          ▼
┌────────────┐  ┌──────────────────┐
│ PostgreSQL │  │ Job / Stage Queue│
└────────────┘  └────────┬─────────┘
                         ▼
              ┌─────────────────────┐
              │ Investigation       │
              │ Orchestrator        │
              └──────┬────────┬─────┘
                     │        │
                     ▼        ▼
             ┌────────────┐ ┌─────────────────┐
             │ Meta Model │ │ Isolated Runner │
             │ API        │ │ Git / Tests /   │
             │ Muse Spark │ │ Playwright      │
             └────────────┘ └────────┬────────┘
                                     │
                                     ▼
                           ┌──────────────────┐
                           │ Artifact Storage │
                           │ Logs / Screens / │
                           │ Traces / Reports │
                           └──────────────────┘
```

The diagram shows logical components. In the first MVP, the API and
orchestrator may share one codebase, while execution must remain
isolated from the API process.

------------------------------------------------------------------------

## 4. High-Level Architecture

### 4.1 Frontend

**Technology:** Next.js, React, TypeScript, Tailwind CSS.

Responsibilities: - User authentication flow. - Workspace and project
management. - Project source upload. - Bug report submission. -
Investigation progress and timeline. - Evidence and root-cause report
display. - Patch diff review. - Patch approval/rejection. - Verification
results. - Report and patch download.

The frontend must not: - Call Meta Model API directly with a secret
key. - Execute repository commands. - Decide whether a fix is
verified. - Trust model-provided status without a corresponding backend
execution record.

### 4.2 API layer

**Technology:** Python, FastAPI, Pydantic.

Responsibilities: - Validate and authorize requests. - Create and
retrieve projects and investigations. - Validate uploads and request
sizes. - Start, cancel, or resume jobs. - Return structured status and
evidence metadata. - Enforce workspace ownership and permissions. -
Record audit events. - Provide signed, time-limited links for artifact
downloads when supported.

The API should return promptly for long-running investigations. It
should create a job and return an investigation/job identifier rather
than keeping an HTTP request open for the entire run.

### 4.3 Investigation orchestrator

Responsibilities: - Load investigation state and project
configuration. - Select the next valid stage. - Build a minimal evidence
context for Muse Spark. - Call the Meta Model API. - Validate model
outputs. - Invoke only permitted tools. - Persist stage results and
artifacts. - Enforce retry, time, and cost budgets. - Stop on
cancellation, policy violation, or terminal state. - Produce the final
report.

For the MVP, implement this as Python modules in the backend/worker
codebase with an explicit state machine. Do not introduce a large
multi-agent framework unless a concrete requirement justifies it.

### 4.4 Repository inspection service

Responsibilities: - Validate and extract project archives safely. -
Identify supported languages and frameworks. - Read project manifests
and test configuration. - Enumerate files while excluding generated,
ignored, and sensitive files. - Search for symbols, imports, routes, and
relevant text. - Read bounded file ranges. - Produce validated file
references and line numbers. - Create isolated Git worktrees or
disposable checkouts when available.

The inspector should use deterministic code and file tools. Muse Spark
can choose which inspection tools to call, but it must not gain
unrestricted filesystem access.

### 4.5 Execution runner

Responsibilities: - Run supported project setup, startup, test, lint,
and type-check commands. - Execute controlled Playwright actions. -
Capture stdout, stderr, exit codes, durations, and artifacts. - Enforce
resource limits and timeouts. - Clean up the workspace after the job. -
Return structured execution results.

The runner is a security boundary. It must not run in the same process
or unrestricted host environment as the API or model credentials.

For a hackathon MVP, use prepared repositories and a restricted
ephemeral runner. A container can provide useful isolation, but it is
not automatically a complete security boundary; configure permissions
carefully and consider stronger isolation before accepting arbitrary
public uploads.

### 4.6 Verification service

Responsibilities: - Determine which checks are required for a given
investigation. - Execute the regression test and relevant existing
checks. - Collect real execution results. - Compare baseline and
post-patch outcomes. - Apply the verification decision rules. - Prevent
success claims when evidence is incomplete.

The model may explain results, but the verification status must be
derived from structured tool results and explicit policy.

### 4.7 Persistence and artifact storage

**PostgreSQL** stores structured records. **Object storage** stores
larger binary/text artifacts.

PostgreSQL stores: - Workspaces, membership, and projects. -
Investigation state and stage history. - Hypotheses and evidence
references. - Patch metadata and approvals. - Verification runs and
individual checks. - Audit/activity events.

Object storage stores: - Uploaded source archives when retention
requires them. - Screenshots and browser traces. - Larger
console/network logs. - Test output. - Generated Markdown reports and
patch files.

Use short-lived signed URLs for artifact access when the storage
provider supports them. Validate authorization before issuing URLs.

------------------------------------------------------------------------

## 5. Logical Component Boundaries

Recommended code-level modules:

``` text
apps/
  web/                         # Next.js UI

services/
  api/
    app/
      main.py
      api/                     # Versioned route handlers
      auth/                    # Authentication and authorization
      projects/                # Project CRUD and source metadata
      investigations/          # Investigation APIs and state
      artifacts/               # Upload/download authorization
      policies/                # Permissions and execution policies
      db/                      # SQLAlchemy or chosen persistence layer
      schemas/                 # Pydantic request/response schemas
      services/                # Application services

workers/
  investigation/
    runner.py                  # Job entry point
    orchestrator.py            # State-machine controller
    stages/
      inspect_project.py
      plan.py
      reproduce.py
      analyze_evidence.py
      create_test.py
      propose_patch.py
      verify_patch.py
      generate_report.py
    tools/
      repo_search.py
      read_file.py
      git_diff.py
      run_tests.py
      run_playwright.py
      collect_logs.py
    model/
      meta_client.py
      prompts/
      schemas.py
    policies/
      tool_allowlist.py
      execution_limits.py
      verification_rules.py

packages/
  shared-types/                 # Optional generated/shared API types

infrastructure/
  runner/                        # Runner image and hardening configuration
  deployment/

docs/
  PRD.md
  ARCHITECTURE.md
  DATABASE.md
  API.md
  SECURITY.md
  TEST_PLAN.md
```

This is a logical structure, not a requirement to create every folder
immediately. For the first proof of concept, keep the number of modules
small and extract boundaries when they improve testability.

------------------------------------------------------------------------

## 6. Investigation State Machine

### 6.1 States

``` text
CREATED
  ↓
PROJECT_INSPECTION
  ↓
PLAN_INVESTIGATION
  ↓
REPRODUCTION
  ↓
EVIDENCE_ANALYSIS
  ↓
HYPOTHESIS_REVIEW
  ↓
REGRESSION_TEST_CREATION
  ↓
BASELINE_TEST_EXECUTION
  ↓
PATCH_PROPOSAL
  ↓
AWAITING_USER_APPROVAL
  ↓
PATCH_APPLICATION
  ↓
POST_PATCH_VERIFICATION
  ↓
REPORT_GENERATION
  ↓
COMPLETED
```

Any non-terminal state may transition to `CANCELLED` when cancellation
is safely honored. Failures may transition to `FAILED`, `BLOCKED`, or
`INCONCLUSIVE` depending on the reason.

### 6.2 Stage outcome rules

-   **Project inspection:** `passed`, `failed`, `blocked`.
-   **Reproduction:** `reproduced`, `not_reproduced`, `blocked`,
    `inconclusive`.
-   **Evidence analysis:** `completed`, `inconclusive`, `failed`.
-   **Baseline test:** `failed_as_expected`, `passed_unexpectedly`,
    `blocked`, `inconclusive`.
-   **Patch proposal:** `proposed`, `not_supported`, `failed`.
-   **User approval:** `approved`, `rejected`, `cancelled`, `timed_out`.
-   **Post-patch verification:** `passed`, `failed`, `partial`,
    `blocked`, `inconclusive`.

The state machine must not proceed as though the bug was reproduced when
the reproduction stage returned `blocked` or `not_reproduced`.

### 6.3 Retry policy

-   Retries are bounded and configurable.
-   A failed tool call can be retried only when the failure is plausibly
    transient and policy permits it.
-   A model can request a new hypothesis or alternative test within the
    configured budget.
-   Repeated failures must not trigger unlimited model calls or test
    runs.
-   All retries and their outputs must be recorded.

------------------------------------------------------------------------

## 7. End-to-End Data Flows

### 7.1 Project onboarding

1.  User uploads a ZIP or selects an authorized repository.
2.  API authenticates the user and checks project permissions.
3.  Upload service validates file size, archive paths, file types, and
    file count.
4.  Source is stored in restricted storage or a temporary intake area.
5.  Inspector extracts it in a safe staging environment.
6.  Inspector detects supported frameworks and scripts.
7.  API stores project metadata and validated configuration.
8.  UI displays detected stack and supported commands for confirmation.

### 7.2 Investigation creation

1.  User submits a bug report and optional evidence.
2.  API validates fields and attachment limits.
3.  API creates an investigation with status `CREATED`.
4.  A job is placed on the configured queue.
5.  The worker loads the project and investigation.
6.  The orchestrator begins the state machine and records events.
7.  UI retrieves progress through polling initially; server-sent events
    can be added later.

### 7.3 Evidence-driven investigation

1.  Inspector creates a bounded repository summary.
2.  Orchestrator asks Muse Spark for an investigation plan using the bug
    report and available context.
3.  The model returns structured proposed steps or tool calls.
4.  Backend validates tool name, arguments, permissions, and budget.
5.  Repository tools read/search permitted files.
6.  Runner executes only approved commands.
7.  Playwright performs constrained browser actions when configured.
8.  Logs, screenshots, traces, exit codes, and metadata are stored.
9.  Orchestrator sends a compact evidence bundle to Muse Spark for
    interpretation.
10. Hypotheses are stored with evidence references and uncertainty
    labels.

### 7.4 Regression test and patch

1.  Agent proposes a regression test.
2.  Backend validates the test file path and framework.
3.  Runner executes it against the original baseline.
4.  If it does not reproduce the failure, the system marks the test
    inconclusive or requests a bounded revision.
5.  Agent proposes a patch diff.
6.  Backend validates changed paths and patch size.
7.  Patch and diff are stored in an isolated workspace.
8.  UI presents the diff and evidence to the user.
9.  Only after explicit approval may the runner apply the patch to the
    isolated working copy or export it.

### 7.5 Verification and final report

1.  Runner executes the regression test after the patch.
2.  Runner executes selected existing tests and checks.
3.  Each check returns a structured result with status, exit code,
    duration, and output artifact.
4.  Verification policy compares baseline and post-patch results.
5.  The system assigns a final status using deterministic rules.
6.  Muse Spark may summarize the verified findings, but cannot override
    the result records.
7.  Report generator produces a Markdown report with evidence
    references, patch summary, test results, and limitations.
8.  UI shows the final result and download options.

------------------------------------------------------------------------

## 8. Meta Model API Integration

### 8.1 Role of Muse Spark

Use Muse Spark for tasks requiring interpretation or reasoning: - Turn
the user's bug report into a structured investigation plan. - Identify
relevant files and evidence to collect. - Interpret browser logs,
screenshots, and source snippets. - Generate and rank root-cause
hypotheses. - Propose regression tests. - Propose code diffs. - Explain
actual verification outcomes.

Use deterministic tools for: - Reading files and searching code. -
Validating file paths and diffs. - Running commands and tests. -
Collecting exit codes and logs. - Computing test pass/fail status. -
Comparing baseline and patched results. - Enforcing budgets and
permissions.

### 8.2 Tool-call lifecycle

``` text
Orchestrator
    │
    ▼
Build minimal context
    │
    ▼
Call Meta Model API
    │
    ▼
Receive structured response/tool request
    │
    ▼
Validate schema + allowlist + permissions + budget
    │
    ├── Invalid → reject and record
    │
    ▼
Execute approved tool
    │
    ▼
Persist tool result and artifacts
    │
    ▼
Return compact result to model/orchestrator
    │
    ▼
Continue, stop, or request user input
```

### 8.3 Tool policy

Initial tools should be narrow and typed, for example:

-   `inspect_project`
-   `search_code`
-   `read_file_range`
-   `get_project_scripts`
-   `run_supported_test`
-   `run_browser_scenario`
-   `get_browser_evidence`
-   `propose_regression_test`
-   `propose_patch`
-   `get_diff`

Do not expose a general `execute_shell(command: string)` tool to the
model. The backend should map a validated action to a known command
template and run it inside the restricted worker.

### 8.4 Model context and prompt-injection resistance

Repository content, comments, README files, logs, and screenshots are
untrusted input. They may contain text that attempts to override the
agent's instructions.

Controls: - Clearly separate trusted policy from untrusted project
data. - Treat repository text as evidence, not instructions. - Never
reveal secrets to the model. - Minimize context to relevant files and
logs. - Validate every tool call independently of model instructions. -
Reject requests to access files or operations outside the project
policy. - Require user approval for patch application. - Keep model
output separate from actual tool-execution records.

### 8.5 Availability validation

Before building the complete workflow, verify the actual Meta Model API
access, available model identifier, authentication method, rate limits,
structured-output support, and tool-calling behavior for the hackathon
account/project. Keep the model client behind an adapter so
model/provider configuration can be changed without rewriting the
orchestrator.

------------------------------------------------------------------------

## 9. Execution Isolation and Runner Design

### 9.1 Trust boundary

The runner handles untrusted repository content and code. It must not
share unrestricted access to: - API credentials. - Database
credentials. - Other users' projects. - Host filesystem paths. - Cloud
instance metadata. - Internal services. - Production credentials.

### 9.2 Runner input

A runner job should contain only: - A source snapshot or isolated
checkout identifier. - An allowlisted command specification. - A timeout
and resource budget. - A list of permitted output artifacts. - An
investigation and stage identifier. - A non-secret correlation ID.

Do not pass model API keys or database passwords into the test process.

### 9.3 Runner output

Return structured fields: - Job status. - Exit code. - Start/end time
and duration. - Sanitized stdout/stderr artifact references. - Browser
evidence references, where applicable. - Resource-limit or timeout
indicators. - Cleanup status.

### 9.4 Required controls

-   Disposable workspace per investigation or stage.
-   Non-root execution where supported.
-   Read-only base image and restricted writable paths.
-   CPU, memory, process, disk, and wall-clock limits.
-   Network disabled or allowlisted where practical.
-   No privileged container mode.
-   No host Docker socket mount.
-   No host filesystem mounts beyond the assigned workspace.
-   Archive extraction protections.
-   Cleanup after completion or cancellation.
-   Monitoring for abandoned processes and workspace leakage.

For the hackathon, prefer prepared demonstration repositories and a
controlled runner over unrestricted public repository execution. A
container helps, but a production-grade hostile-code service may require
stronger isolation such as dedicated ephemeral virtual machines or a
specialized sandbox.

------------------------------------------------------------------------

## 10. Verification Decision Engine

Verification status must be computed from actual execution results and
explicit rules, not generated solely by the model.

### 10.1 Example policy

A patch can be marked **Verified for tested conditions** only if: 1. The
original bug was reproduced or a valid regression test demonstrated the
baseline failure. 2. The regression test passed after the patch. 3.
Required selected existing tests completed successfully. 4. No required
verification check was blocked or skipped. 5. The tested source snapshot
and patch identity are recorded.

A patch should be marked **Partially verified** when the regression test
passes but some non-critical checks could not run, according to a
declared policy.

A patch should be marked **Failed** if the regression test still fails
or required checks fail.

A patch should be **Blocked** if execution could not be completed
because of environment or permission constraints.

A patch should be **Inconclusive** if the available evidence cannot
establish a meaningful result.

The exact policy should be configurable and versioned. A passing test
suite is not proof that the whole application is bug-free.

### 10.2 Baseline caveat

Some bugs may be reproducible through a browser scenario rather than a
generated test. If a test does not fail against the original code,
Meridian must not treat it as a valid regression test merely because it
passes after the patch. It should revise the test within limits or
report the limitation.

------------------------------------------------------------------------

## 11. Data and Storage Architecture

### PostgreSQL

Store structured, queryable records: - Users and workspace
memberships. - Projects and detected stack. - Investigations and
workflow state. - Stage execution records. - Hypotheses and evidence
links. - Regression-test metadata. - Patch metadata and approvals. -
Verification runs and checks. - Audit events.

### Object storage

Store larger artifacts: - Source ZIPs when retained. - Screenshots. -
Playwright traces. - Console/network logs. - Test output. - Patch files
and reports.

### Artifact access

-   Keep object storage private.
-   Authorize every artifact request.
-   Use short-lived signed links when available.
-   Set retention limits and delete artifacts when a project is deleted
    according to policy.
-   Record checksums and content type for integrity and validation.
-   Avoid embedding secret-bearing logs into model context or
    user-facing reports.

### Optional retrieval layer

Do not introduce a vector database in the first implementation unless
direct search proves insufficient. Start with: - File path and symbol
search. - Framework-aware file selection. - Imports and route
inspection. - Bounded source snippets. - Existing test discovery.

If later evaluation shows that semantic retrieval materially improves
relevant-file selection, add embeddings and evaluate them against the
same benchmark.

------------------------------------------------------------------------

## 12. API and Asynchronous Processing

### 12.1 Request pattern

The API should use asynchronous jobs for investigation stages that may
take more than a few seconds.

Example:

``` text
POST /api/v1/projects/{project_id}/investigations
    → 201 Created
    → { "investigation_id": "...", "status": "created" }

POST /api/v1/investigations/{id}/start
    → 202 Accepted
    → { "investigation_id": "...", "status": "queued" }

GET /api/v1/investigations/{id}
    → current status, summary, and timestamps

GET /api/v1/investigations/{id}/events
    → ordered stage/activity events
```

### 12.2 Queue choice

For a first local/demo implementation, a simple background worker may be
sufficient. For reliable deployments, use a proper job queue and worker
process. Choose the queue technology based on hosting constraints and
the team's familiarity; do not add a broker unless needed.

### 12.3 Idempotency and concurrency

-   Prevent the same stage from running concurrently for one
    investigation.
-   Store stage status before dispatching work.
-   Use job identifiers and idempotency keys where appropriate.
-   Make cancellation cooperative and ensure child processes are
    terminated.
-   Avoid duplicate patch application by binding approvals to a specific
    patch hash.
-   Ensure retried jobs do not create duplicate final reports or
    inconsistent state.

------------------------------------------------------------------------

## 13. Observability and Auditability

Record structured events for: - Investigation created, started,
cancelled, or completed. - Stage started and finished. - Tool request
validated, rejected, or executed. - Model call metadata and duration. -
Runner start/exit/timeout. - Patch proposed, approved, rejected,
applied, or discarded. - Verification check result. - Artifact
creation/deletion.

Log: - Correlation ID. - Investigation ID. - Stage name. - Tool name. -
Duration and outcome. - Error category. - Model identifier and request
metadata where appropriate.

Do not log: - API keys. - Passwords. - Session cookies. - Full
environment variables. - Private tokens. - Unredacted sensitive user
data.

Use a redaction layer for stdout/stderr before storing or displaying it.
Keep enough data for debugging without turning logs into a second source
of secret leakage.

------------------------------------------------------------------------

## 14. Deployment Architecture

### MVP deployment

-   **Frontend:** Next.js hosted on a frontend platform such as Vercel.
-   **API:** FastAPI on a Python-compatible host.
-   **Worker:** Separate worker process or isolated execution service.
-   **Database:** Managed PostgreSQL.
-   **Artifacts:** Private object storage.
-   **AI:** Meta Model API.
-   **Source control:** Public Meridian application repository; test
    fixtures included only when their licenses permit.

### Development environment

-   Local Next.js development server.
-   Local FastAPI server.
-   Local PostgreSQL instance or development database.
-   Prepared fixture repositories.
-   A local restricted runner for trusted test fixtures.
-   `.env.example` containing placeholders only.

### Production considerations

-   The worker should not share secrets or permissions with the
    untrusted test process.
-   Separate the trusted orchestration process from the code-execution
    sandbox.
-   Use private networking and restrictive firewall rules where
    available.
-   Back up structured data and define artifact retention.
-   Apply rate limits to uploads and investigation creation.
-   Monitor job backlog, worker failures, API latency, model-call cost,
    and runner resource usage.

------------------------------------------------------------------------

## 15. Failure Handling

  -----------------------------------------------------------------------
  Failure                             Expected behavior
  ----------------------------------- -----------------------------------
  Invalid archive                     Reject upload with a clear
                                      validation message

  Unsupported framework               Mark project inspection as
                                      unsupported or blocked

  Dependency installation fails       Capture sanitized output and mark
                                      reproduction blocked

  Application does not start          Report startup failure; do not
                                      invent browser evidence

  Bug not reproduced                  Preserve collected evidence and
                                      report `not_reproduced`

  Model returns invalid schema        Reject response, record validation
                                      error, optionally retry within
                                      budget

  Tool request is disallowed          Reject tool call and record policy
                                      event

  Test times out                      Mark check `timed_out`; terminate
                                      process tree

  Patch has invalid paths             Reject patch and preserve original
                                      checkout

  User rejects patch                  Do not apply it; retain proposal
                                      for review if configured

  Post-patch test fails               Mark verification failed and show
                                      actual output

  Worker crashes                      Recover job to a safe state; do not
                                      assume success

  User cancels                        Stop new work and terminate child
                                      processes where possible

  Artifact storage fails              Mark artifact unavailable; do not
                                      silently omit required evidence
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 16. Architecture Decisions and Trade-offs

### ADR-001: Modular monolith before microservices

**Decision:** Keep the API and orchestrator in one codebase, with a
separate execution worker.

**Reason:** Faster development, simpler debugging, fewer deployment
dependencies.

**Revisit when:** Independent scaling, team ownership, or security
boundaries require more separation.

### ADR-002: State machine rather than open-ended agent loop

**Decision:** Use explicit stages, transitions, and budgets.

**Reason:** Easier to test, audit, recover, and explain.

**Trade-off:** Less flexible than an unrestricted agent, but much safer
and more predictable.

### ADR-003: Deterministic verification

**Decision:** Compute final verification status from real test/tool
results.

**Reason:** The model must not be allowed to certify its own patch.

### ADR-004: Human approval for patches

**Decision:** Require explicit approval before applying or exporting a
patch to the working copy.

**Reason:** Preserves developer control and limits damage from incorrect
changes.

### ADR-005: Direct code search before vector retrieval

**Decision:** Start with deterministic search and bounded file reads.

**Reason:** Simpler, faster to validate, and often sufficient for a
small supported repository.

### ADR-006: Isolated execution from day one

**Decision:** Never execute untrusted project code inside the API
process.

**Reason:** Prevents repository code from directly inheriting API
credentials and application permissions.

### ADR-007: Store artifacts outside PostgreSQL

**Decision:** Keep large binary artifacts in private object storage.

**Reason:** Better for storage efficiency, downloads, and retention
management.

------------------------------------------------------------------------

## 17. MVP Implementation Order

Build in this order to minimize integration risk:

### Milestone 1 --- Validate dependencies

-   Confirm Meta API access and a working Muse Spark call.
-   Confirm tool calling or structured output supported by the selected
    model.
-   Run Playwright against one prepared web app.
-   Run one test inside the intended isolated runner.

### Milestone 2 --- Create the application skeleton

-   Set up Next.js and FastAPI.
-   Configure PostgreSQL and migrations.
-   Implement authentication/authorization.
-   Implement project and investigation records.

### Milestone 3 --- Implement one controlled investigation

-   Load a prepared repository.
-   Inspect scripts and source files.
-   Submit a bug report.
-   Generate a bounded plan.
-   Run one browser reproduction.
-   Store the evidence.

### Milestone 4 --- Add diagnosis and patch review

-   Generate structured hypotheses.
-   Generate a regression test.
-   Validate the test on the baseline.
-   Generate a patch diff.
-   Implement approval and discard controls.

### Milestone 5 --- Add verification and reporting

-   Run the regression test after the patch.
-   Run selected existing checks.
-   Compute final status.
-   Export the evidence-backed report.
-   Test failure and blocked states.

### Milestone 6 --- Polish the demo

-   Add progress timeline and useful error states.
-   Improve diff and evidence views.
-   Prepare seeded scenarios.
-   Document setup, security limitations, and benchmark results.

------------------------------------------------------------------------

## 18. Architecture Acceptance Criteria

The architecture is ready for the first hackathon demo when:

-   A project can be registered and inspected.
-   A user can create and start an investigation.
-   A real Muse Spark call contributes to the investigation.
-   Repository inspection uses constrained tools.
-   Runtime commands execute outside the API process in the intended
    restricted runner.
-   A seeded bug can be reproduced or a truthful blocked/not-reproduced
    outcome is returned.
-   Evidence artifacts are stored and linked to their originating
    stages.
-   A patch is presented as a diff and requires explicit approval.
-   Verification status is calculated from real test results.
-   A report records what was observed, inferred, changed, tested, and
    left unresolved.
-   Secrets are not passed to untrusted code or exposed to the browser.
-   Failed and cancelled jobs cannot accidentally be displayed as
    verified.

------------------------------------------------------------------------

## 19. Open Questions

Resolve these during the initial technical spike:

1.  Which Meta Model API model identifier is actually enabled for the
    project?
2.  What exact request format and tool-calling/structured-output
    capabilities are available?
3.  Will the first supported app be React/Vite or Next.js?
4.  What is the safest runner option available within the hackathon
    timeline and hosting budget?
5.  Will source intake begin with ZIP upload, prepared fixtures, or
    authorized GitHub import?
6.  Which regression-test pattern will be used for the first seeded bug?
7.  Which artifacts must be retained, for how long, and who can access
    them?
8.  What is the maximum acceptable investigation time and model-call
    budget?

These are implementation decisions, not reasons to expand the MVP.
Resolve them with small proof-of-concept tests.

------------------------------------------------------------------------

## 20. Final Architecture Summary

Meridian should be built as a modular web application with a bounded
investigation orchestrator, a Meta Muse Spark integration, deterministic
repository and test tools, a separate isolated execution runner,
PostgreSQL for structured state, and private object storage for evidence
artifacts.

The model proposes investigative actions and interprets evidence. The
backend enforces permissions and state transitions. The runner executes
approved commands and captures actual results. The verification engine
derives outcomes from those results. The UI makes the process visible
and lets the developer control patch application.

The defining architecture rule is:

> **The AI can propose what to investigate and what to change; only
> validated tools and recorded execution results can establish what
> happened and whether the required checks passed.**
