"""013: investigation reports table (model-written summaries).

Additive only: one table for validated report_v1 documents, owned by
their investigation (deleted with it). Stage/tool links are audit
trail only and null out if their rows disappear.
"""

from collections.abc import Sequence

revision: str = "013_investigation_reports"
down_revision: str | None = "012_execution_run_key"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from alembic import op

    op.execute(
        """
        CREATE TABLE investigation_reports (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            investigation_id uuid NOT NULL REFERENCES investigations(id) ON DELETE CASCADE,
            created_by_stage_id uuid REFERENCES investigation_stages(id) ON DELETE SET NULL,
            tool_run_id uuid REFERENCES tool_runs(id) ON DELETE SET NULL,
            title text NOT NULL CHECK (length(trim(title)) > 0),
            summary text NOT NULL CHECK (length(trim(summary)) > 0),
            sections jsonb NOT NULL,
            model text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_investigation_reports_inv "
        "ON investigation_reports(investigation_id, created_at, id)"
    )


def downgrade() -> None:
    from alembic import op

    op.execute("DROP INDEX IF EXISTS idx_investigation_reports_inv")
    op.execute("DROP TABLE IF EXISTS investigation_reports")
