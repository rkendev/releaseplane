"""Alembic environment for the async control-plane engine.

asyncpg cannot run Alembic's migration context directly, so online migrations
open an async connection and drive the synchronous migration routine through
connection.run_sync. DATABASE_URL and the secret-file password are resolved the
same way the app does, so `alembic upgrade head` targets the dev-stack Postgres
with no extra configuration.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from releaseplane_control import models  # noqa: F401  (register tables on metadata)
from releaseplane_control.db import Base
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL must be set to run migrations")
    return url


def _connect_args() -> dict[str, str]:
    args: dict[str, str] = {}
    pw_file = os.environ.get("DATABASE_PASSWORD_FILE")
    if pw_file and Path(pw_file).exists():
        args["password"] = Path(pw_file).read_text(encoding="utf-8").strip()
    return args


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(_url(), poolclass=pool.NullPool, connect_args=_connect_args())
    async with engine.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
