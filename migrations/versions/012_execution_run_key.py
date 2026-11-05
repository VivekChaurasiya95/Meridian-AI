"""012: execution run key for many container runs per job (M8).

M6 ran one container per job attempt, so (job_id, attempt, scanner)
was unique. M8 verification runs one container per regression test
inside a single job attempt, so executions need a run discriminator.
The scanner CHECK is untouched: preflight semantics do not change.
Existing rows keep run_key '' (the reproduction run).

Also drops the 003-era auto-named snapshot source_type CHECK that 011
missed (it dropped a name that never existed): the leftover narrow
constraint rejects the 'patched_tree' rows 011 was built for.

Downgrade note: fails if duplicate (job, attempt, scanner) rows were
created while 012 was active — restore by deleting the newer
verification rows first.
"""

from collections.abc import Sequence

revision: str = "012_execution_run_key"
down_revision: str | None = "011_patches_verification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from alembic import op

    op.execute("ALTER TABLE sandbox_executions ADD COLUMN run_key text NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE sandbox_executions DROP CONSTRAINT uq_sandbox_exec_job_attempt")
    op.execute(
        "ALTER TABLE sandbox_executions ADD CONSTRAINT uq_sandbox_exec_job_attempt_run "
        "UNIQUE (job_id, attempt, scanner, run_key)"
    )
    # 011 added the wide ck_snapshots_source_type but never removed the
    # 003-era narrow CHECK; drop every auto-named sibling by catalog scan
    # (plain names differ per database history: ..._check, ..._check1).
    op.execute(
        """
        DO $$DECLARE r record; BEGIN
          FOR r IN
            SELECT conname FROM pg_constraint
            WHERE conrelid = 'repository_snapshots'::regclass
              AND conname LIKE 'repository_snapshots_source_type_check%'
          LOOP
            EXECUTE format('ALTER TABLE repository_snapshots DROP CONSTRAINT %I', r.conname);
          END LOOP;
        END$$;
        """
    )
    op.execute(
        "ALTER TABLE repository_snapshots "
        "DROP CONSTRAINT IF EXISTS ck_snapshots_source_type_narrow"
    )


def downgrade() -> None:
    from alembic import op

    op.execute(
        "ALTER TABLE sandbox_executions DROP CONSTRAINT uq_sandbox_exec_job_attempt_run"
    )
    op.execute(
        "ALTER TABLE sandbox_executions ADD CONSTRAINT uq_sandbox_exec_job_attempt "
        "UNIQUE (job_id, attempt, scanner)"
    )
    op.execute("ALTER TABLE sandbox_executions DROP COLUMN run_key")
    op.execute(
        "ALTER TABLE repository_snapshots ADD CONSTRAINT ck_snapshots_source_type_narrow "
        "CHECK (source_type IN ('git_provider', 'uploaded_archive'))"
    )
