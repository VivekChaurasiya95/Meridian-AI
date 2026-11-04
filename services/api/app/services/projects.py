"""Project domain service: workspace-scoped CRUD, snapshots, repository reads.

Every operation resolves the caller's workspace membership first; unknown
or foreign resources answer 404 so existence is never leaked (API.md §3.3).
Role policy (API.md §3.2): reads for all members; create/upload for
owner/admin/developer; update/archive for owner/admin; delete for owner.
Snapshots are immutable: no update or delete endpoints exist for them.
"""

import base64
import datetime as dt
import uuid
from typing import overload

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.envelope import ApiError, access_denied, not_found
from app.models import Project, RepositorySnapshot, SnapshotFile, User, WorkspaceMember
from app.schemas import ProjectCreate, ProjectUpdate

CONTRIBUTOR_ROLES = frozenset({"owner", "admin", "developer"})
MANAGER_ROLES = frozenset({"owner", "admin"})
PROJECT_SORTS = ("updated", "created", "name")
PROJECT_STATUSES = ("active", "archived")


def _iso(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat().replace("+00:00", "Z")


def _short_digest(digest: str | None) -> str | None:
    return digest[:12] if digest else None


def get_membership_role(session: Session, user: User, workspace_id: uuid.UUID) -> str | None:
    row = session.execute(
        select(WorkspaceMember.role).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    ).one_or_none()
    return row[0] if row else None


def require_member(session: Session, user: User, workspace_id: uuid.UUID) -> str:
    role = get_membership_role(session, user, workspace_id)
    if role is None:
        raise not_found("workspace")
    return role


def require_roles(
    session: Session, user: User, workspace_id: uuid.UUID, allowed: frozenset[str]
) -> str:
    role = require_member(session, user, workspace_id)
    if role not in allowed:
        raise access_denied()
    return role


def _get_project(session: Session, user: User, project_id: uuid.UUID) -> tuple[Project, str]:
    """Fetch a project the caller may see, with their workspace role."""
    row = (
        session.execute(
            select(Project, WorkspaceMember.role)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Project.workspace_id)
            .where(Project.id == project_id, WorkspaceMember.user_id == user.id)
        )
    ).one_or_none()
    if row is None:
        raise not_found("project")
    return row[0], row[1]


def _latest_snapshot(session: Session, project_id: uuid.UUID) -> RepositorySnapshot | None:
    return (
        session.execute(
            select(RepositorySnapshot)
            .where(RepositorySnapshot.project_id == project_id)
            .order_by(desc(RepositorySnapshot.created_at), desc(RepositorySnapshot.id))
            .limit(1)
        )
    ).scalar_one_or_none()


def _snapshot_count(session: Session, project_id: uuid.UUID) -> int:
    return (
        session.execute(
            select(func.count()).where(RepositorySnapshot.project_id == project_id)
        )
    ).scalar_one()


def _latest_for_ids(
    session: Session, project_ids: list[uuid.UUID]
) -> dict[uuid.UUID, RepositorySnapshot]:
    """Latest snapshot per project in one query (list-view hydration)."""
    if not project_ids:
        return {}
    subquery = (
        select(
            RepositorySnapshot.project_id,
            func.max(RepositorySnapshot.created_at).label("max_created"),
        )
        .where(RepositorySnapshot.project_id.in_(project_ids))
        .group_by(RepositorySnapshot.project_id)
        .subquery()
    )
    rows = (
        session.execute(
            select(RepositorySnapshot)
            .join(
                subquery,
                and_(
                    RepositorySnapshot.project_id == subquery.c.project_id,
                    RepositorySnapshot.created_at == subquery.c.max_created,
                ),
            )
            .order_by(desc(RepositorySnapshot.id))
        )
    ).scalars()
    latest: dict[uuid.UUID, RepositorySnapshot] = {}
    for snapshot in rows:
        latest.setdefault(snapshot.project_id, snapshot)
    return latest


def create_project(
    session: Session, user: User, workspace_id: uuid.UUID, payload: ProjectCreate
) -> dict:
    """Create a project record. Never executes repository code (API.md §6.5)."""
    role = require_roles(session, user, workspace_id, CONTRIBUTOR_ROLES)
    now = dt.datetime.now(dt.UTC)
    project = Project(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        created_by=user.id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        source_type="uploaded_archive",
        status="active",
        runtime_profile={},
        created_at=now,
        updated_at=now,
    )
    session.add(project)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        if "uq_projects_workspace_slug" not in str(getattr(exc, "orig", exc)):
            raise
        raise ApiError(
            409, "RESOURCE_CONFLICT", "A project with this slug already exists in the workspace."
        ) from exc
    session.refresh(project)
    return serialize_project(project, role)


def list_projects(
    session: Session,
    user: User,
    workspace_id: uuid.UUID,
    limit: int,
    cursor: str | None,
    status: str | None,
    query: str | None,
    sort: str,
) -> tuple[list[dict], str | None]:
    """List workspace projects with filters, allowlisted sorts, cursor pages."""
    role = require_member(session, user, workspace_id)
    if sort not in PROJECT_SORTS:
        raise ApiError(422, "VALIDATION_ERROR", "The sort key is not supported.")
    if status is not None and status not in PROJECT_STATUSES:
        raise ApiError(422, "VALIDATION_ERROR", "The status filter is not supported.")

    stmt = select(Project).where(Project.workspace_id == workspace_id)
    if status is not None:
        stmt = stmt.where(Project.status == status)
    if query:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(Project.name.ilike(f"%{escaped}%", escape="\\"))

    if sort == "name":
        stmt = stmt.order_by(Project.name.asc(), Project.id.asc())
    else:
        order_column = Project.updated_at if sort == "updated" else Project.created_at
        stmt = stmt.order_by(desc(order_column), desc(Project.id))

    if cursor:
        position = decode_cursor(cursor)
        if position is None:
            raise ApiError(422, "VALIDATION_ERROR", "The cursor is invalid.")
        kind, value, project_id = position
        if sort == "name" and kind == "n":
            stmt = stmt.where(
                or_(
                    Project.name > value,
                    and_(Project.name == value, Project.id > project_id),
                )
            )
        elif sort != "name" and kind == "t":
            try:
                stamp = dt.datetime.fromisoformat(value)
            except ValueError:
                raise ApiError(422, "VALIDATION_ERROR", "The cursor is invalid.") from None
            stmt = stmt.where(
                or_(
                    order_column < stamp,
                    and_(order_column == stamp, Project.id < project_id),
                )
            )
        else:
            raise ApiError(422, "VALIDATION_ERROR", "The cursor is invalid for this sort.")

    rows = list(session.execute(stmt.limit(limit + 1)).scalars())
    items = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last = items[-1]
        if sort == "name":
            next_cursor = encode_cursor("n", last.name, last.id)
        else:
            stamp = last.updated_at if sort == "updated" else last.created_at
            next_cursor = encode_cursor("t", stamp.isoformat(), last.id)

    latest = _latest_for_ids(session, [p.id for p in items])
    count_rows = session.execute(
        select(RepositorySnapshot.project_id, func.count())
        .where(RepositorySnapshot.project_id.in_([p.id for p in items]))
        .group_by(RepositorySnapshot.project_id)
    ).all()
    counts = {project_id: total for project_id, total in count_rows}
    return (
        [serialize_project(p, role, latest.get(p.id), counts.get(p.id, 0)) for p in items],
        next_cursor,
    )


def projects_summary(session: Session, user: User, workspace_id: uuid.UUID) -> dict:
    """Honest header metrics, all computed from backend rows (D37)."""
    require_member(session, user, workspace_id)
    total = (
        session.execute(select(func.count()).where(Project.workspace_id == workspace_id))
    ).scalar_one()
    active = (
        session.execute(
            select(func.count()).where(
                Project.workspace_id == workspace_id, Project.status == "active"
            )
        )
    ).scalar_one()
    archived = (
        session.execute(
            select(func.count()).where(
                Project.workspace_id == workspace_id, Project.status == "archived"
            )
        )
    ).scalar_one()
    snapshots_total = (
        session.execute(
            select(func.count())
            .select_from(RepositorySnapshot)
            .join(Project, Project.id == RepositorySnapshot.project_id)
            .where(Project.workspace_id == workspace_id)
        )
    ).scalar_one()
    week_ago = dt.datetime.now(dt.UTC) - dt.timedelta(days=7)
    snapshots_recent = (
        session.execute(
            select(func.count())
            .select_from(RepositorySnapshot)
            .join(Project, Project.id == RepositorySnapshot.project_id)
            .where(
                Project.workspace_id == workspace_id,
                RepositorySnapshot.created_at >= week_ago,
            )
        )
    ).scalar_one()
    # Needs attention: failed setups plus active projects with no snapshot.
    setup_failed = (
        session.execute(
            select(func.count()).where(
                Project.workspace_id == workspace_id, Project.status == "setup_failed"
            )
        )
    ).scalar_one()
    snapshotted_ids = set(
        session.execute(
            select(RepositorySnapshot.project_id)
            .join(Project, Project.id == RepositorySnapshot.project_id)
            .where(Project.workspace_id == workspace_id)
        ).scalars()
    )
    attention_conditions = [
        Project.workspace_id == workspace_id,
        Project.status == "active",
    ]
    if snapshotted_ids:
        attention_conditions.append(Project.id.not_in(snapshotted_ids))
    without_snapshot = (
        session.execute(select(func.count()).where(*attention_conditions))
    ).scalar_one()
    return {
        "total": total,
        "active": active,
        "archived": archived,
        "snapshots_total": snapshots_total,
        "snapshots_recent_7d": snapshots_recent,
        "needs_attention": setup_failed + without_snapshot,
    }


def get_project(session: Session, user: User, project_id: uuid.UUID) -> dict:
    project, role = _get_project(session, user, project_id)
    latest = _latest_snapshot(session, project.id)
    return serialize_project(project, role, latest, _snapshot_count(session, project.id))


def update_project(
    session: Session, user: User, project_id: uuid.UUID, payload: ProjectUpdate
) -> dict:
    project, role = _get_project(session, user, project_id)
    if role not in MANAGER_ROLES:
        raise access_denied()
    project.name = payload.name
    project.description = payload.description
    project.updated_at = dt.datetime.now(dt.UTC)
    session.commit()
    session.refresh(project)
    latest = _latest_snapshot(session, project.id)
    return serialize_project(project, role, latest, _snapshot_count(session, project.id))


def archive_project(session: Session, user: User, project_id: uuid.UUID) -> dict:
    """Archive a project; existing records stay readable (API.md §6.5)."""
    project, role = _get_project(session, user, project_id)
    if role not in MANAGER_ROLES:
        raise access_denied()
    project.status = "archived"
    project.updated_at = dt.datetime.now(dt.UTC)
    session.commit()
    session.refresh(project)
    latest = _latest_snapshot(session, project.id)
    return serialize_project(project, role, latest, _snapshot_count(session, project.id))


def unarchive_project(session: Session, user: User, project_id: uuid.UUID) -> dict:
    """Return an archived project to active (owner/admin)."""
    project, role = _get_project(session, user, project_id)
    if role not in MANAGER_ROLES:
        raise access_denied()
    project.status = "active"
    project.updated_at = dt.datetime.now(dt.UTC)
    session.commit()
    session.refresh(project)
    latest = _latest_snapshot(session, project.id)
    return serialize_project(project, role, latest, _snapshot_count(session, project.id))


def delete_project(session: Session, user: User, project_id: uuid.UUID) -> None:
    """Owner-only hard delete: snapshots and file rows go first in one
    transaction (FK RESTRICT), then the project row itself."""
    project, role = _get_project(session, user, project_id)
    if role != "owner":
        raise access_denied()
    snapshots = list(
        session.execute(
            select(RepositorySnapshot).where(RepositorySnapshot.project_id == project.id)
        ).scalars()
    )
    # Deferred import: storage.py imports this module for record access.
    from app.services import storage as storage_service

    for snapshot in snapshots:
        snapshot.storage_status = "deleting"
        storage_service.delete_snapshot_content(session, snapshot)
        session.delete(snapshot)
    session.delete(project)
    session.commit()


def get_project_record(session: Session, user: User, project_id: uuid.UUID) -> tuple[Project, str]:
    """Project row plus caller role for sibling services (same 404 rule)."""
    return _get_project(session, user, project_id)


def _get_snapshot(
    session: Session, user: User, snapshot_id: uuid.UUID
) -> tuple[RepositorySnapshot, str]:
    """Snapshot the caller may see (membership via the parent project)."""
    row = (
        session.execute(
            select(RepositorySnapshot, WorkspaceMember.role)
            .join(Project, Project.id == RepositorySnapshot.project_id)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Project.workspace_id)
            .where(
                RepositorySnapshot.id == snapshot_id,
                WorkspaceMember.user_id == user.id,
            )
        )
    ).one_or_none()
    if row is None:
        raise not_found("snapshot")
    return row[0], row[1]


def get_snapshot_record(
    session: Session, user: User, snapshot_id: uuid.UUID
) -> tuple[RepositorySnapshot, str]:
    """Snapshot row plus caller role for sibling services (same 404 rule)."""
    return _get_snapshot(session, user, snapshot_id)


def get_workspace_snapshot(
    session: Session, workspace_id: uuid.UUID, snapshot_id: uuid.UUID
) -> RepositorySnapshot:
    """Snapshot row scoped to a workspace (trusted worker authorization).

    Same 404 rule as member access: cross-workspace snapshots do not exist.
    """
    snapshot = (
        session.execute(
            select(RepositorySnapshot)
            .join(Project, Project.id == RepositorySnapshot.project_id)
            .where(
                RepositorySnapshot.id == snapshot_id,
                Project.workspace_id == workspace_id,
            )
        )
    ).scalar_one_or_none()
    if snapshot is None:
        raise not_found("snapshot")
    return snapshot


def _storage_fields(snapshot: RepositorySnapshot) -> dict:
    """Additive M5.1 storage state (never object keys or credentials)."""
    return {
        "storage_status": snapshot.storage_status,
        "storage_bytes": snapshot.storage_bytes,
        "storage_verified_at": _iso(snapshot.storage_verified_at),
        "error_code": snapshot.error_code,
        "error_message": snapshot.error_message,
    }


def serialize_snapshot_detail(snapshot: RepositorySnapshot) -> dict:
    manifest = snapshot.manifest or {}
    return {
        "id": str(snapshot.id),
        "project_id": str(snapshot.project_id),
        "short_hash": _short_digest(snapshot.tree_digest),
        "tree_digest": snapshot.tree_digest,
        "source_type": snapshot.source_type,
        "archive_name": snapshot.archive_name,
        "archive_size": snapshot.archive_size,
        "archive_sha256": snapshot.archive_sha256,
        "file_count": manifest.get("file_count", 0),
        "manifest": manifest,
        "created_at": _iso(snapshot.created_at),
        **_storage_fields(snapshot),
    }


def list_snapshots(
    session: Session, user: User, project_id: uuid.UUID, limit: int, cursor: str | None
) -> tuple[list[dict], str | None]:
    """Cursor-paginated snapshot metadata, newest first (never raw source)."""
    _get_project(session, user, project_id)
    stmt = (
        select(RepositorySnapshot)
        .where(RepositorySnapshot.project_id == project_id)
        .order_by(desc(RepositorySnapshot.created_at), desc(RepositorySnapshot.id))
    )
    if cursor:
        position = decode_cursor(cursor)
        if position is None:
            raise ApiError(422, "VALIDATION_ERROR", "The cursor is invalid.")
        kind, value, _snapshot_id = position
        if kind != "t":
            raise ApiError(422, "VALIDATION_ERROR", "The cursor is invalid for this list.")
        try:
            stamp = dt.datetime.fromisoformat(value)
        except ValueError:
            raise ApiError(422, "VALIDATION_ERROR", "The cursor is invalid.") from None
        stmt = stmt.where(
            or_(
                RepositorySnapshot.created_at < stamp,
                and_(
                    RepositorySnapshot.created_at == stamp,
                    RepositorySnapshot.id < _snapshot_id,
                ),
            )
        )
    rows = list(session.execute(stmt.limit(limit + 1)).scalars())
    items = rows[:limit]
    next_cursor = None
    if len(rows) > limit:
        last = items[-1]
        next_cursor = encode_cursor("t", last.created_at.isoformat(), last.id)
    return ([serialize_snapshot_summary(s) for s in items if s], next_cursor)


def get_snapshot(session: Session, user: User, snapshot_id: uuid.UUID) -> dict:
    snapshot, _role = _get_snapshot(session, user, snapshot_id)
    return serialize_snapshot_detail(snapshot)


def get_tree(
    session: Session,
    user: User,
    snapshot_id: uuid.UUID,
    prefix: str,
    limit: int,
    offset: int,
) -> dict:
    """Flat file listing under ``prefix`` (stable path order, offset page)."""
    snapshot, _role = _get_snapshot(session, user, snapshot_id)
    clean = prefix.strip().strip("/")
    if clean in ("", "."):
        clean = ""
    if ".." in clean.split("/") or clean.startswith("/") or len(clean) > 1024:
        raise ApiError(422, "VALIDATION_ERROR", "The path prefix is invalid.")
    if clean:
        # Escape user text; only the trailing "/%" may wildcard.
        escaped = clean.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%"
    else:
        escaped = "%"
    deeper = escaped + "/%"
    file_filter = [
        SnapshotFile.snapshot_id == snapshot.id,
        SnapshotFile.path.like(escaped, escape="\\"),
        ~SnapshotFile.path.like(deeper, escape="\\"),
    ]
    base = select(SnapshotFile).where(*file_filter).order_by(SnapshotFile.path.asc())
    total = (
        session.execute(
            select(func.count())
            .select_from(SnapshotFile)
            .where(
                SnapshotFile.snapshot_id == snapshot.id,
                SnapshotFile.path.like(escaped, escape="\\"),
            )
        )
    ).scalar_one()
    rows = list(session.execute(base.limit(limit).offset(offset)).scalars())
    entries = [
        {"path": row.path, "size": row.size, "sha256": row.sha256, "is_text": row.is_text}
        for row in rows
    ]
    # Immediate child directories, derived from deeper paths.
    directories: list[str] = []
    seen_dirs: set[str] = set()
    depth = len(clean.split("/")) if clean else 0
    dir_rows = session.execute(
        select(SnapshotFile.path)
        .where(
            SnapshotFile.snapshot_id == snapshot.id,
            SnapshotFile.path.like(escaped, escape="\\"),
        )
        .order_by(SnapshotFile.path.asc())
        .limit(2000)
    ).scalars()
    for path in dir_rows:
        parts = path.split("/")
        if len(parts) > depth + 1:
            child = "/".join(parts[: depth + 1])
            if child not in seen_dirs:
                seen_dirs.add(child)
                directories.append(child)
    return {
        "snapshot_id": str(snapshot.id),
        "prefix": clean,
        "directories": sorted(directories),
        "entries": entries,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


def get_file(session: Session, user: User, snapshot_id: uuid.UUID, path: str) -> dict:
    """Metadata plus safe text preview for one indexed file.

    Only paths present in the snapshot index are servable, so traversal
    outside the snapshot is impossible by construction.
    """
    snapshot, _role = _get_snapshot(session, user, snapshot_id)
    clean = path.strip().strip("/")
    if not clean or ".." in clean.split("/") or len(clean) > 1024:
        raise ApiError(422, "VALIDATION_ERROR", "The file path is invalid.")
    row = (
        session.execute(
            select(SnapshotFile).where(
                SnapshotFile.snapshot_id == snapshot.id, SnapshotFile.path == clean
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise not_found("file")
    return {
        "snapshot_id": str(snapshot.id),
        "path": row.path,
        "size": row.size,
        "sha256": row.sha256,
        "is_text": row.is_text,
        "truncated": row.content is None,
        "content": row.content,
    }


@overload
def serialize_snapshot_summary(snapshot: None) -> None: ...
@overload
def serialize_snapshot_summary(snapshot: RepositorySnapshot) -> dict: ...
def serialize_snapshot_summary(snapshot: RepositorySnapshot | None) -> dict | None:
    if snapshot is None:
        return None
    manifest = snapshot.manifest or {}
    return {
        "id": str(snapshot.id),
        "short_hash": _short_digest(snapshot.tree_digest),
        "tree_digest": snapshot.tree_digest,
        "source_type": snapshot.source_type,
        "archive_name": snapshot.archive_name,
        "archive_size": snapshot.archive_size,
        "file_count": manifest.get("file_count", 0),
        "created_at": _iso(snapshot.created_at),
        **_storage_fields(snapshot),
    }


def serialize_project(
    project: Project,
    role: str,
    latest: RepositorySnapshot | None = None,
    snapshot_count: int = 0,
) -> dict:
    return {
        "id": str(project.id),
        "workspace_id": str(project.workspace_id),
        "name": project.name,
        "slug": project.slug,
        "description": project.description,
        "source_type": project.source_type,
        "repository_url": project.repository_url,
        "default_branch": project.default_branch,
        "status": project.status,
        "runtime_profile": project.runtime_profile or {},
        "role": role,
        "snapshot_count": snapshot_count,
        "latest_snapshot": serialize_snapshot_summary(latest),
        "created_at": _iso(project.created_at),
        "updated_at": _iso(project.updated_at),
    }


def encode_cursor(kind: str, value: str, project_id: uuid.UUID) -> str:
    """Opaque cursor. ``kind`` is ``t`` (ISO timestamp) or ``n`` (name)."""
    raw = f"{kind}|{value}|{project_id}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str) -> tuple[str, str, uuid.UUID] | None:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        kind, value, id_raw = raw.split("|", 2)
        if kind not in ("t", "n"):
            return None
        return kind, value, uuid.UUID(id_raw)
    except (ValueError, TypeError):
        return None
