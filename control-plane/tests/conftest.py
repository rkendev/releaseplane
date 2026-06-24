"""Shared fixtures for the control-plane tests.

Unit tests need no database. Integration tests need Postgres and are guarded by
a DATABASE_URL skip marker the modules apply themselves. To stop those tests
from skipping unnoticed in CI, REQUIRE_DB=1 turns a missing DATABASE_URL into a
hard error. The schema is built once per session with create_all (additive; it
does not drop), so repeated local runs against the dev stack stay safe.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

DATABASE_URL = os.environ.get("DATABASE_URL")


def pytest_configure(config: pytest.Config) -> None:
    if os.environ.get("REQUIRE_DB") and not DATABASE_URL:
        raise pytest.UsageError("REQUIRE_DB is set but DATABASE_URL is missing")


@pytest.fixture(scope="session", autouse=True)
def _create_schema() -> Iterator[None]:
    if not DATABASE_URL:
        yield
        return
    from releaseplane_control import models  # noqa: F401  (register tables)
    from releaseplane_control.db import Base, make_engine

    async def _create() -> None:
        engine = make_engine(DATABASE_URL)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    asyncio.run(_create())
    yield


@pytest.fixture
def client() -> Iterator[TestClient]:
    from releaseplane_control.app import app

    with TestClient(app) as test_client:
        yield test_client
