"""Integration tests for the policy-events routes. Require Postgres."""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="integration test needs Postgres"
)


def test_create_and_list_by_request_id(client: TestClient) -> None:
    request_id = str(uuid.uuid4())
    created = client.post(
        "/policy-events",
        json={
            "request_id": request_id,
            "rule_id": "arithmetic_consistency",
            "outcome": "failed",
            "detail_json": {"total_matches_subtotal_plus_tax": False},
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["request_id"] == request_id
    assert body["rule_id"] == "arithmetic_consistency"

    listed = client.get("/policy-events", params={"request_id": request_id})
    assert listed.status_code == 200
    rows = listed.json()
    assert [r["id"] for r in rows] == [body["id"]]


def test_rule_id_is_optional(client: TestClient) -> None:
    resp = client.post(
        "/policy-events",
        json={"request_id": str(uuid.uuid4()), "outcome": "failed", "detail_json": {}},
    )
    assert resp.status_code == 201
    assert resp.json()["rule_id"] is None
