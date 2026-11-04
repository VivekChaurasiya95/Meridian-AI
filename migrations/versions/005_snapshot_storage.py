"""005: snapshot content storage — object-store columns for M5.1.

Pre-existing M3 snapshots have no stored object (bytes were discarded),
so they are backfilled as failed/LEGACY_NO_OBJECT: their metadata, tree,
and previews keep working, but full-content materialization is
unavailable. Documented in docs/DECISIONS.md D51.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "005_snapshot_storage"
down_revision: str | None = "004_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE repository_snapshots
            ADD COLUMN storage_status text NOT NULL DEFAULT 'pending'
                CHECK (storage_status IN (
                    'pending', 'uploading', 'ready', 'failed',
                    'deleting', 'deleted', 'integrity_failed'
                )),
            ADD COLUMN storage_key text,
            ADD COLUMN storage_bytes bigint CHECK (storage_bytes IS NULL OR storage_bytes >= 0),
            ADD COLUMN storage_verified_at timestamptz,
            ADD COLUMN error_code text,
            ADD COLUMN error_message text
        """
    )
    op.execute("CREATE INDEX idx_snapshots_storage_key ON repository_snapshots(storage_key)")
    op.execute(
        """
        UPDATE repository_snapshots
            SET storage_status = 'failed',
                error_code = 'LEGACY_NO_OBJECT',
                error_message = 'Snapshot created before content storage (M5.1); '
                    'metadata, tree, and previews remain available.'
            WHERE storage_status = 'pending'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_snapshots_storage_key")
    op.execute(
        "ALTER TABLE repository_snapshots "
        "DROP COLUMN IF EXISTS error_message, "
        "DROP COLUMN IF EXISTS error_code, "
        "DROP COLUMN IF EXISTS storage_verified_at, "
        "DROP COLUMN IF EXISTS storage_bytes, "
        "DROP COLUMN IF EXISTS storage_key, "
        "DROP COLUMN IF EXISTS storage_status"
    )
