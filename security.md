# Meridian AI — Security Preflight Integration
## Comprehensive Architecture & Implementation Plan

**Repository:** `VivekChaurasiya95/Meridian-AI`  
**Target subsystem:** Repository Security Preflight  
**Primary stack:** FastAPI, Python Worker, PostgreSQL, MinIO, Docker, Next.js  
**Integration approach:** Extend the existing architecture; do not introduce another backend service or queue.

---

# 1. Executive Summary

Meridian AI is being developed as an evidence-backed software debugging and reliability platform. Its intended workflow is to inspect a repository, investigate a reported problem, reproduce it, develop hypotheses, propose tests and patches, and verify the results.

Before Meridian starts that investigation, it needs an initial understanding of the repository's security posture.

The proposed **Security Preflight** subsystem provides this initial assessment.

It will inspect a repository snapshot using dedicated security scanners, identify potential security issues, normalize their findings, and generate a structured security report.

The initial implementation will use:

1. **Semgrep CE** — static application security analysis and code-pattern detection.
2. **Gitleaks** — exposed credentials and secret detection.
3. **OSV-Scanner** — dependency vulnerability detection, introduced in a later phase.

Security Preflight must operate independently of the AI reasoning system. Its findings must originate from actual scanner execution, not model-generated assumptions.

## Primary objectives

- Detect common insecure coding patterns.
- Identify accidentally committed credentials and secrets.
- Establish a baseline security assessment for each immutable repository snapshot.
- Provide findings with file paths, line numbers, severity, and evidence.
- Prevent untrusted repository contents from accessing Meridian's credentials or infrastructure.
- Preserve the relationship between findings and the exact snapshot scanned.
- Make the results available to subsequent investigation stages.
- Maintain honest, auditable execution states.

## Architectural principle

Security Preflight should be an extension of Meridian's existing ingestion and durable-worker pipeline.

It should not become:

- A separate FastAPI application.
- A separate queue infrastructure.
- An unrestricted shell-execution interface.
- An AI-powered security scanner.
- A replacement for the existing sandbox.
- A guarantee that a repository is safe to execute.

---

# 2. Existing Repository Architecture

Before implementation, the existing repository structure must remain the source of truth.

## 2.1 Existing components

| Component | Existing responsibility | Preflight integration |
|---|---|---|
| `apps/web/` | Next.js application | Display security status and findings |
| `services/api/` | FastAPI backend | Authorization, job orchestration and report retrieval |
| `services/worker/` | Durable PostgreSQL job worker | Execute security-preflight jobs |
| `services/api/app/services/archive_security.py` | Archive validation | Reuse existing validation policy |
| `services/api/app/services/ingestion.py` | Repository ingestion | Establish the preflight trigger after snapshot storage |
| `services/api/app/services/storage.py` | Snapshot materialization and integrity | Provide verified source content to scanners |
| `services/api/app/services/jobs.py` | Job state machine and persistence | Extend the existing durable job lifecycle |
| `services/worker/sandbox/` | Isolated Docker execution | Provide scanner execution isolation |
| `docker-compose.yml` | Local infrastructure | Configure scanner image availability |
| `migrations/versions/` | Database migrations | Add preflight persistence |
| `docs/DECISIONS.md` | Architecture decisions | Record integration decisions |

## 2.2 Existing ingestion flow

The current upload workflow is implemented in:

`services/api/app/api/projects.py`

and:

`services/api/app/services/ingestion.py`

Its current sequence is:

1. Receive ZIP upload.
2. Validate archive size and structure.
3. Extract into a temporary directory.
4. Perform static manifest inspection.
5. Exclude generated directories and secret files from indexing.
6. Generate the indexed repository snapshot.
7. Store snapshot content in MinIO.
8. Persist snapshot metadata and file records.
9. Verify stored content integrity.
10. Mark the snapshot as `ready`.

The upload endpoint returns after this process completes.

This is important because the preflight trigger should occur only after the snapshot has been successfully persisted and marked ready.

It must not run against an incomplete or unverified snapshot.

## 2.3 Existing worker architecture

The worker already provides:

- PostgreSQL-backed durable jobs.
- `SELECT ... FOR UPDATE SKIP LOCKED` job claiming.
- Job ownership and leases.
- Heartbeats.
- Retry and recovery handling.
- Job-stage persistence.
- Graceful shutdown.
- Allowlisted job handlers.

The current registered job types include:

- `lifecycle_test`
- `manifest_recheck`
- `sandbox_smoke`

Security Preflight should become another internally generated job type.

The existing queue is sufficient for the initial implementation.

---

# 3. Proposed Security Preflight Architecture

## 3.1 High-level architecture

The proposed architecture:

```text
                  USER
                   |
                   v
             Meridian Web
                   |
                   v
              FastAPI API
                   |
                   v
          Repository Ingestion
                   |
                   v
          Archive Validation
                   |
                   v
        Static Repository Inspection
                   |
                   v
          Immutable Snapshot
                   |
                   v
             MinIO Storage
                   |
                   v
        Snapshot Integrity Check
                   |
                   v
          Snapshot READY
                   |
                   v
       Enqueue Security Preflight
                   |
                   v
          PostgreSQL Jobs
                   |
                   v
         Existing Python Worker
                   |
                   v
          Preflight Orchestrator
                   |
          +--------+--------+
          |                 |
          v                 v
     Semgrep CE          Gitleaks
          |                 |
          v                 v
     Restricted       Restricted
     Container        Container
          |                 |
          +--------+--------+
                   |
                   v
          Finding Normalizer
                   |
                   v
             Risk Policy
                   |
                   v
        Persist Security Report
                   |
                   v
       Update Preflight Status
                   |
                   v
          Meridian Web UI
                   |
                   v
       Future Investigation Flow
```

OSV-Scanner will be introduced as an additional scanner after the initial integration is stable.

## 3.2 Separation of responsibilities

The architecture should preserve the existing security boundaries.

**API**

- Authorizes the user.
- Accepts repository uploads.
- Creates and validates project resources.
- Enqueues preflight jobs.
- Exposes authorized report retrieval.

The API must never execute scanners or repository commands.

**Worker**

- Claims durable jobs.
- Materializes the required snapshot.
- Orchestrates scanner execution.
- Persists execution outcomes.
- Handles retries, cancellation, and cleanup.

**Scanner containers**

- Execute pinned scanner binaries.
- Receive only the source files needed for their task.
- Have no database or object-storage credentials.
- Have no access to the Docker socket.
- Have no unrestricted network access.

**Normalizer**

- Converts scanner-specific output into a common finding schema.
- Validates file paths and line ranges.
- Removes sensitive values.
- Rejects malformed output.

**Risk policy**

- Applies Meridian-defined severity and confidence rules.
- Determines whether the assessment requires review.
- Never claims that an unscanned repository is safe.

---

# 4. Scanner Selection and Responsibilities

## 4.1 Semgrep CE — Primary static scanner

Semgrep will identify potentially insecure coding patterns.

Initial coverage should focus on:

- SQL injection patterns.
- Command injection.
- Insecure deserialization.
- Path traversal.
- Unsafe use of cryptographic functions.
- Hardcoded credentials in source code.
- Insecure authentication and authorization patterns.
- Dangerous dynamic code execution.
- Common web application security mistakes.

Initial language support:

- Python
- JavaScript
- TypeScript

Additional language rules can be introduced as coverage grows.

### Integration requirements

- Pin the Semgrep scanner image and version.
- Maintain Meridian-owned rules.
- Use structured JSON output.
- Do not trust repository-supplied scanner configurations.
- Do not allow repositories to alter the scanner's command or rule policy.
- Enforce output, runtime, memory, and file-count limits.

Semgrep findings should contain:

- Rule identifier.
- File path.
- Start and end line.
- Severity.
- Confidence, where available.
- Short evidence excerpt.
- Scanner version.

The evidence excerpt must be sanitized before persistence.

## 4.2 Gitleaks — Secret detection

Gitleaks will detect exposed credentials and secrets.

Examples include:

- API keys.
- Cloud credentials.
- Access tokens.
- Private keys.
- Database connection credentials.
- Hardcoded service secrets.
- Other credential patterns supported by its detector rules.

Gitleaks must operate on actual repository source content, including secret files excluded from AI indexing.

### Important existing architecture issue

The current ingestion implementation excludes secret files through `is_secret_file()` before constructing the indexed snapshot.

This is correct for AI indexing, but it creates a limitation for security scanning.

If Gitleaks only receives the current indexed snapshot, it will miss files such as `.env` and private-key files because their contents are not present in that snapshot.

### Required solution: Separate security scan input

Introduce a second content artifact specifically for security preflight.

The ingestion process should maintain two logically distinct source representations:

**A. Analysis snapshot**

Contains:

- Indexed source files.
- Manifest data.
- Small text previews.
- File hashes.
- Existing tree digest.

Used by Meridian's repository browser and future AI investigation pipeline.

**B. Security scan input**

Contains:

- Validated source files required for security scanning.
- Secret files excluded from AI indexing.
- No generated or dependency directories by default.
- No unsafe archive entries or filesystem links.

Used only by the trusted security-preflight orchestrator and restricted scanner containers.

The security scan input must:

- Be produced from the already validated extraction.
- Have its own SHA-256 digest.
- Be stored privately in MinIO.
- Be associated with the exact repository snapshot.
- Never be sent to the model provider.
- Be deleted according to the repository retention and deletion policy.

Do not store raw uploaded ZIP archives indefinitely.

Do not place secret contents in database JSON, scanner logs, job results, or UI responses.

### Scanner-specific inputs

Semgrep should normally receive the analysis source tree.

Gitleaks should receive the security scan input.

This keeps the two scanner responsibilities independent and prevents secret-file exclusions from silently weakening secret detection.

## 4.3 OSV-Scanner — Dependency vulnerability detection

OSV-Scanner should be introduced in a subsequent phase.

Its responsibility is to identify known vulnerabilities in dependencies using supported lockfiles and dependency manifests.

Potential inputs include:

- `package-lock.json`
- `pnpm-lock.yaml`
- `yarn.lock`
- `poetry.lock`
- `uv.lock`
- Other supported lockfiles

Important restrictions:

- Do not install dependencies merely to perform an initial dependency scan.
- Prefer static lockfile analysis.
- Do not resolve dependencies through unrestricted package-manager execution.
- Record unsupported or missing lockfiles honestly.
- Distinguish vulnerable dependencies from malicious dependencies.

A dependency with a known vulnerability is not necessarily malicious.

---

# 5. Proposed Repository Structure

Add a dedicated security package under the existing worker.

```text
services/
│
├── api/
│   └── app/
│       ├── api/
│       ├── services/
│       ├── models.py
│       ├── schemas.py
│       └── config.py
│
└── worker/
    │
    ├── main.py
    │
    ├── sandbox/
    │   ├── container_spec.py
    │   ├── container_runtime.py
    │   ├── execution_policy.py
    │   ├── orchestrator.py
    │   ├── workspace.py
    │   └── exceptions.py
    │
    └── security/
        │
        ├── __init__.py
        ├── preflight.py
        ├── orchestrator.py
        ├── normalizer.py
        ├── risk_policy.py
        ├── result_validator.py
        │
        ├── scanners/
        │   ├── __init__.py
        │   ├── base.py
        │   ├── semgrep.py
        │   ├── gitleaks.py
        │   └── osv.py
        │
        ├── models/
        │   ├── finding.py
        │   └── report.py
        │
        └── rules/
            ├── python-security.yml
            ├── javascript-security.yml
            └── typescript-security.yml
```

These files are proposed additions, not existing modules.

## 5.1 Module responsibilities

| Module | Responsibility |
|---|---|
| `preflight.py` | Main preflight entry point |
| `orchestrator.py` | Executes the required scanner sequence |
| `scanners/base.py` | Shared scanner interface |
| `scanners/semgrep.py` | Semgrep invocation and output collection |
| `scanners/gitleaks.py` | Gitleaks invocation and output collection |
| `scanners/osv.py` | Future dependency scanning |
| `normalizer.py` | Common finding representation |
| `result_validator.py` | Validates scanner output and repository-relative paths |
| `risk_policy.py` | Severity and risk classification |
| `models/finding.py` | Finding schema |
| `models/report.py` | Security report schema |
| `rules/` | Meridian-maintained static-analysis rules |

The package should not duplicate the existing job queue, snapshot storage, or container lifecycle implementations.

---

# 6. Integration with Existing Snapshot Ingestion

This is the first major implementation area.

## 6.1 Existing ingestion module

Primary file:

`services/api/app/services/ingestion.py`

Current function:

`upload_source()`

The current implementation validates, extracts, inspects, stores, and verifies a snapshot.

The preflight integration must preserve this sequence.

## 6.2 Required ingestion changes

Extend the existing ingestion pipeline to generate the additional security scan artifact.

Proposed sequence:

1. Receive the ZIP archive.
2. Validate it using the existing archive security implementation.
3. Extract it into the existing temporary workspace.
4. Inspect the repository.
5. Identify generated and dependency directories.
6. Build the normal indexed snapshot.
7. Build the separate security scan input.
8. Calculate independent content digests.
9. Upload both artifacts to private storage.
10. Persist snapshot and artifact metadata.
11. Verify both stored objects.
12. Mark the snapshot ready only when its required storage artifacts are verified.
13. Enqueue the security-preflight job.
14. Return the upload response.

The job must not be enqueued before the snapshot is ready.

## 6.3 Storage design

There are two viable approaches:

**Preferred for this implementation: additional security artifact metadata associated with the snapshot.**

Add the following fields to `repository_snapshots`:

| Field | Purpose |
|---|---|
| `security_storage_key` | Private MinIO object key |
| `security_content_digest` | SHA-256 of the security scan artifact |
| `security_storage_bytes` | Stored artifact size |
| `security_scan_status` | Storage readiness or availability state |

Use explicit states such as:

- `pending`
- `ready`
- `failed`
- `deleting`
- `deleted`
- `integrity_failed`

These states describe artifact storage, not the security assessment itself.

The scanner should retrieve this artifact through a dedicated trusted storage method.

For example:

`materialize_security_input_for_workspace()`

It should follow the same security principles as `materialize_for_workspace()`:

- Workspace authorization.
- Object digest verification.
- File hash verification.
- Safe path handling.
- Restrictive temporary-directory permissions.
- Cleanup on success and failure.

Do not expose the security storage key through API responses.

## 6.4 Retention and deletion

The security artifact contains sensitive material.

Define an explicit retention policy before production deployment.

Requirements:

- Delete the artifact when its parent snapshot is deleted.
- Handle shared content-addressed objects using reference counting.
- Never delete an object still referenced by another snapshot.
- Ensure failed database writes do not leave unreferenced objects indefinitely.
- Provide cleanup for orphaned objects.
- Do not include security artifact contents in ordinary backup exports without an explicit policy.

---

# 7. Durable Job Integration

The existing job system is one of the strongest parts of Meridian's architecture. Security Preflight should reuse it.

## 7.1 New job type

Introduce:

`security_preflight`

It should be generated internally after a snapshot becomes ready.

The initial user-facing upload operation should not require users to manually submit a scanner job.

## 7.2 Existing integration files

The following files require coordinated changes:

- `services/api/app/models.py`
- `services/api/app/schemas.py`
- `services/api/app/services/jobs.py`
- `services/worker/main.py`
- `migrations/versions/`

The database CHECK constraint, SQLAlchemy model, request validation, and worker handler registry must remain consistent.

Do not simply add a worker handler and assume the job can be submitted.

## 7.3 Internal job payload

Illustrative payload:

```json
{
  "snapshot_id": "snapshot-uuid",
  "scan_profile": "initial_preflight",
  "policy_version": "preflight-v1"
}
```

The following values must be resolved by the backend:

- Workspace ID.
- Project ID.
- Snapshot ID.
- Scanner image references.
- Scanner versions.
- Ruleset version.
- Execution limits.
- Storage artifact references.

Never allow the frontend to select an arbitrary image, command, filesystem path, or scanner configuration.

## 7.4 Job idempotency

A snapshot should not accidentally acquire duplicate active preflight jobs because of:

- Request retries.
- Worker crashes.
- Duplicate upload callbacks.
- API retries.
- Repeated UI actions.

Use a stable idempotency identity based on:

- Snapshot ID.
- Scan profile.
- Policy version.

Only one active job should exist for the same combination.

A deliberate rescan should create a new assessment generation rather than silently overwrite the original report.

## 7.5 Job lifecycle

Use the existing job state machine:

```text
queued
  |
  v
running
  |
  +------> completed
  |
  +------> failed
  |
  +------> retry_wait
  |
  +------> cancelled
```

Do not invent a parallel job lifecycle for security scanning.

---

# 8. Scanner Execution and Sandbox Integration

This is the highest-risk implementation area.

## 8.1 Existing sandbox

Meridian already has:

- `services/worker/sandbox/container_spec.py`
- `services/worker/sandbox/container_runtime.py`
- `services/worker/sandbox/workspace.py`
- `services/worker/sandbox/orchestrator.py`
- `services/worker/sandbox/execution_policy.py`

These modules provide a strong foundation.

However, the existing `sandbox_smoke` profile is a fixed Python smoke command. It is not a general scanner execution framework.

The scanner integration must introduce explicit scanner profiles and must not expose arbitrary commands.

## 8.2 Scanner execution model

Each scanner should run in its own disposable container.

Example:

```text
Trusted Worker
    |
    +--> Prepare Semgrep input
    |        |
    |        v
    |    Semgrep container
    |        |
    |        v
    |    Structured JSON result
    |
    +--> Prepare Gitleaks input
             |
             v
         Gitleaks container
             |
             v
         Structured JSON result
```

The two scanner containers must be independent.

A failure in one scanner should not automatically prevent the other scanner from producing useful results, unless a shared prerequisite has failed.

## 8.3 Required isolation controls

Every scanner container must use:

- Non-root execution.
- Read-only root filesystem.
- Dropped Linux capabilities.
- `no-new-privileges`.
- No privileged mode.
- No Docker socket.
- No host PID or network namespaces.
- No host bind mounts.
- No database credentials.
- No MinIO credentials.
- No model-provider credentials.
- CPU limits.
- Memory limits.
- PID limits.
- Execution timeout.
- Output-size limits.
- Disposable workspaces.
- Guaranteed cleanup.

Use network mode `none` for the initial scanners wherever possible.

Scanner images must be pinned to immutable versions or digests.

Do not build scanner images from repository-controlled Dockerfiles.

Do not execute repository installation scripts during preflight.

## 8.4 Trusted scanner profiles

Introduce server-defined profiles.

Example:

| Profile | Binary | Purpose |
|---|---|---|
| `semgrep_preflight` | Semgrep | Static code scanning |
| `gitleaks_preflight` | Gitleaks | Secret scanning |
| `osv_preflight` | OSV-Scanner | Dependency analysis |

Each profile must define:

- Pinned image.
- Fixed command arguments.
- Allowed input directory.
- Output format.
- Maximum runtime.
- Maximum memory.
- Maximum output.
- Expected exit codes.
- Retry policy.

Scanner-specific argument construction must be controlled by Meridian.

Do not accept model-generated or user-generated command strings.

## 8.5 Exit-code handling

Scanner exit codes must not be interpreted identically.

For example:

- A scanner may return a nonzero code because it found findings.
- A scanner may return a nonzero code because execution failed.
- A scanner may return a timeout.
- A scanner may produce incomplete output.

The wrapper must distinguish findings from operational failures using the scanner's documented output and exit-code contract.

Never mark a scan successful merely because a process returned an exit code.

---

# 9. Normalized Finding Architecture

Different scanners produce different output formats.

Meridian should not expose raw Semgrep and Gitleaks JSON directly to the frontend or future AI stages.

Introduce a normalized finding representation.

## 9.1 Common finding schema

Illustrative contract:

```json
{
  "id": "finding-uuid",
  "scanner": "semgrep",
  "rule_id": "python.sql-injection",
  "category": "injection",
  "severity": "high",
  "confidence": "high",
  "title": "Potential SQL injection",
  "description": "Untrusted input may reach a SQL query.",
  "location": {
    "path": "services/database.py",
    "start_line": 42,
    "end_line": 45
  },
  "evidence": {
    "excerpt": "query construction excerpt",
    "redacted": false
  },
  "fingerprint": "stable-finding-fingerprint"
}
```

The example is a proposed contract, not an existing API response.

## 9.2 Required normalized fields

| Field | Purpose |
|---|---|
| `id` | Unique finding identity |
| `scanner` | Source scanner |
| `rule_id` | Scanner rule identifier |
| `category` | Security issue category |
| `severity` | Meridian severity |
| `confidence` | Confidence assessment |
| `title` | Human-readable finding |
| `description` | Explanation |
| `location.path` | Repository-relative file path |
| `location.start_line` | Starting line |
| `location.end_line` | Ending line |
| `evidence.excerpt` | Sanitized evidence |
| `fingerprint` | Stable deduplication identity |

## 9.3 Severity mapping

Use a consistent Meridian severity vocabulary:

- `critical`
- `high`
- `medium`
- `low`
- `informational`

Scanner-native severities must be mapped explicitly.

Do not assume that different scanners use identical severity scales.

A finding without a reliable severity should be handled through an explicit fallback policy rather than silently assigned a high severity.

## 9.4 Finding deduplication

Different scanners may detect overlapping issues.

Use a stable fingerprint based on suitable attributes, such as:

- Scanner.
- Rule identifier.
- Normalized file path.
- Relevant source location.
- Relevant rule-specific identity.

Do not use raw secret values to calculate or expose finding fingerprints.

Preserve scanner-specific findings when they represent distinct evidence.

---

# 10. Secret Redaction and Sensitive Data Protection

This area requires special attention.

Gitleaks is expected to detect sensitive values. Meridian must not turn those values into another source of exposure.

## 10.1 Never persist raw secrets in reports

Do not store:

- Complete API keys.
- Passwords.
- Private-key material.
- Full connection strings.
- Authentication tokens.

The normalizer should retain only the minimum evidence needed to explain the finding.

For example:

```text
Detected token:
sk_live_************7F2A
```

The exact masking strategy should be detector-aware.

## 10.2 Output handling

Before persistence:

1. Parse scanner output.
2. Validate the structure.
3. Identify sensitive fields.
4. Redact matched values.
5. Validate repository-relative paths.
6. Truncate oversized excerpts.
7. Remove irrelevant environment information.
8. Persist only the sanitized representation.

Scanner logs must also be treated as untrusted input.

Do not write full scanner output to ordinary worker logs.

## 10.3 AI boundary

Security Preflight findings may eventually be used by Meridian's AI reasoning pipeline.

However, only sanitized, authorized findings should be sent to a model provider.

The original security scan artifact and raw scanner output must remain outside the model context.

---

# 11. Security Assessment and Risk Policy

The risk policy translates technical findings into a useful assessment.

It must not pretend to provide a formal security certification.

## 11.1 Assessment states

Recommended assessment statuses:

| Status | Meaning |
|---|---|
| `pending` | Assessment has not started |
| `running` | Scanners are executing |
| `completed` | Required scanners completed and results were persisted |
| `review_required` | Findings require human review |
| `partial` | Some scanners completed, others did not |
| `failed` | Assessment could not be completed |
| `cancelled` | Assessment was cancelled |

`completed` and `review_required` are different concepts.

A completed scan can have no findings, or it can have significant findings.

## 11.2 Risk interpretation

The risk policy should evaluate:

- Finding severity.
- Confidence.
- Scanner reliability.
- Finding category.
- Whether a required scanner failed.
- Whether the snapshot was fully scanned.

Illustrative interpretation:

| Result | Interpretation |
|---|---|
| No findings, all scanners completed | No issues detected by configured checks |
| Low/medium findings | Review recommended |
| High findings | Security review required |
| Critical findings | Strong warning and explicit review |
| Scanner failure | Assessment incomplete |
| Partial scanner completion | Partial assessment |

Do not automatically equate `no findings` with `safe`.

Do not let a low-severity finding hide a failed scanner.

## 11.3 Preflight is not execution authorization

A clean preflight must never bypass the existing sandbox.

The repository remains untrusted regardless of the assessment result.

This rule must be enforced in the backend, not just displayed in the frontend.

---

# 12. Database Design

The initial implementation should minimize schema complexity.

There are two possible persistence approaches.

## 12.1 Recommended initial approach

Use the existing:

- `jobs`
- `job_stages`
- `sandbox_executions`

for job lifecycle, stage progress, and scanner container execution records.

Add a dedicated security assessment table for durable, snapshot-specific findings.

Suggested table:

`security_assessments`

Potential fields:

| Field | Purpose |
|---|---|
| `id` | Assessment UUID |
| `workspace_id` | Tenant ownership |
| `project_id` | Associated project |
| `snapshot_id` | Exact scanned snapshot |
| `job_id` | Associated durable job |
| `generation` | Assessment generation |
| `status` | Assessment status |
| `policy_version` | Meridian policy version |
| `summary` | Sanitized finding counts |
| `scanner_versions` | Scanner version metadata |
| `ruleset_version` | Ruleset identity |
| `started_at` | Execution start |
| `completed_at` | Execution completion |
| `created_at` | Record creation |

Add a child table:

`security_findings`

Potential fields:

| Field | Purpose |
|---|---|
| `id` | Finding UUID |
| `assessment_id` | Parent assessment |
| `fingerprint` | Deduplication identity |
| `scanner` | Scanner name |
| `rule_id` | Rule identifier |
| `severity` | Normalized severity |
| `confidence` | Confidence |
| `category` | Finding category |
| `title` | Finding title |
| `description` | Sanitized description |
| `location` | Repository-relative location |
| `evidence` | Sanitized evidence |
| `created_at` | Creation time |

Use JSONB for structured `summary`, `scanner_versions`, `location`, and `evidence` where appropriate.

Do not create a separate table for every scanner.

## 12.2 Why not use only `jobs.result`?

The existing job result is useful for execution summaries, but security findings have a longer lifecycle.

They need:

- Snapshot-level retrieval.
- Filtering.
- Pagination.
- Stable identities.
- Comparison across snapshots.
- Historical assessments.
- Independent authorization.
- Future investigation references.

Therefore, a dedicated assessment and findings model is preferable once the preflight feature becomes a real product capability.

Keep `jobs.result` concise and use it to reference the persisted assessment.

## 12.3 Migration plan

Proposed migration:

`migrations/versions/007_security_preflight.py`

It should:

1. Add security artifact metadata to `repository_snapshots`.
2. Create `security_assessments`.
3. Create `security_findings`.
4. Add foreign keys and appropriate deletion policies.
5. Add indexes for snapshot, project, workspace, assessment status, and finding severity.
6. Add database CHECK constraints for supported states and severity values.

The SQLAlchemy models must mirror migration SQL exactly.

The migration must be additive.

Do not edit historical migrations.

The job-type constraint must also be extended consistently to include `security_preflight`.

---

# 13. Worker Integration

## 13.1 New handler

In:

`services/worker/main.py`

Add:

`handle_security_preflight()`

The handler should:

1. Validate the job payload.
2. Verify the job is claimed and owned.
3. Resolve the workspace and snapshot.
4. Confirm the snapshot is ready.
5. Verify the security scan artifact.
6. Create the assessment record.
7. Materialize the required scanner inputs.
8. Execute Semgrep.
9. Execute Gitleaks.
10. Collect and validate results.
11. Normalize findings.
12. Apply the risk policy.
13. Persist the assessment and findings.
14. Record final job results.
15. Clean all temporary directories and containers.

Register the handler in the existing `HANDLERS` mapping.

## 13.2 Job stages

Use the existing `job_stages` infrastructure.

Recommended stages:

```text
validate_snapshot
prepare_scan_input
semgrep_scan
gitleaks_scan
normalize_findings
apply_risk_policy
persist_assessment
cleanup
```

Each stage should report a real outcome.

For example:

- `completed`
- `failed`
- `blocked`
- `skipped`
- `cancelled`

Do not mark a scanner stage completed if the scanner did not actually finish.

## 13.3 Retry handling

Differentiate between transient and permanent failures.

Potential transient failures:

- Container runtime temporarily unavailable.
- Storage temporarily unavailable.
- Worker interruption.
- Temporary resource exhaustion.

Potential permanent failures:

- Invalid snapshot.
- Malformed scanner output.
- Unsupported scan profile.
- Invalid security artifact.
- Invalid policy configuration.

A scanner finding is not a job failure.

A scan that successfully identifies vulnerabilities should still complete successfully.

## 13.4 Partial execution

Suppose Semgrep completes but Gitleaks fails.

The report must not be marked fully completed.

It should retain the successful Semgrep findings and record the Gitleaks operational failure.

The overall assessment should become `partial` if the implementation's required scanners are not all successful.

Do not silently retry forever or discard useful completed results.

---

# 14. API Integration

The existing API should expose assessment retrieval rather than exposing raw scanner execution.

Suggested endpoints:

```text
GET /api/v1/projects/{project_id}/security-assessments

GET /api/v1/snapshots/{snapshot_id}/security-assessment

GET /api/v1/security-assessments/{assessment_id}

GET /api/v1/security-assessments/{assessment_id}/findings
```

Optional future endpoint:

```text
POST /api/v1/snapshots/{snapshot_id}/security-assessment/rescan
```

The rescan endpoint should require an authorized contributor role and enforce idempotency and rate limits.

## API rules

- Every endpoint must authorize workspace membership.
- Foreign resources should return 404.
- Viewer access should be read-only.
- Contributors may request rescans.
- Findings should use cursor pagination.
- Raw scanner output must never be returned.
- Object-storage keys must never be exposed.
- Sensitive evidence must remain redacted.
- Every response must use Meridian's existing API envelope.

Do not add an endpoint that accepts arbitrary scanner commands.

---

# 15. Frontend Integration

Security Preflight should appear as part of the existing project experience.

It should not look like an unrelated security dashboard bolted onto Meridian.

## 15.1 Project overview

Add a security assessment section to the project overview.

Display:

- Latest snapshot.
- Assessment status.
- Last scan time.
- Scanner coverage.
- Critical findings.
- High findings.
- Medium findings.
- Low findings.

Use real persisted backend data.

If an assessment is pending, display that state instead of inventing a security score.

## 15.2 Security findings page

Add a dedicated security view.

Suggested structure:

```text
Project
  |
  +-- Overview
  |
  +-- Repository
  |
  +-- Snapshots
  |
  +-- Security
        |
        +-- Assessment Summary
        |
        +-- Findings
        |
        +-- Scanner Coverage
        |
        +-- Assessment History
```

Each finding should display:

- Severity.
- Scanner.
- Rule identifier.
- File path.
- Line number.
- Explanation.
- Sanitized evidence.
- Assessment generation.

Allow filtering by:

- Severity.
- Scanner.
- Category.
- File path.

## 15.3 Snapshot-specific assessment

A security assessment must belong to an exact snapshot.

When users switch between snapshots, the security view must show the assessment associated with the selected snapshot.

Do not display the latest project's security report as if it belongs to an older snapshot.

## 15.4 UI states

Implement:

- Pending.
- Running.
- Completed.
- Review required.
- Partial.
- Failed.
- Cancelled.

The UI must distinguish an assessment with no detected issues from an assessment that could not be performed.

## 15.5 Future investigation integration

Later, Meridian's investigation page can display a compact security context:

- Existing findings.
- Relevant files.
- Security-related warnings.
- Findings potentially related to the reported bug.

The AI should receive only the sanitized findings necessary for its task.

It must not automatically treat every security finding as the cause of the user's reported bug.

---

# 16. Configuration and Deployment

## 16.1 Environment configuration

Add configuration for:

- Scanner enablement.
- Pinned Semgrep image.
- Pinned Gitleaks image.
- Scanner execution timeout.
- CPU limit.
- Memory limit.
- PID limit.
- Maximum output size.
- Maximum scanned file count.
- Maximum total scan bytes.
- Assessment retention.
- Ruleset version.

Avoid hardcoding deployment-specific credentials.

## 16.2 Docker Compose

The existing Compose file contains PostgreSQL, MinIO, API, and worker services.

Do not create a separate permanent service for each scanner.

Scanner containers should be created dynamically by the existing trusted worker orchestrator.

The worker should receive only the permissions required to manage its approved containers.

The scanner containers must never inherit the worker's environment variables.

## 16.3 Scanner image availability

Scanner images should be:

- Version-pinned.
- Verified during deployment.
- Stored in an approved registry or preloaded environment.
- Updated through controlled changes.
- Covered by image and dependency scanning.

The local development environment should support scanner availability checks.

A missing scanner image must result in an explicit unavailable or failed state, not a false clean report.

---

# 17. Testing and Verification Strategy

Security Preflight should be introduced with tests at every boundary.

## 17.1 Unit tests

### Semgrep wrapper

Test:

- Valid JSON.
- Invalid JSON.
- Empty output.
- Finding output.
- Timeout.
- Unsupported scanner version.
- Unexpected exit codes.
- Oversized output.

### Gitleaks wrapper

Test:

- Secret finding.
- No findings.
- Malformed output.
- Redaction.
- Timeout.
- Unexpected output.
- Scanner failure.

### Normalizer

Test:

- Severity mapping.
- Invalid paths.
- Absolute paths.
- Line-number validation.
- Missing fields.
- Duplicate fingerprints.
- Secret redaction.
- Truncated evidence.

### Risk policy

Test:

- No findings.
- Low findings.
- High findings.
- Critical findings.
- Partial scanner execution.
- Scanner failure.
- Unknown severity.

## 17.2 Integration tests

Test the complete flow:

1. Upload a valid repository.
2. Create a snapshot.
3. Verify stored artifacts.
4. Enqueue preflight.
5. Claim the job.
6. Run scanner containers.
7. Normalize findings.
8. Persist the assessment.
9. Retrieve the report through the API.
10. Verify the frontend displays the actual results.

## 17.3 Security tests

Create controlled test repositories containing:

- A known SQL injection pattern.
- An unsafe command invocation.
- A test API key.
- A test private-key fixture.
- A vulnerable dependency lockfile.
- A malicious repository Dockerfile.
- A malicious `.dockerignore`.
- Symlinks.
- Very large files.
- Deep directory structures.
- Unusual file names.

Use synthetic credentials only.

Verify that:

- Repository-controlled Dockerfiles are never executed.
- Scanner containers cannot access MinIO credentials.
- Scanner containers cannot access PostgreSQL.
- Network access is denied.
- Scanner processes cannot escape their workspace.
- Secret values are not persisted in reports or logs.
- Cancellation kills the scanner container.
- Worker crashes do not leave permanent containers.
- Cleanup failures are recorded.

## 17.4 Regression tests

All existing gates must remain green:

**API**

- Ruff.
- Mypy.
- Pytest.
- Alembic migration tests.

**Frontend**

- ESLint.
- Typecheck.
- Production build.
- Playwright E2E.

Do not merge the integration while existing ingestion, authentication, workspace isolation, or job recovery tests are failing.

---

# 18. Implementation Roadmap

The work should be delivered in controlled phases.

## Phase 0 — Architecture and security design

**Objective:** Finalize contracts before implementation.

Tasks:

- Review existing ingestion and snapshot storage.
- Review current worker and sandbox lifecycle.
- Define security scan artifact policy.
- Define assessment and finding schemas.
- Define scanner profiles.
- Define retention policy.
- Define severity mapping.
- Record decisions in `docs/DECISIONS.md`.

Deliverable:

Approved technical design and implementation checklist.

Acceptance criteria:

- No conflict with existing API contracts.
- No raw secret exposure.
- Scanner isolation boundaries documented.
- Snapshot identity preserved.

## Phase 1 — Security artifact support

**Objective:** Make complete source material available to security scanners without exposing secrets to AI indexing.

Tasks:

- Extend ingestion to build the additional security artifact.
- Include validated secret files in the security artifact.
- Continue excluding secret contents from the normal indexed snapshot.
- Preserve existing generated-directory exclusions.
- Add artifact metadata.
- Add storage and materialization methods.
- Implement artifact cleanup and reference counting.
- Add integrity tests.

Deliverable:

Verified security scan input associated with each ready snapshot.

Acceptance criteria:

- Secret files are available to Gitleaks.
- Secret files remain excluded from AI indexing.
- Artifact hashes are verified.
- Storage failures do not produce a ready artifact.
- Existing snapshot behavior remains unchanged.

## Phase 2 — Scanner framework

**Objective:** Implement scanner execution independently of the job pipeline.

Tasks:

- Create `services/worker/security/`.
- Define scanner interface.
- Implement Semgrep wrapper.
- Implement Gitleaks wrapper.
- Pin scanner images.
- Define fixed scanner profiles.
- Implement structured output collection.
- Add timeout and output limits.
- Add scanner unit tests.

Deliverable:

Individually testable Semgrep and Gitleaks integrations.

Acceptance criteria:

- Both scanners execute only approved commands.
- Results are structured.
- Failures are distinguishable from findings.
- Scanner versions are recorded.
- No repository-controlled command execution occurs.

## Phase 3 — Sandbox integration

**Objective:** Run scanners in restricted disposable containers.

Tasks:

- Integrate scanner profiles with the sandbox runtime.
- Reuse approved container controls.
- Implement scanner-specific source preparation.
- Ensure no credentials reach scanner containers.
- Implement cancellation.
- Implement guaranteed cleanup.
- Test malicious repository fixtures.
- Test container lifecycle failures.

Deliverable:

Secure scanner execution environment.

Acceptance criteria:

- Containers run non-root.
- Network access is denied.
- No host mounts or Docker socket are exposed.
- Resource limits are enforced.
- All normal and exceptional paths clean up correctly.

## Phase 4 — Job and database integration

**Objective:** Connect preflight to Meridian's durable workflow.

Tasks:

- Add migration `007_security_preflight.py`.
- Add security assessment model.
- Add security findings model.
- Extend job type constraints.
- Update schemas and job validation.
- Add internal job enqueueing.
- Register worker handler.
- Implement stage recording.
- Implement idempotency.
- Implement retry and partial execution handling.

Deliverable:

End-to-end asynchronous security assessment.

Acceptance criteria:

- Preflight starts only after snapshot readiness.
- Duplicate active jobs are prevented.
- Findings survive worker restarts.
- Partial execution is represented honestly.
- Existing job behavior remains unchanged.

## Phase 5 — API and frontend

**Objective:** Make security results accessible and understandable.

Tasks:

- Add assessment retrieval endpoints.
- Add paginated findings endpoint.
- Add project security overview.
- Add snapshot-specific security history.
- Add finding filters.
- Add scanner coverage display.
- Add assessment lifecycle states.
- Add role-based authorization tests.

Deliverable:

Usable Security Preflight experience within the existing Meridian interface.

Acceptance criteria:

- The frontend displays actual persisted results.
- Users cannot access another workspace's assessments.
- Old snapshots display their own reports.
- Failed and partial assessments are not presented as clean.

## Phase 6 — OSV-Scanner integration

**Objective:** Add dependency vulnerability coverage.

Tasks:

- Implement lockfile detection.
- Add OSV scanner profile.
- Add normalized dependency findings.
- Add package and version metadata.
- Add vulnerability identifiers and references.
- Add dependency-specific severity mapping.
- Test supported lockfile formats.

Deliverable:

Expanded preflight covering source-code patterns, secrets, and known dependency vulnerabilities.

Acceptance criteria:

- No unrestricted package installation is required.
- Unsupported dependency formats are reported.
- Vulnerability findings are linked to exact snapshots.
- Dependency scanning failures do not corrupt other scanner results.

## Phase 7 — Hardening and production readiness

**Objective:** Validate reliability and operational behavior.

Tasks:

- Add scanner concurrency quotas.
- Add workspace scan limits.
- Add cleanup reconciliation.
- Add assessment retention jobs.
- Add image update procedure.
- Add structured metrics.
- Add audit events for rescans.
- Add backup and deletion verification.
- Conduct a security review.

Deliverable:

Production-ready Security Preflight subsystem.

Acceptance criteria:

- No cross-workspace access.
- No secret leakage through scanner output.
- No unbounded scanner execution.
- No permanent orphaned execution resources.
- All security states are auditable.

---

# 19. Acceptance Criteria for the Complete Feature

The feature should be considered integrated only when the following are true.

### Ingestion

- [ ] Existing ZIP validation remains intact.
- [ ] Normal snapshot indexing remains unchanged.
- [ ] Security scan input is separately preserved.
- [ ] Secret files are scanned without being indexed for AI.
- [ ] Both artifacts have verified integrity.

### Scanners

- [ ] Semgrep runs successfully.
- [ ] Gitleaks runs successfully.
- [ ] Scanner images are pinned.
- [ ] Scanner results are structured.
- [ ] Secret values are redacted.
- [ ] Scanner failures are represented accurately.

### Worker

- [ ] Preflight uses the existing durable job system.
- [ ] Job idempotency works.
- [ ] Leases and heartbeats are respected.
- [ ] Cancellation works.
- [ ] Partial execution is supported.
- [ ] Temporary resources are cleaned.

### Database and API

- [ ] Migration is additive.
- [ ] Assessment and findings are persisted.
- [ ] Findings reference exact snapshots.
- [ ] Workspace authorization is enforced.
- [ ] Results are paginated.
- [ ] Raw scanner output is never exposed.

### Frontend

- [ ] Security overview is available.
- [ ] Findings are filterable.
- [ ] Snapshot-specific reports are displayed.
- [ ] Partial and failed assessments are distinguishable.
- [ ] No unsupported security score is displayed.

### Reliability

- [ ] Existing API tests pass.
- [ ] Existing frontend tests pass.
- [ ] New integration tests pass.
- [ ] Security fixtures pass.
- [ ] Migration upgrade and rollback behavior is verified.

---

# 20. Important Architectural Decisions

The following decisions should be treated as implementation constraints.

| Decision | Recommendation |
|---|---|
| Queue | Reuse PostgreSQL jobs |
| Worker | Reuse existing Python worker |
| Scanner isolation | Disposable restricted containers |
| Static scanner | Semgrep CE |
| Secret scanner | Gitleaks |
| Dependency scanner | OSV-Scanner later |
| Scanner configuration | Meridian-controlled |
| Repository execution | Never during preflight |
| Source identity | Immutable snapshot ID and digest |
| Secret handling | Separate security scan artifact |
| Report persistence | Dedicated assessments and findings |
| API | Existing FastAPI application |
| Frontend | Existing project experience |
| AI integration | Sanitized findings only |
| Automatic patching | Not part of preflight |
| Clean-scan interpretation | No detected findings under configured checks, not guaranteed safety |

## Explicit non-goals for V1

Do not attempt to implement:

- Full malware analysis.
- Behavioral malware detection.
- Dynamic penetration testing.
- Automatic exploitation.
- Automatic patch application.
- Automatic remote repository modification.
- Full compliance certification.
- Arbitrary dependency installation.
- AI-generated security verdicts.

These are separate capabilities and should not delay the initial preflight implementation.

---

# 21. Final Recommended Implementation Sequence

The order matters because some components depend on others.

```text
1. Finalize security artifact design
              |
              v
2. Implement dual-artifact ingestion
              |
              v
3. Implement verified security materialization
              |
              v
4. Implement Semgrep and Gitleaks wrappers
              |
              v
5. Integrate restricted scanner containers
              |
              v
6. Implement normalized findings
              |
              v
7. Add assessment database models and migration
              |
              v
8. Register security_preflight job
              |
              v
9. Trigger preflight after snapshot readiness
              |
              v
10. Add assessment APIs
              |
              v
11. Add project Security UI
              |
              v
12. Test failures, isolation and recovery
              |
              v
13. Introduce OSV-Scanner
```

**Do not start by modifying the frontend or adding the job type.** The most important dependency is first making the correct, verified source material available to the scanners.

---

# 22. Final Architectural Recommendation

Security Preflight should become the first structured analysis layer in Meridian's repository lifecycle.

It should establish a security baseline before deeper debugging and reliability investigation begins.

The intended long-term relationship is:

**Repository ingestion → Immutable snapshot → Security preflight → Investigation → Reproduction → Evidence → Hypotheses → Regression tests → Patch proposal → Human approval → Verification → Report.**

Security Preflight contributes an independently verified source of security evidence to this lifecycle.

Its value is not merely that Meridian can run two external scanning tools. Its value is that scanner findings become:

- Bound to an immutable repository snapshot.
- Persisted through a durable execution pipeline.
- Traceable to actual scanner results.
- Protected by the existing tenant and sandbox boundaries.
- Available to future investigations as structured evidence.

This allows Meridian to grow its debugging and reliability capabilities without compromising the architecture already established.

**The recommended V1 scope is deliberately focused: Semgrep CE + Gitleaks, a separate security scan artifact, restricted scanner containers, durable job integration, and a snapshot-specific findings report.**

Once that foundation is stable, dependency vulnerability analysis and deeper investigation integration can be added without redesigning the system.