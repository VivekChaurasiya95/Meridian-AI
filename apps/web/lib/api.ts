/** Typed API client for the Meridian backend (envelope-aware). */

import type {
  AssignableRole,
  ErrorDetail,
  HealthChecks,
  Member,
  PageInfo,
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
