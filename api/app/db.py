"""Database engine, session factory and declarative base.

Postgres is the deployment target (``EMEHUB_DATABASE_URL``). SQLite is supported
only so the test suite can build a throwaway database per test — every migration
must therefore stay dialect-portable (no JSONB, no server-side ``gen_random_uuid``).

Schema changes go through Alembic, always. ``run_migrations`` is called from the
FastAPI lifespan so a container boot brings the schema to ``head`` on its own.
"""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone

from sqlalchemy import DateTime, Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, mapped_column, sessionmaker
from sqlalchemy.types import TypeDecorator

from app.config import API_DIR, settings


def _connect_args(url: str) -> dict:
    """SQLite (tests only) needs ``check_same_thread=False``; Postgres uses a
    normal pooled connection with no overrides."""
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


engine = create_engine(
    settings.database_url,
    connect_args=_connect_args(settings.database_url),
    pool_pre_ping=True,
    echo=False,
)

SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
)


@event.listens_for(Engine, "connect")
def _sqlite_pragmas(dbapi_connection, _connection_record):  # noqa: ANN001
    """WAL + a busy timeout on every SQLite connection. No-op on Postgres.

    Audit writes open their own short-lived session while a request session is
    still open; without WAL the second connection would hit "database is
    locked". Registered on the Engine class so the test suite's per-test engine
    is covered too.
    """
    import sqlite3

    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class UTCDateTime(TypeDecorator):
    """Timezone-aware UTC datetime, stored naive so SQLite and Postgres agree."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):  # noqa: ANN001
        if value is None:
            return None
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value: datetime | None, dialect):  # noqa: ANN001
        if value is None:
            return None
        return value.replace(tzinfo=timezone.utc)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def timestamp_column(**kwargs):  # noqa: ANN003, ANN201
    """Created/updated column with a UTC default."""
    return mapped_column(UTCDateTime, default=utcnow, **kwargs)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a request-scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations() -> None:
    """Apply every Alembic migration up to ``head`` against the current DB.

    Used at API boot (``main.lifespan``) and by the test fixture that builds each
    test's isolated database — schema creation always goes through the same
    migration path rather than an ad-hoc ``create_all``.
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(cfg, "head")


def init_db() -> None:
    """Bring the schema to head. No data backfills — the hub starts empty."""
    run_migrations()
