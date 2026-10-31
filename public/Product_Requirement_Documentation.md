# Meridian --- Product Requirements Document (PRD)

**Document version:** 1.0\
**Status:** Draft for product and engineering planning\
**Product name:** Meridian\
**Product category:** AI-assisted software debugging and reliability\
**Tagline:** *Clarity for complex engineering.*\
**Initial platform:** Web application\
**Initial target users:** Individual developers, student teams, and
small software teams\
**Primary MVP focus:** Investigate reproducible bugs in
JavaScript/TypeScript web applications and produce evidence-backed
debugging reports and verified patch proposals.

------------------------------------------------------------------------

## 1. Executive Summary

Meridian is an AI-assisted software investigation platform designed to
help developers move from an unclear bug report to a clear,
evidence-backed understanding of what failed and what to do next.

A developer can provide a bug description, relevant logs, a screenshot,
and a supported code repository or project archive. Meridian inspects
the project, gathers available runtime evidence, helps formulate and
test hypotheses, and produces a structured investigation report. Where
the environment supports it, Meridian can generate a regression test and
propose a code patch in an isolated workspace. It then runs selected
tests and reports exactly what passed, failed, or could not be verified.

Meridian is not intended to promise that every bug can be automatically
fixed. Its core promise is to **make debugging more systematic,
evidence-driven, and transparent**.

The MVP will prioritize a reliable, demonstrable workflow over broad
language/framework support. It will initially support selected
React/Next.js or other JavaScript/TypeScript web projects with known
startup and test commands.

### Product promise

> Meridian helps developers understand software failures by connecting
> the bug report, repository context, runtime evidence, proposed
> changes, and verification results in one investigation.

### Non-goals for the MVP

-   Automatically fixing every bug or guaranteeing bug-free software.
-   Running arbitrary user code without isolation and safeguards.
-   Supporting every programming language, framework, or production
    environment.
-   Replacing developers, code review, CI/CD, observability, or security
    review.
-   Accessing private production systems or credentials without explicit
    user configuration.
-   Claiming a fix is verified when tests did not actually run or
    results are inconclusive.

------------------------------------------------------------------------

## 2. Problem Statement

Debugging often begins with incomplete information: a vague user report,
a screenshot, an error message, or a failure that occurs only under
certain conditions. Developers must manually connect these clues to
source code, reproduce the failure, determine the likely cause,
implement a change, and check for regressions.

Common pain points include:

1.  **Incomplete reports:** The original report does not provide exact
    reproduction steps.
2.  **Scattered evidence:** Browser errors, network activity, logs,
    source code, and tests live in different places.
3.  **Uncertain root causes:** A visible symptom may have multiple
    possible causes.
4.  **Weakly tested fixes:** A code suggestion can appear plausible
    without addressing the original defect.
5.  **Regression risk:** A change that fixes one issue can break another
    behavior.
6.  **Poor investigation history:** The reasoning and evidence behind a
    fix may not be documented.

Meridian aims to connect these steps into one controlled workflow and
preserve the evidence behind each conclusion.

------------------------------------------------------------------------

## 3. Product Vision and Principles

### Vision

Make reliable software investigation accessible to every developer by
turning fragmented debugging work into a transparent, repeatable
process.

### Product principles

1.  **Evidence before confidence:** Distinguish observed facts from
    model-generated hypotheses.
2.  **Reproduce before repair:** Attempt to establish a repeatable
    failure before proposing a fix.
3.  **Tests before success claims:** Report verification only when
    execution results support it.
4.  **Human control:** Users review and approve proposed changes before
    they are applied to their working project.
5.  **Least privilege:** The agent receives only the repository and
    tools required for the current investigation.
6.  **Small, explainable changes:** Prefer targeted patches over broad
    rewrites.
7.  **Honest uncertainty:** Report blocked, inconclusive, and failed
    investigations explicitly.
8.  **Traceability:** Every key conclusion should link to evidence, a
    file, a log, a test, or a tool result.

------------------------------------------------------------------------

## 4. Target Users and Use Cases

### Primary personas

#### Persona A --- Individual developer

Needs help diagnosing bugs in a web application without repeatedly
switching between the browser, terminal, and editor.

#### Persona B --- Student or hackathon team

Needs a structured debugging process and clear explanations while
building projects with limited engineering resources.

#### Persona C --- Small engineering team

Wants reproducible bug reports, auditable patch proposals, and a record
of test outcomes.

### Primary jobs to be done

-   "Help me understand why this reproducible bug is happening."
-   "Connect this browser error to the relevant source code."
-   "Create a regression test for the issue."
-   "Suggest a small patch and explain its reasoning."
-   "Show me whether the patch passed the checks we ran."
-   "Give me a useful report when the issue cannot be reproduced."

### Initial supported bug categories

-   React component state and rendering issues.
-   Form validation and submission problems.
-   Client-side routing and navigation defects.
-   Browser-visible authentication/session-flow issues in a controlled
    environment.
-   JavaScript/TypeScript runtime errors.
-   Failed browser requests where local test conditions are available.

### Initially unsupported or restricted categories

-   Production incidents requiring privileged access to live systems.
-   Bugs that require unavailable third-party services or secret
    credentials.
-   Hardware, native mobile, and embedded-system defects.
-   Complex distributed-system failures.
-   Security-sensitive code execution or exploitation tasks.
-   Any issue that cannot be tested safely in the configured
    environment.

------------------------------------------------------------------------

## 5. Product Scope

### MVP --- Must have

1.  Create a project workspace.
2.  Upload a supported project ZIP or select a repository already
    available to the configured runner.
3.  Enter a bug description and optional expected behavior.
4.  Attach a screenshot and/or logs.
5.  Inspect project structure and detect framework, scripts, and
    available tests.
6.  Create an investigation plan using Meta Muse Spark through the Meta
    Model API.
7.  Search and read relevant source files through constrained tools.
8.  Run a supported application/test command in an isolated environment.
9.  Perform a controlled browser reproduction with Playwright where
    possible.
10. Capture console errors, failed network requests, screenshots, and
    test output.
11. Produce a structured report of observed facts and ranked hypotheses.
12. Generate a regression-test proposal.
13. Run the regression test against the original code where supported.
14. Propose a minimal code diff in an isolated workspace.
15. Require user approval before applying or exporting a patch.
16. Run selected tests and checks after the patch.
17. Display truthful before/after results and unresolved limitations.
18. Preserve investigation history and artifacts.

### Should have

-   Repository import from GitHub with explicitly authorized access.
-   Markdown export of investigation reports.
-   Downloadable patch file.
-   Test rerun and investigation retry controls.
-   Investigation timeline.
-   Configurable model-call and execution budgets.
-   Support for a small number of seeded demonstration repositories.

### Could have later

-   Pull-request creation.
-   CI workflow integration.
-   Team collaboration and shared workspaces.
-   More programming languages and frameworks.
-   Historical investigation search.
-   Repository-level regression trend analysis.
-   IDE extension.
-   Integrations with issue trackers and observability platforms.

### Won't have in the MVP

-   Unrestricted execution of arbitrary commands on the host.
-   Autonomous commits or pushes to a user's primary branch.
-   Automatic production deployment.
-   Guaranteed one-click fixes.
-   Continuous production monitoring.
-   General-purpose autonomous coding across large repositories.

------------------------------------------------------------------------

## 6. Core User Journey

1.  User signs in and opens a project workspace.
2.  User uploads a project archive or chooses an authorized repository.
3.  Meridian inspects the project and shows the detected stack and
    supported commands.
4.  User creates an investigation by describing the bug and optionally
    attaching screenshots or logs.
5.  Meridian creates an investigation plan and lists the evidence it
    needs.
6.  The runner attempts reproduction in an isolated environment.
7.  Meridian summarizes the observed runtime evidence.
8.  The agent inspects relevant files and ranks possible causes.
9.  If the issue is reproducible, Meridian proposes a regression test.
10. The test is run against the original code. If it does not capture
    the failure, Meridian marks it inconclusive or revises it within a
    bounded budget.
11. Meridian proposes a patch in an isolated workspace.
12. User reviews the patch and approves or rejects it.
13. If approved, Meridian runs the regression test and selected existing
    checks.
14. Meridian displays the result: verified for tested conditions,
    partially verified, failed, blocked, or inconclusive.
15. User can export the report and patch or discard the changes.

------------------------------------------------------------------------

## 7. Functional Requirements

Priority definitions: **P0** = required for MVP; **P1** = important if
time permits; **P2** = future.

### 7.1 Authentication and workspaces

-   **FR-001 (P0):** Users can create and access their own workspaces.
-   **FR-002 (P0):** A user can create a project and start an
    investigation.
-   **FR-003 (P0):** Project and investigation records are isolated by
    user/workspace.
-   **FR-004 (P1):** Users can invite teammates to a shared workspace.

### 7.2 Project intake and inspection

-   **FR-010 (P0):** Accept a supported ZIP archive or configured
    local/repository reference.
-   **FR-011 (P0):** Validate archive type, size, path entries, and file
    count before extraction.
-   **FR-012 (P0):** Detect supported languages, framework indicators,
    package manager, and declared scripts.
-   **FR-013 (P0):** Display detected setup and test commands for user
    confirmation.
-   **FR-014 (P0):** Never expose environment secrets to model prompts
    or untrusted project processes.
-   **FR-015 (P1):** Support authorized GitHub repository import.

### 7.3 Bug intake

-   **FR-020 (P0):** Capture title, description, expected behavior,
    observed behavior, and reproduction notes.
-   **FR-021 (P0):** Accept optional screenshots and text logs.
-   **FR-022 (P0):** Validate file type and size for attachments.
-   **FR-023 (P0):** Show a clear warning when a report lacks enough
    information to run reproduction.

### 7.4 Investigation orchestration

-   **FR-030 (P0):** Track investigation state through explicit stages.
-   **FR-031 (P0):** Use Muse Spark to plan and reason over supplied
    repository/runtime evidence.
-   **FR-032 (P0):** Invoke only allowlisted tools with schema-validated
    arguments.
-   **FR-033 (P0):** Record tool inputs, outputs, timestamps, and
    execution status.
-   **FR-034 (P0):** Distinguish model hypotheses from observed facts.
-   **FR-035 (P0):** Enforce maximum retries, wall-clock time, and
    model-call budgets.
-   **FR-036 (P0):** Allow cancellation of a running investigation.
-   **FR-037 (P1):** Let a user rerun a failed stage after changing
    configuration or evidence.

### 7.5 Runtime reproduction

-   **FR-040 (P0):** Run only supported commands inside an isolated
    runner.
-   **FR-041 (P0):** Apply execution time, CPU, memory, and disk limits.
-   **FR-042 (P0):** Capture stdout, stderr, exit code, duration, and
    relevant artifacts.
-   **FR-043 (P0):** For supported web projects, use Playwright to
    execute a constrained browser action sequence.
-   **FR-044 (P0):** Capture browser console errors, failed requests,
    screenshots, and traces where available.
-   **FR-045 (P0):** Return one of: `reproduced`, `not_reproduced`,
    `blocked`, or `inconclusive`.
-   **FR-046 (P0):** Never treat "not reproduced" as proof that the bug
    does not exist.

### 7.6 Diagnosis

-   **FR-050 (P0):** Generate a structured root-cause report based on
    available evidence.
-   **FR-051 (P0):** Rank hypotheses and include supporting and
    contradictory evidence where available.
-   **FR-052 (P0):** Include file paths and line references only when
    validated against the repository.
-   **FR-053 (P0):** Mark uncertainty and missing evidence explicitly.
-   **FR-054 (P1):** Allow users to provide feedback on a hypothesis.

### 7.7 Regression tests and patching

-   **FR-060 (P0):** Propose a regression test for a reproducible issue
    where supported.
-   **FR-061 (P0):** Run the test against the original code before
    treating it as a valid regression test.
-   **FR-062 (P0):** Generate a patch as a diff rather than overwriting
    the primary project directly.
-   **FR-063 (P0):** Restrict patch paths to the isolated project
    workspace.
-   **FR-064 (P0):** Require user approval before applying/exporting a
    patch.
-   **FR-065 (P0):** Preserve the original checkout and allow changes to
    be discarded.
-   **FR-066 (P0):** Report when a valid regression test cannot be
    generated.

### 7.8 Verification and reporting

-   **FR-070 (P0):** Run the regression test and selected existing tests
    after the patch.
-   **FR-071 (P0):** Report each check as passed, failed, skipped, timed
    out, or blocked.
-   **FR-072 (P0):** Compare before/after results.
-   **FR-073 (P0):** Never mark a patch as verified if required checks
    did not run or results are ambiguous.
-   **FR-074 (P0):** Export a report with the original issue, evidence,
    hypotheses, patch summary, test results, and limitations.
-   **FR-075 (P1):** Download a patch file and Markdown report.

------------------------------------------------------------------------

## 8. Product Design and UX

### Design direction

Meridian should feel like a premium engineering workspace: calm,
precise, evidence-led, and information-dense without being cluttered.

Avoid a generic AI-chat layout as the primary interface. The
investigation and its evidence should be the central experience.

### Visual principles

-   Dark-first engineering interface with a light theme as a possible
    later option.
-   Neutral backgrounds, restrained accent colors, and no excessive
    gradients.
-   Strong typography hierarchy and consistent left-aligned section
    headings.
-   Monospaced typography for code, logs, file paths, and execution
    output.
-   Clear status labels with both color and text; never rely on color
    alone.
-   Progressive disclosure for detailed logs and trace artifacts.
-   Visible source references and test evidence.
-   Motion only when it clarifies stage changes or progress.
-   Responsive layouts, with desktop optimized for code review and
    mobile supporting review/status views.

### Suggested design tokens

These are initial design suggestions, not final brand decisions:

-   **Background:** charcoal or near-black.
-   **Surface:** slightly lighter neutral panels.
-   **Primary text:** off-white.
-   **Secondary text:** muted gray.
-   **Primary accent:** restrained blue or teal.
-   **Success:** accessible green.
-   **Warning:** amber.
-   **Failure:** red.
-   **Typography:** Inter or a similar neutral sans-serif; JetBrains
    Mono or a comparable monospace font for technical output.
-   **Spacing:** consistent 4/8-point spacing system.
-   **Corners:** modest radius; avoid overly rounded consumer-app cards.

### Main screens

#### Screen 1 --- Landing page

Purpose: explain the product and let users start an investigation.

Sections: - Clear headline and product value proposition. - Short
explanation of the investigation workflow. - Example evidence-backed
report. - Primary CTA: "Start an investigation". - Secondary CTA: "View
demo". - Honest note that supported project types and verification scope
are limited.

#### Screen 2 --- Dashboard

Components: - Project list. - Recent investigations. - Status counts. -
"New investigation" CTA. - Recent activity and usage limits.

#### Screen 3 --- Project setup

Components: - Upload project or choose authorized repository. - Detected
stack and framework. - Setup/test command review. -
Supported/unsupported checks. - Security and execution warning. -
Confirm project setup.

#### Screen 4 --- New investigation

Components: - Bug title. - What happened? - What should have happened? -
Steps to reproduce. - Screenshot and log attachments. - Start
investigation CTA.

#### Screen 5 --- Investigation workspace

Recommended layout: - **Left sidebar:** project files, investigation
stages, and artifact list. - **Main panel:** current stage, explanation,
and evidence. - **Right panel:** root-cause hypotheses,
confidence/uncertainty, and next action. - **Bottom or expandable
drawer:** terminal output, browser console, network events, and test
results.

The UI should distinguish: - Observed fact. - Model hypothesis. -
Tool-generated evidence. - User-provided information. - Unverified
recommendation.

#### Screen 6 --- Patch review

Components: - File-by-file diff. - Explanation for each change. -
Original versus proposed code. - Test status before patch. - Approve,
reject, or discard controls. - Explicit warning if the patch is not yet
verified.

#### Screen 7 --- Verification report

Components: - Final investigation status. - Reproduction result. -
Root-cause summary. - Patch summary. - Test matrix with actual
outcomes. - Known limitations and unresolved failures. - Download report
and patch actions.

### Status language

Use clear, truthful states:

-   `Queued`
-   `Inspecting project`
-   `Reproducing`
-   `Analyzing evidence`
-   `Preparing regression test`
-   `Patch awaiting approval`
-   `Verifying`
-   `Verified for tested conditions`
-   `Partially verified`
-   `Failed`
-   `Blocked`
-   `Inconclusive`
-   `Cancelled`

Do not use a single generic "Success" badge for the entire workflow.

------------------------------------------------------------------------

## 9. Technical Architecture

### Recommended stack

  -----------------------------------------------------------------------
  Layer                   Technology              Responsibility
  ----------------------- ----------------------- -----------------------
  Frontend                Next.js, React,         Workspace,
                          TypeScript              investigation timeline,
                                                  diff and report UI

  Styling                 Tailwind CSS            Design system and
                                                  responsive layout

  Backend API             Python, FastAPI,        Request validation,
                          Pydantic                auth integration,
                                                  investigation APIs

  AI model                Meta Muse Spark via     Planning, evidence
                          Meta Model API          interpretation,
                                                  hypothesis generation,
                                                  test/patch proposals

  Orchestration           Python state machine    Stage transitions, tool
                          initially               policy, retry limits

  Browser automation      Playwright              Controlled browser
                                                  reproduction and trace
                                                  capture

  Testing                 pytest; project-native  Test execution and
                          test tools              verification

  Source control          Git CLI or GitPython    Isolated checkouts,
                                                  diffs, reset/discard

  Primary database        PostgreSQL              Users, projects,
                                                  investigations, stages,
                                                  results

  File/artifact storage   S3-compatible object    ZIPs, screenshots,
                          storage or equivalent   traces, logs, reports

  Optional search         PostgreSQL full-text    Relevant file/case
                          search first; ChromaDB  retrieval
                          later if justified      

  Deployment              Vercel frontend plus    Web application and
                          Python API/worker       backend
                          hosting                 

  Execution isolation     Restricted              Running untrusted
                          containers/ephemeral    project commands
                          workers                 
  -----------------------------------------------------------------------

### Architecture overview

``` text
┌─────────────────────────────┐
│        Next.js UI           │
│ Projects / Reports / Diffs  │
└──────────────┬──────────────┘
               │ HTTPS
               ▼
┌─────────────────────────────┐
│       FastAPI Backend       │
│ Auth / API / Validation     │
│ Investigation Management   │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│ Investigation Orchestrator  │
│ State machine + budgets     │
│ Meta Muse Spark + tool calls │
└───────┬──────────┬──────────┘
        │          │
        ▼          ▼
┌──────────────┐ ┌─────────────────┐
│ Repo tools   │ │ Isolated runner │
│ Search/read  │ │ App/test command│
│ Git diff     │ │ Playwright      │
└──────┬───────┘ └────────┬────────┘
       └────────────┬─────┘
                    ▼
┌─────────────────────────────┐
│ Evidence + Verification     │
│ Tests / results / artifacts │
└──────────────┬──────────────┘
               ▼
┌─────────────────────────────┐
│ PostgreSQL + Object Storage │
└─────────────────────────────┘
```

### Agent state machine

Use an explicit workflow instead of allowing an unconstrained agent
loop:

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
13. Terminal states: `COMPLETED`, `FAILED`, `BLOCKED`, `INCONCLUSIVE`,
    `CANCELLED`.

Each stage must define: - Accepted inputs. - Allowed tools. - Expected
structured output. - Timeout and retry limit. - Success and failure
transitions. - Required artifacts.

### AI integration rules

-   Use the Meta Model API according to the current official
    documentation and the actual model access available to the project.
-   Keep API keys on the server and never bundle them in frontend code.
-   Validate model outputs with Pydantic schemas.
-   Use deterministic tools for file inspection, test execution, numeric
    comparisons, and result collection.
-   Treat model-produced file paths, commands, and code as untrusted
    inputs.
-   Do not let the model directly execute arbitrary shell commands.
-   Require tool allowlists, argument validation, and policy checks.
-   Record model version/configuration and tool results for
    reproducibility.
-   Set model-call, token, retry, and execution budgets.

------------------------------------------------------------------------

## 10. Database Design

Use PostgreSQL for relational records. Store large binary artifacts in
object storage and keep their metadata/keys in PostgreSQL. Do not store
entire project ZIPs, screenshots, or traces as database blobs unless
there is a clear reason.

### Entity relationships

``` text
users
  └── workspace_members ── workspaces
                              └── projects
                                    └── investigations
                                          ├── investigation_stages
                                          ├── evidence_artifacts
                                          ├── hypotheses
                                          ├── regression_tests
                                          ├── patches
                                          ├── verification_runs
                                          │      └── verification_checks
                                          └── activity_events
```

### Proposed tables

#### `users`

  Column           Type           Notes
  ---------------- -------------- ------------------
  `id`             UUID, PK       User identifier
  `email`          TEXT, UNIQUE   Normalized email
  `display_name`   TEXT           Optional
  `created_at`     TIMESTAMPTZ    Creation time
  `updated_at`     TIMESTAMPTZ    Last update

Authentication can be delegated to a trusted auth provider. Do not store
raw passwords.

#### `workspaces`

  Column            Type             Notes
  ----------------- ---------------- ----------------------
  `id`              UUID, PK         Workspace identifier
  `name`            TEXT             Workspace name
  `owner_user_id`   UUID, FK users   Owner
  `created_at`      TIMESTAMPTZ      Creation time

#### `workspace_members`

  Column           Type          Notes
  ---------------- ------------- --------------------------------------
  `workspace_id`   UUID, FK      Workspace
  `user_id`        UUID, FK      Member
  `role`           TEXT          `owner`, `admin`, `member`, `viewer`
  `created_at`     TIMESTAMPTZ   Join time

Composite primary key: (`workspace_id`, `user_id`).

#### `projects`

  ----------------------------------------------------------------------------
  Column                  Type                    Notes
  ----------------------- ----------------------- ----------------------------
  `id`                    UUID, PK                Project identifier

  `workspace_id`          UUID, FK                Owning workspace

  `name`                  TEXT                    Project name

  `source_type`           TEXT                    `upload`, `github`,
                                                  `managed_demo`

  `source_reference`      TEXT, nullable          Repository URL/reference;
                                                  avoid storing tokens here

  `default_branch`        TEXT, nullable          Branch name

  `detected_stack`        JSONB                   Framework/language/package
                                                  manager

  `setup_config`          JSONB                   Validated commands and
                                                  configuration

  `created_at`            TIMESTAMPTZ             Creation time

  `updated_at`            TIMESTAMPTZ             Update time
  ----------------------------------------------------------------------------

#### `investigations`

  -----------------------------------------------------------------------------
  Column                        Type                    Notes
  ----------------------------- ----------------------- -----------------------
  `id`                          UUID, PK                Investigation
                                                        identifier

  `project_id`                  UUID, FK                Project

  `created_by`                  UUID, FK users          Requesting user

  `title`                       TEXT                    Bug title

  `description`                 TEXT                    User's report

  `expected_behavior`           TEXT, nullable          Expected behavior

  `observed_behavior`           TEXT, nullable          Observed behavior

  `reproduction_notes`          TEXT, nullable          User-provided steps

  `status`                      TEXT                    Current workflow state

  `reproduction_status`         TEXT, nullable          `reproduced`,
                                                        `not_reproduced`,
                                                        `blocked`,
                                                        `inconclusive`

  `final_verification_status`   TEXT, nullable          `verified`, `partial`,
                                                        `failed`, `blocked`,
                                                        `inconclusive`

  `model_provider`              TEXT                    Provider name

  `model_id`                    TEXT                    Model identifier
                                                        actually used

  `budget_config`               JSONB                   Limits for
                                                        retries/calls/time

  `started_at`                  TIMESTAMPTZ, nullable   Start

  `completed_at`                TIMESTAMPTZ, nullable   Completion

  `created_at`                  TIMESTAMPTZ             Creation time
  -----------------------------------------------------------------------------

#### `investigation_stages`

  -----------------------------------------------------------------------
  Column                  Type                    Notes
  ----------------------- ----------------------- -----------------------
  `id`                    UUID, PK                Stage record

  `investigation_id`      UUID, FK                Investigation

  `stage_name`            TEXT                    State-machine stage

  `status`                TEXT                    `queued`, `running`,
                                                  `passed`, `failed`,
                                                  `blocked`, `skipped`

  `attempt_number`        INTEGER                 Retry count

  `input_summary`         JSONB                   Safe, redacted summary

  `output_summary`        JSONB                   Structured result

  `error_code`            TEXT, nullable          Machine-readable error

  `started_at`            TIMESTAMPTZ, nullable   Start

  `completed_at`          TIMESTAMPTZ, nullable   Completion
  -----------------------------------------------------------------------

#### `evidence_artifacts`

  -----------------------------------------------------------------------
  Column                  Type                    Notes
  ----------------------- ----------------------- -----------------------
  `id`                    UUID, PK                Artifact identifier

  `investigation_id`      UUID, FK                Investigation

  `stage_id`              UUID, FK, nullable      Producing stage

  `artifact_type`         TEXT                    `screenshot`,
                                                  `console_log`,
                                                  `network_log`, `trace`,
                                                  `test_output`,
                                                  `user_attachment`,
                                                  `report`

  `storage_key`           TEXT, nullable          Object-storage key

  `text_content`          TEXT, nullable          For small text
                                                  artifacts only

  `metadata`              JSONB                   Size, mime type,
                                                  source, timestamps

  `sha256`                TEXT, nullable          Integrity check

  `created_at`            TIMESTAMPTZ             Creation time
  -----------------------------------------------------------------------

#### `hypotheses`

  ------------------------------------------------------------------------------
  Column                         Type                    Notes
  ------------------------------ ----------------------- -----------------------
  `id`                           UUID, PK                Hypothesis identifier

  `investigation_id`             UUID, FK                Investigation

  `title`                        TEXT                    Candidate cause

  `description`                  TEXT                    Explanation

  `status`                       TEXT                    `proposed`,
                                                         `supported`,
                                                         `rejected`,
                                                         `unresolved`

  `confidence_label`             TEXT, nullable          Qualitative label; do
                                                         not imply calibrated
                                                         probability

  `supporting_evidence_ids`      UUID\[\] or relation    Evidence references
                                 table                   

  `contradicting_evidence_ids`   UUID\[\] or relation    Contradictory
                                 table                   references

  `created_at`                   TIMESTAMPTZ             Creation time
  ------------------------------------------------------------------------------

For stronger referential integrity, use separate `hypothesis_evidence`
rows instead of UUID arrays.

#### `regression_tests`

  -----------------------------------------------------------------------
  Column                  Type                    Notes
  ----------------------- ----------------------- -----------------------
  `id`                    UUID, PK                Test identifier

  `investigation_id`      UUID, FK                Investigation

  `framework`             TEXT                    Playwright, pytest,
                                                  etc.

  `test_name`             TEXT                    Test label

  `test_path`             TEXT, nullable          Path in isolated
                                                  workspace

  `test_content_hash`     TEXT, nullable          Hash of generated test

  `baseline_status`       TEXT                    `failed`, `passed`,
                                                  `blocked`,
                                                  `inconclusive`

  `created_at`            TIMESTAMPTZ             Creation time
  -----------------------------------------------------------------------

#### `patches`

  -----------------------------------------------------------------------
  Column                  Type                    Notes
  ----------------------- ----------------------- -----------------------
  `id`                    UUID, PK                Patch identifier

  `investigation_id`      UUID, FK                Investigation

  `created_by_agent`      BOOLEAN                 Whether proposed by the
                                                  agent

  `diff_storage_key`      TEXT, nullable          Stored diff artifact

  `diff_summary`          TEXT                    Human-readable summary

  `status`                TEXT                    `proposed`, `approved`,
                                                  `rejected`, `applied`,
                                                  `discarded`

  `approved_by`           UUID, FK users,         Approving user
                          nullable                

  `approved_at`           TIMESTAMPTZ, nullable   Approval time

  `created_at`            TIMESTAMPTZ             Creation time
  -----------------------------------------------------------------------

#### `verification_runs`

  -----------------------------------------------------------------------
  Column                  Type                    Notes
  ----------------------- ----------------------- -----------------------
  `id`                    UUID, PK                Verification run

  `investigation_id`      UUID, FK                Investigation

  `patch_id`              UUID, FK, nullable      Patch under test

  `run_type`              TEXT                    `baseline`,
                                                  `post_patch`

  `overall_status`        TEXT                    `passed`, `failed`,
                                                  `partial`, `blocked`,
                                                  `inconclusive`

  `duration_ms`           BIGINT, nullable        Runtime

  `environment_summary`   JSONB                   Runtime versions and
                                                  test configuration

  `started_at`            TIMESTAMPTZ             Start

  `completed_at`          TIMESTAMPTZ, nullable   Completion
  -----------------------------------------------------------------------

#### `verification_checks`

  -----------------------------------------------------------------------
  Column                  Type                    Notes
  ----------------------- ----------------------- -----------------------
  `id`                    UUID, PK                Check identifier

  `verification_run_id`   UUID, FK                Verification run

  `check_name`            TEXT                    Regression test, unit
                                                  tests, lint, typecheck

  `status`                TEXT                    `passed`, `failed`,
                                                  `skipped`, `timed_out`,
                                                  `blocked`

  `exit_code`             INTEGER, nullable       Process exit code

  `output_artifact_id`    UUID, FK                Captured output
                          evidence_artifacts,     
                          nullable                

  `duration_ms`           BIGINT, nullable        Runtime
  -----------------------------------------------------------------------

#### `activity_events`

  -----------------------------------------------------------------------
  Column                  Type                    Notes
  ----------------------- ----------------------- -----------------------
  `id`                    UUID, PK                Event identifier

  `investigation_id`      UUID, FK                Investigation

  `actor_type`            TEXT                    `user`, `agent`,
                                                  `system`

  `event_type`            TEXT                    Created, stage changed,
                                                  approval, test result,
                                                  etc.

  `summary`               TEXT                    Safe human-readable
                                                  event

  `metadata`              JSONB                   Redacted details

  `created_at`            TIMESTAMPTZ             Event time
  -----------------------------------------------------------------------

### Database rules

-   Use UUID primary keys.
-   Use UTC timestamps.
-   Add indexes on foreign keys, project/workspace lookups,
    investigation status, and creation time.
-   Enforce workspace authorization in the API and, where practical,
    PostgreSQL row-level security.
-   Store artifact bytes in object storage, not large database fields.
-   Redact secrets from logs and model inputs.
-   Define retention and deletion behavior for uploaded source code and
    artifacts.
-   Keep append-only activity records for important actions such as
    patch approval and verification outcomes.

------------------------------------------------------------------------

## 11. API Design

The following routes are a proposed MVP contract. Request/response
schemas should be finalized during implementation.

  ----------------------------------------------------------------------------------------------------------
  Method                  Endpoint                                                   Purpose
  ----------------------- ---------------------------------------------------------- -----------------------
  `GET`                   `/api/v1/workspaces`                                       List accessible
                                                                                     workspaces

  `POST`                  `/api/v1/workspaces`                                       Create a workspace

  `GET`                   `/api/v1/projects`                                         List accessible
                                                                                     projects

  `POST`                  `/api/v1/projects`                                         Create project metadata

  `POST`                  `/api/v1/projects/{project_id}/source`                     Upload or register
                                                                                     source

  `POST`                  `/api/v1/projects/{project_id}/inspect`                    Start project
                                                                                     inspection

  `GET`                   `/api/v1/projects/{project_id}`                            Get project details and
                                                                                     detected stack

  `POST`                  `/api/v1/projects/{project_id}/investigations`             Create an investigation

  `GET`                   `/api/v1/investigations/{investigation_id}`                Get investigation
                                                                                     status and summary

  `POST`                  `/api/v1/investigations/{investigation_id}/start`          Start or resume an
                                                                                     investigation

  `POST`                  `/api/v1/investigations/{investigation_id}/cancel`         Cancel investigation

  `GET`                   `/api/v1/investigations/{investigation_id}/events`         Get investigation
                                                                                     timeline

  `GET`                   `/api/v1/investigations/{investigation_id}/evidence`       List evidence artifacts

  `GET`                   `/api/v1/investigations/{investigation_id}/hypotheses`     List root-cause
                                                                                     hypotheses

  `GET`                   `/api/v1/investigations/{investigation_id}/patches`        List proposed patches

  `POST`                  `/api/v1/patches/{patch_id}/approve`                       Approve patch
                                                                                     application/export

  `POST`                  `/api/v1/patches/{patch_id}/reject`                        Reject patch

  `POST`                  `/api/v1/patches/{patch_id}/discard`                       Discard patch workspace

  `GET`                   `/api/v1/investigations/{investigation_id}/verification`   Get verification
                                                                                     results

  `GET`                   `/api/v1/investigations/{investigation_id}/report`         Export report
  ----------------------------------------------------------------------------------------------------------

Use asynchronous job execution for long-running tasks. The API should
return a job/investigation identifier immediately and let the UI poll or
subscribe to status updates. Server-sent events can be considered for
live progress after the core workflow works.

------------------------------------------------------------------------

## 12. Security, Privacy, and Trust

This section is a release blocker, not an optional enhancement.

### Threats to consider

-   Malicious package install scripts or test commands.
-   Path traversal in uploaded archives.
-   Prompt injection embedded in repository files, comments, logs, or
    screenshots.
-   Attempts to read environment variables or secrets.
-   Excessive resource use or infinite processes.
-   Unauthorized access to another user's project.
-   Sensitive source code leaking into logs or model requests.
-   Model-generated commands or patches targeting files outside the
    workspace.

### Required controls

1.  Run project commands only in isolated, disposable environments.
2.  Never run untrusted commands inside the main API process.
3.  Never expose model API keys to project code or the browser.
4.  Use strict CPU, memory, disk, and time limits.
5.  Restrict filesystem access to the assigned workspace.
6.  Disable network access for test execution where practical;
    explicitly allowlist any required access.
7.  Validate archive paths and reject path traversal, symlinks,
    oversized files, and suspicious archive structures.
8.  Use an allowlist of supported commands and validate their arguments.
9.  Treat repository content as untrusted data, not as system
    instructions.
10. Keep model tools narrow and permissioned.
11. Require explicit approval before patch application.
12. Enforce workspace/project authorization on every API request.
13. Redact tokens, passwords, cookies, and environment values from logs.
14. Provide project/artifact deletion and retention controls.
15. Do not claim production-grade isolation merely because Docker is
    used; containers require careful configuration and may not be
    sufficient for hostile workloads.

### Privacy principles

-   Tell users which code, logs, screenshots, and artifacts may be sent
    to the model provider.
-   Send only the context required for the current step.
-   Avoid collecting production data and secrets.
-   Store source code only as long as necessary under the selected
    retention policy.
-   Make deletion behavior clear.
-   Do not use customer repositories for training without explicit
    authorization and a suitable policy.

------------------------------------------------------------------------

## 13. Non-Functional Requirements

### Reliability

-   Every investigation must end in a terminal state, including failure
    and cancellation.
-   A failed tool call must not silently become a successful stage.
-   Retry policies must be bounded and observable.
-   Partial results should be preserved when safe and useful.

### Performance

Initial targets for a controlled demo environment: - Standard API reads
should usually respond within 500 ms, excluding external services. -
Investigation creation should return promptly without waiting for the
entire investigation. - Long-running execution should provide stage
updates. - Set per-stage and per-investigation timeouts rather than
assuming all projects run quickly.

These are proposed targets, not measured performance guarantees.

### Scalability

-   Separate web requests from long-running investigation workers.
-   Keep execution workers stateless where possible.
-   Store large artifacts externally.
-   Use job queues if concurrent investigations exceed the capacity of a
    single worker.
-   Avoid microservices until there is a demonstrated need.

### Accessibility

-   Keyboard navigation for primary workflows.
-   Readable contrast and visible focus states.
-   Status communicated through text and icons, not color alone.
-   Accessible labels for controls.
-   Responsive layouts.

### Maintainability

-   Typed request/response schemas.
-   Unit tests for orchestration transitions and permission checks.
-   Integration tests for the full investigation workflow.
-   Versioned API routes.
-   Structured logs with sensitive values redacted.
-   Separate model prompts from application code and version them.

------------------------------------------------------------------------

## 14. Testing and Evaluation Plan

A credible demo should use reproducible, seeded defects rather than
relying on an unpredictable live bug.

### Benchmark

Prepare 10--15 controlled bug scenarios across supported web
applications. For each scenario, document: - The original defect. -
Expected behavior. - Reproduction steps. - Relevant files. - The
expected regression-test behavior. - What a correct fix must preserve.

### Metrics

  -----------------------------------------------------------------------
  Metric                              Definition
  ----------------------------------- -----------------------------------
  Reproduction success rate           Percentage of seeded issues
                                      reproduced under supported
                                      conditions

  Root-cause accuracy                 Percentage of diagnoses matching
                                      the documented underlying defect

  Regression-test validity            Percentage of generated tests that
                                      fail on the buggy baseline and pass
                                      on a correct fix

  Verified-fix rate                   Percentage of cases passing the
                                      required verification checks

  Regression rate                     Percentage of proposed patches that
                                      break previously passing checks

  False-verification rate             Percentage of investigations marked
                                      verified without adequate evidence

  Investigation duration              Time from start to terminal status

  Cost per investigation              Model and compute cost per run

  Blocked/inconclusive rate           Percentage of cases that cannot be
                                      conclusively evaluated
  -----------------------------------------------------------------------

Report the sample size and test conditions alongside the metrics. Do not
claim broad real-world reliability from a small benchmark.

### Minimum acceptance criteria for the hackathon demo

-   At least one end-to-end bug investigation completes on a prepared
    repository.
-   Runtime evidence is captured by real tools.
-   The proposed regression test fails on the original bug, where the
    scenario is designed to support this.
-   The patch is shown as a diff and requires user approval.
-   Post-patch tests actually execute.
-   The final report accurately displays pass/fail/blocked states.
-   The UI never reports a verified fix if the required verification did
    not occur.

------------------------------------------------------------------------

## 15. Risks and Mitigations

  -----------------------------------------------------------------------
  Risk                    Impact                  Mitigation
  ----------------------- ----------------------- -----------------------
  Model proposes an       Wasted time or unsafe   Require evidence,
  incorrect cause         changes                 multiple hypotheses,
                                                  and executable checks

  Regression test does    False confidence        Run it against the
  not represent the bug                           original baseline and
                                                  inspect expected
                                                  assertions

  Patch creates a new     Broken behavior         Run relevant existing
  defect                                          tests and preserve the
                                                  original checkout

  Project cannot start in Investigation blocked   Support a narrow stack,
  the runner                                      validate commands,
                                                  provide clear
                                                  diagnostics

  Third-party service     Incomplete reproduction Use mocks/fixtures or
  unavailable                                     mark the investigation
                                                  blocked

  API cost or latency     Poor user experience    Limit retries, context
  grows                                           size, and model calls

  Untrusted code executes Security incident       Isolated workers,
  malicious actions                               restricted permissions,
                                                  resource/network limits

  Feature scope expands   Incomplete MVP          Prioritize one complete
  too far                                         workflow over many
                                                  partial features

  Meta API access/model   Integration delay       Verify access and run a
  behavior differs from                           minimal
  assumptions                                     API/tool-calling proof
                                                  of concept first

  Brand/domain is         Rebranding or legal     Conduct name, domain,
  unavailable             risk                    and trademark checks
                                                  before public launch
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 16. Delivery Roadmap

The initial plan is deliberately staged. The hackathon version should be
completed before expanding the feature set.

### Phase 0 --- Technical validation

-   Verify Meta Model API access and the model identifier available to
    the project.
-   Test a minimal Muse Spark request.
-   Test structured output and tool calling.
-   Run Playwright against a prepared web application.
-   Prove that a test can be executed in a disposable workspace.
-   Validate the feasibility of storing and retrieving evidence
    artifacts.

**Exit criterion:** A minimal proof of concept successfully calls the
model, executes one constrained tool, and captures real test output.

### Phase 1 --- Investigation skeleton

-   Implement database models and APIs.
-   Create project and investigation records.
-   Add the state machine and stage events.
-   Build the basic dashboard and investigation timeline.

**Exit criterion:** A user can create an investigation and see real
state changes.

### Phase 2 --- Repository and reproduction

-   Implement ZIP validation and safe extraction.
-   Detect supported project commands.
-   Implement repository inspection tools.
-   Integrate Playwright reproduction for one prepared application.
-   Capture logs, screenshots, and test outputs.

**Exit criterion:** The system can reproduce or truthfully report why it
could not reproduce a seeded bug.

### Phase 3 --- Diagnosis and patch proposal

-   Integrate evidence-grounded Muse Spark reasoning.
-   Generate structured hypotheses.
-   Generate a regression-test proposal.
-   Validate the test against the original baseline.
-   Produce a patch diff in an isolated workspace.

**Exit criterion:** The UI displays evidence, a diagnosis, a regression
test, and a reviewable patch.

### Phase 4 --- Verification and polish

-   Add user approval.
-   Run post-patch tests.
-   Display before/after outcomes.
-   Export a Markdown report.
-   Test failure, timeout, cancellation, and blocked states.
-   Improve visual hierarchy and demo flow.

**Exit criterion:** One complete scenario works from bug report to
truthful verification report.

### Phase 5 --- After the hackathon

-   GitHub import and pull-request workflow.
-   Additional frameworks and test runners.
-   Team workspaces.
-   CI integration.
-   Better repository retrieval.
-   Historical investigation analytics.
-   More robust sandboxing and security review.

------------------------------------------------------------------------

## 17. Hackathon Demo Plan

### Demo scenario

Use a prepared React/Next.js project with a known, reproducible
defect---for example, a form submission or client-side state bug.

### Demo sequence

1.  Show the broken behavior.
2.  Submit the bug report to Meridian.
3.  Show project inspection and the investigation plan.
4.  Show the browser reproduction and captured evidence.
5.  Show the diagnosis with source references.
6.  Show the regression test failing on the baseline.
7.  Show the proposed patch diff.
8.  Approve the patch.
9.  Run the regression test and relevant checks.
10. Show the actual before/after results.
11. Open the final evidence-backed report, including limitations.

### Demo rules

-   Use real tool executions and test output.
-   Clearly distinguish seeded/demo data from general claims.
-   Keep a backup recording in case the environment fails.
-   Do not fabricate execution results.
-   If a stage fails live, explain the failure rather than presenting it
    as a success.
-   Clearly identify the new work built during the hackathon.

------------------------------------------------------------------------

## 18. Product Success Criteria

### Hackathon success

-   Complete one end-to-end investigation.
-   Demonstrate genuine Meta model integration.
-   Show real repository and runtime evidence.
-   Show a real regression test and patch-verification cycle.
-   Provide a polished, understandable demo.
-   Publish a public repository with setup instructions, architecture,
    limitations, and a demo.

### Early product validation

Before turning Meridian into a commercial product, interview developers
and small teams to understand: - How often they encounter the target bug
categories. - What tools they currently use. - Where their debugging
workflow loses time. - Which repositories and environments they would
trust an agent to access. - What level of automation they would
permit. - Whether they would pay for verified investigation outcomes. -
Which integrations would be essential.

### Longer-term business hypothesis

Potential monetization paths include: - Free individual tier with
limited investigations. - Paid developer tier with larger investigation
budgets. - Team subscriptions with shared history and integrations. -
Enterprise deployment with stronger controls and private execution
environments.

These are hypotheses to validate, not confirmed pricing or
product-market fit.

------------------------------------------------------------------------

## 19. Open Decisions

The following decisions should be confirmed before implementation:

1.  **Initial source input:** ZIP upload first, or GitHub import first?\
    **Recommendation:** ZIP upload or prepared repository first; GitHub
    integration after the core loop works.

2.  **Initial supported framework:** React/Vite or Next.js?\
    **Recommendation:** Select one framework for the first complete
    scenario, then add a second only if time permits.

3.  **Execution environment:** Local development runner or hosted
    isolated worker?\
    **Recommendation:** Use prepared repositories in an isolated,
    controlled runner for the hackathon; do not expose arbitrary public
    code execution.

4.  **Patch application:** Automatic or human-approved?\
    **Recommendation:** Human approval is required.

5.  **Search strategy:** Vector database or direct code search?\
    **Recommendation:** Start with direct search and targeted file
    reads. Add embeddings only if evaluation shows they improve
    retrieval.

6.  **Live progress:** Polling or server-sent events?\
    **Recommendation:** Polling for the first version; server-sent
    events can follow.

7.  **Model availability:** Which Meta model identifier and capabilities
    are available to the account/project?\
    **Recommendation:** Confirm against current official documentation
    and a working API call before finalizing prompts and schemas.

8.  **Name availability:** Is Meridian available for the intended
    software category, domain, and jurisdiction?\
    **Recommendation:** Complete legal and domain checks before public
    launch.

------------------------------------------------------------------------

## 20. Final Product Definition

**Meridian is an evidence-driven AI software investigation platform.**
It helps developers investigate supported software failures by combining
repository inspection, controlled runtime reproduction, structured
reasoning, regression-test generation, patch review, and post-change
verification.

Its defining principle is not that AI can always fix a bug. It is that
the system should show **what it observed, what it inferred, what it
changed, which checks actually ran, and what remains uncertain**.

The MVP should focus on one supported web stack and a small set of
reproducible bugs. A complete and honest investigation workflow is more
valuable than a broad product that only partially works.

------------------------------------------------------------------------

## Appendix A --- Suggested Repository Structure

``` text
meridian/
├── apps/
│   └── web/                     # Next.js frontend
├── services/
│   └── api/                     # FastAPI application
├── workers/
│   └── investigation/            # Orchestration and job execution
├── packages/
│   ├── shared-types/             # Shared API types/schemas if needed
│   └── ui/                        # Reusable UI components if needed
├── infrastructure/
│   ├── docker/                    # Restricted runner images/configuration
│   └── deployment/                # Deployment configuration
├── docs/
│   ├── PRD.md
│   ├── ARCHITECTURE.md
│   ├── DATABASE.md
│   ├── API.md
│   ├── SECURITY.md
│   └── TEST_PLAN.md
├── fixtures/
│   └── seeded-bugs/               # Controlled demonstration repositories
├── .env.example
├── README.md
└── LICENSE
```

This is a suggested monorepo structure. It can be simplified for the
hackathon; do not create separate packages or services unless they
provide practical value.

## Appendix B --- Initial Environment Variables

Use a secret manager or deployment environment for actual secrets. The
example file should contain placeholders only.

``` env
# API
APP_ENV=development
API_BASE_URL=http://localhost:8000
FRONTEND_ORIGIN=http://localhost:3000

# Database
DATABASE_URL=postgresql://USER:PASSWORD@localhost:5432/meridian

# Meta Model API
META_API_KEY=
META_MODEL_ID=

# Artifact storage (provider-specific)
OBJECT_STORAGE_ENDPOINT=
OBJECT_STORAGE_BUCKET=
OBJECT_STORAGE_ACCESS_KEY=
OBJECT_STORAGE_SECRET_KEY=

# Execution policy
MAX_INVESTIGATION_SECONDS=900
MAX_STAGE_RETRIES=2
MAX_MODEL_CALLS_PER_INVESTIGATION=20
MAX_UPLOAD_SIZE_MB=50
```

All values are illustrative configuration placeholders. Confirm actual
Meta API settings and model identifiers from the current official
documentation. Never commit real secrets to Git.

## Appendix C --- Glossary

-   **Evidence:** An observed artifact such as a log, screenshot,
    network event, source snippet, or test result.
-   **Hypothesis:** A possible explanation that still requires
    supporting evidence.
-   **Reproduction:** An attempt to trigger the reported failure under
    controlled conditions.
-   **Regression test:** A test intended to detect the previously
    reported defect in the future.
-   **Patch:** A proposed source-code change.
-   **Verification:** Execution of defined checks to evaluate whether a
    patch addresses the issue and whether relevant existing behavior
    remains intact.
-   **Blocked:** The workflow could not proceed because a prerequisite
    or environmental capability was unavailable.
-   **Inconclusive:** Available evidence was insufficient to reach a
    reliable result.
-   **Verified for tested conditions:** The specified checks passed;
    this does not guarantee that the entire application is bug-free.
