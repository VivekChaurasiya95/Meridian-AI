"""Alembic environment: URL from settings, metadata from app models."""

import os
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool

# Allow `alembic` to run from the repository root (prepend_sys_path in
# alembic.ini covers the CLI case; this covers programmatic use from tests).
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_SRC = os.path.join(REPO_ROOT, "services", "api")
if API_SRC not in sys.path:
    sys.path.insert(0, API_SRC)

from app.config import get_settings  # noqa: E402
from app.models import Base  # noqa: E402

config = context.config

# Programmatic runs (tests) may override the URL via config attributes;
# otherwise use settings so secrets never live in alembic.ini.
database_url = config.attributes.get("meridian_database_url")
if not database_url:
    try:
        database_url = get_settings().database_url
    except Exception:
        database_url = config.get_main_option("sqlalchemy.url")
config.set_main_option("sqlalchemy.url", database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
