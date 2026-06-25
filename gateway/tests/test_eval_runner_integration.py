"""End-to-end test for the eval runner. Requires Postgres, makes zero API calls.

Wires the gateway and the control plane in one event loop over the same Postgres
(the same harness as test_invoke_integration), seeds a release carrying the real
invoice schemas, loads the 30-case dataset, and runs the evals runner against a
scripted provider that returns each case's ground truth. A fully-correct provider
gives a fully-passing run, which proves the runner computes and persists the
metrics and the per-tier summary. The provider is in-process, so no model is
called.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

import httpx
import pytest
from releaseplane_evals.generator.invoices import build_cases
from releaseplane_evals.loader import build_dataset_payload
from releaseplane_evals.runner import run_eval
from releaseplane_gateway.app import app as gateway_app
from releaseplane_gateway.invoke import get_provider, get_resolver
from releaseplane_gateway.providers import ModelInvocationConfig, StructuredResult
from releaseplane_gateway.resolution import ReleaseResolver

from examples.invoice_extraction.models import InvoiceExtraction, InvoiceVariables

DATABASE_URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="integration test needs Postgres")

DEVELOPER_PROMPT = "Extract the invoice fields from:\n----\n{{ invoice_pdf_text }}\n----"


class _ScriptedProvider:
    """Returns the ground-truth extraction for whichever case the prompt carries.

    The rendered developer prompt embeds the case's invoice text verbatim, so the
    provider finds the matching case by substring and echoes its expected output.
    This stands in for a perfect model: a fully-passing run, with zero API calls.
    """

    name = "scripted"

    def __init__(self, outputs_by_text: list[tuple[str, dict[str, Any]]]) -> None:
        # Longest text first so a short invoice cannot shadow a longer superset.
        self._outputs = sorted(outputs_by_text, key=lambda pair: len(pair[0]), reverse=True)

    async def generate_structured(
        self,
        *,
        system: str,
        prompt: str,
        model_config: ModelInvocationConfig,
        output_schema: dict[str, Any],
    ) -> StructuredResult:
        for text, output in self._outputs:
            if text in prompt:
                return StructuredResult(
                    output=dict(output),
                    model=model_config.model,
                    input_tokens=1,
                    output_tokens=1,
                    latency_ms=0.0,
                    finish_reason="tool_use",
                )
        raise AssertionError("no scripted output matched the prompt")


def _make_control_plane_app() -> Any:
    from releaseplane_control import models  # noqa: F401  (register tables)
    from releaseplane_control.app import app as cp_app
    from releaseplane_control.db import make_engine, make_sessionmaker

    engine = make_engine(DATABASE_URL or "")
    cp_app.state.engine = engine
    cp_app.state.sessionmaker = make_sessionmaker(engine)
    cp_app.state.db_ok = True
    return cp_app, engine


async def _create_schema(engine: Any) -> None:
    from releaseplane_control.db import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _seed_release(cp: httpx.AsyncClient, prompt_name: str) -> str:
    """Create a draft release carrying the real invoice schemas; return its id."""
    mc = (
        await cp.post(
            "/model-configs",
            json={
                "name": f"mc-{uuid.uuid4().hex[:10]}",
                "provider": "claude",
                "model_name": "claude-sonnet-4-6",
                "model_version_pin": "claude-sonnet-4-6",
                "temperature": 0.0,
                "max_tokens": 4096,
                "timeout_ms": 30000,
                "tool_mode": "structured_output",
                "active": True,
                "cost_per_mtok_input_usd": 3.00,
                "cost_per_mtok_output_usd": 15.00,
            },
        )
    ).json()
    prompt = (
        await cp.post(
            "/prompts",
            json={"name": prompt_name, "team": "ap-platform", "use_case": "ap_invoice_extraction"},
        )
    ).json()
    version = (
        await cp.post(
            f"/prompts/{prompt['id']}/versions",
            json={
                "version": "v1",
                "system_prompt": "You extract invoices.",
                "developer_prompt": DEVELOPER_PROMPT,
                "variables_schema_json": InvoiceVariables.model_json_schema(),
                "output_schema_json": InvoiceExtraction.model_json_schema(),
                "created_by": "phase4-runner-test",
            },
        )
    ).json()
    pb = (
        await cp.post(
            "/policy-bundles",
            json={
                "name": f"pb-{uuid.uuid4().hex[:8]}",
                "version": "v1",
                "rules_json": {},
                "severity_mode": "warn",
            },
        )
    ).json()
    rel = (
        await cp.post(
            "/releases",
            json={
                "prompt_version_id": version["id"],
                "model_config_id": mc["id"],
                "policy_bundle_id": pb["id"],
            },
        )
    ).json()
    return str(rel["id"])


def _scripted_outputs() -> list[tuple[str, dict[str, Any]]]:
    return [(case.pdf_text, case.extraction.model_dump(mode="json")) for case in build_cases()]


def test_runner_scores_and_persists_a_full_run() -> None:
    prompt_name = f"invoice-{uuid.uuid4().hex[:10]}"

    async def run() -> dict[str, Any]:
        cp_app, engine = _make_control_plane_app()
        await _create_schema(engine)
        try:
            cp_transport = httpx.ASGITransport(app=cp_app)
            async with httpx.AsyncClient(transport=cp_transport, base_url="http://cp") as cp:
                release_id = await _seed_release(cp, prompt_name)
                load = (
                    await cp.post(
                        "/eval-datasets",
                        json=build_dataset_payload(f"invoice_v1-{uuid.uuid4().hex[:8]}"),
                    )
                ).json()
                dataset_id = load["dataset"]["id"]

                gateway_app.dependency_overrides[get_resolver] = lambda: ReleaseResolver(cp)
                gateway_app.dependency_overrides[get_provider] = lambda: _ScriptedProvider(
                    _scripted_outputs()
                )
                gw_transport = httpx.ASGITransport(app=gateway_app)
                async with httpx.AsyncClient(transport=gw_transport, base_url="http://gw") as gw:
                    completed = await run_eval(
                        cp_client=cp,
                        gw_client=gw,
                        release_id=release_id,
                        dataset_id=dataset_id,
                    )
                    results = (await cp.get(f"/eval-runs/{completed['id']}/results")).json()
                return {"run": completed, "results": results}
        finally:
            await engine.dispose()

    outcome = asyncio.run(run())
    run_row = outcome["run"]
    results = outcome["results"]

    assert run_row["status"] == "succeeded"
    assert run_row["finished_at"] is not None

    tiers = run_row["summary_json"]["tiers"]
    assert {t: tiers[t]["count"] for t in tiers} == {"1": 10, "2": 10, "3": 10}
    # A perfect provider passes every metric in every tier.
    for tier in tiers.values():
        for metric in ("schema_validity", "arithmetic_consistency", "checksum_match"):
            assert tier[metric]["rate"] == 1.0

    # 30 cases x 3 metrics = 90 result rows, all passing.
    assert len(results) == 90
    assert all(row["pass_fail"] for row in results)

    # The per-case artifact (model output) rides on the schema-validity row.
    schema_rows = [r for r in results if r["metric_name"] == "schema_validity"]
    assert len(schema_rows) == 30
    assert all("model_output" in (r["notes"] or {}) for r in schema_rows)


@pytest.fixture(autouse=True)
def _clear_overrides() -> Any:
    yield
    gateway_app.dependency_overrides.clear()
