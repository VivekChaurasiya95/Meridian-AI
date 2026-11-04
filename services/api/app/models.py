"""SQLAlchemy models for migrations 001-006: identity, tenancy, projects, jobs, sandbox.

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
            "source_type IN ('git_provider', 'uploaded_archive')",
            name="ck_snapshots_source_type",
        ),
        CheckConstraint(
            "storage_status IN ('pending', 'uploading', 'ready', 'failed', "
            "'deleting', 'deleted', 'integrity_failed')",
            name="ck_snapshots_storage_status",
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
            "job_type IN ('lifecycle_test', 'manifest_recheck', 'sandbox_smoke')",
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
        Index("idx_sandbox_exec_status", "status"),
        UniqueConstraint("job_id", "attempt", name="uq_sandbox_exec_job_attempt"),
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
