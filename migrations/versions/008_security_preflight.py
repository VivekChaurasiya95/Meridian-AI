"""008: security preflight — job type, scan artifact, assessments (D61).

Additive only: widens the jobs type check with ``security_preflight``,
adds security-artifact metadata to ``repository_snapshots``, creates
``security_assessments`` + ``security_findings``, and extends
``sandbox_executions`` with a ``scanner`` discriminator so two scanner
containers in one job attempt keep distinct rows (smoke rows use '').
"""

from collections.abc import Sequence

revision: str = "008_security_preflight"
down_revision: str | None = "007_git_import"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from alembic import op

    op.execute("ALTER TABLE jobs DROP CONSTRAINT IF EXISTS ck_jobs_type")
    op.execute(
        "ALTER TABLE jobs ADD CONSTRAINT ck_jobs_type CHECK (job_type IN "
        "('lifecycle_test', 'manifest_recheck', 'sandbox_smoke', 'git_preview', "
        "'git_import', 'security_preflight'))"
    )
    op.execute(
        "ALTER TABLE repository_snapshots "
        "ADD COLUMN IF NOT EXISTS security_storage_key text, "
        "ADD COLUMN IF NOT EXISTS security_content_digest text, "
        "ADD COLUMN IF NOT EXISTS security_storage_bytes bigint, "
        "ADD COLUMN IF NOT EXISTS security_scan_status text NOT NULL DEFAULT 'pending'"
    )
    op.execute("ALTER TABLE repository_snapshots DROP CONSTRAINT IF EXISTS ck_snapshots_security_status")
    op.execute(
        "ALTER TABLE repository_snapshots ADD CONSTRAINT ck_snapshots_security_status "
        "CHECK (security_scan_status IN ('pending', 'ready', 'failed', "
        "'deleting', 'deleted', 'integrity_failed'))"
    )
    op.execute(
        """
        CREATE TABLE security_assessments (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
            project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
            snapshot_id uuid NOT NULL REFERENCES repository_snapshots(id) ON DELETE CASCADE,
            job_id uuid REFERENCES jobs(id) ON DELETE SET NULL,
            generation integer NOT NULL DEFAULT 1 CHECK (generation >= 1),
            status text NOT NULL DEFAULT 'pending'
                CHECK (status IN (
                    'pending', 'running', 'completed', 'review_required',
                    'partial', 'failed', 'cancelled'
                )),
            policy_version text NOT NULL,
            summary jsonb NOT NULL DEFAULT '{}'::jsonb,
            scanner_versions jsonb NOT NULL DEFAULT '{}'::jsonb,
            ruleset_version text NOT NULL,
            started_at timestamptz,
            completed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_security_assessments_job ON security_assessments(job_id)"
    )
    op.execute(
        "CREATE INDEX idx_security_assessments_snapshot "
        "ON security_assessments(snapshot_id, generation)"
    )
    op.execute(
        "CREATE INDEX idx_security_assessments_project "
        "ON security_assessments(project_id, created_at, id)"
    )
    op.execute(
        "CREATE INDEX idx_security_assessments_workspace "
        "ON security_assessments(workspace_id, created_at, id)"
    )
    op.execute(
        "CREATE INDEX idx_security_assessments_status ON security_assessments(status)"
    )
    op.execute(
        """
        CREATE TABLE security_findings (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            assessment_id uuid NOT NULL REFERENCES security_assessments(id) ON DELETE CASCADE,
            fingerprint text NOT NULL,
            scanner text NOT NULL CHECK (scanner IN ('semgrep', 'gitleaks')),
            rule_id text NOT NULL,
            severity text NOT NULL CHECK (severity IN (
                'critical', 'high', 'medium', 'low', 'informational'
            )),
            confidence text NOT NULL CHECK (confidence IN ('high', 'medium', 'low')),
            category text NOT NULL,
            title text NOT NULL,
            description text NOT NULL DEFAULT '',
            location jsonb NOT NULL,
            evidence jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_security_findings_fingerprint "
        "ON security_findings(assessment_id, fingerprint)"
    )
    op.execute(
        "CREATE INDEX idx_security_findings_assessment "
        "ON security_findings(assessment_id, severity, id)"
    )
    op.execute(
        "ALTER TABLE sandbox_executions ADD COLUMN IF NOT EXISTS scanner text NOT NULL DEFAULT ''"
    )
    # 006 created this name as a UNIQUE INDEX, not a table constraint,
    # so the constraint drop alone is a no-op: drop both spellings.
    op.execute("ALTER TABLE sandbox_executions DROP CONSTRAINT IF EXISTS uq_sandbox_exec_job_attempt")
    op.execute("DROP INDEX IF EXISTS uq_sandbox_exec_job_attempt")
    op.execute(
        "ALTER TABLE sandbox_executions ADD CONSTRAINT uq_sandbox_exec_job_attempt "
        "UNIQUE (job_id, attempt, scanner)"
    )
    op.execute("ALTER TABLE sandbox_executions DROP CONSTRAINT IF EXISTS ck_sandbox_exec_scanner")
    op.execute(
        "ALTER TABLE sandbox_executions ADD CONSTRAINT ck_sandbox_exec_scanner "
        "CHECK (scanner IN ('', 'semgrep', 'gitleaks'))"
    )


def downgrade() -> None:
    from alembic import op

    op.execute("ALTER TABLE sandbox_executions DROP CONSTRAINT IF EXISTS ck_sandbox_exec_scanner")
    op.execute("ALTER TABLE sandbox_executions DROP CONSTRAINT IF EXISTS uq_sandbox_exec_job_attempt")
    op.execute("DROP INDEX IF EXISTS uq_sandbox_exec_job_attempt")
    op.execute(
        "ALTER TABLE sandbox_executions ADD CONSTRAINT uq_sandbox_exec_job_attempt "
        "UNIQUE (job_id, attempt)"
    )
    op.execute("ALTER TABLE sandbox_executions DROP COLUMN IF EXISTS scanner")
    op.execute("DROP INDEX IF EXISTS idx_security_findings_assessment")
    op.execute("DROP INDEX IF EXISTS uq_security_findings_fingerprint")
    op.execute("DROP TABLE IF EXISTS security_findings")
    op.execute("DROP INDEX IF EXISTS idx_security_assessments_status")
    op.execute("DROP INDEX IF EXISTS idx_security_assessments_workspace")
    op.execute("DROP INDEX IF EXISTS idx_security_assessments_project")
    op.execute("DROP INDEX IF EXISTS idx_security_assessments_snapshot")
    op.execute("DROP INDEX IF EXISTS uq_security_assessments_job")
    op.execute("DROP TABLE IF EXISTS security_assessments")
    op.execute(
        "ALTER TABLE repository_snapshots DROP CONSTRAINT IF EXISTS ck_snapshots_security_status"
    )
    op.execute(
        "ALTER TABLE repository_snapshots "
        "DROP COLUMN IF EXISTS security_scan_status, "
        "DROP COLUMN IF EXISTS security_storage_bytes, "
        "DROP COLUMN IF EXISTS security_content_digest, "
        "DROP COLUMN IF EXISTS security_storage_key"
    )
    op.execute("ALTER TABLE jobs DROP CONSTRAINT IF EXISTS ck_jobs_type")
    op.execute(
        "ALTER TABLE jobs ADD CONSTRAINT ck_jobs_type CHECK (job_type IN "
        "('lifecycle_test', 'manifest_recheck', 'sandbox_smoke', 'git_preview', 'git_import'))"
    )
