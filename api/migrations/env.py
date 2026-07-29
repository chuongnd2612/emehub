"""Alembic environment.

Resolves the database URL from ``app.config.settings`` (the single source of
truth — ``alembic.ini``'s ``sqlalchemy.url`` is never used) and imports every
ORM model so ``--autogenerate`` sees the full schema.
"""

from __future__ import annotations

from sqlalchemy import engine_from_config, pool

from alembic import context

# Import models so they register on Base.metadata before Alembic inspects it.
from app import models  # noqa: F401
from app.config import settings
from app.db import Base

config = context.config

# Deliberately no `logging.config.fileConfig(...)`: the app owns its logging
# setup and migrations run inside its boot path, so applying alembic.ini's
# logging section here would clobber the handlers the app just installed.

target_metadata = Base.metadata


def get_url() -> str:
    return settings.database_url


def run_migrations_offline() -> None:
    """Emit SQL without a live connection."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    connectable = engine_from_config(
        {"sqlalchemy.url": get_url()},
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite (tests) cannot ALTER a column in place; batch mode rewrites
            # the table instead. No-op on Postgres.
            render_as_batch=connection.dialect.name == "sqlite",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
