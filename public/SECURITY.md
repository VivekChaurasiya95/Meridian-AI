# Meridian --- Security Design and Operations

**Document:** `SECURITY.md`\
**Product:** Meridian --- Clarity for complex engineering\
**Status:** Proposed MVP security baseline\
**Applies to:** Web application, API, model integration, repository
ingestion, execution workers, evidence storage, and operations\
**Last updated:** 2026-10-28

------------------------------------------------------------------------

## 1. Purpose

Meridian analyzes software repositories, bug reports, browser behavior,
logs, and test results, then proposes evidence-backed code changes. This
creates a distinctive security profile: the platform processes
potentially sensitive source code and also runs parts of that code to
reproduce bugs and verify patches.

This document defines the security requirements for the MVP. It is an
engineering baseline, not a claim of certification or a substitute for a
professional security review.

## 2. Security objectives

Meridian must:

1.  Protect source code, bug reports, logs, screenshots, traces,
    reports, and user identity data.
2.  Prevent one workspace from accessing another workspace's resources.
3.  Treat repositories, uploaded archives, issue text, browser pages,
    and tool output as untrusted input.
4.  Prevent untrusted code from accessing the API process, host system,
    credentials, or other tenants' work.
5.  Require explicit human approval before applying a proposed patch.
6.  Bind approval to the exact patch digest and base snapshot reviewed.
7.  Report only verification results supported by actual, persisted tool
    execution.
8.  Preserve a useful audit trail for security-sensitive actions.
9.  Minimize data retention and make deletion reliable.
10. Fail safely when the model provider, queue, runner, database, or
    object storage is unavailable.

### 2.1 Non-goals for the MVP

The MVP does not promise: - Safe execution of arbitrary repositories
without isolation. - Support for every language, framework, or build
system. - Automatic merging or publishing of patches to remote
branches. - A guarantee that every proposed patch is correct or
secure. - Formal security certification or compliance status. -
Protection against every possible malicious repository or dependency.

------------------------------------------------------------------------

## 3. Threat model

### 3.1 Assets

  -----------------------------------------------------------------------
  Asset                   Examples                Primary concern
  ----------------------- ----------------------- -----------------------
  Source code             Git repository, ZIP     Confidentiality,
                          archive, worktree       integrity

  Identity                Provider subject,       Account security
                          profile, sessions       

  Tenant data             Projects,               Cross-workspace
                          investigations, reports isolation

  Execution environment   Browser, test runner,   Escape and lateral
                          filesystem              movement

  Secrets                 Provider credentials,   Exfiltration
                          database credentials,   
                          API keys                

  Evidence                Screenshots, logs,      Confidentiality,
                          traces, source excerpts integrity

  Patch approval          User, diff digest, base Unauthorized or stale
                          snapshot                changes

  Verification record     Commands, exit codes,   Integrity and truthful
                          check statuses          reporting

  Audit trail             Approval, access,       Accountability
                          deletion, membership    
                          events                  

  Service availability    Queue, database, runner Abuse and denial of
                          capacity                service
  -----------------------------------------------------------------------

### 3.2 Trust boundaries

``` text
Untrusted browser/client
        |
        v
Public web application and API
        |
        +---- Identity provider (validated token)
        |
        +---- PostgreSQL (authorized data access)
        |
        +---- Private object storage (authorized signed URLs)
        |
        v
Durable queue / outbox
        |
        v
Isolated execution worker <---- untrusted repository / dependencies
        |
        +---- browser reproduction
        +---- test/build/lint/type-check commands
        +---- sanitized evidence output
        |
        v
Evidence validation + verification engine
        |
        v
Persisted outcomes and user-facing report
```

The model provider is a reasoning service, not a trusted execution
authority. Its output is untrusted until schema-validated and
policy-checked.

### 3.3 Adversaries and failure modes

Consider: - A malicious user attempting cross-tenant access. - A
compromised account approving or downloading resources. - A repository
containing prompt injection, malware, malicious scripts, or symlinks. -
A dependency installation script attempting to read secrets or reach
internal networks. - A malicious web page attempting to exploit the
browser runner. - A model response proposing dangerous commands or
misleading verification claims. - A stolen signed URL or leaked provider
credential. - A worker crash that leaves jobs or patch state
inconsistent. - A large archive, infinite loop, or repeated job requests
exhausting resources. - An insider or misconfigured service accessing
more data than required.

------------------------------------------------------------------------

## 4. Security architecture requirements

### 4.1 Separation of responsibilities

-   **API:** authenticate, authorize, validate input, persist records,
    enqueue work. It must not execute repository commands.
-   **Orchestrator:** manage state transitions and schedule allowlisted
    operations.
-   **Model adapter:** send only necessary, authorized context to the
    model provider; parse structured outputs.
-   **Policy layer:** validate tool name, argument schema, file paths,
    limits, and permissions.
-   **Execution runner:** run repository code in an isolated, disposable
    environment.
-   **Evidence processor:** limit output, redact sensitive data,
    validate artifact type, and create private object references.
-   **Verification engine:** derive statuses from actual runner results,
    not model statements.
-   **Report generator:** use persisted facts and explicitly labeled
    hypotheses.

Use separate service identities and least-privilege permissions. A model
output must never directly invoke shell commands, change authorization,
approve a patch, or set verification status.

### 4.2 Environment separation

At minimum, separate development, test, and production: - Separate
databases and object-storage buckets. - Separate model/API
credentials. - Separate identity-provider configuration where
feasible. - No production source data in local development fixtures. -
Restricted production access and audited administrative actions. -
Separate worker pools for untrusted repository execution.

------------------------------------------------------------------------

## 5. Authentication and session security

### 5.1 Identity validation

If Firebase Authentication or another identity provider is used: -
Validate token signature using the provider's supported verification
library. - Validate issuer, audience, expiry, and expected token type. -
Validate revocation/session policy where required. - Resolve the stable
provider subject to the internal `users.id`. - Never accept a
client-provided `user_id`, email, or role as proof of identity. - Never
log bearer tokens or refresh tokens.

Do not implement custom password handling if an identity provider
already owns authentication.

### 5.2 Authorization

Every request involving a workspace, project, investigation, patch,
report, evidence item, or audit event must perform server-side
authorization.

-   Check workspace membership and role.
-   Confirm resource relationships are consistent (for example, an
    evidence item belongs to the investigation and project claimed in
    the URL).
-   Use scoped database queries; do not fetch arbitrary UUIDs and trust
    the client.
-   Enforce permissions for every object-storage download URL.
-   Repeat authorization checks for background jobs and sensitive state
    transitions.
-   Avoid leaking private-resource existence; use `404` where
    appropriate.
-   Treat frontend route guards as UX only, never as the security
    boundary.

### 5.3 Role and privilege management

-   Enforce owner/admin/developer/viewer permissions on the server.
-   Prevent removing or demoting the last workspace owner.
-   Require re-checking role and membership at patch approval time.
-   Audit membership changes and sensitive administrative actions.
-   Keep worker/service identities separate from user identities.

------------------------------------------------------------------------

## 6. Repository and archive ingestion

Uploaded code must be treated as hostile until inspected.

### 6.1 Archive validation

Before extracting an archive: - Enforce maximum compressed size,
expanded size, file count, nesting depth, and compression ratio. -
Reject absolute paths, `..` traversal, invalid path encodings, and paths
that escape the extraction root. - Reject or safely handle symlinks and
hard links; do not allow links to escape the root. - Reject device
files, sockets, and unsupported entry types. - Defend against ZIP bombs
and recursive archives. - Normalize paths and check for duplicate paths
after normalization. - Do not trust filename extensions or
client-provided MIME types. - Verify the digest against the actual
uploaded bytes. - Extract into a new, isolated temporary directory with
restrictive permissions. - Do not execute scripts or package lifecycle
hooks during upload validation. - Exclude known secret/config files from
indexing by default, including `.env`, private keys, credential files,
and local secret stores.

### 6.2 Repository inspection

-   Pin the exact commit/tree snapshot used by an investigation.
-   Avoid following symlinks outside the repository root.
-   Apply file-size and total-indexing limits.
-   Skip binary, generated, dependency, and vendor directories by
    default.
-   Detect and redact likely secrets before sending code context to
    external services.
-   Avoid collecting source files unrelated to the investigation when a
    smaller context is sufficient.
-   Record snapshot digests so evidence and patches can be tied to a
    stable source version.

### 6.3 Git provider connections

-   Prefer provider installations or narrowly scoped, short-lived
    credentials.
-   Grant read-only repository access for the MVP where possible.
-   Never store credentials in repository URLs or ordinary project JSON.
-   Do not accept arbitrary Git URLs without SSRF and destination
    validation.
-   Block access to loopback, private, link-local, metadata-service, and
    otherwise prohibited IP ranges unless explicitly required by a
    controlled internal service.
-   Revalidate DNS and resolved IPs at connection time to reduce
    DNS-rebinding risk.
-   Do not follow redirects to disallowed destinations.
-   Do not automatically push or merge patches in the MVP.

------------------------------------------------------------------------

## 7. Secure execution environment

This is the highest-risk subsystem in Meridian.

### 7.1 Isolation baseline

Run every repository inspection that executes code, browser
reproduction, dependency installation, test, build, lint, or type-check
in a disposable isolated worker.

Required controls: - No privileged containers. - Never mount the host
Docker socket. - Do not run repository processes as root. - Use a
read-only base filesystem where practical and a bounded writable
workspace. - Drop Linux capabilities and enable seccomp/AppArmor or
equivalent controls where available. - Set CPU, memory, process-count,
file-size, disk, and wall-clock limits. - Apply per-job and
per-workspace concurrency quotas. - Terminate child processes and clean
temporary storage on timeout/cancellation. - Do not place API, database,
model-provider, or object-storage credentials in the repository process
environment. - Keep worker control-plane credentials out of the
untrusted process namespace. - Use separate short-lived workload
identity for worker-to-service communication. - Restrict outbound
network by default; enable only explicitly required destinations through
a controlled proxy. - Prevent access to cloud instance metadata
endpoints and internal control-plane services. - Keep the host kernel
and container runtime patched.

Containers are a useful isolation layer but are not automatically a
complete security boundary. For higher-risk workloads, evaluate stronger
sandboxing or microVM-based execution.

### 7.2 Command policy

The model may request a supported tool action, but the policy layer
must: 1. Validate the tool name against an allowlist. 2. Validate all
arguments against a strict schema. 3. Resolve file paths and ensure they
remain within the workspace. 4. Apply timeout and resource limits. 5.
Build the process argument vector without shell interpolation. 6. Filter
environment variables. 7. Apply network policy. 8. Bound stdout/stderr
size. 9. Persist a sanitized result. 10. Return only the minimum result
needed for the next step.

Do not use `shell=True` with model-controlled strings. Do not expose an
arbitrary command-execution endpoint to the browser or model.

### 7.3 Dependency installation

Package managers and install scripts execute untrusted code. For the
MVP: - Support only selected package managers and known runtime
profiles. - Pin runner images and runtime versions. - Apply strict
network and time limits. - Do not expose credentials or host mounts
during install. - Prefer cached, vetted dependencies where feasible. -
Record package-manager output and lockfile identity. - Mark the run
blocked/inconclusive if the dependency setup cannot be completed
safely. - Do not claim a verification result when required dependencies
could not be installed.

### 7.4 Browser reproduction

-   Use a fresh browser context per investigation.
-   Do not reuse user cookies or authenticated personal browser
    sessions.
-   Run the browser inside the same or a stricter sandbox boundary.
-   Block internal IPs, loopback, metadata endpoints, and control-plane
    routes.
-   Restrict downloads and file access.
-   Limit pages, navigation time, request count, and total runtime.
-   Treat DOM text, page content, console messages, and network
    responses as untrusted data.
-   Capture only necessary screenshots/traces and redact sensitive
    content.
-   Do not let page content issue tools or override the system's policy.

### 7.5 Network egress

Default-deny is preferred. If outbound network is necessary for package
installation or reproduction: - Use a controlled egress proxy or network
policy. - Allowlist domains and ports where feasible. - Resolve and
validate destination IPs. - Block private, loopback, link-local,
multicast, and metadata ranges. - Re-check redirects and DNS results. -
Prevent DNS rebinding and proxy bypass. - Log destination metadata
without collecting unnecessary payloads. - Never assume a hostname is
safe based only on its textual name.

------------------------------------------------------------------------

## 8. Model integration and prompt-injection defense

### 8.1 Treat model output as untrusted

Model output may be incomplete, malformed, misleading, or manipulated by
repository content. For every response: - Validate structured output
against a strict schema. - Reject unknown tool names and unexpected
fields. - Enforce argument limits and path restrictions. - Apply
authorization and policy checks independently of the model. - Require
deterministic tool output before asserting a fact. - Handle refusal,
malformed output, timeout, and provider outage safely. - Limit retries
and total token/cost budget. - Keep model credentials in the trusted
backend only.

### 8.2 Prompt injection

Bug reports, source comments, README files, web pages, issue
descriptions, and logs can contain instructions such as "ignore previous
rules" or requests to reveal secrets. Treat all such content as
**data**, not authority.

Controls: - Clearly separate system policy from repository content in
prompts. - Label retrieved source and browser text as untrusted
evidence. - Do not put secrets in the model context. - Do not allow
repository text to change tool permissions, safety policy, or approval
rules. - Validate every proposed action outside the model. - Use
least-context retrieval and redact secrets. - Keep the user-visible
rationale tied to evidence and tool results.

Prompt wording alone is not a security boundary. The policy layer and
execution isolation must enforce safety.

### 8.3 Truthful verification

-   The model cannot set a verification run or check to `passed`.
-   A trusted verification service records actual exit codes,
    timestamps, durations, and outcomes.
-   A run with no executed required checks cannot pass.
-   `failed`, `blocked`, `timed_out`, `cancelled`, `skipped`, and
    `inconclusive` must remain distinct.
-   Reports must distinguish observed facts from model hypotheses.
-   A successful build alone does not prove the reported bug is fixed.
-   Do not silently omit failing checks from summaries.

------------------------------------------------------------------------

## 9. Patch approval and change integrity

### 9.1 Patch lifecycle

Recommended lifecycle:

``` text
PROPOSED
  -> AWAITING_APPROVAL
  -> APPROVED
  -> APPLIED_IN_ISOLATED_WORKSPACE
  -> POST_PATCH_VERIFICATION
  -> VERIFICATION_PASSED | VERIFICATION_FAILED
```

A patch may also be rejected, discarded, stale, or failed. Do not merge
these states into a generic success/failure indicator.

### 9.2 Approval binding

Approval must bind to: - Exact `diff_sha256`. - Exact `base_snapshot_id`
/ commit/tree digest. - Approving user ID and role. - Approval
timestamp. - Optional review note.

At approval time: 1. Re-authorize the user. 2. Lock the patch record. 3.
Confirm the patch is still awaiting approval. 4. Compare the submitted
diff digest and base snapshot with the current stored values. 5. Confirm
the base is still valid under project policy. 6. Persist the decision
and audit event in one transaction. 7. Queue application only after
commit.

If the diff or base changes, invalidate approval. Require a fresh
review.

### 9.3 Safe application

-   Apply changes only in a disposable worktree/sandbox.
-   Validate all paths and reject path traversal.
-   Do not automatically push, merge, or deploy in the MVP.
-   Preserve the original snapshot and patch diff.
-   Re-run the configured checks after application.
-   If application partially fails, record the failure and clean the
    workspace.
-   Provide a downloadable diff only after authorization and appropriate
    redaction.

### 9.4 Approval UI

The UI should show changed files, diff, base snapshot, digest/version,
rationale, and available verification results before approval. The
approval button must not be enabled if the diff is stale or the current
user lacks permission.

------------------------------------------------------------------------

## 10. API, frontend, and browser security

### 10.1 API security

-   Enforce HTTPS in production.
-   Validate input with typed schemas and reject unexpected fields.
-   Set request-body, upload, and response-size limits.
-   Use parameterized database queries/ORM bindings.
-   Rate-limit resource creation, uploads, downloads, and costly
    operations.
-   Use idempotency keys for retryable creation requests.
-   Return generic external errors and log sanitized internal
    diagnostics.
-   Set secure CORS origins explicitly; do not use wildcard origins with
    credentials.
-   Use security headers appropriate to the deployment, including a
    considered Content Security Policy.
-   Validate redirect targets and avoid open redirects.
-   Keep framework and dependency versions patched.
-   Separate public API routes from internal worker/control-plane
    endpoints.

### 10.2 Browser/frontend security

-   Render repository content, logs, diffs, and model output as text,
    never trusted HTML.
-   Avoid unsafe HTML injection APIs. If rich rendering is required,
    sanitize with a maintained allowlist sanitizer.
-   Keep API secrets out of browser bundles.
-   Store auth tokens according to the identity provider's recommended
    secure flow.
-   Avoid long-lived tokens in local storage where a safer supported
    approach exists.
-   Use a restrictive Content Security Policy compatible with required
    functionality.
-   Prevent clickjacking with appropriate frame-ancestors policy.
-   Avoid leaking source code or signed URLs through analytics, error
    reporting, or client logs.
-   Ensure external links use safe target/rel behavior.
-   Apply CSRF protections if cookie-based authentication is used.

### 10.3 CORS and CSRF

-   Allow only configured production frontend origins.
-   Do not reflect arbitrary `Origin` values.
-   Do not combine wildcard CORS with credentials.
-   If authentication uses cookies, use `Secure`, `HttpOnly`, and
    appropriate `SameSite` attributes, plus CSRF tokens or another
    robust defense for state-changing requests.
-   If using bearer tokens in the Authorization header, still protect
    against token theft, XSS, and unsafe token storage.

------------------------------------------------------------------------

## 11. Secrets and configuration

### 11.1 Secret handling

Store secrets in a managed secrets store or deployment secret manager: -
Database credentials. - Model-provider API keys. - Identity-provider
service credentials. - Git provider installation credentials. -
Object-storage credentials. - Signing keys and internal service
credentials.

Never commit secrets to Git, put them in repository URLs, embed them in
frontend environment variables, or include them in model prompts.

### 11.2 Environment files

-   Commit only `.env.example` with placeholder values.
-   Add `.env`, private keys, credentials, local dumps, and real logs to
    `.gitignore`.
-   Restrict local file permissions for secrets.
-   Rotate any credential that may have been exposed.
-   Use different credentials for local development, CI, staging, and
    production.
-   Do not pass the complete backend environment to repository
    subprocesses.

### 11.3 Rotation and access

-   Restrict secret read access to the services that need each secret.
-   Rotate credentials on suspected exposure and at policy-defined
    intervals.
-   Prefer short-lived workload identity over static credentials.
-   Audit secret-management access where available.
-   Never write secret values into audit metadata.

------------------------------------------------------------------------

## 12. Evidence, object storage, and privacy

### 12.1 Artifact protection

Evidence may contain proprietary source, user data, session identifiers,
or secrets.

-   Store artifacts in private buckets/containers.
-   Use opaque, unguessable object keys.
-   Authorize every access before issuing a signed URL.
-   Use short URL expiry, such as a few minutes, appropriate to the
    operation.
-   Do not log signed URLs.
-   Enforce size, type, and retention limits.
-   Verify actual MIME type and digest server-side.
-   Encrypt in transit and at rest.
-   Redact before display or sharing.
-   Keep storage access separate from end-user database permissions.

### 12.2 Redaction

Redact likely: - API keys and bearer tokens. - Passwords, session
cookies, and authorization headers. - Private keys and connection
strings. - `.env` values. - Personal data not needed for debugging. -
Sensitive query parameters and request bodies.

Redaction can produce false positives and false negatives. Preserve a
secure original only if policy requires it; default to minimizing
retained raw content. If required redaction fails, do not expose the
artifact.

### 12.3 Data minimization and retention

Suggested initial retention policy, subject to user-facing policy and
operational needs: - Temporary execution workspace: remove promptly
after job completion or expiry. - Raw logs/traces: retain for a short
configurable window, e.g. 14--30 days. - Reports and investigation
metadata: retain according to workspace/user policy. - Upload staging
objects: delete after successful processing or expiry. - Idempotency
records: expire after the supported retry window. - Audit records:
retain for a documented operational/security period with restricted
access.

Deletion must cover relational metadata, object-storage bytes, temporary
workspaces, caches, and queued work. Use idempotent asynchronous
deletion jobs and retry failures. Do not promise complete deletion until
all relevant stores have been processed.

------------------------------------------------------------------------

## 13. Database security and integrity

-   Use TLS for database connections in production.
-   Use a dedicated application database role with minimum required
    privileges.
-   Do not use a superuser account from the application.
-   Separate migration credentials from runtime credentials.
-   Use parameterized queries.
-   Keep backups encrypted and access-controlled.
-   Test restore procedures.
-   Enforce workspace authorization in service code; consider PostgreSQL
    RLS as defense in depth.
-   Never trust a client-supplied workspace ID without verifying
    membership.
-   Make audit events append-only to application roles.
-   Use migrations for schema changes; do not mutate production schema
    automatically at application startup.
-   Avoid storing raw source code or large binary artifacts in JSONB
    fields.

### 13.1 Cross-tenant consistency

Foreign keys alone may not ensure that a patch, evidence item, project,
and investigation belong to the same tenant. Enforce these invariants in
service-layer transactions and, where appropriate, composite foreign
keys. Add automated tests for cross-workspace ID substitution.

------------------------------------------------------------------------

## 14. Logging, monitoring, and incident response

### 14.1 Safe logging

Log: - Request/correlation ID. - Route, status code, and latency. -
Job/stage/tool IDs and terminal outcomes. - Resource-limit events and
timeout reasons. - Model-provider latency/error category. -
Authorization failures and sensitive actions. - Artifact
validation/redaction outcomes. - Verification check outcomes.

Do not log by default: - Access/refresh tokens or cookies. - Secret
environment variables. - Signed URLs. - Full request bodies. - Raw
source code or unredacted tool output. - Full prompts containing
proprietary source. - Database connection strings.

### 14.2 Monitoring and alerts

Alert on: - Repeated authorization failures or suspicious resource
enumeration. - Unusual archive sizes, extraction failures, or repeated
timeouts. - Worker sandbox failures or unexpected network attempts. -
Egress-policy denials and attempted metadata access. - Secret-scanner
detections. - Repeated model tool-policy rejections. - Abnormal artifact
download volume. - Queue backlogs and stuck running jobs. - Unexpected
verification-state transitions. - Deletion jobs that repeatedly fail.

### 14.3 Incident response checklist

If a credential, source artifact, or tenant boundary may have been
compromised:

1.  Contain the affected service, worker pool, credential, or access
    path.
2.  Revoke/rotate potentially exposed credentials.
3.  Preserve relevant audit records and sanitized logs.
4.  Determine affected workspaces, projects, artifacts, and time window.
5.  Stop or isolate suspicious jobs and remove their network access.
6.  Remove exposed artifacts and invalidate signed URLs where possible.
7.  Restore from known-good images/configuration if required.
8.  Notify affected users and stakeholders according to applicable
    obligations.
9.  Document root cause, impact, remediation, and follow-up controls.
10. Add regression tests to prevent recurrence.

This checklist is an operational starting point. Assign incident owners
and communication responsibilities before production launch.

------------------------------------------------------------------------

## 15. Dependency and supply-chain security

-   Pin application and runner dependencies where practical.
-   Commit lockfiles.
-   Scan dependencies and container images in CI.
-   Use trusted base images and rebuild them regularly.
-   Avoid running CI with production credentials.
-   Restrict GitHub Actions or other CI permissions to the minimum
    required.
-   Pin third-party CI actions by immutable commit where feasible.
-   Review new packages and their install scripts.
-   Produce an SBOM when the release process supports it.
-   Track and patch critical vulnerabilities.
-   Separate dependencies used by the trusted control plane from
    dependencies installed for untrusted repositories.

------------------------------------------------------------------------

## 16. Secure development checklist

### Before every release

-   [ ] No secrets or production data committed.
-   [ ] Authentication token validation is tested.
-   [ ] Authorization is checked server-side for every resource.
-   [ ] Cross-tenant access tests pass.
-   [ ] Request schemas reject unexpected fields.
-   [ ] Rate limits and upload limits are enabled.
-   [ ] Archive path traversal and compression-bomb tests pass.
-   [ ] Runner has no privileged mode or host Docker socket.
-   [ ] Repository subprocesses receive no service/API secrets.
-   [ ] Egress policy blocks metadata and private internal networks by
    default.
-   [ ] Model-proposed tools are schema-validated and allowlisted.
-   [ ] Patch approval binds to exact diff digest and base snapshot.
-   [ ] Verification status is computed from actual runner results.
-   [ ] Artifact access requires authorization and short-lived URLs.
-   [ ] Redaction failures prevent exposure where redaction is required.
-   [ ] Logs are scrubbed of credentials and sensitive payloads.
-   [ ] Retention and deletion jobs are tested.
-   [ ] Dependencies and runner images are scanned.
-   [ ] Database migrations and backup restoration are tested.
-   [ ] Security-sensitive events are auditable.

### Before public beta

-   Conduct a threat-model review with the actual deployment topology.
-   Test the runner isolation and network boundary explicitly.
-   Perform a focused application security review and penetration test.
-   Verify recovery from worker crashes and queue/database failures.
-   Review privacy disclosures and retention/deletion behavior.
-   Establish vulnerability reporting and incident response contacts.
-   Confirm the product's claims match the security controls actually
    deployed.

------------------------------------------------------------------------

## 17. Vulnerability reporting

Before public launch, publish a security contact and a responsible
disclosure process. Do not invent a contact address in the application
documentation until one is configured and monitored.

A public disclosure process should specify: - What systems are in
scope. - How to report a vulnerability securely. - Expected
acknowledgement and response timelines. - Rules for testing without
accessing other users' data or disrupting service. - How findings will
be coordinated and disclosed.

Do not promise a bug bounty unless one exists and is funded.

------------------------------------------------------------------------

## 18. Security acceptance criteria

Meridian's MVP should not be considered ready for untrusted public
repositories until:

1.  All repository code execution occurs outside the API process in
    disposable isolation.
2.  Runner limits, cancellation, cleanup, and network egress controls
    are verified by tests.
3.  No backend/model/object-storage secrets are exposed to repository
    processes.
4.  Workspace authorization covers every API resource and artifact
    download.
5.  Upload validation blocks traversal, unsafe links, and decompression
    abuse.
6.  Model output cannot bypass the tool policy, approval gate, or
    verification engine.
7.  Patch approvals are bound to immutable diff/base identifiers.
8.  Verification outcomes reflect actual executed checks and preserve
    uncertainty.
9.  Logs and artifacts have documented redaction, access, and retention
    behavior.
10. Cross-tenant and abuse cases are covered by automated tests.
11. Dependency scanning, incident handling, backups, and deletion
    workflows are documented and exercised.
12. Security review findings are triaged before the product is exposed
    to arbitrary user repositories.

------------------------------------------------------------------------

## 19. Security decision log

Record important security decisions here as the implementation evolves.

  -----------------------------------------------------------------------
  Decision                Recommended MVP choice  Revisit when
  ----------------------- ----------------------- -----------------------
  Repository execution    Disposable isolated     Workload risk or scale
                          worker                  changes

  Network egress          Deny by default;        Supported package
                          explicit                ecosystems require more
                          allowlist/proxy         access

  Patch publication       No automatic remote     A separately authorized
                          push/merge              publishing workflow is
                                                  designed

  Artifact access         Private storage +       Storage architecture
                          short-lived signed URLs changes

  Tenant isolation        Server-side             Before multi-tenant
                          authorization; evaluate production launch
                          RLS                     

  Secrets                 Managed secret          Deployment platform is
                          store/workload identity selected

  Live progress           Polling backed by       Real-time UX becomes
                          durable state           necessary

  Raw artifact retention  Short configurable      User needs and legal
                          window                  review are known
  -----------------------------------------------------------------------

------------------------------------------------------------------------

**End of document.**
