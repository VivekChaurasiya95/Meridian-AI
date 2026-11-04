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

export type ProjectStatus = "active" | "archived" | "setup_failed";

export interface RuntimeProfile {
  languages: string[];
  frameworks: string[];
  package_manager: string | null;
  test_framework: string | null;
  build_system: string | null;
}

export type SnapshotStorageStatus =
  | "pending"
  | "uploading"
  | "ready"
  | "failed"
  | "deleting"
  | "deleted"
  | "integrity_failed";

export interface SnapshotSummary {
  id: string;
  short_hash: string | null;
  tree_digest: string;
  source_type: string;
  archive_name: string | null;
  archive_size: number | null;
  file_count: number;
  created_at: string;
  storage_status: SnapshotStorageStatus;
  storage_bytes: number | null;
  storage_verified_at: string | null;
  error_code: string | null;
  error_message: string | null;
}

export interface Project {
  id: string;
  workspace_id: string;
  name: string;
  slug: string;
  description: string | null;
  source_type: string;
  repository_url: string | null;
  default_branch: string | null;
  status: ProjectStatus;
  runtime_profile: RuntimeProfile;
  role: "owner" | "admin" | "developer" | "viewer";
  snapshot_count: number;
  latest_snapshot: SnapshotSummary | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectsSummary {
  total: number;
  active: number;
  archived: number;
  snapshots_total: number;
  snapshots_recent_7d: number;
  needs_attention: number;
}

export interface InspectionStage {
  key: string;
  status: string;
}

export interface ProjectManifest {
  policy_version: string;
  file_count: number;
  total_bytes: number;
  archive_files: number;
  archive_uncompressed_bytes: number;
  languages: Record<string, number>;
  frameworks: { name: string; version: string | null }[];
  package_manager: string | null;
  test_framework: string | null;
  build_system: string | null;
  entry_points: Record<string, string>;
  skipped_dirs: Record<string, number>;
  secrets_excluded: number;
  warnings: string[];
}

export interface UploadResult {
  snapshot: SnapshotSummary;
  inspection: {
    stages: InspectionStage[];
    manifest: ProjectManifest;
  };
}

export interface SnapshotDetail extends SnapshotSummary {
  project_id: string;
  archive_sha256: string | null;
  manifest: ProjectManifest;
}

export interface TreeEntry {
  path: string;
  size: number;
  sha256: string;
  is_text: boolean;
}

export interface TreeListing {
  snapshot_id: string;
  prefix: string;
  directories: string[];
  entries: TreeEntry[];
  total: number;
  limit: number;
  offset: number;
}

export interface FilePreview {
  snapshot_id: string;
  path: string;
  size: number;
  sha256: string;
  is_text: boolean;
  truncated: boolean;
  content: string | null;
}

export type JobStatus =
  | "queued"
  | "running"
  | "retry_wait"
  | "completed"
  | "failed"
  | "cancelled";

export interface Job {
  id: string;
  workspace_id: string;
  project_id: string | null;
  investigation_id: string | null;
  job_type: string;
  status: JobStatus;
  priority: number;
  attempts: number;
  max_attempts: number;
  worker_id: string | null;
  error_code: string | null;
  error_message: string | null;
  available_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  payload?: Record<string, unknown>;
  result?: Record<string, unknown> | null;
}

export type JobStageStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "blocked"
  | "skipped"
  | "cancelled";

export interface JobStage {
  id: string;
  job_id: string;
  stage_key: string;
  status: JobStageStatus;
  attempt: number;
  result_summary: Record<string, unknown>;
  error_code: string | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface HealthChecks {
  database: string;
  queue: string;
  object_storage: string;
}
