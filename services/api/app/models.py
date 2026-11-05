"""SQLAlchemy models: identity, tenancy, projects, jobs, sandbox, investigations.

These models mirror the migration SQL exactly (same tables, constraints,
and indexes). The migration SQL is authoritative; any drift between the
two is a bug.
"""

import datetime as dt
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'disabled', 'deletion_pending')", name="ck_users_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    auth_provider: Mapped[str] = mapped_column(Text, nullable=False)
    provider_subject: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str | None] = mapped_column(Text)
    avatar_url: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))
    updated_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))


class Workspace(Base):
    __tablename__ = "workspaces"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_workspaces_name"),
        CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="ck_workspaces_slug"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))
    updated_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))

    members: Mapped[list["WorkspaceMember"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True
    )


class LocalCredential(Base):
    """Password hash for `local`-provider users (migration 002)."""

    __tablename__ = "local_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))
    updated_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))


class UserSession(Base):
    """Opaque server-side session (migration 002). Only hashes are stored."""

    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_sessions_token_hash"),
        CheckConstraint("expires_at > created_at", name="ck_sessions_expiry"),
        Index("idx_sessions_user", "user_id"),
    )

    token_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))
    expires_at: Mapped[dt.datetime] = mapped_column(nullable=False)
    revoked_at: Mapped[dt.datetime | None] = mapped_column()


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"
    __table_args__ = (
        CheckConstraint(
            "role IN ('owner', 'admin', 'developer', 'viewer')",
            name="ck_workspace_members_role",
        ),
        Index("idx_workspace_members_user", "user_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)
    joined_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    workspace: Mapped[Workspace] = relationship(back_populates="members")


class Project(Base):
    """A codebase known to Meridian (migration 003)."""

    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="ck_projects_name"),
        CheckConstraint("slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="ck_projects_slug"),
        CheckConstraint(
            "source_type IN ('git_provider', 'uploaded_archive')",
            name="ck_projects_source_type",
        ),
        CheckConstraint(
            "status IN ('active', 'archived', 'setup_failed')", name="ck_projects_status"
        ),
        CheckConstraint(
            "(source_type = 'git_provider' AND repository_url IS NOT NULL)"
            " OR source_type = 'uploaded_archive'",
            name="ck_project_source_reference",
        ),
        Index("idx_projects_workspace", "workspace_id", "created_at", "id"),
        UniqueConstraint("workspace_id", "slug", name="uq_projects_workspace_slug"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="uploaded_archive"
    )
    repository_url: Mapped[str | None] = mapped_column(Text)
    provider_installation_id: Mapped[str | None] = mapped_column(Text)
    default_branch: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    runtime_profile: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))
    updated_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))

    # Read-side relationship only: snapshot rows are deleted explicitly by
    # the service (FK RESTRICT), never by ORM cascade.
    snapshots: Mapped[list["RepositorySnapshot"]] = relationship(back_populates="project")


class RepositorySnapshot(Base):
    """An immutable inspected repository state (migration 003)."""

    __tablename__ = "repository_snapshots"
    __table_args__ = (
        CheckConstraint("tree_digest ~ '^[0-9a-f]{64}$'", name="ck_snapshots_tree_digest"),
        CheckConstraint(
            "source_type IN ('git_provider', 'uploaded_archive', 'patched_tree')",
            name="ck_snapshots_source_type",
        ),
        CheckConstraint(
            "storage_status IN ('pending', 'uploading', 'ready', 'failed', "
            "'deleting', 'deleted', 'integrity_failed')",
            name="ck_snapshots_storage_status",
        ),
        CheckConstraint(
            "security_scan_status IN ('pending', 'ready', 'failed', "
            "'deleting', 'deleted', 'integrity_failed')",
            name="ck_snapshots_security_status",
        ),
        Index("idx_snapshots_project", "project_id", "created_at", "id"),
        Index("idx_snapshots_storage_key", "storage_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    commit_sha: Mapped[str | None] = mapped_column(Text)
    tree_digest: Mapped[str] = mapped_column(Text, nullable=False)
    branch_name: Mapped[str | None] = mapped_column(Text)
    source_ref: Mapped[str | None] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="uploaded_archive"
    )
    archive_name: Mapped[str | None] = mapped_column(Text)
    archive_size: Mapped[int | None] = mapped_column(BigInteger)
    archive_sha256: Mapped[str | None] = mapped_column(Text)
    manifest: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    storage_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    storage_key: Mapped[str | None] = mapped_column(Text)
    storage_bytes: Mapped[int | None] = mapped_column(BigInteger)
    storage_verified_at: Mapped[dt.datetime | None] = mapped_column()
    security_storage_key: Mapped[str | None] = mapped_column(Text)
    security_content_digest: Mapped[str | None] = mapped_column(Text)
    security_storage_bytes: Mapped[int | None] = mapped_column(BigInteger)
    security_scan_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="pending"
    )
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))

    project: Mapped[Project] = relationship(back_populates="snapshots")
    files: Mapped[list["SnapshotFile"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan", passive_deletes=True
    )


class SnapshotFile(Base):
    """One indexed file inside a snapshot (migration 003).

    Only metadata plus small text previews are stored; secret and
    generated files are never indexed (see archive policy).
    """

    __tablename__ = "snapshot_files"
    __table_args__ = (Index("idx_snapshot_files_snapshot", "snapshot_id", "path"),)

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="CASCADE"), primary_key=True
    )
    path: Mapped[str] = mapped_column(Text, primary_key=True)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    is_text: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    content: Mapped[str | None] = mapped_column(Text)

    snapshot: Mapped[RepositorySnapshot] = relationship(back_populates="files")


class Job(Base):
    """A durable unit of background work (migration 004)."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "job_type IN ('lifecycle_test', 'manifest_recheck', 'sandbox_smoke', "
            "'git_preview', 'git_import', 'security_preflight', 'investigation')",
            name="ck_jobs_type",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'retry_wait', 'completed', 'failed', 'cancelled')",
            name="ck_jobs_status",
        ),
        Index(
            "idx_jobs_claim",
            "status",
            "priority",
            "available_at",
            "created_at",
            "id",
        ),
        Index("idx_jobs_workspace", "workspace_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT")
    )
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    result: Mapped[dict | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("5"))
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    available_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))
    worker_id: Mapped[str | None] = mapped_column(Text)
    lease_expires_at: Mapped[dt.datetime | None] = mapped_column()
    heartbeat_at: Mapped[dt.datetime | None] = mapped_column()
    started_at: Mapped[dt.datetime | None] = mapped_column()
    completed_at: Mapped[dt.datetime | None] = mapped_column()
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))
    updated_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))

    stages: Mapped[list["JobStage"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", passive_deletes=True
    )


class JobStage(Base):
    """One persisted workflow stage attempt for a job (migration 004)."""

    __tablename__ = "job_stages"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'blocked', "
            "'skipped', 'cancelled')",
            name="ck_job_stages_status",
        ),
        Index("idx_job_stages_job", "job_id", "stage_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    stage_key: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    result_summary: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[dt.datetime | None] = mapped_column()
    finished_at: Mapped[dt.datetime | None] = mapped_column()
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))

    job: Mapped[Job] = relationship(back_populates="stages")


class SandboxExecution(Base):
    """One container execution for a job attempt (migration 006).

    The row id is the execution id (32-hex form labels the container),
    so worker restarts reconcile orphaned containers from this table.
    stdout/stderr hold bounded excerpts only; larger artifacts belong in
    object storage in a later milestone.
    """

    __tablename__ = "sandbox_executions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'completed', 'failed', 'timed_out', 'cancelled')",
            name="ck_sandbox_exec_status",
        ),
        CheckConstraint(
            "cleanup_status IN ('pending', 'cleaned', 'cleanup_failed')",
            name="ck_sandbox_exec_cleanup",
        ),
        CheckConstraint(
            "scanner IN ('', 'semgrep', 'gitleaks')",
            name="ck_sandbox_exec_scanner",
        ),
        Index("idx_sandbox_exec_status", "status"),
        UniqueConstraint(
            "job_id",
            "attempt",
            "scanner",
            "run_key",
            name="uq_sandbox_exec_job_attempt_run",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    worker_id: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="SET NULL")
    )
    profile: Mapped[str] = mapped_column(Text, nullable=False)
    scanner: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    run_key: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="running")
    exit_code: Mapped[int | None] = mapped_column(Integer)
    timed_out: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    stdout: Mapped[str | None] = mapped_column(Text)
    stderr: Mapped[str | None] = mapped_column(Text)
    output_truncated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    cleanup_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))
    completed_at: Mapped[dt.datetime | None] = mapped_column()


class SecurityAssessment(Base):
    """One preflight assessment of an exact snapshot (migration 008).

    One row per job (retries reuse it); ``generation`` counts
    assessments per snapshot for future rescans. ``summary`` and
    ``scanner_versions`` are sanitized JSONB — finding counts and
    versions only, never raw scanner output or secret values.
    """

    __tablename__ = "security_assessments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'review_required', "
            "'partial', 'failed', 'cancelled')",
            name="ck_security_assessments_status",
        ),
        Index("idx_security_assessments_snapshot", "snapshot_id", "generation"),
        Index("idx_security_assessments_project", "project_id", "created_at", "id"),
        Index("idx_security_assessments_workspace", "workspace_id", "created_at", "id"),
        Index("idx_security_assessments_status", "status"),
        UniqueConstraint("job_id", name="uq_security_assessments_job"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    generation: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    scanner_versions: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    ruleset_version: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[dt.datetime | None] = mapped_column()
    completed_at: Mapped[dt.datetime | None] = mapped_column()
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))

    findings: Mapped[list["SecurityFinding"]] = relationship(
        back_populates="assessment", cascade="all, delete-orphan", passive_deletes=True
    )


class SecurityFinding(Base):
    """One normalized, sanitized preflight finding (migration 008).

    Evidence excerpts are masked at normalization time: complete
    secrets, private keys, and tokens are never stored here.
    """

    __tablename__ = "security_findings"
    __table_args__ = (
        CheckConstraint(
            "scanner IN ('semgrep', 'gitleaks')",
            name="ck_security_findings_scanner",
        ),
        CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low', 'informational')",
            name="ck_security_findings_severity",
        ),
        CheckConstraint(
            "confidence IN ('high', 'medium', 'low')",
            name="ck_security_findings_confidence",
        ),
        Index("idx_security_findings_assessment", "assessment_id", "severity", "id"),
        UniqueConstraint("assessment_id", "fingerprint", name="uq_security_findings_fingerprint"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("security_assessments.id", ondelete="CASCADE"), nullable=False
    )
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    scanner: Mapped[str] = mapped_column(Text, nullable=False)
    rule_id: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    location: Mapped[dict] = mapped_column(JSONB, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))

    assessment: Mapped[SecurityAssessment] = relationship(back_populates="findings")


class Investigation(Base):
    """One debugging session against a pinned snapshot (migration 009)."""

    __tablename__ = "investigations"
    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="ck_investigations_title"),
        CheckConstraint("length(trim(bug_report)) > 0", name="ck_investigations_bug_report"),
        CheckConstraint(
            "status IN ('queued', 'running', 'awaiting_approval', 'completed', "
            "'failed', 'blocked', 'inconclusive', 'cancelled')",
            name="ck_investigations_status",
        ),
        CheckConstraint(
            "current_stage IS NULL OR current_stage IN ("
            "'project_inspection', 'plan_investigation', 'reproduction', "
            "'evidence_analysis', 'hypothesis_review', 'regression_test_creation', "
            "'baseline_test_execution', 'patch_proposal', 'awaiting_user_approval', "
            "'patch_application', 'post_patch_verification', 'report_generation')",
            name="ck_investigations_stage",
        ),
        CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical', 'unspecified')",
            name="ck_investigations_severity",
        ),
        Index("idx_investigations_project", "project_id", "created_at", "id"),
        Index("idx_investigations_status", "project_id", "status", "created_at", "id"),
        UniqueConstraint(
            "project_id", "idempotency_key", name="uq_investigations_project_idempotency"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    repository_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="RESTRICT")
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    bug_report: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    current_stage: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(Text, nullable=False, server_default="unspecified")
    result_summary: Mapped[str | None] = mapped_column(Text)
    reproduction_context: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    idempotency_key: Mapped[str | None] = mapped_column(Text)
    request_hash: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[dt.datetime | None] = mapped_column()
    completed_at: Mapped[dt.datetime | None] = mapped_column()
    cancelled_at: Mapped[dt.datetime | None] = mapped_column()
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))
    updated_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))


class InvestigationStage(Base):
    """One stage attempt inside an investigation (migration 009)."""

    __tablename__ = "investigation_stages"
    __table_args__ = (
        CheckConstraint("attempt_number > 0", name="ck_investigation_stages_attempt"),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'blocked', "
            "'skipped', 'inconclusive', 'cancelled')",
            name="ck_investigation_stages_status",
        ),
        Index(
            "idx_investigation_stages_inv",
            "investigation_id",
            "stage_key",
            "attempt_number",
        ),
        UniqueConstraint(
            "investigation_id",
            "stage_key",
            "attempt_number",
            name="uq_investigation_stage_attempt",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False
    )
    stage_key: Mapped[str] = mapped_column(Text, nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    input_summary: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    output_summary: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[dt.datetime | None] = mapped_column()
    finished_at: Mapped[dt.datetime | None] = mapped_column()
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))


class ToolRun(Base):
    """One allowlisted deterministic tool invocation (migration 009)."""

    __tablename__ = "tool_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'timed_out', "
            "'blocked', 'cancelled')",
            name="ck_tool_runs_status",
        ),
        Index("idx_tool_runs_inv", "investigation_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False
    )
    stage_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("investigation_stages.id", ondelete="SET NULL")
    )
    tool_name: Mapped[str] = mapped_column(Text, nullable=False)
    tool_version: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    request_summary: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    result_summary: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    exit_code: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[dt.datetime | None] = mapped_column()
    finished_at: Mapped[dt.datetime | None] = mapped_column()
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))


class EvidenceArtifact(Base):
    """Metadata for bytes in the private evidence bucket (migration 009)."""

    __tablename__ = "evidence_artifacts"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('log', 'screenshot', 'trace', 'video', 'source_excerpt', "
            "'test_output', 'build_output', 'network_summary', 'report', 'other')",
            name="ck_evidence_kind",
        ),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="ck_evidence_sha256"),
        CheckConstraint("byte_size >= 0", name="ck_evidence_byte_size"),
        CheckConstraint(
            "redaction_status IN ('pending', 'redacted', 'not_required', 'failed')",
            name="ck_evidence_redaction",
        ),
        CheckConstraint(
            "visibility IN ('workspace', 'investigation_private')",
            name="ck_evidence_visibility",
        ),
        Index("idx_evidence_inv", "investigation_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False
    )
    tool_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tool_runs.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    redaction_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    visibility: Mapped[str] = mapped_column(Text, nullable=False, server_default="workspace")
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    captured_at: Mapped[dt.datetime | None] = mapped_column()
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))


class ActivityEvent(Base):
    """User-visible investigation timeline event (migration 009)."""

    __tablename__ = "activity_events"
    __table_args__ = (Index("idx_activity_inv", "investigation_id", "created_at", "id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))


class AuditEvent(Base):
    """Append-only security audit record (migration 009)."""

    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint("actor_type IN ('user', 'system', 'service')", name="ck_audit_actor_type"),
        Index("idx_audit_workspace", "workspace_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    resource_type: Mapped[str | None] = mapped_column(Text)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    request_id: Mapped[str | None] = mapped_column(Text)
    ip_digest: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))


class Hypothesis(Base):
    """A candidate cause proposed from evidence (migration 010)."""

    __tablename__ = "hypotheses"
    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="ck_hypotheses_title"),
        CheckConstraint("length(trim(description)) > 0", name="ck_hypotheses_description"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_hypotheses_confidence",
        ),
        CheckConstraint(
            "status IN ('proposed', 'supported', 'refuted', 'inconclusive', 'superseded')",
            name="ck_hypotheses_status",
        ),
        Index("idx_hypotheses_inv", "investigation_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False
    )
    created_by_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("investigation_stages.id", ondelete="SET NULL")
    )
    tool_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tool_runs.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="proposed")
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))
    updated_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))


class HypothesisEvidence(Base):
    """Hypothesis-evidence link with an explained relationship (010)."""

    __tablename__ = "hypothesis_evidence"
    __table_args__ = (
        CheckConstraint(
            "relationship IN ('supports', 'contradicts', 'context')",
            name="ck_hypothesis_evidence_relationship",
        ),
        Index("idx_hypothesis_evidence_evidence", "evidence_artifact_id"),
    )

    hypothesis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hypotheses.id", ondelete="CASCADE"), primary_key=True
    )
    evidence_artifact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evidence_artifacts.id", ondelete="RESTRICT"), primary_key=True
    )
    relationship: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))


class HypothesisReview(Base):
    """A user verdict on one hypothesis, newest wins (migration 015)."""

    __tablename__ = "hypothesis_reviews"
    __table_args__ = (
        CheckConstraint(
            "verdict IN ('useful', 'rejected', 'needs_evidence')",
            name="ck_hypothesis_reviews_verdict",
        ),
        Index("idx_hypothesis_reviews_hyp", "hypothesis_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    hypothesis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("hypotheses.id", ondelete="CASCADE"), nullable=False
    )
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    verdict: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))


class InvestigationReport(Base):
    """A validated model-written investigation summary (migration 013)."""

    __tablename__ = "investigation_reports"
    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="ck_investigation_reports_title"),
        CheckConstraint("length(trim(summary)) > 0", name="ck_investigation_reports_summary"),
        Index("idx_investigation_reports_inv", "investigation_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False
    )
    created_by_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("investigation_stages.id", ondelete="SET NULL")
    )
    tool_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tool_runs.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    sections: Mapped[list] = mapped_column(JSONB, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))


class Report(Base):
    """A deterministic downloadable report file (migration 014, M10).

    Rendered ONLY from persisted rows (never model-written prose with
    IDs), stored as private bytes in the evidence bucket. ``patch_id``
    and ``verification_run_id`` are provenance pointers to the latest
    rows at generation time; NULL when none existed.
    """

    __tablename__ = "reports"
    __table_args__ = (
        CheckConstraint("format IN ('md', 'html')", name="ck_reports_format"),
        CheckConstraint(
            "status IN ('queued', 'running', 'ready', 'failed', 'blocked')",
            name="ck_reports_status",
        ),
        CheckConstraint(
            "digest_sha256 IS NULL OR digest_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_reports_digest",
        ),
        CheckConstraint("byte_size IS NULL OR byte_size >= 0", name="ck_reports_byte_size"),
        Index("idx_reports_inv", "investigation_id", "created_at", "id"),
        Index("idx_reports_project", "project_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    patch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("patches.id", ondelete="SET NULL")
    )
    verification_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("verification_runs.id", ondelete="SET NULL")
    )
    format: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    digest_sha256: Mapped[str | None] = mapped_column(Text)
    storage_key: Mapped[str | None] = mapped_column(Text)
    byte_size: Mapped[int | None] = mapped_column(BigInteger)
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))


class RegressionTest(Base):
    """A regression test idea plus its executable artifact (011)."""

    __tablename__ = "regression_tests"
    __table_args__ = (
        CheckConstraint("length(trim(title)) > 0", name="ck_regression_tests_title"),
        CheckConstraint(
            "test_type IN ('unit', 'integration', 'e2e', 'regression', 'manual')",
            name="ck_regression_tests_type",
        ),
        CheckConstraint(
            "status IN ('proposed', 'created', 'baseline_passed', 'baseline_failed', "
            "'post_patch_passed', 'post_patch_failed', 'blocked', 'not_run')",
            name="ck_regression_tests_status",
        ),
        Index("idx_regression_tests_inv", "investigation_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False
    )
    created_by_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("investigation_stages.id", ondelete="SET NULL")
    )
    tool_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tool_runs.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    test_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="proposed")
    file_path: Mapped[str | None] = mapped_column(Text)
    test_name: Mapped[str | None] = mapped_column(Text)
    created_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evidence_artifacts.id", ondelete="SET NULL")
    )
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))
    updated_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))


class Patch(Base):
    """A patch proposal with scoped human approval (migration 011)."""

    __tablename__ = "patches"
    __table_args__ = (
        CheckConstraint("length(trim(summary)) > 0", name="ck_patches_summary"),
        CheckConstraint("diff_sha256 ~ '^[0-9a-f]{64}$'", name="ck_patches_sha256"),
        CheckConstraint("diff_byte_size >= 0", name="ck_patches_byte_size"),
        CheckConstraint(
            "status IN ('proposed', 'awaiting_approval', 'approved', 'rejected', "
            "'applied', 'verification_passed', 'verification_failed', 'stale', "
            "'discarded', 'failed')",
            name="ck_patches_status",
        ),
        CheckConstraint(
            "approval_status IN ('not_requested', 'pending', 'approved', 'rejected', 'expired')",
            name="ck_patches_approval",
        ),
        Index("idx_patches_inv", "investigation_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    base_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    applied_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="RESTRICT")
    )
    created_by_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("investigation_stages.id", ondelete="SET NULL")
    )
    tool_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tool_runs.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="proposed")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    diff_storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    diff_sha256: Mapped[str] = mapped_column(Text, nullable=False)
    diff_byte_size: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    files_changed: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    approval_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    approval_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="not_requested"
    )
    approval_note: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[dt.datetime | None] = mapped_column()
    applied_at: Mapped[dt.datetime | None] = mapped_column()
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))
    updated_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))


class VerificationRun(Base):
    """One trusted baseline/post-patch verification attempt (011)."""

    __tablename__ = "verification_runs"
    __table_args__ = (
        CheckConstraint(
            "phase IN ('baseline', 'post_patch', 'regression_test', 'diagnostic')",
            name="ck_verification_runs_phase",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'passed', 'failed', 'blocked', "
            "'timed_out', 'cancelled', 'inconclusive')",
            name="ck_verification_runs_status",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0", name="ck_verification_runs_duration"
        ),
        Index("idx_verification_runs_inv", "investigation_id", "created_at", "id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    patch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("patches.id", ondelete="SET NULL")
    )
    repository_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="RESTRICT"), nullable=False
    )
    created_by_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("investigation_stages.id", ondelete="SET NULL")
    )
    phase: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    runner_image: Mapped[str | None] = mapped_column(Text)
    runtime_profile: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    started_at: Mapped[dt.datetime | None] = mapped_column()
    finished_at: Mapped[dt.datetime | None] = mapped_column()
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))


class VerificationCheck(Base):
    """One check inside a verification run (migration 011)."""

    __tablename__ = "verification_checks"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'passed', 'failed', 'blocked', "
            "'timed_out', 'skipped', 'cancelled', 'inconclusive')",
            name="ck_verification_checks_status",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0", name="ck_verification_checks_duration"
        ),
        Index("idx_verification_checks_run", "verification_run_id", "check_key"),
        UniqueConstraint("verification_run_id", "check_key", name="uq_verification_check_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    verification_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("verification_runs.id", ondelete="CASCADE"), nullable=False
    )
    regression_test_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("regression_tests.id", ondelete="SET NULL")
    )
    check_key: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="queued")
    command_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    exit_code: Mapped[int | None] = mapped_column(Integer)
    stdout_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evidence_artifacts.id", ondelete="SET NULL")
    )
    stderr_artifact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("evidence_artifacts.id", ondelete="SET NULL")
    )
    started_at: Mapped[dt.datetime | None] = mapped_column()
    finished_at: Mapped[dt.datetime | None] = mapped_column()
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[dt.datetime] = mapped_column(nullable=False, server_default=text("now()"))
