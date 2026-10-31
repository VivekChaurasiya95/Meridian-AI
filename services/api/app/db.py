"""Database engine and session management (sync SQLAlchemy 2.x, psycopg).

The engine is created lazily so importing the application (e.g. for
``/health/live`` checks or pure unit tests) never requires a live database.
"""

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Return the process-wide engine, creating it on first use."""
    global _session_factory
    if _session_factory is None:
        engine = create_engine(
            get_settings().database_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 3},
        )
        _session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    engine = _session_factory.kw["bind"]
    assert isinstance(engine, Engine)
    return engine


def get_session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def check_database(engine: Engine | None = None) -> bool:
    """Return True when a trivial query succeeds; never raise or leak details."""
    try:
        target = engine or get_engine()
        with target.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
