/** Shared API shapes (mirrors the backend envelope, API.md §4). */

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  role: "owner" | "admin" | "developer" | "viewer";
  created_at: string;
}

export interface PageInfo {
  limit: number;
  next_cursor: string | null;
}

export interface User {
  id: string;
  display_name: string | null;
  email: string | null;
  status: string;
}

export type AssignableRole = "admin" | "developer" | "viewer";

export interface Member {
  user_id: string;
  email: string | null;
  display_name: string | null;
  role: string;
  joined_at: string;
}

export interface ErrorDetail {
  field: string;
  issue: string;
}

export interface HealthChecks {
  database: string;
  queue: string;
  object_storage: string;
}
