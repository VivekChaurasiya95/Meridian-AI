"""009: investigations — debugging sessions, stages, evidence (M6).

Adds the investigation aggregate and its M6 companions: stage attempts,
tool runs, evidence metadata (bytes live in the private evidence
bucket), the user-visible activity timeline, and append-only audit
events. Also widens the jobs type check with ``investigation``.
"""

from collections.abc import Sequence

revision: str = "009_investigations"
down_revision: str | None = "008_security_preflight"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JOB_TYPES_009 = (
    "'lifecycle_test', 'manifest_recheck', 'sandbox_smoke', 'git_preview', "
    "'git_import', 'security_preflight', 'investigation'"
)
_JOB_TYPES_008 = (
    "'lifecycle_test', 'manifest_recheck', 'sandbox_smoke', 'git_preview', "
    "'git_import', 'security_preflight'"
)


def upgrade() -> None:
    from alembic import op

    op.execute("ALTER TABLE jobs DROP CONSTRAINT IF EXISTS ck_jobs_type")
    op.execute(
        "ALTER TABLE jobs ADD CONSTRAINT ck_jobs_type "
        f"CHECK (job_type IN ({_JOB_TYPES_009}))"
    )
    op.execute(
        """
        CREATE TABLE investigations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
            created_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            repository_snapshot_id uuid REFERENCES repository_snapshots(id)
                ON DELETE RESTRICT,
            job_id uuid REFERENCES jobs(id) ON DELETE SET NULL,
            title text NOT NULL CHECK (length(trim(title)) > 0),
            bug_report text NOT NULL CHECK (length(trim(bug_report)) > 0),
            status text NOT NULL DEFAULT 'queued'
                CHECK (status IN (
                    'queued', 'running', 'awaiting_approval', 'completed',
                    'failed', 'blocked', 'inconclusive', 'cancelled'
                )),
            current_stage text CHECK (current_stage IS NULL OR current_stage IN (
                'project_inspection', 'plan_investigation', 'reproduction',
                'evidence_analysis', 'hypothesis_review',
                'regression_test_creation', 'baseline_test_execution',
                'patch_proposal', 'awaiting_user_approval', 'patch_application',
                'post_patch_verification', 'report_generation'
            )),
            severity text NOT NULL DEFAULT 'unspecified'
                CHECK (severity IN ('low', 'medium', 'high', 'critical', 'unspecified')),
            result_summary text,
            reproduction_context jsonb NOT NULL DEFAULT '{}'::jsonb,
            cancel_requested boolean NOT NULL DEFAULT false,
            idempotency_key text,
            request_hash text,
            started_at timestamptz,
            completed_at timestamptz,
            cancelled_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_investigations_project_idempotency
                UNIQUE (project_id, idempotency_key)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_investigations_project "
        "ON investigations(project_id, created_at DESC, id DESC)"
    )
    op.execute(
        "CREATE INDEX idx_investigations_status "
        "ON investigations(project_id, status, created_at DESC, id DESC)"
    )
    op.execute(
        """
        CREATE TABLE investigation_stages (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            investigation_id uuid NOT NULL REFERENCES investigations(id)
                ON DELETE CASCADE,
            stage_key text NOT NULL,
            attempt_number integer NOT NULL CHECK (attempt_number > 0),
            status text NOT NULL DEFAULT 'pending'
                CHECK (status IN (
                    'pending', 'running', 'completed', 'failed', 'blocked',
                    'skipped', 'inconclusive', 'cancelled'
                )),
            input_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
            output_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
            error_code text,
            error_message text,
            started_at timestamptz,
            finished_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_investigation_stage_attempt
                UNIQUE (investigation_id, stage_key, attempt_number)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_investigation_stages_inv "
        "ON investigation_stages(investigation_id, stage_key, attempt_number)"
    )
    op.execute(
        """
        CREATE TABLE tool_runs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            investigation_id uuid NOT NULL REFERENCES investigations(id)
                ON DELETE CASCADE,
            stage_execution_id uuid REFERENCES investigation_stages(id)
                ON DELETE SET NULL,
            tool_name text NOT NULL,
            tool_version text,
            status text NOT NULL DEFAULT 'queued'
                CHECK (status IN (
                    'queued', 'running', 'succeeded', 'failed', 'timed_out',
                    'blocked', 'cancelled'
                )),
            request_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
            result_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
            exit_code integer,
            started_at timestamptz,
            finished_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_tool_runs_inv "
        "ON tool_runs(investigation_id, created_at, id)"
    )
    op.execute(
        """
        CREATE TABLE evidence_artifacts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
            investigation_id uuid NOT NULL REFERENCES investigations(id)
                ON DELETE CASCADE,
            tool_run_id uuid REFERENCES tool_runs(id) ON DELETE SET NULL,
            kind text NOT NULL CHECK (kind IN (
                'log', 'screenshot', 'trace', 'video', 'source_excerpt',
                'test_output', 'build_output', 'network_summary', 'report', 'other'
            )),
            storage_key text NOT NULL,
            mime_type text NOT NULL,
            byte_size bigint NOT NULL CHECK (byte_size >= 0),
            sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
            redaction_status text NOT NULL DEFAULT 'pending'
                CHECK (redaction_status IN (
                    'pending', 'redacted', 'not_required', 'failed'
                )),
            visibility text NOT NULL DEFAULT 'workspace'
                CHECK (visibility IN ('workspace', 'investigation_private')),
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            captured_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_evidence_inv "
        "ON evidence_artifacts(investigation_id, created_at, id)"
    )
    op.execute(
        """
        CREATE TABLE activity_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            investigation_id uuid NOT NULL REFERENCES investigations(id)
                ON DELETE CASCADE,
            actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
            event_type text NOT NULL,
            message text NOT NULL,
            payload jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_activity_inv "
        "ON activity_events(investigation_id, created_at, id)"
    )
    op.execute(
        """
        CREATE TABLE audit_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id uuid REFERENCES workspaces(id) ON DELETE CASCADE,
            actor_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
            actor_type text NOT NULL
                CHECK (actor_type IN ('user', 'system', 'service')),
            action text NOT NULL,
            resource_type text,
            resource_id uuid,
            request_id text,
            ip_digest text,
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_audit_workspace "
        "ON audit_events(workspace_id, created_at, id)"
    )


def downgrade() -> None:
    from alembic import op

    op.execute("DROP INDEX IF EXISTS idx_audit_workspace")
    op.execute("DROP TABLE IF EXISTS audit_events")
    op.execute("DROP INDEX IF EXISTS idx_activity_inv")
    op.execute("DROP TABLE IF EXISTS activity_events")
    op.execute("DROP INDEX IF EXISTS idx_evidence_inv")
    op.execute("DROP TABLE IF EXISTS evidence_artifacts")
    op.execute("DROP INDEX IF EXISTS idx_tool_runs_inv")
    op.execute("DROP TABLE IF EXISTS tool_runs")
    op.execute("DROP INDEX IF EXISTS idx_investigation_stages_inv")
    op.execute("DROP TABLE IF EXISTS investigation_stages")
    op.execute("DROP INDEX IF EXISTS idx_investigations_status")
    op.execute("DROP INDEX IF EXISTS idx_investigations_project")
    op.execute("DROP TABLE IF EXISTS investigations")
    op.execute("ALTER TABLE jobs DROP CONSTRAINT IF EXISTS ck_jobs_type")
    op.execute(
        "ALTER TABLE jobs ADD CONSTRAINT ck_jobs_type "
        f"CHECK (job_type IN ({_JOB_TYPES_008}))"
    )
