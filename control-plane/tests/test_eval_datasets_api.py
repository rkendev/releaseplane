"""Integration tests for the eval-dataset load/read routes. Require Postgres.

These drive the real generator payload through the endpoint, so they double as a
check that the control plane accepts the evals package's load shape end to end.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from releaseplane_evals.loader import build_dataset_payload

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="integration test needs Postgres"
)


def _unique_name() -> str:
    import uuid

    return f"invoice_v1-{uuid.uuid4().hex[:10]}"


def test_load_lands_30_cases_with_tier_split(client: TestClient) -> None:
    payload = build_dataset_payload(_unique_name())

    created = client.post("/eval-datasets", json=payload)
    assert created.status_code == 201
    body = created.json()
    assert body["cases_total"] == 30
    assert body["cases_created"] == 30
    assert body["dataset"]["row_count"] == 30

    dataset_id = body["dataset"]["id"]
    cases = client.get(f"/eval-datasets/{dataset_id}/cases").json()
    assert len(cases) == 30
    tiers = [case["tier"] for case in cases]
    assert tiers.count(1) == 10
    assert tiers.count(2) == 10
    assert tiers.count(3) == 10

    case_14 = next(c for c in cases if c["input_path"] == "case_14.pdf")
    assert case_14["expected_json"]["total"] == "1247.50"
    assert "Invoice Number: INV-2026-1140" in case_14["input_text"]


def test_reload_is_idempotent(client: TestClient) -> None:
    payload = build_dataset_payload(_unique_name())

    first = client.post("/eval-datasets", json=payload)
    assert first.status_code == 201
    assert first.json()["cases_created"] == 30
    dataset_id = first.json()["dataset"]["id"]

    again = client.post("/eval-datasets", json=payload)
    assert again.status_code == 200
    assert again.json()["cases_created"] == 0
    # Same dataset row, no duplicate cases.
    assert again.json()["dataset"]["id"] == dataset_id
    assert len(client.get(f"/eval-datasets/{dataset_id}/cases").json()) == 30


def test_cases_for_unknown_dataset_is_404(client: TestClient) -> None:
    import uuid

    missing = client.get(f"/eval-datasets/{uuid.uuid4()}/cases")
    assert missing.status_code == 404
