"""011: regression tests, patches, verification runs/checks (M8).

Test ideas with executable artifacts, patch proposals with scoped
human approval, and trusted verification attempts with per-check
records. Additive only: no changes to existing tables.
"""

from collections.abc import Sequence

revision: str = "011_patches_verification"
down_revision: str | None = "010_hypotheses"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from alembic import op

    op.execute("ALTER TABLE repository_snapshots DROP CONSTRAINT IF EXISTS ck_snapshots_source_type")
    op.execute(
        "ALTER TABLE repository_snapshots ADD CONSTRAINT ck_snapshots_source_type "
        "CHECK (source_type IN ('git_provider', 'uploaded_archive', 'patched_tree'))"
    )
    op.execute(
        """
        CREATE TABLE regression_tests (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            investigation_id uuid NOT NULL REFERENCES investigations(id)
                ON DELETE CASCADE,
            created_by_stage_id uuid REFERENCES investigation_stages(id)
                ON DELETE SET NULL,
            tool_run_id uuid REFERENCES tool_runs(id) ON DELETE SET NULL,
            title text NOT NULL CHECK (length(trim(title)) > 0),
            description text,
            test_type text NOT NULL
                CHECK (test_type IN ('unit', 'integration', 'e2e', 'regression', 'manual')),
            status text NOT NULL DEFAULT 'proposed'
                CHECK (status IN (
                    'proposed', 'created', 'baseline_passed', 'baseline_failed',
                    'post_patch_passed', 'post_patch_failed', 'blocked', 'not_run'
                )),
            file_path text,
            test_name text,
            created_artifact_id uuid REFERENCES evidence_artifacts(id)
                ON DELETE SET NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_regression_tests_inv "
        "ON regression_tests(investigation_id, created_at, id)"
    )
    op.execute(
        """
        CREATE TABLE patches (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            investigation_id uuid NOT NULL REFERENCES investigations(id)
                ON DELETE CASCADE,
            project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
            base_snapshot_id uuid NOT NULL REFERENCES repository_snapshots(id)
                ON DELETE RESTRICT,
            applied_snapshot_id uuid REFERENCES repository_snapshots(id)
                ON DELETE RESTRICT,
            created_by_stage_id uuid REFERENCES investigation_stages(id)
                ON DELETE SET NULL,
            tool_run_id uuid REFERENCES tool_runs(id) ON DELETE SET NULL,
            status text NOT NULL DEFAULT 'proposed'
                CHECK (status IN (
                    'proposed', 'awaiting_approval', 'approved', 'rejected',
                    'applied', 'verification_passed', 'verification_failed',
                    'stale', 'discarded', 'failed'
                )),
            summary text NOT NULL CHECK (length(trim(summary)) > 0),
            diff_storage_key text NOT NULL,
            diff_sha256 text NOT NULL CHECK (diff_sha256 ~ '^[0-9a-f]{64}$'),
            diff_byte_size bigint NOT NULL DEFAULT 0 CHECK (diff_byte_size >= 0),
            files_changed jsonb NOT NULL DEFAULT '[]'::jsonb,
            approval_by uuid REFERENCES users(id) ON DELETE SET NULL,
            approval_status text NOT NULL DEFAULT 'not_requested'
                CHECK (approval_status IN (
                    'not_requested', 'pending', 'approved', 'rejected', 'expired'
                )),
            approval_note text,
            approved_at timestamptz,
            applied_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_patches_inv ON patches(investigation_id, created_at, id)"
    )
    op.execute(
        """
        CREATE TABLE verification_runs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            investigation_id uuid NOT NULL REFERENCES investigations(id)
                ON DELETE CASCADE,
            project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
            patch_id uuid REFERENCES patches(id) ON DELETE SET NULL,
            repository_snapshot_id uuid NOT NULL REFERENCES repository_snapshots(id)
                ON DELETE RESTRICT,
            created_by_stage_id uuid REFERENCES investigation_stages(id)
                ON DELETE SET NULL,
            phase text NOT NULL
                CHECK (phase IN ('baseline', 'post_patch', 'regression_test', 'diagnostic')),
            status text NOT NULL DEFAULT 'queued'
                CHECK (status IN (
                    'queued', 'running', 'passed', 'failed', 'blocked',
                    'timed_out', 'cancelled', 'inconclusive'
                )),
            runner_image text,
            runtime_profile jsonb NOT NULL DEFAULT '{}'::jsonb,
            started_at timestamptz,
            finished_at timestamptz,
            duration_ms bigint CHECK (duration_ms IS NULL OR duration_ms >= 0),
            summary text,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_verification_runs_inv "
        "ON verification_runs(investigation_id, created_at DESC, id DESC)"
    )
    op.execute(
        """
        CREATE TABLE verification_checks (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            verification_run_id uuid NOT NULL REFERENCES verification_runs(id)
                ON DELETE CASCADE,
            regression_test_id uuid REFERENCES regression_tests(id)
                ON DELETE SET NULL,
            check_key text NOT NULL,
            display_name text NOT NULL,
            status text NOT NULL DEFAULT 'queued'
                CHECK (status IN (
                    'queued', 'running', 'passed', 'failed', 'blocked',
                    'timed_out', 'skipped', 'cancelled', 'inconclusive'
                )),
            command_fingerprint text NOT NULL,
            exit_code integer,
            stdout_artifact_id uuid REFERENCES evidence_artifacts(id)
                ON DELETE SET NULL,
            stderr_artifact_id uuid REFERENCES evidence_artifacts(id)
                ON DELETE SET NULL,
            started_at timestamptz,
            finished_at timestamptz,
            duration_ms bigint CHECK (duration_ms IS NULL OR duration_ms >= 0),
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_verification_check_key
                UNIQUE (verification_run_id, check_key)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_verification_checks_run "
        "ON verification_checks(verification_run_id, check_key)"
    )


def downgrade() -> None:
    from alembic import op

    op.execute("ALTER TABLE repository_snapshots DROP CONSTRAINT IF EXISTS ck_snapshots_source_type")
    op.execute(
        "ALTER TABLE repository_snapshots ADD CONSTRAINT ck_snapshots_source_type "
        "CHECK (source_type IN ('git_provider', 'uploaded_archive'))"
    )
    op.execute("DROP INDEX IF EXISTS idx_verification_checks_run")
    op.execute("DROP TABLE IF EXISTS verification_checks")
    op.execute("DROP INDEX IF EXISTS idx_verification_runs_inv")
    op.execute("DROP TABLE IF EXISTS verification_runs")
    op.execute("DROP INDEX IF EXISTS idx_patches_inv")
    op.execute("DROP TABLE IF EXISTS patches")
    op.execute("DROP INDEX IF EXISTS idx_regression_tests_inv")
    op.execute("DROP TABLE IF EXISTS regression_tests")
