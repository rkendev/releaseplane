"""Database wiring for the control plane: engine, session, declarative base.

The password is read from a mounted secret file (DATABASE_PASSWORD_FILE) so it
never lands in the connection URL or an env value, matching the lifespan loader
in app.py. The async engine and sessionmaker are created from DATABASE_URL; the
get_session dependency yields a request-scoped AsyncSession from the sessionmaker
that app.py stores on app.state.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import Request
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base shared by every control-plane model."""


def password_connect_args() -> dict[str, str]:
    """Resolve the DB password from the mounted secret file, if present."""
    connect_args: dict[str, str] = {}
    pw_file = os.environ.get("DATABASE_PASSWORD_FILE")
    if pw_file and Path(pw_file).exists():
        connect_args["password"] = Path(pw_file).read_text(encoding="utf-8").strip()
    return connect_args


def make_engine(url: str) -> AsyncEngine:
    """Create the async engine for the given URL with secret-file password."""
    return create_async_engine(url, connect_args=password_connect_args())


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Build a sessionmaker; expire_on_commit off so response models can read."""
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yield a session from the app-state sessionmaker."""
    sessionmaker: async_sessionmaker[AsyncSession] = request.app.state.sessionmaker
    async with sessionmaker() as session:
        yield session
