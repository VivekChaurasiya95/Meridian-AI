"""007: git import job types (public GitHub, worker-executed).

Additive only: widens the jobs type check. No columns, no data changes.
Snapshot provenance reuses existing commit_sha/branch_name/source_ref.
"""

from collections.abc import Sequence

revision: str = "007_git_import"
down_revision: str | None = "006_sandbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from alembic import op

    op.execute("ALTER TABLE jobs DROP CONSTRAINT IF EXISTS ck_jobs_type")
    op.execute("ALTER TABLE jobs DROP CONSTRAINT IF EXISTS jobs_job_type_check")
    op.execute(
        "ALTER TABLE jobs ADD CONSTRAINT ck_jobs_type CHECK (job_type IN "
        "('lifecycle_test', 'manifest_recheck', 'sandbox_smoke', 'git_preview', 'git_import'))"
    )


def downgrade() -> None:
    from alembic import op

    op.execute("ALTER TABLE jobs DROP CONSTRAINT IF EXISTS ck_jobs_type")
    op.execute(
        "ALTER TABLE jobs ADD CONSTRAINT ck_jobs_type CHECK (job_type IN "
        "('lifecycle_test', 'manifest_recheck', 'sandbox_smoke'))"
    )
