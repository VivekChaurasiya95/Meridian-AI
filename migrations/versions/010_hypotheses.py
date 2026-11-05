"""010: hypotheses — candidate causes with evidence links (M7).

Model-proposed hypotheses persist as data rows plus a many-to-many
join to the evidence that supports, contradicts, or contextualizes
each one. Additive only: no changes to existing tables.
"""

from collections.abc import Sequence

revision: str = "010_hypotheses"
down_revision: str | None = "009_investigations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from alembic import op

    op.execute(
        """
        CREATE TABLE hypotheses (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            investigation_id uuid NOT NULL REFERENCES investigations(id)
                ON DELETE CASCADE,
            created_by_stage_id uuid REFERENCES investigation_stages(id)
                ON DELETE SET NULL,
            tool_run_id uuid REFERENCES tool_runs(id) ON DELETE SET NULL,
            title text NOT NULL CHECK (length(trim(title)) > 0),
            description text NOT NULL CHECK (length(trim(description)) > 0),
            confidence numeric(4, 3) CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
            status text NOT NULL DEFAULT 'proposed'
                CHECK (status IN (
                    'proposed', 'supported', 'refuted', 'inconclusive', 'superseded'
                )),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_hypotheses_inv "
        "ON hypotheses(investigation_id, created_at, id)"
    )
    op.execute(
        """
        CREATE TABLE hypothesis_evidence (
            hypothesis_id uuid NOT NULL REFERENCES hypotheses(id)
                ON DELETE CASCADE,
            evidence_artifact_id uuid NOT NULL REFERENCES evidence_artifacts(id)
                ON DELETE RESTRICT,
            relationship text NOT NULL
                CHECK (relationship IN ('supports', 'contradicts', 'context')),
            note text,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT pk_hypothesis_evidence
                PRIMARY KEY (hypothesis_id, evidence_artifact_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_hypothesis_evidence_evidence "
        "ON hypothesis_evidence(evidence_artifact_id)"
    )


def downgrade() -> None:
    from alembic import op

    op.execute("DROP INDEX IF EXISTS idx_hypothesis_evidence_evidence")
    op.execute("DROP TABLE IF EXISTS hypothesis_evidence")
    op.execute("DROP INDEX IF EXISTS idx_hypotheses_inv")
    op.execute("DROP TABLE IF EXISTS hypotheses")
