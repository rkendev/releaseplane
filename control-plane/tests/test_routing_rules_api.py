"""Integration tests for the routing-rules routes. Require Postgres."""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="integration test needs Postgres"
)


def _seed_model_config(client: TestClient) -> str:
    return str(client.post("/model-configs/seed").json()["id"])


def test_create_list_get_routing_rule(client: TestClient) -> None:
    target = _seed_model_config(client)
    use_case = f"uc-{uuid.uuid4().hex[:10]}"
    body = {
        "use_case": use_case,
        "predicate": {"field": "input_length", "op": "lt", "value": 600},
        "target_model_config_id": target,
        "priority": 10,
    }
    created = client.post("/routing-rules", json=body)
    assert created.status_code == 201
    rule = created.json()
    assert rule["predicate"] == {"field": "input_length", "op": "lt", "value": 600}
    assert rule["target_model_config_id"] == target

    listed = client.get("/routing-rules", params={"use_case": use_case})
    assert listed.status_code == 200
    assert [r["id"] for r in listed.json()] == [rule["id"]]

    got = client.get(f"/routing-rules/{rule['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == rule["id"]


def test_list_orders_by_priority(client: TestClient) -> None:
    target = _seed_model_config(client)
    use_case = f"uc-{uuid.uuid4().hex[:10]}"

    def _make(priority: int) -> None:
        client.post(
            "/routing-rules",
            json={
                "use_case": use_case,
                "predicate": {"field": "input_length", "op": "lt", "value": priority},
                "target_model_config_id": target,
                "priority": priority,
            },
        )

    _make(30)
    _make(10)
    _make(20)
    priorities = [
        r["priority"] for r in client.get("/routing-rules", params={"use_case": use_case}).json()
    ]
    assert priorities == [10, 20, 30]


def test_dangling_target_is_422(client: TestClient) -> None:
    resp = client.post(
        "/routing-rules",
        json={
            "use_case": "x",
            "predicate": {"field": "input_length", "op": "lt", "value": 600},
            "target_model_config_id": str(uuid.uuid4()),
            "priority": 1,
        },
    )
    assert resp.status_code == 422


def test_malformed_predicate_is_422(client: TestClient) -> None:
    target = _seed_model_config(client)
    resp = client.post(
        "/routing-rules",
        json={
            "use_case": "x",
            "predicate": {"field": "__class__", "op": "eq", "value": 1},
            "target_model_config_id": target,
            "priority": 1,
        },
    )
    assert resp.status_code == 422


def test_get_missing_rule_is_404(client: TestClient) -> None:
    assert client.get(f"/routing-rules/{uuid.uuid4()}").status_code == 404
