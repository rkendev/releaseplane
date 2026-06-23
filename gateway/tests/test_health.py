"""Healthcheck test for the gateway service."""

from __future__ import annotations

from fastapi.testclient import TestClient
from releaseplane_gateway.app import app


def test_healthz_returns_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "gateway"
