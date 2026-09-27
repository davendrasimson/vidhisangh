"""Alembic environment — async-aware, driven by application settings.

The connection URL comes from ``Settings`` (never hard-coded), and
``target_metadata`` is the full application metadata so ``--autogenerate``
sees every model.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import Connection

from app.core.config import settings
from app.db.base import Base  # noqa: F401 — imports all models for metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Migrations use the sync psycopg driver for broad tooling compatibility.
config.set_main_option("sqlalchemy.url", settings.sync_database_url)

target_metadata = Base.metadata


def _run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        include_schemas=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=settings.sync_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Migrations run synchronously via the psycopg driver (robust tooling path).
    engine = create_engine(settings.sync_database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        _run_migrations(connection)
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
