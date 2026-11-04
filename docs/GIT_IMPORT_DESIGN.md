# Meridian AI — Secure Git Repository Import: Architecture Assessment & Implementation Plan

Status: DESIGN ONLY — awaiting approval. No product code changed by this document.
Decisions locked with requester: (1) design-only first, (2) this file is the review artifact,
(3) fetch mechanism = `git` CLI in the trusted worker (not GitHub archive download, not API-process fetch).
Scope v1: public GitHub HTTPS repositories only. No private auth, no arbitrary Git servers, no tokens.

## 1. Architecture assessment (Phase A — read-only audit)

### 1.1 How ZIP ingestion produces a snapshot today

- Entry point: `POST /api/v1/projects/{project_id}/source-uploads` in
  `services/api/app/api/projects.py:127` (`upload_source`). It streams the multipart body with a
  one-byte tripwire cap (`upload_max_bytes + 1`), joins chunks in memory, then calls
  `ingestion_service.upload_source(...)`.
- Pipeline: `services/api/app/services/ingestion.py:143` (`upload_source`) is synchronous in-request
  (D39). Order: workspace role check (`CONTRIBUTOR_ROLES`, 404-for-foreign via
  `project_service.get_project_record`), per-user upload rate limit, `.zip` suffix gate,
  `validate_archive` → `extract_archive` into `tempfile.mkdtemp(prefix="meridian-upload-")` →
  `inspect_tree` → skip-dir/secret filtering → `build_snapshot_tar` → SHA-256 of tar →
  content-addressed `put_file` (dedup via `_key_in_use`) → DB commit → read-back digest verify →
  `storage_status="ready"`. Temp dirs are removed in `finally`.
- Validation: `services/api/app/services/archive_security.py`. `validate_archive` enforces ZIP magic,
  compressed/expanded size, file count, depth, compression ratio; `_normalize` rejects NUL, backslash,
  absolute/drive paths, `..`, duplicates; symlink/device/FIFO/socket entries rejected
  (`_is_symlink`, `_is_unsafe_type`). `extract_archive` streams with per-file SHA-256 and re-verifies
  declared sizes. `compute_tree_digest` = SHA-256 over sorted `path\0size\0sha256\n` lines.
- Indexing policy: `SKIP_DIRS` (includes `.git`, `node_modules`, `dist`, `vendor`, …) and
  `is_secret_file` (`.env*`, keys, credential files) are excluded from the index; counts land in
  `manifest`. Small text previews go to `snapshot_files.content` under `preview_max_bytes` /
  `index_budget_bytes` (`services/api/app/config.py:58-59`).
- Deterministic object: `services/api/app/services/object_store.py:237` (`build_snapshot_tar`):
  sorted members, `PAX_FORMAT`, mtime/uid/gid zeroed, mode `0600`, regular files only. Key =
  `snapshots/<sha256[0:2]>/<sha256>.tar` (`storage_key_for_digest`). Bucket is private; no signed URLs;
  credentials never appear in responses/logs (`StorageError` carries safe codes only).
- Retrieval: `services/api/app/services/storage.py`. `materialize_snapshot` /
  `materialize_for_workspace` verify object digest (`_key_digest`), per-file hashes, index set
  equality, and tree digest before writing into a caller-provided empty dir. Nothing is executed.
  `delete_snapshot_content` honours shared-key refcounts; `list_orphan_keys` is detect-only (D51).

### 1.2 Data model — Git was anticipated, never wired

- `projects` already allows Git: `ck_projects_source_type IN ('git_provider','uploaded_archive')`,
  `ck_project_source_reference` requires `repository_url IS NOT NULL` for `git_provider`
  (`services/api/app/models.py:138-149`). Columns exist: `repository_url`,
  `provider_installation_id`, `default_branch` (`models.py:169-171`).
- `repository_snapshots` already carries `commit_sha`, `branch_name`, `source_ref`, `source_type`
  (`models.py:209-215`), plus `tree_digest`, `manifest` JSONB, storage fields, `created_at`.
- But creation is ZIP-only: `create_project` hard-codes `source_type="uploaded_archive"`
  (`services/api/app/services/projects.py:143`); `ProjectCreate` has no source fields
  (`services/api/app/schemas.py:70-76`); D44 states the Git option “renders visibly disabled”.
- Jobs are allowlisted in three places that must move together: DB check
  `ck_jobs_type IN ('lifecycle_test','manifest_recheck','sandbox_smoke')` (`models.py:263-266`),
  `JOB_TYPES` (`services/api/app/services/jobs.py:29`), `JobSubmit.job_type` Literal
  (`schemas.py:90`), and worker `SAFE_JOB_TYPES`/`HANDLERS`
  (`services/worker/main.py:53,177-181`). Claim uses `FOR UPDATE SKIP LOCKED`, DB-time leases,
  heartbeat, attempt caps, idempotency key (`jobs.py:343-428`).

### 1.3 Worker and sandbox today

- Trusted worker (`services/worker/main.py`): claims only `SAFE_JOB_TYPES`, calls the service layer
  directly (D45, no worker HTTP credentials), heartbeat thread, lease-loss abort, startup orphan
  recovery (D55). It never executes repo code (D48).
- Sandbox (`services/worker/sandbox/orchestrator.py`, `execution_policy.py`): allowlisted profiles
  with exact argv, pinned images (no `:latest`), `Meridian.Dockerfile` reserved-name rule (D54),
  materialization before execution, guaranteed cleanup. Execution containers hold no credentials
  (D53 as corrected by D59: worker holds read-only repo credentials; containers hold none).
- Ingestion today runs in the API process (synchronous upload). Git fetch must NOT follow that
  pattern: the brief and `public/SECURITY.md` §4.1 require the API to never execute/fetch repo code.
  Therefore Git import is a new worker job type, while ZIP stays synchronous (no M1–M5.2 regression).

### 1.4 Frontend today

- Wizard: `apps/web/app/app/projects/new/page.tsx`. Three steps (Source → Details → Review).
  ZIP card is selected-styled; Git card is `cursor-not-allowed opacity-55`,
  `title="Git connections are not built yet"`, `aria-disabled` (`page.tsx:315-325`, D44).
- Flow: `createProject` then `uploadProjectArchive` with XHR progress + `AbortController`
  (`page.tsx:178-233`); project page re-upload at `apps/web/app/app/projects/[id]/page.tsx:641`.
  Client caps mirror server (`CLIENT_MAX_BYTES = 25 MB`). Design language: Sage & Bone tokens
  (`border-sage/40 bg-sage-subtle`, `text-sage`, hairline `border-line`) — reuse, do not invent.
- Jobs UI/API already exist (`submitJob`, `listJobs`, `getJob`, `getJobStages` in
  `apps/web/lib/api.ts`); import progress should poll jobs, not invent a channel (D11 polling).

### 1.5 Policy constraints that bind this design

- `public/SECURITY.md` §6.3: no arbitrary Git URLs without SSRF/destination validation; block
  loopback/private/link-local/metadata; revalidate DNS at connection time; do not follow redirects
  to disallowed destinations; never store credentials in URLs. §7.5: default-deny egress, allowlist
  domains/ports, re-check redirects and DNS, prevent rebinding. §6.1/§6.2: archive validation and
  “pin the exact commit/tree”, record snapshot digests.
- DECISIONS: D37–D44 (ZIP-first, sync ingestion, no-Git-UI), D45 (worker uses service layer),
  D47 (DB-time leases), D48 (safe job types only), D51–D53/D59 (content-addressed MinIO, ready
  semantics, retrieval never executes, credential split), D54–D58 (sandbox hardening).
  O2 records “Git-provider timing open” — this feature closes O2 for public GitHub only.
- Gap found: no egress/DNS validation code exists anywhere; no `git` invocation exists; no audit
  event table exists (logging only). All three are new, narrowly scoped additions below.

## 2. Threat model (Phase B)

Severity: C=critical, H=high, M=medium. “Owner” = where the control lives (API / worker / both).

| # | Threat | Sev | Mitigation (v1) | Owner |
|---|--------|-----|-----------------|-------|
| 1 | SSRF via URL to internal services | C | Host allowlist = exactly `github.com`; scheme `https`; port absent/443 only; no userinfo; DNS answers rejected if any A/AAAA is non-public (fail closed on mixed answers) | API validate + worker revalidate |
| 2 | DNS rebinding (validate-then-resolve TOCTOU) | C | Resolve once in worker, reject non-public, then pin connection: `git -c http.curloptResolve=github.com:443:<ip>` (verify libcurl support in tests; if unsupported, fail closed — do not fall back to unpinned). GitHub clone may contact `codeload.github.com` only via redirect — redirects disabled (see #3), so single-host pin suffices | Worker |
| 3 | Redirect-based SSRF (renamed/moved repo → internal) | H | `-c http.followRedirects=false`; any redirect = `GIT_REDIRECT_REFUSED`. Renamed repos fail with a clear message in v1 (accepted trade-off) | Worker |
| 4 | Localhost/private/metadata targets (`169.254.169.254`, `metadata.google.internal`, RFC1918, `::1`, link-local, multicast, unspecified) | C | Central `is_public_ip` denylist (loopback, private, link-local, multicast, reserved, unspecified) applied to every resolved address, IPv4+IPv6; hostname never trusted textually | Both |
| 5 | Malicious Git URLs (`ext::`, `ssh://`, `file://`, `-oProxyCommand`, leading-dash refs, `?`/`#`, backslash, non-canonical paths) | C | Strict grammar: `https://github.com/<owner>/<repo>[.git]` only; owner/repo regexes (GitHub rules); reject query/fragment/port/userinfo; branch/SHA validated separately; argv array, never shell; first argv after subcommand cannot start with `-` unvalidated | API + worker |
| 6 | Credential leakage | H | No tokens in v1; reject `user:pass@`; env scrubbed (`GIT_ASKPASS` to a failing shim, `GIT_TERMINAL_PROMPT=0`, no credential helper); logs record host/owner/repo/SHA only; job payload stores canonical URL without userinfo by construction | Both |
| 7 | Oversized repositories / pack bombs | H | `git_import_max_bytes` (extracted tree, default = `extracted_max_bytes`), max files (= `max_archive_files`), max single file (new cap, §5), shallow `--depth 1`, timeout, temp-disk quota checked during walk; abort + cleanup on breach | Worker |
| 8 | Malicious symlinks/hardlinks (checkout → host escape, esp. Windows junctions) | C | Post-checkout walk with `os.lstat`: reject symlink/hardlink/special files (mirror `ARCHIVE_SYMLINK`); reject Windows reparse points; never follow links; `.git` deleted before indexing; materialization already rejects special files | Worker |
| 9 | Git config injection (`.git/config`, `include.path`, `core.fsmonitor`, `protocol.ext.allow`) | C | Fresh `git init` in empty temp dir; `-c` allowlist on every invocation; `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=<empty>`, `HOME=<empty temp>`, `XDG_CONFIG_HOME=<empty temp>`; `-c protocol.allow=never -c protocol.https.allow=always`; repo `.git/config` never re-read for a second fetch; checkout with `--no-optional-locks` irrelevant — single fetch only | Worker |
| 10 | Git hooks (`post-checkout`, sample hooks, `core.hooksPath`) | H | `-c core.hooksPath=<empty dir>`; hooks never run because no repo command runs; checkout is `git checkout` of a pinned SHA with hooks path empty; template dir empty (`-c init.templateDir=<empty>`) | Worker |
| 11 | Submodule attacks (`.gitmodules` → second SSRF/execution surface) | H | `-c protocol.file.allow=never`, `--no-recurse-submodules` (fetch/checkout), reject snapshot if `.gitmodules` present (`GIT_SUBMODULES_NOT_SUPPORTED` in v1) | Worker |
| 12 | Git LFS abuse (pointer → arbitrary endpoint fetch) | H | `GIT_LFS_SKIP_SMUDGE=1`, `-c filter.lfs.required=false` + lfs filter configs emptied; reject LFS pointer files detected by header `version https://git-lfs.github.com/spec/v1` (`GIT_LFS_NOT_SUPPORTED`) | Worker |
| 13 | Archive extraction attacks (via produced tar / checkout) | H | Checkout tree passes the same normalized-path/depth/dup checks as `_normalize`; snapshot tar is built only by `build_snapshot_tar` from the validated index; materialization re-verifies (§1.1) | Worker |
| 14 | Path traversal (`../`, absolute, drive, ADS `file:stream`, trailing dot/space Windows quirks) | C | POSIX-normalized index paths only; reject `\\`, `:`, trailing `.`/space components, reserved Windows names (`CON`, `PRN`, `AUX`, `NUL`, `COM*.`, `LPT*.`); case-fold duplicate detection (Windows FS is case-insensitive — `A.py`+`a.py` = duplicate) | Worker |
| 15 | Resource exhaustion (CPU/mem/disk/time, job flooding) | H | Subprocess timeout (`git_import_timeout_seconds`, default 120), bounded stdout/stderr, per-user import rate limit (reuse upload limiter key shape), job `max_attempts` small (default 2 for fetch — network flakes only), workspace running cap reuse, temp dir quota; Windows Job Objects for CPU/mem are Phase-2 (documented residual, §8) | Worker + API |

Windows-specific note: the trusted worker runs on the developer's Windows machine with Docker Desktop,
Postgres (`:5435`) and MinIO (`:9010`) on loopback. The controls above ensure a URL can only ever cause
TCP 443 to a pinned public GitHub address. Git ingestion gets no route to `localhost`, Docker
(`npipe`/TCP), Postgres, or MinIO: it needs no credentials for any of them and receives none.

Residual risks (accepted, recorded): (a) git/libcurl 0-day in pack parsing — mitigated by shallow
fetch, size caps, worker holding only read-only repo credentials (D59) and no execution of content;
(b) `http.curloptResolve` availability depends on the shipped git build — gated by a startup self-test
(§8); (c) egress is host-process network (no proxy) in v1 — IP pinning + host allowlist is the control;
a forward proxy is the production hardening path (§10, slice 6 optional).

## 3. Proposed Git ingestion flow

1. **Validate (API, no network).** User submits canonical URL + optional branch/SHA. API parses with
   the strict grammar (§8.1), resolves workspace role (contributor), rate-limits, and stores nothing yet.
   Response is either `422 GIT_URL_*` or a normalized `{provider, owner, repo, canonical_url}`.
2. **Preview (worker job, read-only).** UI asks for branches: API enqueues `git_preview` (same job
   machinery, payload = canonical URL). Worker resolves DNS, pins IP, runs
   `git ls-remote --heads --tags-` equivalent (`--heads` only, no tags in v1) with hardened config,
   returns default branch (from `HEAD` symref line), branch names, and HEAD SHA per branch. No clone,
   no checkout, result cached in job `result` only. Failure codes are user-safe (§4).
3. **Create + import (API enqueue, worker execute).** On Review confirm: API creates the project with
   `source_type='git_provider'`, `repository_url=<canonical>`, `default_branch=<chosen>`, then enqueues
   `git_import` with idempotency key (double-click safe). API never runs git (SECURITY §4.1).
4. **Fetch (worker).** In a fresh temp dir: re-validate URL + re-resolve DNS + pin IP → `git init` →
   `git remote add origin <canonical>` (argv) → fetch exactly one ref:
   `git fetch --depth 1 --no-tags --no-recurse-submodules origin <branch-or-sha>` →
   resolve to commit SHA (`FETCH_HEAD`) → if user pinned a SHA, require equality / fetch that SHA
   directly → `git checkout --detach <sha>` with hooks/filters disabled → record SHA.
   Branch name is never the snapshot identity; `commit_sha` is.
5. **Tree validation (worker).** Delete `.git`; walk with `lstat`: reject symlinks/special/LFS/
   submodules/Windows-unsafe paths; apply `SKIP_DIRS` + secret exclusion exactly like ZIP; enforce
   file-count/bytes/depth/single-file caps; hash every file (streaming) → `ValidatedEntry` list.
6. **Snapshot (shared core).** Build deterministic tar → content-addressed put (dedup) → insert
   `repository_snapshots` (`source_type='git_provider'`, `commit_sha`, `branch_name`, `source_ref`,
   `manifest.provenance`) + `snapshot_files` rows + text previews → read-back verify → `ready`.
   This is the same terminal state as ZIP; §5 refactors the shared tail, it does not fork it.
7. **Cleanup (always).** Temp dirs removed on every path (`finally`), orphan object deleted if DB
   commit fails after a fresh upload (same rule as `ingestion.py:299-306`), job failed with safe code;
   no snapshot row is left `uploading` — failures mark the job, and no snapshot is created until the
   object+row commit succeeds (failed imports create no half-snapshot; project stays with zero
   snapshots and shows the job error).

## 4. API design

Envelope, `request_id`, error taxonomy, and 404-for-foreign rules follow D2/D42 unchanged.
New client-visible codes: `GIT_URL_INVALID`, `GIT_URL_UNSUPPORTED`, `GIT_HOST_NOT_ALLOWED`,
`GIT_CREDENTIALS_NOT_ALLOWED`, `GIT_BRANCH_NOT_FOUND`, `GIT_COMMIT_NOT_FOUND`,
`GIT_REDIRECT_REFUSED`, `GIT_PRIVATE_ADDRESS`, `GIT_REPO_TOO_LARGE`, `GIT_TOO_MANY_FILES`,
`GIT_SUBMODULES_NOT_SUPPORTED`, `GIT_LFS_NOT_SUPPORTED`, `GIT_FETCH_FAILED`,
`GIT_FETCH_TIMEOUT`. None echoes credentials or internal paths.

| Method & path | Purpose | Auth |
|---|---|---|
| `POST /api/v1/git/validate` | Grammar-only validation + normalization (no network, no DNS) | Session |
| `POST /api/v1/workspaces/{ws}/projects/{proj}/git-imports` — or, for new projects, `POST /api/v1/workspaces/{ws}/git-imports` with `{name, slug, description, repository_url, branch?, commit_sha?}` | Create project (`git_provider`) + enqueue `git_import`; idempotency key supported | Contributor |
| (existing) `POST /api/v1/workspaces/{ws}/jobs` with `job_type="git_preview"` | Branch/SHA discovery; poll `GET …/jobs/{id}` + stages | Contributor |
| (existing) `GET /api/v1/jobs/{id}`, `…/stages`, `POST …/cancel` | Progress, metadata preview (from job result), cancel | Member |

Schemas (`StrictModel`, `extra="forbid"`): `GitValidateRequest{repository_url}`,
`GitImportCreate{name, slug, description?, repository_url, branch?, commit_sha?}` where
`branch` matches `^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$` (no `..`, no trailing `/` or `.lock`) and
`commit_sha` matches `^[0-9a-f]{40}$` (full SHA only; short SHAs rejected — pinning must be exact).
`JobSubmit.job_type` gains `git_preview`/`git_import`. Adding a Git snapshot to an existing
ZIP project (and vice versa) is allowed — snapshots are per-project history; `source_type` lives on
the snapshot. Project-level `source_type` records how the project was created and never mutates.

## 5. Database changes

One migration (`007_git_import.py`), additive only:

1. `jobs`: widen `ck_jobs_type` to add `'git_preview'`, `'git_import'` (drop + recreate check).
2. No new snapshot columns required: provenance reuses `commit_sha`, `branch_name`, `source_ref`
   (= canonical URL), `source_type='git_provider'`, `created_at` (= import timestamp), and
   `manifest.provenance = {provider:"github", canonical_url, branch, commit_sha, imported_at}`.
   `projects.repository_url`/`default_branch` already exist. `provider_installation_id` stays NULL
   (private auth is a future phase; D26-style provider work must not overload it now).
3. Settings (trusted operator config, never API-overridable — mirroring
   `sandbox_max_running_jobs_per_workspace`): `git_import_timeout_seconds=120`,
   `git_import_max_file_bytes=25 MiB`, reuse `max_archive_files` / `extracted_max_bytes` /
   `max_archive_depth` so ZIP and Git share one resource language.

Backward compatibility: ZIP rows, digests, keys, and retrieval are untouched; `tree_digest` algorithm
is unchanged, so identical trees from ZIP and Git dedup to the same MinIO object (by design — the
object is content, the provenance lives on the snapshot row).

Shared-core refactor (behaviour-preserving, prerequisite): extract from
`ingestion.upload_source` the tail starting at tar build (`build_snapshot_tar` → put → snapshot +
files + verify → ready) into `snapshot_from_tree(session, *, project, indexed, source_dir, previews,
provenance fields…)` used by both ZIP (ZIP supplies previews from its second zip pass) and Git
(previews read from the validated tree under the same caps). ZIP tests must stay green byte-for-byte.

## 6. Worker changes

- New module `services/worker/git_import/` (trusted-worker only; API never imports it):
  `url_policy.py` (grammar + IP denylist, pure/testable), `git_runner.py` (argv/env/config
  construction + subprocess with timeout and bounded output), `tree_validate.py` (lstat walk →
  `ValidatedEntry` list), `handlers.py` (`handle_git_preview`, `handle_git_import`).
- `services/worker/main.py`: `SAFE_JOB_TYPES` += both types; `HANDLERS` += both handlers. Claim /
  heartbeat / lease-loss abort reuse `process_job` unchanged; fetch honours cancellation by killing
  the subprocess tree on lease loss (Windows: `taskkill /T` on the child PID — worker-owned child only).
- Git binary is located once at startup (`shutil.which("git")`); absence fails the handler with
  `GIT_UNAVAILABLE` (non-retryable), never a fallback fetch path. Startup self-test asserts
  `git config --get http.curloptResolve` support indirectly via `git ls-remote` against the pinned-IP
  path in tests (§9); production startup logs git version only.
- The execution sandbox is untouched: `network_mode=none` stays; Git egress lives only in the
  trusted worker process, which is the documented separation the brief requires. Worker still holds
  only read-only repository credentials (D59); the git subprocess env contains none of them (§8).

## 7. Frontend changes

Single file primarily: `apps/web/app/app/projects/new/page.tsx`, plus `apps/web/lib/api.ts` /
`apps/web/lib/types.ts` for `validateGitUrl`, `createGitProject`, job polling helpers.

- Source step: Git card becomes selectable (sage selected state mirroring the ZIP card). Selecting
  Git swaps the dropzone for: repository URL field (with inline grammar feedback and provider chip
  “GitHub” once host matches), branch selector (populated by `git_preview` job polling; default
  branch pre-selected; loading/error states explicit), optional commit SHA field (40-hex, “pin exact
  commit”), and the same untrusted-code notice. ZIP path is byte-identical behaviour.
- Details step unchanged. Review step shows source = Git repository, canonical URL, branch, pinned
  or resolved-at-import SHA note (“branch will be pinned to a commit at import”), workspace.
- After create: navigate to project page showing the `git_import` job stages
  (`validate → resolve → fetch → validate_tree → snapshot → verify`) via existing job polling;
  metadata preview (file count, total size, languages from manifest) appears when the job completes.
  Errors render the safe API message; `GIT_BRANCH_NOT_FOUND` etc. are mapped to plain language.
- Project page (`[id]/page.tsx`): snapshot list already renders `source_type` generically; add
  provenance line (GitHub owner/repo @ short SHA, branch) from snapshot fields when present.
  No new design tokens; premium = same cards, hairlines, sage accents, skeleton/progress patterns.

## 8. Security controls (normative)

### 8.1 URL grammar (single implementation, used by API and worker)

Accept only: scheme `https` (case-insensitive, normalized lower), host exactly `github.com`
(no trailing dot, no IDNA tricks — non-ASCII host rejected), no port or `:443`, no userinfo,
no query, no fragment, path `/{owner}/{repo}` with optional `.git` suffix (stripped) and optional
single trailing `/`. Owner: GitHub login rules (1–39, alnum/hyphen, no leading/trailing hyphen).
Repo: 1–100, `[A-Za-z0-9._-]`, not `.`/`..`, no leading `.`/`-`. Canonical form stored:
`https://github.com/<owner>/<repo>` (case preserved as given; host lowercased). Everything else:
specific `GIT_URL_*` code. `git@`, `ssh://`, `git://`, `http://`, `file://`, `ext::`, IPs as host,
and `localhost`/private hostnames are rejected by the same grammar (host allowlist subsumes them).

### 8.2 DNS and connection pinning

Worker resolves `github.com` via `socket.getaddrinfo(443, SOCK_STREAM)`; if any returned address is
non-public → `GIT_PRIVATE_ADDRESS` (mixed answers fail closed). Chooses one public address and pins:
`git -c http.curloptResolve=github.com:443:<ip>`. TLS verification is never disabled
(no `http.sslVerify=false` anywhere; test asserts its absence). Redirects off (§2 #3). If the git
build lacks `curloptResolve`, the handler fails closed with `GIT_UNAVAILABLE` — unpinned fetch is
forbidden. (Fallback for a future slice: egress proxy with CONNECT pinning; not v1.)

### 8.3 Git invocation (every call, no exceptions)

Argv array via `subprocess.run([...], shell=False)`, `cwd=<fresh temp>`, `timeout=`, output capped.
Environment is built from scratch (not inherited): `PATH`, `SYSTEMROOT`/`WINDIR` (Windows needs
these), `TEMP`/`TMP`→temp, plus `GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=<empty file>`,
`GIT_CONFIG_SYSTEM=<empty file>` where supported, `HOME=<empty temp>`, `XDG_CONFIG_HOME=<empty>`,
`GIT_TERMINAL_PROMPT=0`, `GIT_ASKPASS=<failing shim>`, `GIT_LFS_SKIP_SMUDGE=1`. No `AWS_*`, `S3_*`,
`DATABASE_URL`, Docker, or Firebase variables are ever copied in.
Config `-c` set: `credential.helper=`, `core.hooksPath=<empty dir>`, `init.templateDir=<empty>`,
`protocol.allow=never`, `protocol.https.allow=always`, `protocol.file.allow=never`,
`filter.lfs.clean=`, `filter.lfs.smudge=`, `filter.lfs.process=`, `filter.lfs.required=false`,
`core.autocrlf=false`, `core.symlinks=false` (Windows: prevents symlink creation on checkout),
`http.followRedirects=false`, `fetch.recurseSubmodules=false`, `submodule.recurse=false`.
Forbidden everywhere (test-grepped): `shell=True`, `--upload-pack`, `-c` from user input, `--config`,
`--exec-path`, proxy variables from payload, executing any file from the tree, `docker build`,
package-manager invocations.

### 8.4 Tree and limits

Post-checkout: delete `.git` recursively (after SHA recorded); `lstat` walk rejecting links/special
files, `.gitmodules`, LFS pointers, secret files, `SKIP_DIRS`; normalized-path rules of
`archive_security._normalize` plus Windows additions (§2 #14); caps: files ≤ `max_archive_files`,
Σbytes ≤ `extracted_max_bytes`, per-file ≤ `git_import_max_file_bytes`, depth ≤ `max_archive_depth`,
temp-disk guard = extracted cap + 20% headroom checked during walk. Inspection (`inspect_tree`)
runs on the tree exactly as for ZIP — static only, nothing executed (D13/D48 preserved).

### 8.5 Audit and logging

Structured log lines (existing `meridian.*` loggers) for: validation failure (code only), preview,
import enqueued, fetch start (host/owner/repo/branch, no URL userinfo — impossible by grammar),
resolved SHA, tree stats, snapshot ready (snapshot id, storage key, dedup flag), failure (safe code).
Fields: timestamp (logger), request/job id, user id (API side), workspace id, project id.
No passwords, tokens, session material, or env values are logged — consistent with D14 and
`object_store` practice. A database audit table is explicitly deferred (no such table exists today;
adding one is its own decision, not smuggled into this feature).

## 9. Test strategy

New tests live with existing owners: `services/api/tests/test_git_url_policy.py` (pure),
`services/api/tests/test_git_import_jobs.py` (API + job lifecycle, fake git runner),
`services/worker/tests/test_git_fetch.py` (hardened invocation against a local fixture repo),
`apps/web/e2e` spec for wizard source selection. No test contacts GitHub or internal services:
network is faked at the runner seam; DNS is faked at `getaddrinfo`; a local bare fixture repo on a
temp path supplies real git behaviour without egress (worker tests use `file://` only inside the
test harness seam — production grammar still rejects it).

Coverage mapped to the brief: valid/malformed URLs, scheme/port/userinfo/query rejection, private
IPv4+IPv6 + localhost + metadata IPs, redirect refusal, DNS-rebinding (resolver answers public at
validate, private at fetch → fetch must use pinned public or fail), oversized repo/file/count/depth,
symlink + Windows reparse, traversal + ADS/reserved names + case-fold duplicates, hooks present in
fixture (assert not executed — sentinel file absent), `.git/config` injection (`include.path`,
`fsmonitor` sentinel), submodule present → rejected, LFS pointer → rejected, invalid branch,
short-SHA rejection, commit pinning (branch moves between preview and import → snapshot keeps the
SHA fetched at import; pinned SHA mismatch fails), snapshot dedup (same tree via ZIP and Git → same
`storage_key`, two snapshot rows), cross-workspace authorization (foreign project/job → 404),
failed import cleanup (no snapshot row, no orphan object via `FakeObjectStore`, temp dirs gone),
job cancellation during fetch (subprocess killed, job `cancelled`, no snapshot), API-never-runs-git
(assert no `subprocess`/`git` import in API package), sandbox regression suite untouched and green.
Gates before merge (existing): `ruff check` + `ruff format --check`, `mypy app`, full `pytest`,
web lint/typecheck/build, e2e. Secret scanning: grep tests for token-shaped strings in logs/payloads.

## 10. Implementation sequence (each slice independently reviewable)

1. **Pure policy + config**: `url_policy` grammar/IP rules, `git_import_*` settings, unit tests. No wiring.
2. **Shared snapshot core refactor**: extract `snapshot_from_tree`; ZIP tests green byte-for-byte; no behaviour change.
3. **Schema + job plumbing**: migration `007`, `JOB_TYPES`/`JobSubmit`/worker allowlists, `GitImportCreate` + create/enqueue endpoints (handler stub fails `GIT_UNAVAILABLE`). API tests.
4. **Worker fetch**: `git_runner` + `tree_validate` + handlers, fixture-repo tests, cancellation/timeout.
5. **Frontend**: wizard Git source, preview polling, review, project provenance; e2e.
6. **Hardening verification**: rebinding/redirect/pinning tests against fake resolver, log secret-scan, full gates, update `docs/DECISIONS.md` (new D-entry closing O2 for public GitHub) — only after approval to implement.

## Approval gate

This document is the deliverable for Phases 1–7 design. **No code will be modified until the
requester approves this plan** (or amends it). On approval, implementation proceeds slice by slice
in §10 order, each slice landing with its tests; any critical finding during implementation stops
work and is reported before proceeding (per execution rules Phase F/G).

Open items needing requester decision at approval time:
(a) `git_preview` as a job (async, recommended) vs API-side `ls-remote` — API-side is rejected by
SECURITY §4.1 in this plan; confirm. (b) Rejecting renamed repos (redirects off) vs allowlisting
`codeload.github.com` redirects — v1 rejects; confirm. (c) Per-file cap default 25 MiB; confirm.

