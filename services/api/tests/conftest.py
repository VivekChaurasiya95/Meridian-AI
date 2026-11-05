"""Shared fixtures.

Database tests run the real Alembic migrations against ``TEST_DATABASE_URL``
and truncate the M1 tables between tests. When PostgreSQL is unreachable the
DB tests SKIP LOUDLY (never silently): the skip reason names the missing
dependency, and CI always provides Postgres so skips there would be a signal,
not a pass.
"""

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://meridian:meridian@localhost:5432/meridian"
)

import pathlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _alembic_config(database_url: str):  # type: ignore[no-untyped-def]
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    cfg.attributes["meridian_database_url"] = database_url
    return cfg


def _postgres_reachable(database_url: str) -> bool:
    try:
        engine = create_engine(database_url, connect_args={"connect_timeout": 2})
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set; database tests need PostgreSQL.")
    if not _postgres_reachable(url):
        pytest.skip(f"PostgreSQL unreachable; is the database up? ({url!r} not probed)")
    return url


@pytest.fixture(scope="session")
def migrated_db(test_database_url: str) -> str:
    try:
        from alembic import command
    except ImportError:
        pytest.skip("alembic is not installed; database tests need it.")
    command.upgrade(_alembic_config(test_database_url), "head")
    return test_database_url


def _truncate(database_url: str) -> None:
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE job_stages, jobs, snapshot_files, repository_snapshots, projects, "
                "local_credentials, sessions, workspace_members, "
                "security_findings, security_assessments, sandbox_executions, "
                "investigation_reports, investigations, audit_events, "
                "workspaces, users RESTART IDENTITY CASCADE"
            )
        )
    engine.dispose()


def _test_app(database_url: str):  # type: ignore[no-untyped-def]
    from sqlalchemy.orm import sessionmaker

    from app.db import get_db
    from app.main import create_app

    engine = create_engine(database_url)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():  # type: ignore[no-untyped-def]
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    application = create_app()
    application.dependency_overrides[get_db] = override_get_db
    return application, engine


@pytest.fixture()
def client(migrated_db: str):
    """Raw TestClient on the migrated test database, truncated per test."""
    _truncate(migrated_db)
    application, engine = _test_app(migrated_db)
    with TestClient(application) as test_client:
        yield test_client
    engine.dispose()


@pytest.fixture()
def auth_client_factory(migrated_db: str):
    """Build authenticated clients: one signup per email, cookies retained.

    Clients carry `Origin: http://localhost:3000` (the default CORS origin)
    so cookie-authenticated mutations pass the origin check.
    """
    _truncate(migrated_db)
    created: list = []

    def make(
        email: str,
        password: str = "password-1234",
        display_name: str = "Test User",
    ):  # type: ignore[no-untyped-def]
        application, engine = _test_app(migrated_db)
        test_client = TestClient(application, headers={"Origin": "http://localhost:3000"})
        test_client.__enter__()
        created.append((test_client, engine))
        response = test_client.post(
            "/api/v1/auth/signup",
            json={"email": email, "password": password, "display_name": display_name},
        )
        assert response.status_code == 201, response.text
        return test_client

    yield make
    for test_client, engine in created:
        test_client.__exit__(None, None, None)
        engine.dispose()


@pytest.fixture()
def auth_client(auth_client_factory):  # type: ignore[no-untyped-def]
    """Single authenticated client (owner@example.com)."""
    return auth_client_factory("owner@example.com")


@pytest.fixture()
def db_session_factory(migrated_db: str):  # type: ignore[no-untyped-def]
    """Direct SQLAlchemy sessions for service-level tests (same test DB)."""
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(migrated_db)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    engine.dispose()
