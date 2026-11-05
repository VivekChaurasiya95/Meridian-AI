"""Dev-only helper: seed (or reset) the scripted demo workspace.

Usage (repo root, venv active, database + object storage running):
    $env:DATABASE_URL="postgresql+psycopg://meridian:meridian@localhost:5435/meridian"
    python scripts/demo_seed.py --email you@example.com
    python scripts/demo_seed.py --reset

Seed creates workspace "Demo" (slug ``demo``) with two projects, one
snapshot each, and one investigation each:

- ``demo-shop`` — a fixable bug: the cart total on / never updates
  because app.js reads a DOM id that does not exist.
- ``demo-ghost`` — a report that cannot be reproduced: it describes a
  /checkout crash, but the snapshot has no checkout route or payment
  code, so the pipeline is expected to reach blocked/inconclusive.

Reset deletes every row the seed created (jobs, investigations, projects,
workspace), in FK-safe order, then exits. Object-storage blobs from demo
uploads are left behind; they are harmless dev residue.

Uses the real service layer (same validation as the API). Not part of
the product; never import this from application code.
"""

import argparse
import io
import pathlib
import sys
import uuid
import zipfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "api"))

import os  # noqa: E402

from sqlalchemy import create_engine, delete, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.models import (  # noqa: E402
    Hypothesis,
    HypothesisEvidence,
    Investigation,
    Job,
    Project,
    User,
    Workspace,
    WorkspaceMember,
)
from app.schemas import InvestigationCreate, ProjectCreate, WorkspaceCreate  # noqa: E402
from app.security import SlidingWindowLimiter  # noqa: E402
from app.services import ingestion as ingestion_service  # noqa: E402
from app.services import investigations as investigation_service  # noqa: E402
from app.services import projects as project_service  # noqa: E402
from app.services import workspaces as workspace_service  # noqa: E402

DEMO_SLUG = "demo"

SHOP_FILES = {
    "index.html": """<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>Demo Shop</title></head>
  <body>
    <h1>Demo Shop</h1>
    <p>Cart total: <span id="totals">$0.00</span></p>
    <button id="add">Add $9.99 item</button>
    <script src="app.js"></script>
  </body>
</html>
""",
    "app.js": """let total = 0;
document.getElementById("add").addEventListener("click", () => {
  total += 9.99;
  // BUG: the span id is "totals", so this throws and the total stalls.
  document.getElementById("total").textContent = "$" + total.toFixed(2);
});
""",
}

GHOST_FILES = {
    "index.html": """<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>Demo Ghost</title></head>
  <body>
    <h1>Demo Ghost</h1>
    <p>A one-page site. There is no checkout and no payment code.</p>
  </body>
</html>
""",
}

SHOP_BUG = (
    "Cart total never updates on /. Clicking Add shows no change and the "
    "console reports a TypeError. Expected: the total grows by $9.99."
)
GHOST_BUG = (
    "Checkout crashes on /checkout with a payment error after entering a "
    "card. Expected: an order confirmation. Note: this snapshot has no "
    "/checkout route and no payment code, so the report cannot be reproduced."
)


def make_zip(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def session_factory():  # type: ignore[no-untyped-def]
    return sessionmaker(
        bind=create_engine(os.environ["DATABASE_URL"]),
        autoflush=False,
        expire_on_commit=False,
    )


def find_user(session, email: str) -> User:  # type: ignore[no-untyped-def]
    user = session.execute(
        select(User).where(User.email == email, User.status == "active")
    ).scalar_one_or_none()
    if user is None:
        print(f"no active user with email {email!r} (sign up first)", file=sys.stderr)
        raise SystemExit(1)
    return user


def reset_demo(session) -> bool:  # type: ignore[no-untyped-def]
    """Delete the demo workspace and everything under it. Returns True when
    anything was removed."""
    workspace = session.execute(
        select(Workspace).where(Workspace.slug == DEMO_SLUG)
    ).scalar_one_or_none()
    if workspace is None:
        print("no demo workspace; nothing to reset")
        return False
    project_ids = list(
        session.execute(
            select(Project.id).where(Project.workspace_id == workspace.id)
        ).scalars()
    )
    inv_ids = []
    if project_ids:
        inv_ids = list(
            session.execute(
                select(Investigation.id).where(Investigation.project_id.in_(project_ids))
            ).scalars()
        )
    # Jobs first: they RESTRICT the workspace row. Stages and executions
    # cascade; job references elsewhere SET NULL.
    session.execute(delete(Job).where(Job.workspace_id == workspace.id))
    session.flush()
    if inv_ids:
        hyp_ids = list(
            session.execute(
                select(Hypothesis.id).where(Hypothesis.investigation_id.in_(inv_ids))
            ).scalars()
        )
        # Evidence links RESTRICT their evidence rows, so links go first;
        # everything else under an investigation cascades.
        if hyp_ids:
            session.execute(
                delete(HypothesisEvidence).where(HypothesisEvidence.hypothesis_id.in_(hyp_ids))
            )
            session.flush()
        session.execute(delete(Investigation).where(Investigation.id.in_(inv_ids)))
        session.flush()
    if project_ids:
        owner = session.execute(
            select(User)
            .join(WorkspaceMember, WorkspaceMember.user_id == User.id)
            .where(
                WorkspaceMember.workspace_id == workspace.id,
                WorkspaceMember.role == "owner",
            )
            .limit(1)
        ).scalar_one_or_none()
        if owner is None:
            print("demo workspace has no owner; cannot remove projects", file=sys.stderr)
            raise SystemExit(1)
        for project_id in project_ids:
            project_service.delete_project(session, owner, project_id)
    session.delete(workspace)
    session.commit()
    print(f"removed demo workspace {workspace.id}")
    return True


def seed_demo(session, user: User) -> None:  # type: ignore[no-untyped-def]
    existing = session.execute(
        select(Workspace).where(Workspace.slug == DEMO_SLUG)
    ).scalar_one_or_none()
    if existing is not None:
        print("demo workspace already exists; run with --reset first", file=sys.stderr)
        raise SystemExit(1)
    limiter = SlidingWindowLimiter(1000, 3600)
    workspace = workspace_service.create_workspace(
        session, user, WorkspaceCreate(name="Demo", slug=DEMO_SLUG)
    )
    print(f"workspace_id={workspace['id']}")
    fixtures = [
        ("demo-shop", "Demo Shop", SHOP_FILES, SHOP_BUG, "/"),
        ("demo-ghost", "Demo Ghost", GHOST_FILES, GHOST_BUG, "/checkout"),
    ]
    for slug, name, files, bug, route in fixtures:
        project = project_service.create_project(
            session,
            user,
            uuid.UUID(workspace["id"]),
            ProjectCreate(name=name, slug=slug, description=f"Scripted demo fixture: {name}."),
        )
        upload = ingestion_service.upload_source(
            session, user, uuid.UUID(project["id"]), f"{slug}.zip", make_zip(files), limiter
        )
        snapshot_id = upload["snapshot"]["id"]
        investigation, _ = investigation_service.create_investigation(
            session,
            user,
            uuid.UUID(project["id"]),
            InvestigationCreate(
                title=f"{name}: scripted demo case",
                bug_report=bug,
                severity="medium",
                repository_snapshot_id=snapshot_id,
                reproduction_context={"route": route},
            ),
            idempotency_key=f"demo-seed-{slug}",
            request_id="demo-seed",
        )
        print(f"project={slug} project_id={project['id']}")
        print(f"  snapshot_id={snapshot_id}")
        print(f"  investigation_id={investigation['id']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed or reset the scripted demo workspace.")
    parser.add_argument("--email", help="existing active user to own the demo workspace")
    parser.add_argument("--reset", action="store_true", help="remove the demo workspace and exit")
    args = parser.parse_args()
    factory = session_factory()
    with factory() as session:
        if args.reset:
            reset_demo(session)
            return
        if not args.email:
            print("seed needs --email of an existing active user", file=sys.stderr)
            raise SystemExit(2)
        seed_demo(session, find_user(session, args.email))


if __name__ == "__main__":
    main()
