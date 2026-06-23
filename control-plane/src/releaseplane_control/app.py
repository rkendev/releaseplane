"""Control-plane FastAPI app: health, DB lifespan, tracing, metrics.

The lifespan loader opens an async SQLAlchemy engine and verifies connectivity
to Postgres at startup. A failed connection is logged, not fatal, so the process
still serves liveness and tests run without a database. /healthz reports the
recorded DB status; /metrics exposes Prometheus metrics for the dev stack.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from prometheus_client import make_asgi_app
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from .telemetry import configure_tracing

logger = logging.getLogger(__name__)
SERVICE_NAME = "control-plane"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = None
    db_ok = False
    url = os.environ.get("DATABASE_URL")
    if url:
        # The URL carries user/host/db; the password comes from a mounted secret
        # file so it never lands in the compose file or an env value.
        connect_args: dict[str, str] = {}
        pw_file = os.environ.get("DATABASE_PASSWORD_FILE")
        if pw_file and Path(pw_file).exists():
            connect_args["password"] = Path(pw_file).read_text(encoding="utf-8").strip()
        engine = create_async_engine(url, connect_args=connect_args)
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            logger.warning("control-plane could not reach the database at startup", exc_info=True)
    app.state.engine = engine
    app.state.db_ok = db_ok
    yield
    if engine is not None:
        await engine.dispose()


app = FastAPI(title="ReleasePlane Control Plane", lifespan=lifespan)
configure_tracing(app, SERVICE_NAME)
app.mount("/metrics", make_asgi_app())


@app.get("/healthz")
async def healthz() -> dict[str, object]:
    return {"status": "ok", "service": SERVICE_NAME, "db": bool(getattr(app.state, "db_ok", False))}
