"""Database engine and session helpers for Smriti."""

from contextlib import contextmanager
from collections.abc import Iterator
import os

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from . import models  # noqa: F401 - registers all table models
from .config import settings


def normalize_database_url(url: str) -> str:
    """Prefer the installed psycopg v3 driver for plain PostgreSQL URLs."""
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    return url


DATABASE_URL = normalize_database_url(settings.database_url)
DB_AUTO_CREATE = settings.db_auto_create
_is_sqlite = DATABASE_URL.startswith("sqlite")
engine_options = {
    "echo": False,
    "pool_pre_ping": True,
}
if not _is_sqlite:
    engine_options.update(
        pool_size=max(1, int(os.getenv("DB_POOL_SIZE", "5"))),
        max_overflow=max(0, int(os.getenv("DB_MAX_OVERFLOW", "10"))),
        pool_timeout=max(1, int(os.getenv("DB_POOL_TIMEOUT_SECONDS", "30"))),
    )
engine = create_engine(
    DATABASE_URL,
    **engine_options,
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
        patient_columns = {column["name"] for column in inspect(engine).get_columns("patients")}
        ingestion_columns = {column["name"] for column in inspect(engine).get_columns("ingestion_jobs")}
        ingestion_additions = {
            "filename": "TEXT NOT NULL DEFAULT 'report'",
            "content_type": "TEXT NOT NULL DEFAULT 'application/octet-stream'",
            "use_fixture": "BOOLEAN NOT NULL DEFAULT 0",
            "pii_redactions": "INTEGER NOT NULL DEFAULT 0",
            "pii_provider": "TEXT NOT NULL DEFAULT 'unknown'",
        }
        with engine.begin() as connection:
            for name, data_type in additions.items():
                if name not in columns:
                    connection.execute(text(f"ALTER TABLE contradictions ADD COLUMN {name} {data_type}"))
            if "external_subject" not in patient_columns:
                connection.execute(text("ALTER TABLE patients ADD COLUMN external_subject TEXT"))
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_patients_external_subject "
                    "ON patients (external_subject)"
                )
            )
            for name, data_type in ingestion_additions.items():
                if name not in ingestion_columns:
                    connection.execute(text(f"ALTER TABLE ingestion_jobs ADD COLUMN {name} {data_type}"))
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
