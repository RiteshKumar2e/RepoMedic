"""Database engine and session management.

Targets Turso (libSQL) in production via the ``sqlite+libsql`` SQLAlchemy
dialect, and a local SQLite file when ``DATABASE_URL`` is empty so the project
runs with zero external services.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import event, inspect, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_url = settings.sqlalchemy_url
_connect_args: dict = {}
if _url.startswith("sqlite"):
    # FastAPI serves requests on a thread pool; sessions are per-request.
    _connect_args["check_same_thread"] = False

engine: Engine = create_engine(
    _url,
    echo=False,
    pool_pre_ping=True,
    connect_args=_connect_args,
)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """SQLite ignores FK constraints unless explicitly enabled per connection."""
    try:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:  # pragma: no cover - non-SQLite backends
        pass


# Columns added after a database was first created. ``create_all`` only creates
# missing *tables*, so an existing deployment needs the ALTER explicitly. Keep
# entries additive and nullable — this runs on every boot.
_ADDITIVE_COLUMNS: tuple[tuple[str, str, str], ...] = (("users", "password_hash", "TEXT"),)


def _apply_additive_columns() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    for table, column, column_type in _ADDITIVE_COLUMNS:
        if table not in existing_tables:
            continue
        if column in {c["name"] for c in inspector.get_columns(table)}:
            continue
        with engine.begin() as connection:
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"))
        logger.info("database.column_added", table=table, column=column)


def init_db() -> None:
    """Create tables when running without Alembic (dev, tests, demo)."""
    import app.models  # noqa: F401  ensures every table is registered

    SQLModel.metadata.create_all(engine)
    _apply_additive_columns()
    logger.info("database.initialised", dialect=engine.dialect.name, turso=settings.is_turso)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a transactional session."""
    with Session(engine) as session:
        yield session


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context manager for background workers and scripts."""
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
