"""015: hypothesis reviews (M7-FINISH, user annotations on hypotheses).

Additive only: one row per review, owned by the hypothesis (deleted
with it). History is append-only — a new review supersedes the
previous one as the effective verdict but never overwrites it.
"""

from collections.abc import Sequence

revision: str = "015_hypothesis_reviews"
down_revision: str | None = "014_reports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from alembic import op

    op.execute(
        """
        CREATE TABLE hypothesis_reviews (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            hypothesis_id uuid NOT NULL REFERENCES hypotheses(id) ON DELETE CASCADE,
            reviewer_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
            verdict text NOT NULL CHECK (
                verdict IN ('useful', 'rejected', 'needs_evidence')
            ),
            note text,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_hypothesis_reviews_hyp "
        "ON hypothesis_reviews(hypothesis_id, created_at, id)"
    )


def downgrade() -> None:
    from alembic import op

    op.execute("DROP INDEX IF EXISTS idx_hypothesis_reviews_hyp")
    op.execute("DROP TABLE IF EXISTS hypothesis_reviews")
