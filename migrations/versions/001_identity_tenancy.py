"""001: identity + tenancy (users, workspaces, workspace_members).

Raw SQL mirrors public/DATABASE.md §6 verbatim for these tables so the
migration and the specification cannot drift. Projects and later tables arrive
in their own milestone migrations (docs/DECISIONS.md C6).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "001_identity_tenancy"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute(
        """
        CREATE TABLE users (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            auth_provider text NOT NULL,
            provider_subject text NOT NULL,
            email text,
            display_name text,
            avatar_url text,
            status text NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'disabled', 'deletion_pending')),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_users_provider_subject UNIQUE (auth_provider, provider_subject)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE workspaces (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            name text NOT NULL CHECK (length(trim(name)) > 0),
            slug text NOT NULL UNIQUE CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
            created_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE workspace_members (
            workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role text NOT NULL CHECK (role IN ('owner', 'admin', 'developer', 'viewer')),
            joined_at timestamptz NOT NULL DEFAULT now(),
            invited_by uuid REFERENCES users(id) ON DELETE SET NULL,
            PRIMARY KEY (workspace_id, user_id)
        )
        """
    )
    op.execute("CREATE INDEX idx_workspace_members_user ON workspace_members(user_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_workspace_members_user")
    op.execute("DROP TABLE IF EXISTS workspace_members")
    op.execute("DROP TABLE IF EXISTS workspaces")
    op.execute("DROP TABLE IF EXISTS users")
