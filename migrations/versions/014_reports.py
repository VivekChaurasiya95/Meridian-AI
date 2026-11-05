"""014: downloadable investigation reports (M10).

Deterministic md/html documents rendered ONLY from persisted rows and
stored as private bytes in the evidence bucket. One row per request;
history is append-only (regeneration creates a new row, never
overwrites). Additive only: the model-written investigation_reports
table (013) is untouched.
"""

from collections.abc import Sequence

revision: str = "014_reports"
down_revision: str | None = "013_investigation_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from alembic import op

    op.execute(
        """
        CREATE TABLE reports (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            investigation_id uuid NOT NULL REFERENCES investigations(id)
                ON DELETE CASCADE,
            project_id uuid NOT NULL REFERENCES projects(id)
                ON DELETE RESTRICT,
            patch_id uuid REFERENCES patches(id) ON DELETE SET NULL,
            verification_run_id uuid REFERENCES verification_runs(id)
                ON DELETE SET NULL,
            format text NOT NULL CHECK (format IN ('md', 'html')),
            status text NOT NULL DEFAULT 'queued'
                CHECK (status IN (
                    'queued', 'running', 'ready', 'failed', 'blocked'
                )),
            digest_sha256 text CHECK (digest_sha256 ~ '^[0-9a-f]{64}$'),
            storage_key text,
            byte_size bigint CHECK (byte_size IS NULL OR byte_size >= 0),
            error_code text,
            error_message text,
            created_by uuid REFERENCES users(id) ON DELETE SET NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_reports_inv "
        "ON reports(investigation_id, created_at, id)"
    )
    op.execute(
        "CREATE INDEX idx_reports_project "
        "ON reports(project_id, created_at, id)"
    )


def downgrade() -> None:
    from alembic import op

    op.execute("DROP INDEX IF EXISTS idx_reports_project")
    op.execute("DROP INDEX IF EXISTS idx_reports_inv")
    op.execute("DROP TABLE IF EXISTS reports")
