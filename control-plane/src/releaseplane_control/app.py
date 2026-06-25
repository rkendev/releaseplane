"""Control-plane FastAPI app: health, DB lifespan, tracing, metrics, registry.

The lifespan loader opens an async SQLAlchemy engine, verifies connectivity to
Postgres at startup, and stores a sessionmaker on app.state for the registry
routes. A failed connection is logged, not fatal, so the process still serves
liveness and tests run without a database. /healthz reports the recorded DB
status; /metrics exposes Prometheus metrics for the dev stack.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_client import make_asgi_app
from sqlalchemy import text

from .api import eval_datasets, eval_runs, model_configs, policy_bundles, prompts, releases
from .db import make_engine, make_sessionmaker
from .telemetry import configure_tracing

logger = logging.getLogger(__name__)
SERVICE_NAME = "control-plane"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    engine = None
    sessionmaker = None
    db_ok = False
    url = os.environ.get("DATABASE_URL")
    if url:
        engine = make_engine(url)
        sessionmaker = make_sessionmaker(engine)
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            logger.warning("control-plane could not reach the database at startup", exc_info=True)
    app.state.engine = engine
    app.state.sessionmaker = sessionmaker
    app.state.db_ok = db_ok
    yield
    if engine is not None:
        await engine.dispose()


app = FastAPI(title="ReleasePlane Control Plane", lifespan=lifespan)
configure_tracing(app, SERVICE_NAME)
app.mount("/metrics", make_asgi_app())
app.include_router(prompts.router)
app.include_router(model_configs.router)
app.include_router(policy_bundles.router)
app.include_router(releases.router)
app.include_router(eval_datasets.router)
app.include_router(eval_runs.router)


@app.get("/healthz")
async def healthz() -> dict[str, object]:
    return {"status": "ok", "service": SERVICE_NAME, "db": bool(getattr(app.state, "db_ok", False))}
