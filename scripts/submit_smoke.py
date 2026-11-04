"""Dev-only helper: queue one sandbox_smoke job for a project's latest READY snapshot.

Usage (repo root, venv active):
    $env:DATABASE_URL="postgresql+psycopg://meridian:meridian@localhost:5435/meridian"
    python scripts/submit_smoke.py <project-slug>

Uses the real submit_job service (same validation as the API). Not part of
the product; never import this from application code.
"""

import os
import pathlib
import sys
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models import Project, RepositorySnapshot, User, WorkspaceMember  # noqa: E402
from app.services import jobs as job_service  # noqa: E402


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: python scripts/submit_smoke.py <project-slug>", file=sys.stderr)
        raise SystemExit(2)
    slug = sys.argv[1]
    factory = sessionmaker(
        bind=create_engine(os.environ["DATABASE_URL"]),
        autoflush=False,
        expire_on_commit=False,
    )
    with factory() as session:
        project = session.execute(
            select(Project).where(Project.slug == slug)
        ).scalar_one_or_none()
        if project is None:
            print(f"no project with slug {slug!r}", file=sys.stderr)
            raise SystemExit(1)
        member = session.execute(
            select(User)
            .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
            .where(
                WorkspaceMember.workspace_id == project.workspace_id,
                WorkspaceMember.role.in_(("owner", "admin", "developer")),
            )
            .limit(1)
        ).scalar_one_or_none()
        if member is None:
            print("project workspace has no contributing member", file=sys.stderr)
            raise SystemExit(1)
        snapshot = session.execute(
            select(RepositorySnapshot)
            .where(
                RepositorySnapshot.project_id == project.id,
                RepositorySnapshot.storage_status == "ready",
            )
            .order_by(RepositorySnapshot.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if snapshot is None:
            print("project has no READY snapshot yet", file=sys.stderr)
            raise SystemExit(1)
        job, created = job_service.submit_job(
            session,
            member,
            project.workspace_id,
            "sandbox_smoke",
            {"snapshot_id": str(snapshot.id)},
            idempotency_key=f"smoke-{uuid.uuid4().hex[:12]}",
        )
        print(f"job_id={job['id']} created={created}")
        print(f"workspace_id={project.workspace_id}")
        print(f"snapshot_id={snapshot.id} tree={snapshot.tree_digest[:12]}")


if __name__ == "__main__":
    main()
