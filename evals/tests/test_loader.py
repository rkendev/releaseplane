"""Unit tests for the dataset-load payload builder and the HTTP post.

No network and no database: the post is exercised against an httpx MockTransport,
so the path, method, and response handling are covered without a running server.
"""

from __future__ import annotations

import json

import httpx
import pytest
from releaseplane_evals.generator.invoices import SEED
from releaseplane_evals.loader import DATASET_NAME, build_dataset_payload, load_dataset


def _by_path(payload: dict) -> dict[str, dict]:
    return {case["input_path"]: case for case in payload["cases"]}


def test_payload_metadata_and_30_cases() -> None:
    payload = build_dataset_payload()
    assert payload["name"] == DATASET_NAME
    assert payload["generator_seed"] == SEED
    assert len(payload["cases"]) == 30


def test_tier_split_is_ten_each() -> None:
    tiers = [case["tier"] for case in build_dataset_payload()["cases"]]
    assert tiers.count(1) == 10
    assert tiers.count(2) == 10
    assert tiers.count(3) == 10


def test_case_14_ground_truth_and_input_text() -> None:
    case = _by_path(build_dataset_payload())["case_14.pdf"]
    assert case["tier"] == 2
    # Decimals serialize as strings, matching the committed ground-truth JSON.
    assert case["expected_json"]["total"] == "1247.50"
    assert case["expected_json"]["subtotal"] == "1150.00"
    assert "Invoice Number: INV-2026-1140" in case["input_text"]
    assert case["metadata_json"]["case_id"] == "case_14"


def test_case_21_leading_zero_invoice_number_preserved() -> None:
    case = _by_path(build_dataset_payload())["case_21.pdf"]
    assert case["tier"] == 2
    assert case["expected_json"]["invoice_number"] == "007341"


def test_payload_is_deterministic() -> None:
    assert build_dataset_payload() == build_dataset_payload()


@pytest.mark.asyncio
async def test_load_dataset_posts_to_endpoint_and_parses_result() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            201,
            json={
                "dataset": {"name": "invoice_v1", "row_count": 30},
                "cases_total": 30,
                "cases_created": 30,
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://control-plane") as client:
        result = await load_dataset(client, {"name": "invoice_v1", "cases": []})

    assert captured["method"] == "POST"
    assert captured["path"] == "/eval-datasets"
    assert result["cases_created"] == 30


@pytest.mark.asyncio
async def test_load_dataset_raises_on_error_status() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(500, json={"detail": "boom"}))
    async with httpx.AsyncClient(transport=transport, base_url="http://control-plane") as client:
        with pytest.raises(httpx.HTTPStatusError):
            await load_dataset(client, {"name": "x", "cases": []})
