"""The arithmetic-gate headline, as a committed test. Requires Postgres, zero API.

A prompt regression that hallucinates case_14's total is caught by the arithmetic
metric, drops the tier-2 arithmetic pass rate below 100%, and the eval gate then
blocks promotion. The bad output is injected through a scripted provider (no model
call), so the whole demo runs offline. A clean run over the same release promotes,
which is the contrast that makes the block meaningful.
"""

from __future__ import annotations

import asyncio
import copy
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
HALLUCINATED_CASE_14_TOTAL = "1257.50"  # ground truth is 1247.50


class _ScriptedProvider:
    """Echoes each case's ground truth, optionally hallucinating case_14's total."""

    name = "scripted"

    def __init__(self, *, tamper_case_14: bool) -> None:
        outputs: list[tuple[str, dict[str, Any]]] = []
        for case in build_cases():
            output = case.extraction.model_dump(mode="json")
            if tamper_case_14 and case.case_id == "case_14":
                output = copy.deepcopy(output)
                output["total"] = HALLUCINATED_CASE_14_TOTAL
            outputs.append((case.pdf_text, output))
        self._outputs = sorted(outputs, key=lambda pair: len(pair[0]), reverse=True)

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
                "created_by": "phase4-gate-regression",
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


async def _eval_then_promote(*, tamper_case_14: bool) -> tuple[dict[str, Any], httpx.Response]:
    cp_app, engine = _make_control_plane_app()
    await _create_schema(engine)
    try:
        cp_transport = httpx.ASGITransport(app=cp_app)
        async with httpx.AsyncClient(transport=cp_transport, base_url="http://cp") as cp:
            prompt_name = f"invoice-{uuid.uuid4().hex[:10]}"
            release_id = await _seed_release(cp, prompt_name)
            load = (
                await cp.post(
                    "/eval-datasets",
                    json=build_dataset_payload(f"invoice_v1-{uuid.uuid4().hex[:8]}"),
                )
            ).json()

            gateway_app.dependency_overrides[get_resolver] = lambda: ReleaseResolver(cp)
            gateway_app.dependency_overrides[get_provider] = lambda: _ScriptedProvider(
                tamper_case_14=tamper_case_14
            )
            gw_transport = httpx.ASGITransport(app=gateway_app)
            async with httpx.AsyncClient(transport=gw_transport, base_url="http://gw") as gw:
                run = await run_eval(
                    cp_client=cp,
                    gw_client=gw,
                    release_id=release_id,
                    dataset_id=load["dataset"]["id"],
                )
            promote = await cp.post(f"/releases/{release_id}/promote")
            return run, promote
    finally:
        await engine.dispose()


def test_hallucinated_case_14_blocks_promotion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_GATE_ENFORCED", "true")
    run, promote = asyncio.run(_eval_then_promote(tamper_case_14=True))

    # The run completed; the bad case dropped tier-2 arithmetic below 100%.
    assert run["status"] == "succeeded"
    assert run["summary_json"]["tiers"]["2"]["arithmetic_consistency"]["rate"] < 1.0

    assert promote.status_code == 409
    detail = promote.json()["detail"]
    assert "promotion blocked" in detail
    assert "tier 2 arithmetic_consistency" in detail


def test_clean_run_allows_promotion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_GATE_ENFORCED", "true")
    run, promote = asyncio.run(_eval_then_promote(tamper_case_14=False))

    assert run["summary_json"]["tiers"]["2"]["arithmetic_consistency"]["rate"] == 1.0
    assert promote.status_code == 200
    assert promote.json()["stage"] == "candidate"


@pytest.fixture(autouse=True)
def _clear_overrides() -> Any:
    yield
    gateway_app.dependency_overrides.clear()
