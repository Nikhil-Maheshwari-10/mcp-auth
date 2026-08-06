"""
Alembic environment configuration.

Uses the async SQLAlchemy engine from db/engine.py and auto-detects
model metadata from db/models.py for autogenerate support.
"""

import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine

# Make sure the project root is on sys.path so `db` imports work.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

load_dotenv()

from db.models import Base  # noqa: E402 — must come after sys.path fix

# Alembic config object (alembic.ini)
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The metadata object Alembic inspects for autogenerate
target_metadata = Base.metadata


def _get_url() -> str:
    url = os.environ["DATABASE_URL"]
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (SQL script output)."""
    url = _get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations with an async DB connection."""
    connectable = create_async_engine(_get_url())
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
