/** Typed API client for the Meridian backend (envelope-aware). */

import type {
  AssignableRole,
  ErrorDetail,
  FilePreview,
  HealthChecks,
  Job,
  JobStage,
  Member,
  PageInfo,
  Project,
  ProjectsSummary,
  SnapshotDetail,
  SnapshotSummary,
  TreeListing,
  UploadResult,
  User,
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
    job_type: "lifecycle_test" | "manifest_recheck";
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
