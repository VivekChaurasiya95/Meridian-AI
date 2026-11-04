"""006: sandbox execution — smoke job type and execution records (M5.2).

Extends the job-type check with ``sandbox_smoke`` (aligning the database
with the ``ck_jobs_type`` name models.py already declares) and adds the
``sandbox_executions`` table: one row per job attempt that enters a
container, so retries never reuse a stale environment and worker
restarts can reconcile orphaned containers from persisted state.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "006_sandbox"
down_revision: str | None = "005_snapshot_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_job_type_check")
    op.execute(
        "ALTER TABLE jobs ADD CONSTRAINT ck_jobs_type "
        "CHECK (job_type IN ('lifecycle_test', 'manifest_recheck', 'sandbox_smoke'))"
    )
    op.execute(
        """
        CREATE TABLE sandbox_executions (
            id uuid PRIMARY KEY,
            job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            worker_id text NOT NULL,
            snapshot_id uuid REFERENCES repository_snapshots(id) ON DELETE SET NULL,
            profile text NOT NULL,
            status text NOT NULL DEFAULT 'running'
                CHECK (status IN (
                    'running', 'completed', 'failed', 'timed_out', 'cancelled'
                )),
            exit_code integer,
            timed_out boolean NOT NULL DEFAULT false,
            duration_ms integer CHECK (duration_ms IS NULL OR duration_ms >= 0),
            stdout text,
            stderr text,
            output_truncated boolean NOT NULL DEFAULT false,
            error_code text,
            error_message text,
            cleanup_status text NOT NULL DEFAULT 'pending'
                CHECK (cleanup_status IN ('pending', 'cleaned', 'cleanup_failed')),
            attempt integer NOT NULL DEFAULT 1 CHECK (attempt > 0),
            created_at timestamptz NOT NULL DEFAULT now(),
            completed_at timestamptz
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_sandbox_exec_job_attempt "
        "ON sandbox_executions(job_id, attempt)"
    )
    op.execute("CREATE INDEX idx_sandbox_exec_status ON sandbox_executions(status)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_sandbox_exec_status")
    op.execute("DROP INDEX IF EXISTS uq_sandbox_exec_job_attempt")
    op.execute("DROP TABLE IF EXISTS sandbox_executions")
    op.execute("ALTER TABLE jobs DROP CONSTRAINT IF EXISTS ck_jobs_type")
    op.execute(
        "ALTER TABLE jobs ADD CONSTRAINT jobs_job_type_check "
        "CHECK (job_type IN ('lifecycle_test', 'manifest_recheck'))"
    )
