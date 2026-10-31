# Meridian --- API Specification

**Document:** `API.md`\
**Product:** Meridian --- Clarity for complex engineering\
**Status:** Proposed MVP API contract\
**API style:** REST over HTTPS, JSON, asynchronous investigation jobs\
**Backend:** Python / FastAPI\
**Database:** PostgreSQL\
**Last updated:** 2026-10-28

------------------------------------------------------------------------

## 1. Purpose and scope

This document defines the HTTP API between the Meridian web client and
backend services. It aligns with `Meridian_PRD.md`, `ARCHITECTURE.md`,
and `DATABASE.md`.

The API supports:

-   Authentication and current-user context.
-   Workspace and project management.
-   Repository onboarding and source snapshot creation.
-   Investigation creation, monitoring, cancellation, and timeline
    retrieval.
-   Evidence listing and authorized downloads.
-   Hypothesis review.
-   Regression-test and patch proposal workflows.
-   Explicit patch approval or rejection.
-   Baseline and post-patch verification results.
-   Reports, activity history, and operational health.

The MVP is intentionally scoped to supported web repositories and
controlled investigation flows. The API must not imply that every
repository or bug can be automatically debugged.

### 1.1 Contract principles

1.  **Evidence over claims:** model output is advisory. Deterministic
    tools and persisted runner results establish what actually happened.
2.  **Async by default:** investigation creation returns quickly with a
    resource ID; long-running work runs in background workers.
3.  **Human approval:** a patch must not be applied before an authorized
    approval of that exact diff.
4.  **Truthful verification:** do not report `passed` unless required
    checks really ran and met the configured criteria.
5.  **Tenant isolation:** every resource request is authorized through
    workspace membership and resource ownership relationships.
6.  **Validated tool execution:** model-proposed tool arguments are
    validated against schemas and allowlists; the model cannot execute
    arbitrary commands.
7.  **Versioned contract:** breaking changes require an API version
    change or a documented compatibility plan.
8.  **No secrets in logs:** redact credentials, cookies, tokens,
    environment variables, and sensitive source data from API logs and
    error responses.

------------------------------------------------------------------------

## 2. Base URL, versioning, and content types

### 2.1 Base URL

Local development:

``` text
http://localhost:8000/api/v1
```

Production:

``` text
https://<configured-api-host>/api/v1
```

Do not hard-code production hosts into the frontend. Configure them
through a public API base URL environment variable.

### 2.2 Versioning

All public endpoints live under `/api/v1`. Additive fields and new
endpoints may be introduced without a version bump. Removing fields,
changing meanings, or changing response semantics requires a
compatibility plan and likely `/api/v2`.

### 2.3 Content types

-   Requests and responses: `application/json`.
-   File upload: `multipart/form-data` for small, direct uploads or a
    signed-upload flow for larger files.
-   File downloads: binary responses or short-lived signed URLs issued
    after authorization.
-   All requests should use UTF-8.
-   The API must enforce body-size and upload-size limits.

### 2.4 Common headers

  ----------------------------------------------------------------------------
  Header                                   Purpose
  ---------------------------------------- -----------------------------------
  `Authorization: Bearer <token>`          Identity-provider access token or
                                           ID token, validated by the backend

  `Content-Type: application/json`         JSON requests

  `Accept: application/json`               JSON responses

  `Idempotency-Key: <opaque-random-key>`   Deduplicates supported
                                           resource-creating/mutating requests

  `X-Request-ID: <opaque-id>`              Optional caller correlation ID;
                                           server validates or replaces it

  `If-Match: "<etag>"`                     Optional optimistic concurrency
                                           control for mutable resources
  ----------------------------------------------------------------------------

The backend must validate token signature, issuer, audience, expiry, and
relevant claims. Never trust user IDs, roles, or workspace permissions
supplied in request bodies.

------------------------------------------------------------------------

## 3. Authentication and authorization

### 3.1 Authentication

The frontend obtains an identity token from the configured
authentication provider. It sends the token as a bearer token to the
API. The backend validates the token on every request and resolves it to
the internal `users.id`.

The `users` table stores the provider and stable provider subject; it
does not store authentication tokens or passwords.

### 3.2 Authorization

Every protected endpoint requires:

1.  A valid authenticated principal.
2.  Workspace membership or an explicit resource-level permission.
3.  Validation that the resource belongs to the authorized workspace.
4.  A role check for sensitive operations.

Suggested role policy:

  ---------------------------------------------------------------------------------------------
  Action                                     Owner          Admin      Developer         Viewer
  --------------------------------- -------------- -------------- -------------- --------------
  Read                                         Yes            Yes            Yes            Yes
  workspace/project/investigation                                                

  Create project/investigation                 Yes            Yes            Yes             No

  Update project configuration                 Yes            Yes        Limited             No

  Upload or manage project source              Yes            Yes        Yes, if             No
                                                                         enabled 

  Approve/reject patch                         Yes            Yes   Yes, subject             No
                                                                       to policy 

  Manage workspace membership                  Yes   Yes, subject             No             No
                                                     to ownership                
                                                            rules                

  Delete workspace                             Yes             No             No             No
  ---------------------------------------------------------------------------------------------

Implement a centralized authorization dependency/service. Do not
duplicate incomplete permission checks across route handlers.

### 3.3 Resource authorization

Use workspace-scoped queries. A UUID is an identifier, not proof of
permission. Return `404 Not Found` for inaccessible resources where
appropriate to avoid leaking resource existence; use `403 Forbidden`
when the caller is authenticated, the resource is visible, and a
specific action is disallowed.

### 3.4 Service-to-service authentication

Workers and internal services must use separate service identities or
workload credentials. Do not accept public requests that claim to be
from a trusted runner merely because they contain a `service=true`
field.

------------------------------------------------------------------------

## 4. Common response format

### 4.1 Success

Return the resource directly for simple reads and a resource envelope
for long-running jobs or collections. Keep one convention consistent
across all endpoints.

Example:

``` json
{
  "data": {
    "id": "a4e7f6df-72f1-4e1b-aed7-57c35f2d1b90",
    "title": "Login form fails after refresh",
    "status": "queued",
    "created_at": "2026-10-28T08:30:00Z"
  },
  "request_id": "req_01J..."
}
```

### 4.2 Error

Use a consistent problem envelope:

``` json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The request contains invalid fields.",
    "details": [
      {
        "field": "title",
        "issue": "Field must not be empty."
      }
    ]
  },
  "request_id": "req_01J..."
}
```

Do not return raw Python exceptions, SQL messages, stack traces,
internal prompts, secrets, filesystem paths, or unredacted tool output.

### 4.3 Pagination

Use cursor pagination for timeline/evidence/event collections that may
grow large. A simple first implementation may use `limit` and an opaque
`cursor` based on `(created_at, id)`.

Query parameters:

-   `limit`: integer, default `25`, maximum `100`.
-   `cursor`: opaque, URL-safe continuation token.
-   `sort`: endpoint-specific allowlisted sort key; never pass arbitrary
    user strings into SQL `ORDER BY`.

Example response:

``` json
{
  "data": [],
  "page": {
    "limit": 25,
    "next_cursor": null
  },
  "request_id": "req_01J..."
}
```

Use stable ordering such as `created_at DESC, id DESC` and cursor on
both values to avoid duplicate/missing rows when timestamps match.

### 4.4 HTTP status codes

  -----------------------------------------------------------------------
  Status                              Use
  ----------------------------------- -----------------------------------
  `200 OK`                            Successful read/update/action

  `201 Created`                       Resource created

  `202 Accepted`                      Async operation queued

  `204 No Content`                    Successful deletion with no body

  `400 Bad Request`                   Malformed request or invalid state
                                      transition

  `401 Unauthorized`                  Missing/invalid authentication

  `403 Forbidden`                     Authenticated caller lacks
                                      permission

  `404 Not Found`                     Resource absent or intentionally
                                      hidden

  `409 Conflict`                      State conflict, stale patch,
                                      idempotency-key mismatch

  `413 Content Too Large`             Upload/request exceeds configured
                                      limit

  `415 Unsupported Media Type`        Unsupported upload content type

  `422 Unprocessable Content`         Schema/field validation error

  `429 Too Many Requests`             Rate limit exceeded

  `500 Internal Server Error`         Unexpected server error

  `502 Bad Gateway`                   Upstream provider failure

  `503 Service Unavailable`           Temporary service/worker capacity
                                      issue

  `504 Gateway Timeout`               Synchronous upstream timeout
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 5. API resource map

Base prefix: `/api/v1`

  --------------------------------------------------------------------------------------------------
  Area                                Endpoints
  ----------------------------------- --------------------------------------------------------------
  System                              `GET /health/live`, `GET /health/ready`

  User                                `GET /me`, `PATCH /me`

  Workspaces                          `GET /workspaces`, `POST /workspaces`,
                                      `GET /workspaces/{workspace_id}`,
                                      `PATCH /workspaces/{workspace_id}`

  Membership                          `GET /workspaces/{workspace_id}/members`,
                                      `POST /workspaces/{workspace_id}/members`,
                                      `PATCH /workspaces/{workspace_id}/members/{user_id}`,
                                      `DELETE /workspaces/{workspace_id}/members/{user_id}`

  Projects                            `GET /workspaces/{workspace_id}/projects`,
                                      `POST /workspaces/{workspace_id}/projects`,
                                      `GET /projects/{project_id}`, `PATCH /projects/{project_id}`,
                                      `POST /projects/{project_id}/archive`

  Source                              `POST /projects/{project_id}/source-uploads`,
                                      `POST /projects/{project_id}/source-uploads/complete`,
                                      `POST /projects/{project_id}/snapshots`,
                                      `GET /projects/{project_id}/snapshots`

  Investigations                      `GET /projects/{project_id}/investigations`,
                                      `POST /projects/{project_id}/investigations`,
                                      `GET /investigations/{investigation_id}`,
                                      `POST /investigations/{investigation_id}/cancel`,
                                      `POST /investigations/{investigation_id}/retry`

  Stages                              `GET /investigations/{investigation_id}/stages`

  Activity                            `GET /investigations/{investigation_id}/activity`

  Evidence                            `GET /investigations/{investigation_id}/evidence`,
                                      `GET /evidence/{evidence_id}`,
                                      `POST /evidence/{evidence_id}/download-url`

  Hypotheses                          `GET /investigations/{investigation_id}/hypotheses`,
                                      `PATCH /hypotheses/{hypothesis_id}`

  Regression tests                    `GET /investigations/{investigation_id}/regression-tests`,
                                      `POST /investigations/{investigation_id}/regression-tests`,
                                      `GET /regression-tests/{test_id}`

  Patches                             `GET /investigations/{investigation_id}/patches`,
                                      `GET /patches/{patch_id}`, `POST /patches/{patch_id}/approve`,
                                      `POST /patches/{patch_id}/reject`,
                                      `POST /patches/{patch_id}/discard`,
                                      `GET /patches/{patch_id}/diff`

  Verification                        `GET /investigations/{investigation_id}/verification-runs`,
                                      `GET /verification-runs/{run_id}`

  Reports                             `POST /investigations/{investigation_id}/reports`,
                                      `GET /investigations/{investigation_id}/reports/{report_id}`

  Audit                               `GET /workspaces/{workspace_id}/audit-events` (owner/admin
                                      only)
  --------------------------------------------------------------------------------------------------

This is the public MVP contract. Internal runner callbacks should use a
separate private route group or authenticated queue messages, not be
exposed as ordinary user endpoints.

------------------------------------------------------------------------

## 6. Endpoint contracts

For brevity, common authentication, workspace authorization, request ID,
and error-envelope requirements apply to every endpoint unless
explicitly stated otherwise. UUIDs below are examples; use valid UUIDs
in actual requests.

### 6.1 Health endpoints

#### `GET /health/live`

Purpose: process liveness only. No credentials required.

Response `200`:

``` json
{ "status": "ok" }
```

Do not make liveness depend on database or model-provider availability;
otherwise transient dependency outages can cause restart loops.

#### `GET /health/ready`

Purpose: readiness check for required dependencies. Keep response
sanitized.

Response `200`:

``` json
{
  "status": "ready",
  "checks": {
    "database": "ok",
    "queue": "ok",
    "object_storage": "ok"
  }
}
```

Return `503` when a critical dependency prevents safe service. Do not
reveal connection strings, bucket names, provider secrets, or internal
hostnames.

### 6.2 Current user

#### `GET /me`

Returns the authenticated internal user profile and effective membership
summaries.

Response `200`:

``` json
{
  "data": {
    "id": "d7d5b124-66c0-4e72-bd39-6c36e22c9b3a",
    "display_name": "Developer",
    "email": "developer@example.com",
    "status": "active"
  }
}
```

#### `PATCH /me`

Allows a small allowlist of profile fields, such as `display_name`.
Never allow the client to update `auth_provider`, `provider_subject`,
`status`, or workspace roles.

Request:

``` json
{ "display_name": "Vivek" }
```

Response `200`: updated profile.

### 6.3 Workspaces

#### `POST /workspaces`

Creates a workspace and its owner membership in one database
transaction.

Request:

``` json
{
  "name": "Product Engineering",
  "slug": "product-engineering"
}
```

Response `201`:

``` json
{
  "data": {
    "id": "2f4d0d12-0b7e-47bb-96a1-7254a56f68e9",
    "name": "Product Engineering",
    "slug": "product-engineering",
    "role": "owner",
    "created_at": "2026-10-28T08:30:00Z"
  }
}
```

Errors: `409` if slug is taken; `422` for invalid slug/name.

#### `GET /workspaces`

Lists only workspaces the current user can access.

#### `GET /workspaces/{workspace_id}`

Returns workspace metadata and caller's role.

#### `PATCH /workspaces/{workspace_id}`

Owner/admin only. Allowlist `name`; slug changes should be treated
carefully because URLs may be externally referenced.

### 6.4 Workspace membership

#### `GET /workspaces/{workspace_id}/members`

Owner/admin may see full member administration details. Other roles
receive only fields allowed by workspace policy.

#### `POST /workspaces/{workspace_id}/members`

Adds a member using a known internal user ID or a validated invitation
workflow. Do not let a caller add arbitrary users by guessing UUIDs. If
email invitations are not in the MVP, require an existing user and an
explicit authorization check.

Request:

``` json
{
  "user_id": "d7d5b124-66c0-4e72-bd39-6c36e22c9b3a",
  "role": "developer"
}
```

Response `201`: membership record.

#### `PATCH /workspaces/{workspace_id}/members/{user_id}`

Owner/admin only. Changes role within allowed policy. Prevent
demoting/removing the last owner. Ownership transfer must be a separate,
audited operation or transaction.

#### `DELETE /workspaces/{workspace_id}/members/{user_id}`

Owner/admin may remove a member subject to last-owner and self-removal
rules. Emit an audit event.

### 6.5 Projects

#### `POST /workspaces/{workspace_id}/projects`

Creates a project record. It does not immediately execute repository
code.

Request for a connected Git repository:

``` json
{
  "name": "Web Client",
  "description": "Supported React application",
  "source_type": "git_provider",
  "repository_url": "https://git.example.com/org/web-client",
  "default_branch": "main",
  "runtime_profile": {
    "framework": "nextjs",
    "package_manager": "npm"
  }
}
```

Request for an uploaded archive:

``` json
{
  "name": "Reproduction App",
  "source_type": "uploaded_archive",
  "runtime_profile": {
    "framework": "react",
    "package_manager": "npm"
  }
}
```

Response `201`: project resource.

Validation: - `source_type` must be supported. - Repository URL must be
normalized and credentials must not be embedded. - Runtime profile keys
and values must be allowlisted. - The client cannot set privileged
execution commands, secrets, container flags, or arbitrary network
permissions. - Project creation must not trigger code execution.

#### `GET /workspaces/{workspace_id}/projects`

Lists workspace projects with pagination.

#### `GET /projects/{project_id}`

Returns project metadata and latest snapshot summary.

#### `PATCH /projects/{project_id}`

Allows an allowlist of metadata fields such as `name`, `description`,
and approved runtime settings. Changes to source or execution policy
should create an auditable event and may require re-inspection.

#### `POST /projects/{project_id}/archive`

Archives a project and prevents new investigations. Existing records
remain readable according to retention policy.

### 6.6 Source upload and snapshots

#### `POST /projects/{project_id}/source-uploads`

Starts an upload session for an archive. Prefer
direct-to-private-object-storage upload for large files.

Request:

``` json
{
  "file_name": "reproduction-app.zip",
  "content_length": 2840012,
  "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
```

Response `201`:

``` json
{
  "data": {
    "upload_id": "up_01J...",
    "upload_url": "short-lived-signed-upload-url",
    "expires_at": "2026-10-28T08:45:00Z",
    "max_bytes": 52428800
  }
}
```

The signed URL is a bearer capability. Keep its lifetime short and never
log it. The actual implementation should return a real provider URL;
this example is illustrative.

Limits must be configurable and enforced server-side. A client-supplied
digest is only a claim until the server verifies the uploaded bytes.

#### `POST /projects/{project_id}/source-uploads/complete`

Request:

``` json
{
  "upload_id": "up_01J..."
}
```

Response `202`:

``` json
{
  "data": {
    "status": "validating",
    "job_id": "job_01J..."
  }
}
```

The backend validates archive integrity, file count/size, path
traversal, symlinks, compression bombs, ignored files, and secrets
policy before creating a usable snapshot. Do not execute archive
contents during validation.

#### `POST /projects/{project_id}/snapshots`

Requests inspection of a supported source revision. Response `202` with
snapshot job ID. The runner inspects the source in an isolated
environment and records a `repository_snapshots` row only after
validation.

Request:

``` json
{
  "source_ref": "main"
}
```

Do not accept arbitrary clone credentials or shell commands in this
request.

#### `GET /projects/{project_id}/snapshots`

Returns snapshot metadata only, not raw source. Use cursor pagination.

### 6.7 Investigations

#### `POST /projects/{project_id}/investigations`

Creates and queues an investigation. Requires an idempotency key for
clients that may retry after network failure.

Request:

``` json
{
  "title": "Login form fails after refresh",
  "bug_report": "After refreshing the login page, submitting valid credentials leaves the button disabled.",
  "severity": "medium",
  "repository_snapshot_id": "d94fd20f-1a73-4bc1-bc6b-965d9e9dd111",
  "attachments": [
    {
      "upload_id": "up_01J..."
    }
  ],
  "reproduction_context": {
    "route": "/login",
    "browser": "chromium",
    "viewport": {
      "width": 1440,
      "height": 900
    }
  }
}
```

`attachments` and `reproduction_context` are optional. Their fields must
be schema-validated and size-limited. Browser choice and viewport are
allowlisted, not arbitrary browser launch arguments.

Response `202`:

``` json
{
  "data": {
    "id": "8f63d2e4-c0d6-4d0b-b61e-52e0e9bbd83d",
    "project_id": "4e2d9c1e-6e32-43e5-aec2-7bd88a3e4c3c",
    "title": "Login form fails after refresh",
    "status": "queued",
    "current_stage": null,
    "created_at": "2026-10-28T08:30:00Z"
  },
  "links": {
    "self": "/api/v1/investigations/8f63d2e4-c0d6-4d0b-b61e-52e0e9bbd83d",
    "activity": "/api/v1/investigations/8f63d2e4-c0d6-4d0b-b61e-52e0e9bbd83d/activity"
  }
}
```

Server behavior: 1. Authorize project access and creation permission. 2.
Confirm the snapshot belongs to the requested project and is usable. 3.
Create the investigation, initial activity event, and durable
queue/outbox record transactionally. 4. Return `202` without waiting for
reproduction or test execution. 5. Process the investigation in the
worker/orchestrator.

Errors: `404` for inaccessible project/snapshot; `409` for stale or
incompatible source; `422` for invalid report/context; `429` for limits.

#### `GET /projects/{project_id}/investigations`

Lists project investigations, newest first. Filters may include
`status`, `severity`, and date range from an allowlist.

#### `GET /investigations/{investigation_id}`

Returns summary and linked resource counts. Do not include large logs or
raw diffs inline.

Response example:

``` json
{
  "data": {
    "id": "8f63d2e4-c0d6-4d0b-b61e-52e0e9bbd83d",
    "title": "Login form fails after refresh",
    "status": "running",
    "current_stage": "reproduction",
    "severity": "medium",
    "result_summary": null,
    "created_at": "2026-10-28T08:30:00Z",
    "started_at": "2026-10-28T08:30:02Z",
    "completed_at": null,
    "counts": {
      "evidence": 3,
      "hypotheses": 2,
      "patches": 0,
      "verification_runs": 0
    }
  }
}
```

#### `POST /investigations/{investigation_id}/cancel`

Cancels a queued or running investigation if the current stage can be
safely stopped.

Response `202`:

``` json
{
  "data": {
    "id": "8f63d2e4-c0d6-4d0b-b61e-52e0e9bbd83d",
    "status": "cancelled"
  }
}
```

If cleanup is still in progress, return `202` with
`status: "cancelling"` only if that state is explicitly added to the
state model. Otherwise return a queued cancellation request and retain
the actual state until the worker confirms stop. Do not claim the runner
stopped until it has acknowledged cancellation.

#### `POST /investigations/{investigation_id}/retry`

Retries only eligible failed/blocked/inconclusive stages according to
policy. Require a request body that identifies the retry scope; do not
restart every stage blindly.

Request:

``` json
{
  "from_stage": "reproduction",
  "reason": "Updated reproduction instructions"
}
```

Response `202`: investigation retry accepted. Create a new stage
attempt; preserve previous attempts and evidence. Reject retry if the
investigation is already running or the stage is not retryable.

### 6.8 Investigation stages

#### `GET /investigations/{investigation_id}/stages`

Returns stage history in execution order, including retries.

Response `200`:

``` json
{
  "data": [
    {
      "id": "6a5b3c2d-1e0f-4a5b-8c7d-9e0f1a2b3c4d",
      "stage_key": "reproduction",
      "attempt_number": 1,
      "status": "completed",
      "started_at": "2026-10-28T08:31:00Z",
      "finished_at": "2026-10-28T08:31:15Z",
      "summary": {
        "reproduced": true,
        "evidence_count": 2
      }
    }
  ]
}
```

Only return sanitized stage summaries. Never expose internal prompts,
hidden reasoning, raw environment values, or unfiltered command output.

### 6.9 Activity timeline

#### `GET /investigations/{investigation_id}/activity`

Returns cursor-paginated user-visible timeline events.

Response `200`:

``` json
{
  "data": [
    {
      "id": "b3c8a9d1-6f42-4e0a-9d1b-7c2e5f8a0b11",
      "event_type": "evidence.captured",
      "message": "Browser console output was captured.",
      "payload": {
        "evidence_id": "d4a2f09e-8b1c-4d6a-9e5f-2c7b1a8d3e90"
      },
      "created_at": "2026-10-28T08:31:15Z"
    }
  ],
  "page": {
    "limit": 25,
    "next_cursor": null
  }
}
```

### 6.10 Evidence

#### `GET /investigations/{investigation_id}/evidence`

Lists evidence metadata. Filter by `kind` and `redaction_status` only
through allowlisted values.

#### `GET /evidence/{evidence_id}`

Returns evidence metadata and safe preview capability if supported. It
must not reveal raw object-storage keys or permanent public URLs.

#### `POST /evidence/{evidence_id}/download-url`

Authorizes the caller, checks redaction/visibility policy, and returns a
short-lived signed download URL.

Response `200`:

``` json
{
  "data": {
    "url": "short-lived-signed-download-url",
    "expires_at": "2026-10-28T08:35:00Z"
  }
}
```

Do not generate a URL if redaction failed or the artifact is not
authorized for the caller. Avoid logging the signed URL.

### 6.11 Hypotheses

#### `GET /investigations/{investigation_id}/hypotheses`

Returns hypotheses with linked evidence summaries. Clearly label them as
candidate explanations.

#### `PATCH /hypotheses/{hypothesis_id}`

Only allow human-review fields such as user feedback or an explicit
disposition if the product supports it. Do not let a user edit
tool-generated evidence or silently overwrite the original hypothesis.

Recommended request:

``` json
{
  "review_status": "accepted",
  "review_note": "Consistent with the reproduced console error."
}
```

If user review is needed in the MVP, store it in a separate
`hypothesis_reviews` table rather than overloading model-generated
`status`. The current database schema does not include that table;
either add it in a migration or omit this endpoint until implemented. Do
not write `accepted` into the current hypothesis `status` check
constraint.

### 6.12 Regression tests

#### `GET /investigations/{investigation_id}/regression-tests`

Lists proposed tests and their latest execution summaries.

#### `POST /investigations/{investigation_id}/regression-tests`

Creates a proposed regression test or requests the isolated worker to
create a test artifact, depending on the chosen MVP flow.

Request:

``` json
{
  "title": "Login submit re-enables after a failed request",
  "description": "The submit button becomes usable after the request resolves.",
  "test_type": "e2e",
  "file_path": "tests/login.spec.ts",
  "test_name": "login submit recovers after request"
}
```

Response `201` for metadata-only creation, or `202` if the request
queues a worker action. Pick one behavior and document it in the
implementation. For the recommended MVP, create a proposed record
synchronously, then use a separate controlled stage to create/run it.

#### `GET /regression-tests/{test_id}`

Returns test metadata and linked verification history. Never report a
test as passing without a corresponding actual check result.

### 6.13 Patches

#### `GET /investigations/{investigation_id}/patches`

Lists patch proposals and their approval/verification summaries.

#### `GET /patches/{patch_id}`

Returns patch metadata, changed-file summary, base snapshot, approval
status, and latest verification status.

#### `GET /patches/{patch_id}/diff`

Returns a diff only after authorization. Use either a bounded text
response for small diffs or a signed URL for larger artifacts.
Escape/encode diff content correctly in the UI; do not render it as
trusted HTML.

#### `POST /patches/{patch_id}/approve`

Requires an authorized human approver. Approval must apply to the exact
diff digest and base snapshot the user reviewed.

Request:

``` json
{
  "diff_sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "base_snapshot_id": "d94fd20f-1a73-4bc1-bc6b-965d9e9dd111",
  "note": "Reviewed the changed files and intended behavior."
}
```

Response `202`:

``` json
{
  "data": {
    "patch_id": "9d7b6c5a-4e3f-4210-8a9b-0c1d2e3f4a5b",
    "approval_status": "approved",
    "status": "approved",
    "application_status": "queued"
  }
}
```

Implementation requirements: - Lock the patch row in a transaction. -
Verify current state is awaiting approval and approval is pending. -
Compare digest and base snapshot to current persisted values. - Re-check
project/workspace authorization. - Persist the approval and audit event
atomically. - Enqueue patch application only after commit. - Do not
auto-push or merge to a remote branch as a side effect.

If patch application requires a separate confirmation, return `approved`
without queuing application and expose a separate explicit apply
endpoint. Choose one policy and use it consistently. The safer MVP is
**approve the patch for isolated application/verification only**, not
remote publication.

#### `POST /patches/{patch_id}/reject`

Request:

``` json
{
  "reason": "The change does not address the reproduced failure."
}
```

Response `200`: patch marked rejected and audit event recorded. No patch
application may proceed.

#### `POST /patches/{patch_id}/discard`

Marks a proposal discarded if it is not currently being applied. Keep
metadata for audit/history; object deletion follows retention policy.

### 6.14 Verification

#### `GET /investigations/{investigation_id}/verification-runs`

Returns verification attempts, ordered newest first.

#### `GET /verification-runs/{run_id}`

Returns the run and its checks:

``` json
{
  "data": {
    "id": "a13d2c4b-5e6f-4789-9a0b-1c2d3e4f5a6b",
    "phase": "post_patch",
    "status": "failed",
    "summary": "Build passed; the regression test failed.",
    "started_at": "2026-10-28T08:40:00Z",
    "finished_at": "2026-10-28T08:40:12Z",
    "checks": [
      {
        "check_key": "build",
        "display_name": "Build",
        "status": "passed",
        "exit_code": 0,
        "duration_ms": 6500
      },
      {
        "check_key": "regression_test",
        "display_name": "Regression test",
        "status": "failed",
        "exit_code": 1,
        "duration_ms": 4200
      }
    ]
  }
}
```

The API returns persisted results from the trusted runner/verification
service. Do not accept a user request that directly sets verification
status to `passed`.

### 6.15 Reports

#### `POST /investigations/{investigation_id}/reports`

Queues report generation from persisted investigation records and
evidence. Reports should include scope, reproduced behavior, observed
evidence, hypotheses, patch summary, actual verification results, and
limitations.

Request:

``` json
{
  "format": "pdf"
}
```

Allowed formats for the MVP: `pdf`, `markdown`. Response `202` with
report job ID.

The `reports` resource is represented by `evidence_artifacts` with
`kind = report` unless a dedicated reports table is added. If a
dedicated table is preferred, add it in a migration before implementing
these routes.

#### `GET /investigations/{investigation_id}/reports/{report_id}`

Returns report metadata and a short-lived download link after
authorization. Verify that the report belongs to the specified
investigation.

### 6.16 Audit events

#### `GET /workspaces/{workspace_id}/audit-events`

Owner/admin only. Cursor-paginated. Filter by a fixed allowlist of
`action`, `actor_user_id`, and date range. Audit logs are read-only to
ordinary users and must not expose secrets or raw request bodies.

------------------------------------------------------------------------

## 7. Asynchronous job and event model

Investigations, archive validation, snapshot inspection, report
generation, browser reproduction, and verification can take seconds or
minutes. Do not keep an HTTP request open while executing these tasks.

### 7.1 Job acceptance

Return `202 Accepted` with a resource ID or job ID, then let the client
poll the resource endpoint. A WebSocket or Server-Sent Events (SSE)
stream can be added for live progress later; polling is sufficient for
the first MVP.

### 7.2 Client polling

Recommended initial interval: - First 30 seconds: poll every 2--3
seconds. - After 30 seconds: back off to 5--10 seconds. - Stop polling
on a terminal status. - Use exponential backoff and jitter for transient
errors. - Respect `Retry-After` when returned.

Do not treat an API timeout as proof that the underlying job failed;
fetch the resource to determine its actual state.

### 7.3 Investigation state machine

Proposed stages:

``` text
PROJECT_INSPECTION
  -> PLAN_INVESTIGATION
  -> REPRODUCTION
  -> EVIDENCE_ANALYSIS
  -> HYPOTHESIS_REVIEW
  -> REGRESSION_TEST_CREATION
  -> BASELINE_TEST_EXECUTION
  -> PATCH_PROPOSAL
  -> AWAITING_USER_APPROVAL
  -> PATCH_APPLICATION
  -> POST_PATCH_VERIFICATION
  -> REPORT_GENERATION
```

Possible terminal outcomes:

``` text
COMPLETED | FAILED | BLOCKED | INCONCLUSIVE | CANCELLED
```

Not every investigation must reach patch generation. If the bug cannot
be reproduced, evidence is insufficient, or the project is unsupported,
end with an accurate `inconclusive` or `blocked` outcome and explain
why.

### 7.4 Events

The database `activity_events` table is the durable timeline. Optional
SSE/WebSocket notifications are transient delivery mechanisms and should
carry only a resource/event identifier plus sanitized status. Clients
can always recover from the persisted timeline endpoint.

------------------------------------------------------------------------

## 8. Idempotency and concurrency

### 8.1 Idempotency

Require `Idempotency-Key` for important mutation requests: -
`POST /workspaces` - `POST /workspaces/{workspace_id}/projects` -
`POST /projects/{project_id}/investigations` -
`POST /projects/{project_id}/source-uploads` -
`POST /investigations/{investigation_id}/reports`

Store a normalized request hash. Same key and same request returns the
original result; same key with a different request returns
`409 IDEMPOTENCY_KEY_REUSED`.

Do not rely only on client-side disabling of buttons to prevent
duplicate jobs.

### 8.2 Optimistic concurrency

For mutable resources, return an `ETag` or `updated_at` version and
support `If-Match` where practical. Return `409 VERSION_CONFLICT` if a
stale client attempts to overwrite a newer state.

Patch approval must always re-check the current diff digest and base
snapshot regardless of ETag.

### 8.3 State-transition protection

Implement state transitions as explicit service methods, not arbitrary
updates to a `status` column. Use a transaction and row lock for
sensitive transitions such as cancellation, approval, and worker claim.
Reject invalid transitions with `409 INVALID_STATE_TRANSITION`.

------------------------------------------------------------------------

## 9. Upload, artifact, and execution security

### 9.1 Upload validation

-   Enforce maximum request and archive sizes.
-   Validate actual content, file count, nesting depth, compression
    ratio, and archive paths.
-   Reject path traversal, unsafe symlinks, device files, and
    unsupported archive formats.
-   Exclude `.env`, private keys, credential files, dependency caches,
    and large generated directories from indexing unless explicitly
    approved by policy.
-   Treat uploaded code, README files, issue text, screenshots, and logs
    as untrusted input.
-   Do not execute code during upload validation.

### 9.2 Runner isolation

The public API must never execute repository commands inside the FastAPI
process. It should enqueue work for an isolated runner with: - CPU,
memory, process-count, disk, and time limits. - No privileged container
and no Docker socket mount. - Restricted or disabled outbound network by
default. - No API keys in the repository process environment. -
Allowlisted commands and validated arguments. - Workspace cleanup and
bounded output. - Separate credentials for worker services.

### 9.3 Prompt injection

Repository files, bug reports, browser pages, and tool output may
contain instructions intended to manipulate the model. Treat them as
untrusted data. The model may propose investigation actions, but a
policy layer must validate tool names, argument schemas, paths, and
permissions before execution.

### 9.4 Evidence access

Use opaque object keys and private buckets. Check authorization before
creating short-lived download URLs. Do not return permanent public
object URLs or storage keys.

------------------------------------------------------------------------

## 10. Rate limits and quotas

Use per-user and per-workspace limits. Initial values are product
decisions and should be configurable, not hard-coded in route handlers.

  -----------------------------------------------------------------------
  Operation                           Example initial limit
  ----------------------------------- -----------------------------------
  Read endpoints                      120 requests/minute/user

  Create investigation                5 requests/minute/user and a
                                      workspace concurrency cap

  Upload initiation                   10 requests/hour/user

  Evidence download URL               60 requests/minute/user

  Report generation                   10 requests/hour/workspace

  Patch approval/rejection            30 requests/minute/user
  -----------------------------------------------------------------------

Return `429` with a `Retry-After` header. Also enforce job concurrency,
execution duration, artifact size, and model-provider budget limits
independently of HTTP rate limits.

------------------------------------------------------------------------

## 11. Error codes

Use stable machine-readable codes independent of human-facing message
text.

  ---------------------------------------------------------------------------------
  Code                                    Typical HTTP status Meaning
  ------------------------------ ---------------------------- ---------------------
  `AUTH_REQUIRED`                                         401 Missing/invalid
                                                              identity

  `ACCESS_DENIED`                                         403 Caller lacks
                                                              permission

  `RESOURCE_NOT_FOUND`                                    404 Missing or hidden
                                                              resource

  `VALIDATION_ERROR`                                      422 Invalid request

  `IDEMPOTENCY_KEY_REUSED`                                409 Same key used with
                                                              different request

  `INVALID_STATE_TRANSITION`                              409 Action not valid in
                                                              current state

  `VERSION_CONFLICT`                                      409 Stale update

  `PROJECT_ARCHIVED`                                      409 Cannot start new work

  `UNSUPPORTED_REPOSITORY`                                422 Repository stack or
                                                              structure unsupported

  `SNAPSHOT_NOT_READY`                                    409 Source snapshot
                                                              unavailable

  `PATCH_STALE`                                           409 Patch base/diff no
                                                              longer matches

  `PATCH_APPROVAL_REQUIRED`                               409 Patch not approved

  `EVIDENCE_REDACTION_PENDING`                            409 Artifact not safe to
                                                              expose yet

  `UPLOAD_TOO_LARGE`                                      413 Upload exceeds limit

  `UNSUPPORTED_MEDIA_TYPE`                                415 File type unsupported

  `RATE_LIMITED`                                          429 Rate limit or quota
                                                              reached

  `MODEL_PROVIDER_UNAVAILABLE`                            503 Model provider
                                                              unavailable

  `RUNNER_UNAVAILABLE`                                    503 Isolated runner
                                                              unavailable

  `JOB_TIMEOUT`                                           504 A bounded job timed
                                                              out

  `INTERNAL_ERROR`                                        500 Unexpected internal
                                                              failure
  ---------------------------------------------------------------------------------

Do not leak whether a private resource exists when the caller lacks
access.

------------------------------------------------------------------------

## 12. FastAPI implementation guidance

### 12.1 Suggested module layout

``` text
backend/
  app/
    main.py
    api/
      deps.py
      errors.py
      v1/
        router.py
        health.py
        users.py
        workspaces.py
        members.py
        projects.py
        source.py
        investigations.py
        stages.py
        activity.py
        evidence.py
        hypotheses.py
        regression_tests.py
        patches.py
        verification.py
        reports.py
        audit.py
    schemas/
      common.py
      users.py
      workspaces.py
      projects.py
      investigations.py
      evidence.py
      patches.py
      verification.py
    services/
      authorization.py
      workspace_service.py
      project_service.py
      investigation_service.py
      evidence_service.py
      patch_service.py
      verification_service.py
      report_service.py
    models/
    repositories/
    workers/
    security/
      identity.py
      upload_validation.py
      redaction.py
    migrations/
```

### 12.2 Pydantic schemas

Use separate request and response models. Never serialize ORM models
blindly or return arbitrary JSON from the model provider.

Example:

``` python
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class InvestigationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=160)
    bug_report: str = Field(min_length=1, max_length=20_000)
    severity: Literal[
        "low", "medium", "high", "critical", "unspecified"
    ] = "unspecified"
    repository_snapshot_id: UUID
    reproduction_context: dict = Field(default_factory=dict)


class InvestigationResponse(BaseModel):
    id: UUID
    project_id: UUID
    title: str
    status: Literal[
        "queued", "running", "awaiting_approval", "completed",
        "failed", "blocked", "inconclusive", "cancelled"
    ]
    current_stage: str | None = None
    created_at: datetime
```

For `reproduction_context`, replace the generic dictionary with a strict
nested schema before production. Use `extra="forbid"` on external
request models so unrecognized fields are not silently accepted.

### 12.3 Route handler rules

Route handlers should: 1. Parse and validate request schemas. 2. Resolve
authenticated user. 3. Call centralized authorization. 4. Invoke a
service-layer operation. 5. Return a typed response schema. 6. Map known
domain errors to stable HTTP errors. 7. Avoid embedding workflow logic,
SQL, or runner execution in route functions.

### 12.4 Background work

Use a durable queue or transactional outbox. Do not use FastAPI
`BackgroundTasks` for long-running browser/test execution that must
survive process restarts. A worker should claim a job, create
stage/tool-run records, execute within isolation limits, persist
results, and transition state transactionally.

### 12.5 OpenAPI

FastAPI can generate OpenAPI from typed routes and Pydantic schemas.
Treat the generated document as a build artifact to validate in CI. The
examples in this document are the design contract; implementation should
keep the generated OpenAPI schema aligned with it.

------------------------------------------------------------------------

## 13. Observability

Every request should have a correlation/request ID. Propagate it into
worker jobs, tool-run records, audit events, and structured logs.

Record: - Route and status code. - Request duration. - Queue delay and
job duration. - Stage and tool-run status. - Runner resource use and
timeout reason. - Model provider latency/error category. - Artifact
upload/redaction outcome. - Verification check results. - Authorization
failures and sensitive actions.

Do not log bearer tokens, signed URLs, full request bodies by default,
raw environment variables, or unredacted source/log output. Use stable
error codes and scrubbed diagnostic details.

------------------------------------------------------------------------

## 14. API acceptance tests

Before considering the API ready, test at least:

### Authentication and authorization

-   Missing, expired, wrong-audience, and invalid-signature tokens are
    rejected.
-   A user cannot access another workspace's projects, investigations,
    artifacts, or reports by guessing UUIDs.
-   Viewer role cannot create investigations or approve patches.
-   Last-owner removal/demotion is rejected.
-   Service-only endpoints reject end-user tokens.

### Investigations

-   Duplicate create requests with the same idempotency key create one
    investigation.
-   Reusing the same key with a different body returns `409`.
-   Invalid snapshots and snapshots belonging to another project are
    rejected.
-   Cancelling a queued investigation prevents it from starting.
-   Cancellation does not claim a running process has stopped before
    worker acknowledgement.
-   Retrying creates a new stage attempt and preserves old evidence.

### Patches and verification

-   Approval with the wrong digest or base snapshot is rejected.
-   Rejected/discarded/stale patches cannot be applied.
-   A patch cannot be applied without authorization and approval.
-   Model output cannot set verification status.
-   A run with zero required checks cannot be marked passed.
-   Failed, blocked, timed-out, and inconclusive outcomes remain
    distinguishable.

### Uploads and artifacts

-   Archive path traversal, unsafe symlinks, and compression bombs are
    rejected.
-   A user cannot obtain a download URL for an unauthorized artifact.
-   An artifact with failed redaction cannot be downloaded if redaction
    is required.
-   Signed URLs are short-lived and never appear in application logs.

### Reliability

-   Queue publication and database writes are atomic via outbox or
    equivalent recovery.
-   Worker crashes do not leave jobs permanently marked `running`.
-   Database/provider outages return safe errors without leaking
    secrets.
-   OpenAPI generation and migration tests run in CI.

------------------------------------------------------------------------

## 15. Implementation order

Recommended order for a focused MVP:

1.  Authentication and `/me`.
2.  Workspace creation, membership, and authorization dependencies.
3.  Project creation and source onboarding.
4.  Snapshot validation and inspection job.
5.  Investigation creation, state polling, stages, and activity
    timeline.
6.  Evidence metadata and private downloads.
7.  Hypothesis and regression-test views.
8.  Patch diff display and explicit approval/rejection.
9.  Verification-run and per-check results.
10. Report generation and download.
11. Audit endpoints, rate limits, quotas, retention, and hardening.

Do not build every endpoint before completing one end-to-end workflow.
Start with a single supported repository and demonstrate: create project
→ inspect snapshot → create investigation → capture evidence → propose
patch → human approval → run checks → report truthful result.

------------------------------------------------------------------------

## 16. Open contract decisions

Resolve these before implementation:

1.  **Authentication provider:** Confirm token type, issuer/audience,
    and user provisioning behavior.
2.  **Source provider:** Decide whether the first demo supports Git
    provider integration, ZIP upload, or both.
3.  **Report persistence:** Use `evidence_artifacts(kind='report')`
    initially or add a dedicated `reports` table.
4.  **Hypothesis review:** Add a `hypothesis_reviews` table if human
    dispositions must be stored separately from model-generated
    hypothesis status.
5.  **Patch apply semantics:** Recommended: approval authorizes isolated
    application and verification only; remote publication requires a
    separate explicit action.
6.  **Live progress:** Start with polling; add SSE only when the
    end-to-end flow is stable.
7.  **Uploads:** Decide maximum archive size, allowed MIME types, signed
    URL TTL, and storage provider.
8.  **Quotas:** Set concrete per-workspace concurrent-run limits and
    execution budgets.
9.  **RLS:** Decide whether PostgreSQL row-level security is enabled in
    the first deployment or added before multi-tenant production.

------------------------------------------------------------------------

**End of document.**
