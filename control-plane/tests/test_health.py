"""Healthcheck test for the control-plane service.

Runs the app through TestClient (which drives the lifespan). The reported db
flag follows whether a database is configured: false with no DATABASE_URL set,
true when the integration database is present (as in CI). /healthz returns 200
either way.
"""

from __future__ import annotations

import os

from fastapi.testclient import TestClient
from releaseplane_control.app import app


def test_healthz_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "control-plane"
    assert body["db"] is bool(os.environ.get("DATABASE_URL"))
