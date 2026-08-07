from logging.config import fileConfig
import os
import sys

from alembic import context
from alembic.util import CommandError
from sqlalchemy import engine_from_config, pool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from backend.app.models import SQLModel  # noqa: E402


config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def database_url() -> str:
    return os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))


def run_migrations_offline() -> None:
    if database_url().startswith("sqlite"):
        raise CommandError("Alembic migrations target PostgreSQL; use DB_AUTO_CREATE=true for local SQLite")
    context.configure(url=database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    if database_url().startswith("sqlite"):
        raise CommandError("Alembic migrations target PostgreSQL; use DB_AUTO_CREATE=true for local SQLite")
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = database_url()
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
