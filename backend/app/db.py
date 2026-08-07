"""Database engine and session helpers for Smriti."""

from contextlib import contextmanager
from collections.abc import Iterator

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from . import models  # noqa: F401 - registers all table models
from .config import settings


DATABASE_URL = settings.database_url
DB_AUTO_CREATE = settings.db_auto_create
_is_sqlite = DATABASE_URL.startswith("sqlite")
engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)
_initialized = False


def init_db() -> None:
    """Create the mapped tables for local development and first boot."""
    global _initialized
    if _initialized or not DB_AUTO_CREATE:
        return
    SQLModel.metadata.create_all(engine)
    if _is_sqlite:
        # Local SQLite is a convenience mode, not the production migration
        # target. Keep existing developer databases usable after additive
        # model changes without weakening the PostgreSQL Alembic path.
        columns = {column["name"] for column in inspect(engine).get_columns("contradictions")}
        additions = {
            "review_decision": "TEXT",
            "reviewer_note": "TEXT",
            "reviewed_at": "DATETIME",
            "reviewed_by": "TEXT",
        }
        with engine.begin() as connection:
            for name, data_type in additions.items():
                if name not in columns:
                    connection.execute(text(f"ALTER TABLE contradictions ADD COLUMN {name} {data_type}"))
    _initialized = True


def check_database() -> bool:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transaction-scoped session for graph nodes and services."""
    init_db()
    with Session(engine, expire_on_commit=False) as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
