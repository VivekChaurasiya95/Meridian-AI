/** Typed API client for the Meridian backend (envelope-aware). */

import type {
  ActivityEvent,
  AssignableRole,
  AuditEvent,
  DownloadUrl,
  ErrorDetail,
  EvidenceArtifact,
  FilePreview,
  HealthChecks,
  Hypothesis,
  HypothesisReview,
  HypothesisVerdict,
  Investigation,
  InvestigationDetail,
  InvestigationReport,
  InvestigationSeverity,
  InvestigationStage,
  InvestigationStatus,
  Job,
  JobStage,
  Member,
  PageInfo,
  Patch,
  PatchApproval,
  PatchDiff,
  Project,
  ProjectsSummary,
  RegressionTest,
  Report,
  ReportFormat,
  SandboxExecution,
  SecurityAssessment,
  SecurityFinding,
  SecurityFindingScanner,
  SecurityFindingSeverity,
  SnapshotDetail,
  SnapshotSummary,
  SnapshotVerification,
  TreeListing,
  UploadResult,
  User,
  VerificationComparison,
  VerificationComparisonRow,
  VerificationRun,
  Workspace,
} from "./types";

export const DEFAULT_API_BASE = "http://localhost:8010";
export const SESSION_PRESENT_COOKIE = "meridian_session_present";

/**
 * Pure hostname fix-up: when both the configured API host and the page host
 * are loopback names that differ (`localhost` vs `127.0.0.1`), talk to the
 * page's spelling so the session cookie stays same-site. Anything else
 * (including LAN/production hosts) is returned unchanged.
 */
export function resolveApiBase(configured: string, pageHostname: string | null): string {
  if (!pageHostname) return configured;
  let url: URL;
  try {
    url = new URL(configured);
  } catch {
    return configured;
  }
  const loopback = new Set(["localhost", "127.0.0.1", "[::1]"]);
  if (loopback.has(url.hostname) && loopback.has(pageHostname) && url.hostname !== pageHostname) {
    url.hostname = pageHostname;
  }
  return url.toString().replace(/\/$/, "");
}

function apiBase(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL ?? DEFAULT_API_BASE;
  const pageHostname = typeof window === "undefined" ? null : window.location.hostname;
  return resolveApiBase(configured, pageHostname);
}

/** True when the readable session-presence flag cookie is set. */
export function hasSessionFlag(): boolean {
  if (typeof document === "undefined") return false;
  return document.cookie.split("; ").some((part) => part.startsWith(`${SESSION_PRESENT_COOKIE}=`));
}

/** Clear the presence flag (used when the server reports the session dead). */
export function clearSessionFlag(): void {
  if (typeof document === "undefined") return;
  document.cookie = `${SESSION_PRESENT_COOKIE}=; Max-Age=0; Path=/; SameSite=Lax`;
}

export class MeridianApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: ErrorDetail[];
  readonly requestId: string | null;

  constructor(
    status: number,
    code: string,
    message: string,
    details: ErrorDetail[] = [],
    requestId: string | null = null,
  ) {
    super(message);
    this.name = "MeridianApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<{ data: T; requestId: string | null; page?: PageInfo }> {
  let response: Response;
  try {
    response = await fetch(`${apiBase()}${path}`, {
      ...init,
      credentials: "include",
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new MeridianApiError(0, "API_UNREACHABLE", "The Meridian API is unreachable. Is it running?");
  }
  const requestId = response.headers.get("X-Request-ID");
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // Non-JSON body: fall through to status handling.
  }
  if (!response.ok || (typeof body === "object" && body !== null && "error" in body)) {
    const err = (body as { error?: { code?: string; message?: string; details?: ErrorDetail[] } })?.error;
    throw new MeridianApiError(
      response.status,
      err?.code ?? "INTERNAL_ERROR",
      err?.message ?? `Request failed with status ${response.status}.`,
      err?.details ?? [],
      requestId,
    );
  }
  const { data, page } = (body ?? {}) as { data: T; page?: PageInfo };
  return { data, page, requestId };
}

export async function getLiveness(): Promise<{ status: string }> {
  const res = await fetch(`${apiBase()}/health/live`);
  if (!res.ok) throw new Error(`Liveness check failed: ${res.status}`);
  return (await res.json()) as { status: string };
}

export async function getReadiness(): Promise<{ status: string; checks: HealthChecks }> {
  const res = await fetch(`${apiBase()}/health/ready`);
  const body = (await res.json()) as { status: string; checks: HealthChecks };
  if (!res.ok) throw new MeridianApiError(res.status, "SERVICE_NOT_READY", "The API reports it is not ready.");
  return body;
}

export async function listWorkspaces(
  limit = 25,
  cursor?: string | null,
): Promise<{ items: Workspace[]; page: PageInfo }> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set("cursor", cursor);
  const { data, page } = await apiFetch<Workspace[]>(`/api/v1/workspaces?${params}`);
  return { items: data, page: page ?? { limit, next_cursor: null } };
}

export async function createWorkspace(input: { name: string; slug: string }): Promise<Workspace> {
  const { data } = await apiFetch<Workspace>("/api/v1/workspaces", {
    method: "POST",
    body: JSON.stringify(input),
  });
  return data;
}

export async function getWorkspace(id: string): Promise<Workspace> {
  const { data } = await apiFetch<Workspace>(`/api/v1/workspaces/${id}`);
  return data;
}

export async function updateWorkspace(id: string, input: { name: string }): Promise<Workspace> {
  const { data } = await apiFetch<Workspace>(`/api/v1/workspaces/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
  return data;
}

export async function signup(input: {
  email: string;
  password: string;
  display_name: string;
}): Promise<User> {
  const { data } = await apiFetch<User>("/api/v1/auth/signup", {
    method: "POST",
    body: JSON.stringify(input),
  });
  return data;
}

export async function login(input: { email: string; password: string }): Promise<User> {
  const { data } = await apiFetch<User>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify(input),
  });
  return data;
}

/** Exchange a Firebase ID token (Google/GitHub) for a Meridian session. */
export async function loginWithFirebase(idToken: string): Promise<User> {
  const { data } = await apiFetch<User>("/api/v1/auth/firebase", {
    method: "POST",
    body: JSON.stringify({ id_token: idToken }),
  });
  return data;
}

export async function logout(): Promise<void> {
  await apiFetch<null>("/api/v1/auth/logout", { method: "POST" });
}

export async function getMe(): Promise<User> {
  const { data } = await apiFetch<User>("/api/v1/me");
  return data;
}

export async function updateMe(input: { display_name: string }): Promise<User> {
  const { data } = await apiFetch<User>("/api/v1/me", {
    method: "PATCH",
    body: JSON.stringify(input),
  });
  return data;
}

export async function listAuditEvents(
  workspaceId: string,
  options?: { limit?: number; cursor?: string | null; action?: string | null },
): Promise<{ items: AuditEvent[]; page: PageInfo }> {
  const params = new URLSearchParams({ limit: String(options?.limit ?? 25) });
  if (options?.cursor) params.set("cursor", options.cursor);
  if (options?.action) params.set("action", options.action);
  const { data, page } = await apiFetch<AuditEvent[]>(
    `/api/v1/workspaces/${workspaceId}/audit-events?${params}`,
  );
  return { items: data, page: page ?? { limit: options?.limit ?? 25, next_cursor: null } };
}

export async function listMembers(workspaceId: string): Promise<Member[]> {
  const { data } = await apiFetch<Member[]>(`/api/v1/workspaces/${workspaceId}/members`);
  return data;
}

export async function addMember(
  workspaceId: string,
  input: { email: string; role: AssignableRole },
): Promise<Member> {
  const { data } = await apiFetch<Member>(`/api/v1/workspaces/${workspaceId}/members`, {
    method: "POST",
    body: JSON.stringify(input),
  });
  return data;
}

export async function updateMemberRole(
  workspaceId: string,
  userId: string,
  input: { role: AssignableRole },
): Promise<Member> {
  const { data } = await apiFetch<Member>(`/api/v1/workspaces/${workspaceId}/members/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
  return data;
}

export async function removeMember(workspaceId: string, userId: string): Promise<void> {
  await apiFetch<null>(`/api/v1/workspaces/${workspaceId}/members/${userId}`, {
    method: "DELETE",
  });
}

export type ProjectSort = "updated" | "created" | "name";
export type ProjectStatusFilter = "active" | "archived";

export async function listProjects(
  workspaceId: string,
  options?: {
    limit?: number;
    cursor?: string | null;
    status?: ProjectStatusFilter | null;
    q?: string | null;
    sort?: ProjectSort;
  },
): Promise<{ items: Project[]; page: PageInfo }> {
  const params = new URLSearchParams({ limit: String(options?.limit ?? 25) });
  if (options?.cursor) params.set("cursor", options.cursor);
  if (options?.status) params.set("status", options.status);
  if (options?.q) params.set("q", options.q);
  if (options?.sort) params.set("sort", options.sort);
  const { data, page } = await apiFetch<Project[]>(
    `/api/v1/workspaces/${workspaceId}/projects?${params}`,
  );
  return { items: data, page: page ?? { limit: 25, next_cursor: null } };
}

export async function getProjectsSummary(workspaceId: string): Promise<ProjectsSummary> {
  const { data } = await apiFetch<ProjectsSummary>(
    `/api/v1/workspaces/${workspaceId}/projects/summary`,
  );
  return data;
}

export async function createProject(
  workspaceId: string,
  input: { name: string; slug: string; description?: string | null },
): Promise<Project> {
  const { data } = await apiFetch<Project>(`/api/v1/workspaces/${workspaceId}/projects`, {
    method: "POST",
    body: JSON.stringify(input),
  });
  return data;
}

export interface GitValidation {
  provider: string;
  owner: string;
  repo: string;
  canonical_url: string;
}

export async function validateGitUrl(repositoryUrl: string): Promise<GitValidation> {
  const { data } = await apiFetch<GitValidation>("/api/v1/git/validate", {
    method: "POST",
    body: JSON.stringify({ repository_url: repositoryUrl }),
  });
  return data;
}

export async function createGitImport(
  workspaceId: string,
  input: {
    name: string;
    slug: string;
    description?: string | null;
    repository_url: string;
    branch?: string | null;
    commit_sha?: string | null;
    idempotency_key?: string;
  },
): Promise<{ project: Project; job: Job }> {
  const { data } = await apiFetch<{ project: Project; job: Job }>(
    `/api/v1/workspaces/${workspaceId}/git-imports`,
    { method: "POST", body: JSON.stringify(input) },
  );
  return data;
}

export async function getProject(id: string): Promise<Project> {
  const { data } = await apiFetch<Project>(`/api/v1/projects/${id}`);
  return data;
}

export async function updateProject(
  id: string,
  input: { name: string; description?: string | null },
): Promise<Project> {
  const { data } = await apiFetch<Project>(`/api/v1/projects/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
  return data;
}

export async function archiveProject(id: string): Promise<Project> {
  const { data } = await apiFetch<Project>(`/api/v1/projects/${id}/archive`, {
    method: "POST",
  });
  return data;
}

export async function deleteProject(id: string): Promise<void> {
  await apiFetch<null>(`/api/v1/projects/${id}`, { method: "DELETE" });
}

export async function unarchiveProject(id: string): Promise<Project> {
  const { data } = await apiFetch<Project>(`/api/v1/projects/${id}/unarchive`, {
    method: "POST",
  });
  return data;
}

export async function listSnapshots(
  projectId: string,
  limit = 25,
  cursor?: string | null,
): Promise<{ items: SnapshotSummary[]; page: PageInfo }> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set("cursor", cursor);
  const { data, page } = await apiFetch<SnapshotSummary[]>(
    `/api/v1/projects/${projectId}/snapshots?${params}`,
  );
  return { items: data, page: page ?? { limit, next_cursor: null } };
}

export async function getSnapshot(id: string): Promise<SnapshotDetail> {
  const { data } = await apiFetch<SnapshotDetail>(`/api/v1/snapshots/${id}`);
  return data;
}

export async function getTree(
  snapshotId: string,
  prefix = "",
  limit = 500,
  offset = 0,
): Promise<TreeListing> {
  const params = new URLSearchParams({
    prefix,
    limit: String(limit),
    offset: String(offset),
  });
  const { data } = await apiFetch<TreeListing>(`/api/v1/snapshots/${snapshotId}/tree?${params}`);
  return data;
}

export async function getFilePreview(snapshotId: string, path: string): Promise<FilePreview> {
  const params = new URLSearchParams({ path });
  const { data } = await apiFetch<FilePreview>(`/api/v1/snapshots/${snapshotId}/file?${params}`);
  return data;
}

export async function verifySnapshot(snapshotId: string): Promise<SnapshotVerification> {
  const { data } = await apiFetch<SnapshotVerification>(
    `/api/v1/snapshots/${snapshotId}/verify`,
    { method: "POST" },
  );
  return data;
}

/**
 * Upload a ZIP archive with real progress events. Uses XMLHttpRequest
 * because fetch cannot report upload progress. Rejects with
 * MeridianApiError carrying the backend code (ARCHIVE_* / INVALID_STATE).
 */
export function uploadProjectArchive(
  projectId: string,
  file: File,
  onProgress?: (fraction: number) => void,
  signal?: AbortSignal | null,
): Promise<UploadResult> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const form = new FormData();
    form.append("file", file, file.name);
    if (signal?.aborted) {
      reject(new MeridianApiError(0, "UPLOAD_CANCELLED", "The upload was cancelled."));
      return;
    }
    const onAbort = () => xhr.abort();
    signal?.addEventListener("abort", onAbort, { once: true });
    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable && event.total > 0) onProgress?.(event.loaded / event.total);
    });
    xhr.addEventListener("load", () => {
      signal?.removeEventListener("abort", onAbort);
      let body: unknown = null;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        body = null;
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        const err = (body as { error?: { code?: string; message?: string } })?.error;
        reject(
          new MeridianApiError(
            xhr.status,
            err?.code ?? "UPLOAD_FAILED",
            err?.message ?? `Upload failed with status ${xhr.status}.`,
          ),
        );
        return;
      }
      resolve((body as { data: UploadResult }).data);
    });
    xhr.addEventListener("error", () => {
      signal?.removeEventListener("abort", onAbort);
      reject(new MeridianApiError(0, "API_UNREACHABLE", "The Meridian API is unreachable."));
    });
    xhr.addEventListener("abort", () => {
      signal?.removeEventListener("abort", onAbort);
      reject(new MeridianApiError(0, "UPLOAD_CANCELLED", "The upload was cancelled."));
    });
    xhr.open("POST", `${apiBase()}/api/v1/projects/${projectId}/source-uploads`);
    xhr.withCredentials = true;
    xhr.send(form);
  });
}

export async function submitJob(
  workspaceId: string,
  input: {
    job_type: "lifecycle_test" | "manifest_recheck" | "sandbox_smoke" | "git_preview" | "git_import";
    payload?: Record<string, unknown>;
    idempotency_key?: string;
  },
): Promise<Job> {
  const { data } = await apiFetch<Job>(`/api/v1/workspaces/${workspaceId}/jobs`, {
    method: "POST",
    body: JSON.stringify({ payload: {}, ...input }),
  });
  return data;
}

export async function listJobs(
  workspaceId: string,
  options?: { limit?: number; cursor?: string | null; status?: string | null },
): Promise<{ items: Job[]; page: PageInfo }> {
  const params = new URLSearchParams({ limit: String(options?.limit ?? 25) });
  if (options?.cursor) params.set("cursor", options.cursor);
  if (options?.status) params.set("status", options.status);
  const { data, page } = await apiFetch<Job[]>(
    `/api/v1/workspaces/${workspaceId}/jobs?${params}`,
  );
  return { items: data, page: page ?? { limit: 25, next_cursor: null } };
}

export async function getJob(id: string): Promise<Job> {
  const { data } = await apiFetch<Job>(`/api/v1/jobs/${id}`);
  return data;
}

export async function cancelJob(id: string): Promise<Job> {
  const { data } = await apiFetch<Job>(`/api/v1/jobs/${id}/cancel`, { method: "POST" });
  return data;
}

export async function getJobStages(id: string): Promise<JobStage[]> {
  const { data } = await apiFetch<{ stages: JobStage[] }>(`/api/v1/jobs/${id}/stages`);
  return data.stages;
}

export async function listJobExecutions(jobId: string): Promise<SandboxExecution[]> {
  const { data } = await apiFetch<{ executions: SandboxExecution[] }>(
    `/api/v1/jobs/${jobId}/executions`,
  );
  return data.executions;
}

export async function getExecution(id: string): Promise<SandboxExecution> {
  const { data } = await apiFetch<SandboxExecution>(`/api/v1/executions/${id}`);
  return data;
}

export interface InvestigationCreateInput {
  title: string;
  bug_report: string;
  severity: InvestigationSeverity;
  repository_snapshot_id: string;
  reproduction_context?: { route?: string };
}

export async function createInvestigation(
  projectId: string,
  input: InvestigationCreateInput,
  idempotencyKey?: string,
): Promise<Investigation> {
  const { data } = await apiFetch<Investigation>(
    `/api/v1/projects/${projectId}/investigations`,
    {
      method: "POST",
      body: JSON.stringify(input),
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : undefined,
    },
  );
  return data;
}

export async function listInvestigations(
  projectId: string,
  params?: { status?: InvestigationStatus; severity?: InvestigationSeverity },
): Promise<Investigation[]> {
  const query = new URLSearchParams();
  if (params?.status) query.set("status", params.status);
  if (params?.severity) query.set("severity", params.severity);
  const suffix = query.size > 0 ? `?${query.toString()}` : "";
  const { data } = await apiFetch<Investigation[]>(
    `/api/v1/projects/${projectId}/investigations${suffix}`,
  );
  return data;
}

export async function listWorkspaceInvestigations(
  workspaceId: string,
  options?: { limit?: number; cursor?: string | null },
): Promise<{ items: Investigation[]; page: PageInfo }> {
  const params = new URLSearchParams({ limit: String(options?.limit ?? 25) });
  if (options?.cursor) params.set("cursor", options.cursor);
  const { data, page } = await apiFetch<Investigation[]>(
    `/api/v1/workspaces/${workspaceId}/investigations?${params}`,
  );
  return { items: data, page: page ?? { limit: 25, next_cursor: null } };
}

export async function getInvestigation(id: string): Promise<InvestigationDetail> {
  const { data } = await apiFetch<InvestigationDetail>(`/api/v1/investigations/${id}`);
  return data;
}

export async function cancelInvestigation(id: string): Promise<Investigation> {
  const { data } = await apiFetch<Investigation>(`/api/v1/investigations/${id}/cancel`, {
    method: "POST",
  });
  return data;
}

export async function retryInvestigation(
  id: string,
  input: { from_stage: string; reason: string },
): Promise<Investigation> {
  const { data } = await apiFetch<Investigation>(`/api/v1/investigations/${id}/retry`, {
    method: "POST",
    body: JSON.stringify(input),
  });
  return data;
}

export async function getInvestigationStages(id: string): Promise<InvestigationStage[]> {
  const { data } = await apiFetch<InvestigationStage[]>(`/api/v1/investigations/${id}/stages`);
  return data;
}

export async function getInvestigationActivity(id: string): Promise<ActivityEvent[]> {
  const { data } = await apiFetch<ActivityEvent[]>(`/api/v1/investigations/${id}/activity`);
  return data;
}

export async function listInvestigationEvidence(id: string): Promise<EvidenceArtifact[]> {
  const { data } = await apiFetch<EvidenceArtifact[]>(`/api/v1/investigations/${id}/evidence`);
  return data;
}

export async function listHypotheses(id: string): Promise<Hypothesis[]> {
  const { data } = await apiFetch<Hypothesis[]>(`/api/v1/investigations/${id}/hypotheses`);
  return data;
}

export async function getHypothesis(id: string): Promise<Hypothesis> {
  const { data } = await apiFetch<Hypothesis>(`/api/v1/hypotheses/${id}`);
  return data;
}

export async function reviewHypothesis(
  id: string,
  input: { verdict: HypothesisVerdict; note?: string },
): Promise<HypothesisReview> {
  const { data } = await apiFetch<HypothesisReview>(`/api/v1/hypotheses/${id}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
  return data;
}

export async function listRegressionTests(investigationId: string): Promise<RegressionTest[]> {
  const { data } = await apiFetch<RegressionTest[]>(
    `/api/v1/investigations/${investigationId}/regression-tests`,
  );
  return data;
}

export async function createRegressionTest(
  investigationId: string,
  input: {
    title: string;
    description?: string;
    test_type?: string;
    file_path?: string;
    test_name?: string;
  },
): Promise<RegressionTest> {
  const { data } = await apiFetch<RegressionTest>(
    `/api/v1/investigations/${investigationId}/regression-tests`,
    { method: "POST", body: JSON.stringify(input) },
  );
  return data;
}

export async function getRegressionTest(testId: string): Promise<RegressionTest> {
  const { data } = await apiFetch<RegressionTest>(`/api/v1/regression-tests/${testId}`);
  return data;
}

export async function listPatches(investigationId: string): Promise<Patch[]> {
  const { data } = await apiFetch<Patch[]>(
    `/api/v1/investigations/${investigationId}/patches`,
  );
  return data;
}

export async function getPatch(patchId: string): Promise<Patch> {
  const { data } = await apiFetch<Patch>(`/api/v1/patches/${patchId}`);
  return data;
}

export async function getPatchDiff(patchId: string): Promise<PatchDiff> {
  const { data } = await apiFetch<PatchDiff>(`/api/v1/patches/${patchId}/diff`);
  return data;
}

export async function approvePatch(
  patchId: string,
  input: { diff_sha256: string; base_snapshot_id: string; note?: string },
): Promise<PatchApproval> {
  const { data } = await apiFetch<PatchApproval>(`/api/v1/patches/${patchId}/approve`, {
    method: "POST",
    body: JSON.stringify(input),
  });
  return data;
}

export async function rejectPatch(patchId: string, input: { reason: string }): Promise<Patch> {
  const { data } = await apiFetch<Patch>(`/api/v1/patches/${patchId}/reject`, {
    method: "POST",
    body: JSON.stringify(input),
  });
  return data;
}

export async function discardPatch(patchId: string): Promise<Patch> {
  const { data } = await apiFetch<Patch>(`/api/v1/patches/${patchId}/discard`, {
    method: "POST",
  });
  return data;
}

export async function listVerificationRuns(investigationId: string): Promise<VerificationRun[]> {
  const { data } = await apiFetch<VerificationRun[]>(
    `/api/v1/investigations/${investigationId}/verification-runs`,
  );
  return data;
}

export async function getVerificationRun(runId: string): Promise<VerificationRun> {
  const { data } = await apiFetch<VerificationRun>(`/api/v1/verification-runs/${runId}`);
  return data;
}

export async function createVerificationRun(
  investigationId: string,
  input: { selected_check_keys?: string[] },
): Promise<VerificationRun> {
  const { data } = await apiFetch<VerificationRun>(
    `/api/v1/investigations/${investigationId}/verification-runs`,
    { method: "POST", body: JSON.stringify(input) },
  );
  return data;
}

export async function getVerificationComparison(
  investigationId: string,
): Promise<VerificationComparison> {
  // The endpoint returns the paged test rows; the caller already knows
  // which investigation it asked for, so echo it back into the shape.
  const { data } = await apiFetch<VerificationComparisonRow[]>(
    `/api/v1/investigations/${investigationId}/verification-comparison`,
  );
  return { investigation_id: investigationId, tests: data };
}

export async function getLatestInvestigationReport(
  investigationId: string,
): Promise<InvestigationReport> {
  const { data } = await apiFetch<InvestigationReport>(
    `/api/v1/investigations/${investigationId}/report`,
  );
  return data;
}

export async function listReports(investigationId: string): Promise<Report[]> {
  const { data } = await apiFetch<Report[]>(
    `/api/v1/investigations/${investigationId}/reports`,
  );
  return data;
}

export async function listWorkspaceReports(workspaceId: string): Promise<Report[]> {
  const { data } = await apiFetch<Report[]>(`/api/v1/workspaces/${workspaceId}/reports`);
  return data;
}

export async function getReport(id: string): Promise<Report> {
  const { data } = await apiFetch<Report>(`/api/v1/reports/${id}`);
  return data;
}

export async function createReport(
  investigationId: string,
  input: { format: ReportFormat },
): Promise<Report> {
  const { data } = await apiFetch<Report>(`/api/v1/investigations/${investigationId}/reports`, {
    method: "POST",
    body: JSON.stringify(input),
  });
  return data;
}

export async function issueReportDownload(id: string): Promise<DownloadUrl> {
  const { data } = await apiFetch<DownloadUrl>(`/api/v1/reports/${id}/download-url`, {
    method: "POST",
  });
  return data;
}

export async function issueEvidenceDownload(id: string): Promise<DownloadUrl> {
  const { data } = await apiFetch<DownloadUrl>(`/api/v1/evidence/${id}/download-url`, {
    method: "POST",
  });
  return data;
}

export async function listProjectAssessments(
  projectId: string,
  options?: { limit?: number; cursor?: string | null },
): Promise<{ items: SecurityAssessment[]; page: PageInfo }> {
  const params = new URLSearchParams({ limit: String(options?.limit ?? 25) });
  if (options?.cursor) params.set("cursor", options.cursor);
  const { data, page } = await apiFetch<SecurityAssessment[]>(
    `/api/v1/projects/${projectId}/security-assessments?${params}`,
  );
  return { items: data, page: page ?? { limit: 25, next_cursor: null } };
}

export async function getSnapshotAssessment(snapshotId: string): Promise<SecurityAssessment> {
  const { data } = await apiFetch<SecurityAssessment>(
    `/api/v1/snapshots/${snapshotId}/security-assessment`,
  );
  return data;
}

export async function getSecurityAssessment(assessmentId: string): Promise<SecurityAssessment> {
  const { data } = await apiFetch<SecurityAssessment>(
    `/api/v1/security-assessments/${assessmentId}`,
  );
  return data;
}

export async function listAssessmentFindings(
  assessmentId: string,
  options?: {
    limit?: number;
    cursor?: string | null;
    severity?: SecurityFindingSeverity | null;
    scanner?: SecurityFindingScanner | null;
    category?: string | null;
    pathPrefix?: string | null;
  },
): Promise<{ items: SecurityFinding[]; page: PageInfo }> {
  const params = new URLSearchParams({ limit: String(options?.limit ?? 25) });
  if (options?.cursor) params.set("cursor", options.cursor);
  if (options?.severity) params.set("severity", options.severity);
  if (options?.scanner) params.set("scanner", options.scanner);
  if (options?.category) params.set("category", options.category);
  if (options?.pathPrefix) params.set("path_prefix", options.pathPrefix);
  const { data, page } = await apiFetch<SecurityFinding[]>(
    `/api/v1/security-assessments/${assessmentId}/findings?${params}`,
  );
  return { items: data, page: page ?? { limit: 25, next_cursor: null } };
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value >= 100 ? 0 : 1)} ${units[unit]}`;
}

export function formatTimestamp(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
