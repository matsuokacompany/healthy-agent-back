from logging.config import fileConfig
import os
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def load_environment() -> None:
    """
    Load local dotenv files only as a fallback.

    Production/Supabase deploys must provide DATABASE_URL directly in the
    process environment. Development may keep using .env.dev for the local
    Docker PostgreSQL service.
    """
    if os.getenv("DATABASE_URL"):
        return

    env = os.getenv("ENV", "dev").lower()
    dotenv_file = ".env.dev" if env in {"dev", "development", "local"} else ".env"
    dotenv_path = Path(dotenv_file)

    if dotenv_path.exists():
        load_dotenv(dotenv_path)


load_environment()

from app.db.base import Base  # noqa: E402

target_metadata = Base.metadata


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is required to run Alembic migrations. "
            "Production must provide the Supabase connection string through DATABASE_URL."
        )
    return database_url


config.set_main_option("sqlalchemy.url", get_database_url())


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
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
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
