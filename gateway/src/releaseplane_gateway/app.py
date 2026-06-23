"""Gateway FastAPI app: health, tracing, metrics.

The provider adapter (the generate_structured Protocol on the Claude path) is
wired in a later phase; this phase establishes the service surface, tracing, and
the metrics endpoint. /healthz reports liveness; /metrics exposes Prometheus
metrics for the dev stack.
"""

from __future__ import annotations

from fastapi import FastAPI
from prometheus_client import make_asgi_app

from .telemetry import configure_tracing

SERVICE_NAME = "gateway"

app = FastAPI(title="ReleasePlane Gateway")
configure_tracing(app, SERVICE_NAME)
app.mount("/metrics", make_asgi_app())


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}
