"""Drive a release over a dataset and persist a scored eval run.

The runner is the orchestrator for decision D-RUNNER-HOME (the evals package owns
the loop; the control plane owns the tables). For each case it calls the gateway
POST /invoke (decision D-EVAL-CALL: score the real resolve -> render -> provider
path), scores the output with the three metric scorers, and writes the per-case
results plus a per-tier summary back through the control-plane API. The provider
is whatever the gateway is configured with, so tests run this on DummyProvider
and make zero API calls; only a deliberate GATEWAY_PROVIDER=claude run spends.

The full per-case model output is attached to the schema-validity result's notes
as the per-case artifact (decision D-ARTIFACTS: Postgres JSONB); the input text
already lives on eval_cases, so it is not duplicated.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import httpx

from .scorers import (
    ARITHMETIC_CONSISTENCY,
    CHECKSUM_MATCH,
    SCHEMA_VALIDITY,
    MetricResult,
    score_case,
)

INVOICE_VARIABLE = "invoice_pdf_text"
METRIC_ORDER = (SCHEMA_VALIDITY, ARITHMETIC_CONSISTENCY, CHECKSUM_MATCH)


def summarize(scored: list[tuple[int, dict[str, bool]]]) -> dict[str, Any]:
    """Aggregate per-case pass/fail into per-tier, per-metric pass rates.

    scored is a list of (tier, {metric_name: passed}). The shape the gate reads:
    {"tiers": {"1": {"count": n, "schema_validity": {"passed", "total", "rate"},
    ...}}}.
    """
    by_tier: dict[int, list[dict[str, bool]]] = defaultdict(list)
    for tier, metrics in scored:
        by_tier[tier].append(metrics)

    tiers: dict[str, Any] = {}
    for tier, cases in sorted(by_tier.items()):
        count = len(cases)
        tier_summary: dict[str, Any] = {"count": count}
        for metric_name in METRIC_ORDER:
            passed = sum(1 for case in cases if case.get(metric_name))
            tier_summary[metric_name] = {
                "passed": passed,
                "total": count,
                "rate": passed / count if count else 0.0,
            }
        tiers[str(tier)] = tier_summary
    return {"tiers": tiers}


def _result_rows(
    case_id: str, output: dict[str, Any], metrics: list[MetricResult]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for metric in metrics:
        notes = dict(metric.detail)
        if metric.name == SCHEMA_VALIDITY:
            # Per-case artifact: the raw model output, kept once per case.
            notes["model_output"] = output
        rows.append(
            {
                "case_id": case_id,
                "metric_name": metric.name,
                "metric_value": metric.value,
                "pass_fail": metric.passed,
                "notes": notes,
            }
        )
    return rows


async def _invoke(
    gw_client: httpx.AsyncClient, *, prompt_name: str, release_id: str, input_text: str
) -> dict[str, Any]:
    response = await gw_client.post(
        "/invoke",
        json={
            "prompt_name": prompt_name,
            "release_id": release_id,
            "variables": {INVOICE_VARIABLE: input_text},
        },
    )
    response.raise_for_status()
    output: dict[str, Any] = response.json()["output"]
    return output


async def run_eval(
    *,
    cp_client: httpx.AsyncClient,
    gw_client: httpx.AsyncClient,
    release_id: str,
    dataset_id: str,
) -> dict[str, Any]:
    """Run the eval and return the completed eval-run record.

    Opens a run, scores every case through the gateway, and completes the run
    with all results and the per-tier summary. If a gateway call fails, the run
    is completed with status failed and whatever was scored so far, so a broken
    run is recorded (and non-passing to the gate) rather than left dangling.
    """
    resolved = (await cp_client.get(f"/releases/{release_id}/resolved")).raise_for_status()
    resolved_body = resolved.json()
    prompt_name = resolved_body["prompt_name"]
    output_schema = resolved_body["output_schema_json"]

    cases_resp = await cp_client.get(f"/eval-datasets/{dataset_id}/cases")
    cases_resp.raise_for_status()
    cases = cases_resp.json()

    run_resp = await cp_client.post(
        "/eval-runs", json={"release_id": release_id, "dataset_id": dataset_id}
    )
    run_resp.raise_for_status()
    run_id = run_resp.json()["id"]

    results: list[dict[str, Any]] = []
    scored: list[tuple[int, dict[str, bool]]] = []
    status = "succeeded"
    try:
        for case in cases:
            output = await _invoke(
                gw_client,
                prompt_name=prompt_name,
                release_id=release_id,
                input_text=case["input_text"],
            )
            metrics = score_case(
                output=output, expected=case["expected_json"], output_schema=output_schema
            )
            results.extend(_result_rows(case["id"], output, metrics))
            scored.append((case["tier"], {m.name: m.passed for m in metrics}))
    except httpx.HTTPError:
        status = "failed"

    summary = summarize(scored)
    completed = await cp_client.post(
        f"/eval-runs/{run_id}/complete",
        json={"status": status, "summary_json": summary, "results": results},
    )
    completed.raise_for_status()
    body: dict[str, Any] = completed.json()
    return body
