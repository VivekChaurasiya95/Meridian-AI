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
  finished_at?: string;
  detail?: string;
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
  model: string;
}

export type InvestigationStatus =
  | "queued"
  | "running"
  | "awaiting_approval"
  | "completed"
  | "failed"
  | "blocked"
  | "inconclusive"
  | "cancelled";

export type InvestigationSeverity = "low" | "medium" | "high" | "critical" | "unspecified";

export interface Investigation {
  id: string;
  project_id: string;
  title: string;
  status: InvestigationStatus;
  current_stage: string | null;
  severity: InvestigationSeverity;
  result_summary: string | null;
  repository_snapshot_id: string | null;
  cancel_requested: boolean;
  started_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface InvestigationDetail extends Investigation {
  counts: {
    evidence: number;
    hypotheses: number;
    patches: number;
    verification_runs: number;
  };
}

export type StageStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "blocked"
  | "skipped"
  | "inconclusive"
  | "cancelled";

export interface InvestigationStage {
  id: string;
  stage_key: string;
  attempt_number: number;
  status: StageStatus;
  input_summary: Record<string, unknown>;
  output_summary: Record<string, unknown>;
  error_code: string | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface ActivityEvent {
  id: string;
  event_type: string;
  message: string;
  payload: Record<string, unknown>;
  actor_user_id: string | null;
  created_at: string;
}

export interface EvidenceArtifact {
  id: string;
  project_id: string;
  investigation_id: string;
  tool_run_id: string | null;
  kind: string;
  mime_type: string;
  byte_size: number;
  sha256: string;
  redaction_status: "pending" | "redacted" | "not_required" | "failed";
  visibility: "workspace" | "investigation_private";
  metadata: Record<string, unknown>;
  captured_at: string | null;
  created_at: string;
}

export interface DownloadUrl {
  url: string;
  expires_at: string;
}

export interface HypothesisEvidenceLink {
  evidence_id: string;
  kind: string;
  relationship: "supports" | "contradicts" | "context";
}

export type HypothesisVerdict = "useful" | "rejected" | "needs_evidence";

export interface HypothesisReview {
  id: string;
  hypothesis_id: string;
  reviewer_user_id: string | null;
  verdict: HypothesisVerdict;
  note: string | null;
  created_at: string;
}

export interface Hypothesis {
  id: string;
  title: string;
  description: string;
  confidence: number | null;
  status: "proposed" | "supported" | "refuted" | "inconclusive" | "superseded";
  created_at: string;
  updated_at: string;
  links: { evidence: HypothesisEvidenceLink[] };
  reviews: HypothesisReview[];
}

export type VerificationRunStatus =
  | "queued"
  | "running"
  | "passed"
  | "failed"
  | "blocked"
  | "timed_out"
  | "cancelled"
  | "inconclusive";

export type VerificationCheckStatus =
  | "queued"
  | "running"
  | "passed"
  | "failed"
  | "blocked"
  | "timed_out"
  | "skipped"
  | "cancelled"
  | "inconclusive";

export type VerificationPhase = "baseline" | "post_patch" | "regression_test" | "diagnostic";

export interface VerificationCheck {
  id: string;
  check_key: string;
  display_name: string;
  status: VerificationCheckStatus;
  exit_code: number | null;
  stdout_artifact_id: string | null;
  stderr_artifact_id: string | null;
  duration_ms: number | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface PlannedCheck {
  check_key: string;
  display_name: string;
}

export interface VerificationRun {
  id: string;
  phase: VerificationPhase;
  status: VerificationRunStatus;
  patch_id: string | null;
  repository_snapshot_id: string;
  runner_image: string | null;
  runtime_profile: {
    requested_by?: string;
    selected_check_keys?: string[];
    planned_checks?: PlannedCheck[];
    adopted_from_queue?: boolean;
    [key: string]: unknown;
  };
  duration_ms: number | null;
  summary: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  checks?: VerificationCheck[];
}

export interface VerificationComparisonEntry {
  check_status: VerificationCheckStatus;
  run_status: VerificationRunStatus;
  exit_code: number | null;
  duration_ms: number | null;
  created_at: string;
}

export interface VerificationComparisonRow {
  test_id: string;
  title: string;
  status: string;
  baseline: VerificationComparisonEntry | null;
  post_patch: VerificationComparisonEntry | null;
}

export interface VerificationComparison {
  investigation_id: string;
  tests: VerificationComparisonRow[];
}

export interface RegressionTestHistoryEntry {
  phase: VerificationPhase;
  run_status: VerificationRunStatus;
  check_status: VerificationCheckStatus;
  display_name: string;
  created_at: string | null;
}

export interface RegressionTest {
  id: string;
  title: string;
  description: string | null;
  test_type: string;
  status: string;
  file_path: string | null;
  test_name: string | null;
  created_artifact_id: string | null;
  created_at: string;
  updated_at: string;
  verification_history: RegressionTestHistoryEntry[];
}

export type PatchStatus =
  | "proposed"
  | "awaiting_approval"
  | "approved"
  | "rejected"
  | "applied"
  | "verification_passed"
  | "verification_failed"
  | "stale"
  | "discarded"
  | "failed";

export type PatchApprovalStatus =
  | "not_requested"
  | "pending"
  | "approved"
  | "rejected"
  | "expired";

export interface PatchFileChange {
  path: string;
  change: "added" | "modified" | "deleted";
  additions: number;
  deletions: number;
}

export interface PatchVerification {
  phase: VerificationPhase;
  status: VerificationRunStatus;
  summary: string | null;
}

export interface Patch {
  id: string;
  investigation_id: string;
  base_snapshot_id: string;
  applied_snapshot_id: string | null;
  status: PatchStatus;
  summary: string;
  diff_sha256: string;
  diff_byte_size: number;
  files_changed: PatchFileChange[];
  approval_status: PatchApprovalStatus;
  approval_by: string | null;
  approval_note: string | null;
  approved_at: string | null;
  applied_at: string | null;
  created_at: string;
  updated_at: string;
  verification: PatchVerification | null;
}

export interface PatchDiffInline {
  diff_sha256: string;
  diff_text: string;
  truncated: false;
}

export interface PatchDiffRemote {
  diff_sha256: string;
  download_url: string;
  expires_at: string;
}

export type PatchDiff = PatchDiffInline | PatchDiffRemote;

export interface PatchApproval {
  patch_id: string;
  approval_status: string;
  status: string;
  application_status: string;
}

export type ReportFormat = "md" | "html";

export type ReportStatus = "queued" | "running" | "ready" | "failed" | "blocked";

export interface Report {
  id: string;
  investigation_id: string;
  project_id: string;
  patch_id: string | null;
  verification_run_id: string | null;
  format: ReportFormat;
  status: ReportStatus;
  digest_sha256: string | null;
  byte_size: number | null;
  error_code: string | null;
  error_message: string | null;
  created_by: string | null;
  created_at: string;
}

export type ExecutionStatus = "running" | "completed" | "failed" | "timed_out" | "cancelled";

export interface SandboxExecution {
  id: string;
  job_id: string;
  worker_id: string;
  snapshot_id: string | null;
  profile: string;
  run_key: string;
  status: ExecutionStatus;
  attempt: number;
  exit_code: number | null;
  timed_out: boolean;
  duration_ms: number | null;
  stdout_excerpt: string | null;
  stdout_chars: number;
  stderr_excerpt: string | null;
  stderr_chars: number;
  output_truncated: boolean;
  error_code: string | null;
  error_message: string | null;
  cleanup_status: "pending" | "cleaned" | "cleanup_failed";
  created_at: string;
  completed_at: string | null;
}
