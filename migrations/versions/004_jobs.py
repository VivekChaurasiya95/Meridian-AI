"""004: durable jobs — job queue, leases, retry, stage persistence.

DB-backed queue per C5/D10: workers claim with SELECT ... FOR UPDATE
SKIP LOCKED, own jobs through leases + heartbeats, and record
job_stages rows that survive restarts. No broker.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "004_jobs"
down_revision: str | None = "003_projects"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE jobs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
            project_id uuid REFERENCES projects(id) ON DELETE RESTRICT,
            investigation_id uuid,
            job_type text NOT NULL
                CHECK (job_type IN ('lifecycle_test', 'manifest_recheck')),
            status text NOT NULL DEFAULT 'queued'
                CHECK (status IN (
                    'queued', 'running', 'retry_wait',
                    'completed', 'failed', 'cancelled'
                )),
            priority integer NOT NULL DEFAULT 0,
            payload jsonb NOT NULL DEFAULT '{}'::jsonb
                CHECK (jsonb_typeof(payload) = 'object'),
            result jsonb CHECK (result IS NULL OR jsonb_typeof(result) = 'object'),
            error_code text,
            error_message text,
            attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
            max_attempts integer NOT NULL DEFAULT 5 CHECK (max_attempts >= 1),
            idempotency_key text,
            available_at timestamptz NOT NULL DEFAULT now(),
            worker_id text,
            lease_expires_at timestamptz,
            heartbeat_at timestamptz,
            started_at timestamptz,
            completed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_jobs_workspace_idempotency "
        "ON jobs(workspace_id, idempotency_key) WHERE idempotency_key IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX idx_jobs_claim "
        "ON jobs(status, priority DESC, available_at ASC, created_at ASC, id ASC)"
    )
    op.execute(
        "CREATE INDEX idx_jobs_workspace "
        "ON jobs(workspace_id, created_at DESC, id DESC)"
    )
    op.execute(
        "CREATE INDEX idx_jobs_lease ON jobs(status, lease_expires_at) "
        "WHERE status = 'running'"
    )
    op.execute(
        """
        CREATE TABLE job_stages (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            stage_key text NOT NULL CHECK (stage_key ~ '^[a-z0-9_]{1,64}$'),
            status text NOT NULL DEFAULT 'pending'
                CHECK (status IN (
                    'pending', 'running', 'completed', 'failed',
                    'blocked', 'skipped', 'cancelled'
                )),
            attempt integer NOT NULL DEFAULT 1 CHECK (attempt > 0),
            result_summary jsonb NOT NULL DEFAULT '{}'::jsonb
                CHECK (jsonb_typeof(result_summary) = 'object'),
            error_code text,
            error_message text,
            started_at timestamptz,
            finished_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_job_stage_attempt UNIQUE (job_id, stage_key, attempt)
        )
        """
    )
    op.execute("CREATE INDEX idx_job_stages_job ON job_stages(job_id, stage_key)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_job_stages_job")
    op.execute("DROP TABLE IF EXISTS job_stages")
    op.execute("DROP INDEX IF EXISTS idx_jobs_lease")
    op.execute("DROP INDEX IF EXISTS idx_jobs_workspace")
    op.execute("DROP INDEX IF EXISTS idx_jobs_claim")
    op.execute("DROP INDEX IF EXISTS uq_jobs_workspace_idempotency")
    op.execute("DROP TABLE IF EXISTS jobs")
