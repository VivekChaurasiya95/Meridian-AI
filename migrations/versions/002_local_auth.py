"""002: local auth — credentials, sessions, local-email uniqueness."""

from collections.abc import Sequence

from alembic import op

revision: str = "002_local_auth"
down_revision: str | None = "001_identity_tenancy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE local_credentials (
            user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            password_hash text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE sessions (
            token_hash text PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            expires_at timestamptz NOT NULL,
            revoked_at timestamptz,
            CHECK (expires_at > created_at)
        )
        """
    )
    op.execute("CREATE INDEX idx_sessions_user ON sessions(user_id)")
    op.execute(
        "CREATE UNIQUE INDEX uq_users_local_email "
        "ON users(lower(email)) WHERE auth_provider = 'local'"
    )
    op.execute(
        "ALTER TABLE users ADD CONSTRAINT ck_users_local_email "
        "CHECK (auth_provider <> 'local' OR email IS NOT NULL)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_local_email")
    op.execute("DROP INDEX IF EXISTS uq_users_local_email")
    op.execute("DROP INDEX IF EXISTS idx_sessions_user")
    op.execute("DROP TABLE IF EXISTS sessions")
    op.execute("DROP TABLE IF EXISTS local_credentials")
