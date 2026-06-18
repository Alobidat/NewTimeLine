"""Alembic environment. Uses the sync DB URL from chronos_core.settings and the ORM
metadata from chronos_core.models (single source of truth for the schema)."""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from chronos_core.db.base import Base
from chronos_core.settings import get_settings

# Importing the models package registers every table on Base.metadata.
import chronos_core.models  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().sync_database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a DB connection."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live DB."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata, compare_type=True
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
