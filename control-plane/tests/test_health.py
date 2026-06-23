"""Healthcheck test for the control-plane service.

Runs the app through TestClient (which drives the lifespan). With no
DATABASE_URL set, the DB connection is skipped and /healthz still returns 200.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from releaseplane_control.app import app


def test_healthz_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "control-plane"
    assert body["db"] is False
