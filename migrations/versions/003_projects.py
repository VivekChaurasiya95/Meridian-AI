"""003: projects — project registry, snapshots, snapshot file index.

Mirrors public/DATABASE.md §5.4/§5.5 and §6 for ``projects`` and
``repository_snapshots``. Additive M3 columns (documented in
docs/DECISIONS.md D37): ``projects.slug`` (unique per workspace),
snapshot source-traceability columns, and the ``snapshot_files`` index
that powers repository browsing and safe text previews.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "003_projects"
down_revision: str | None = "002_local_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE projects (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE RESTRICT,
            created_by uuid NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            name text NOT NULL CHECK (length(trim(name)) > 0),
            slug text NOT NULL CHECK (slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$'),
            description text,
            source_type text NOT NULL DEFAULT 'uploaded_archive'
                CHECK (source_type IN ('git_provider', 'uploaded_archive')),
            repository_url text,
            provider_installation_id text,
            default_branch text,
            status text NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'archived', 'setup_failed')),
            runtime_profile jsonb NOT NULL DEFAULT '{}'::jsonb
                CHECK (jsonb_typeof(runtime_profile) = 'object'),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_projects_workspace_slug UNIQUE (workspace_id, slug),
            CONSTRAINT ck_project_source_reference CHECK (
                (source_type = 'git_provider' AND repository_url IS NOT NULL)
                OR source_type = 'uploaded_archive'
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_projects_workspace "
        "ON projects(workspace_id, created_at DESC, id DESC)"
    )
    op.execute(
        """
        CREATE TABLE repository_snapshots (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id uuid NOT NULL REFERENCES projects(id) ON DELETE RESTRICT,
            commit_sha text,
            tree_digest text NOT NULL CHECK (tree_digest ~ '^[0-9a-f]{64}$'),
            branch_name text,
            source_ref text,
            source_type text NOT NULL DEFAULT 'uploaded_archive'
                CHECK (source_type IN ('git_provider', 'uploaded_archive')),
            archive_name text,
            archive_size bigint CHECK (archive_size IS NULL OR archive_size >= 0),
            archive_sha256 text
                CHECK (archive_sha256 IS NULL OR archive_sha256 ~ '^[0-9a-f]{64}$'),
            manifest jsonb NOT NULL DEFAULT '{}'::jsonb
                CHECK (jsonb_typeof(manifest) = 'object'),
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_snapshots_project "
        "ON repository_snapshots(project_id, created_at DESC, id DESC)"
    )
    op.execute(
        """
        CREATE TABLE snapshot_files (
            snapshot_id uuid NOT NULL REFERENCES repository_snapshots(id) ON DELETE CASCADE,
            path text NOT NULL CHECK (length(path) > 0 AND length(path) <= 1024),
            size bigint NOT NULL CHECK (size >= 0),
            sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
            is_text boolean NOT NULL DEFAULT false,
            content text,
            PRIMARY KEY (snapshot_id, path)
        )
        """
    )
    op.execute("CREATE INDEX idx_snapshot_files_snapshot ON snapshot_files(snapshot_id, path)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_snapshot_files_snapshot")
    op.execute("DROP TABLE IF EXISTS snapshot_files")
    op.execute("DROP INDEX IF EXISTS idx_snapshots_project")
    op.execute("DROP TABLE IF EXISTS repository_snapshots")
    op.execute("DROP INDEX IF EXISTS idx_projects_workspace")
    op.execute("DROP TABLE IF EXISTS projects")
