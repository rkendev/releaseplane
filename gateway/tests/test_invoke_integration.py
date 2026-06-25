"""Integration test for POST /invoke against a real registry. Requires Postgres.

This is the D-RESOLVE contract end to end: the gateway resolves the active
release through the control-plane HTTP API (here an in-process ASGI transport
over the same Postgres) and calls DummyProvider, so the suite makes zero API
calls. Everything runs in one event loop because the asyncpg engine is bound to
the loop that created it; a second TestClient loop would detach its connections.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

import httpx
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from releaseplane_gateway.app import app as gateway_app
from releaseplane_gateway.invoke import get_provider, get_resolver
from releaseplane_gateway.providers import DummyProvider
from releaseplane_gateway.resolution import ReleaseResolver

DATABASE_URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="integration test needs Postgres")

DUMMY_OUTPUT = {"vendor_name": "Riverside Office Supplies", "total": "542.50"}

VARIABLES_SCHEMA = {
    "type": "object",
    "properties": {"invoice_pdf_text": {"type": "string"}},
    "required": ["invoice_pdf_text"],
}
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"vendor_name": {"type": "string"}, "total": {"type": "string"}},
    "required": ["vendor_name", "total"],
}


def _make_control_plane_app() -> Any:
    """Build the control-plane app with a sessionmaker bound to this event loop.

    ASGITransport does not run lifespan events, so state is wired by hand here.
    """
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


async def _seed_active_release(cp: httpx.AsyncClient, prompt_name: str) -> str:
    """Create config + prompt + version + bundle + release and promote to active."""
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
                "developer_prompt": "Extract from:\n----\n{{ invoice_pdf_text }}\n----",
                "variables_schema_json": VARIABLES_SCHEMA,
                "output_schema_json": OUTPUT_SCHEMA,
                "created_by": "phase3-integration",
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
    await cp.post(f"/releases/{rel['id']}/promote")
    await cp.post(f"/releases/{rel['id']}/promote")
    return str(rel["id"])


def _install_gateway(cp_app: Any) -> None:
    transport = httpx.ASGITransport(app=cp_app)
    client = httpx.AsyncClient(transport=transport, base_url="http://control-plane")
    gateway_app.dependency_overrides[get_resolver] = lambda: ReleaseResolver(client)
    gateway_app.dependency_overrides[get_provider] = lambda: DummyProvider(output=DUMMY_OUTPUT)


def _exporter() -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    trace.get_tracer_provider().add_span_processor(SimpleSpanProcessor(exporter))  # type: ignore[attr-defined]
    return exporter


async def _post_invoke(body: dict[str, Any]) -> httpx.Response:
    transport = httpx.ASGITransport(app=gateway_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as gw:
        return await gw.post("/invoke", json=body)


def test_invoke_resolves_active_release_and_emits_span() -> None:
    exporter = _exporter()
    prompt_name = f"invoice-{uuid.uuid4().hex[:10]}"

    async def run() -> tuple[httpx.Response, str]:
        cp_app, engine = _make_control_plane_app()
        await _create_schema(engine)
        try:
            cp_transport = httpx.ASGITransport(app=cp_app)
            async with httpx.AsyncClient(transport=cp_transport, base_url="http://cp") as cp:
                release_id = await _seed_active_release(cp, prompt_name)
            _install_gateway(cp_app)
            response = await _post_invoke(
                {"prompt_name": prompt_name, "variables": {"invoice_pdf_text": "Riverside\nTotal"}}
            )
            return response, release_id
        finally:
            await engine.dispose()

    response, release_id = asyncio.run(run())
    assert response.status_code == 200
    body = response.json()
    assert body["output"] == DUMMY_OUTPUT
    assert body["metadata"]["release_id"] == release_id
    assert body["metadata"]["model"] == "claude-sonnet-4-6"
    assert body["metadata"]["use_case"] == "ap_invoice_extraction"

    spans = [s for s in exporter.get_finished_spans() if s.name == "gateway.invoke"]
    assert spans, "no gateway.invoke span exported"
    attrs = spans[-1].attributes or {}
    assert attrs["releaseplane.release_id"] == release_id


def test_invoke_honors_release_id_override() -> None:
    prompt_name = f"invoice-{uuid.uuid4().hex[:10]}"

    async def run() -> tuple[httpx.Response, str]:
        cp_app, engine = _make_control_plane_app()
        await _create_schema(engine)
        try:
            cp_transport = httpx.ASGITransport(app=cp_app)
            async with httpx.AsyncClient(transport=cp_transport, base_url="http://cp") as cp:
                release_id = await _seed_active_release(cp, prompt_name)
            _install_gateway(cp_app)
            response = await _post_invoke(
                {
                    "prompt_name": "ignored-when-pinned",
                    "variables": {"invoice_pdf_text": "x"},
                    "release_id": release_id,
                }
            )
            return response, release_id
        finally:
            await engine.dispose()

    response, release_id = asyncio.run(run())
    assert response.status_code == 200
    assert response.json()["metadata"]["release_id"] == release_id


def test_invoke_unknown_prompt_returns_404() -> None:
    async def run() -> httpx.Response:
        cp_app, engine = _make_control_plane_app()
        await _create_schema(engine)
        try:
            _install_gateway(cp_app)
            return await _post_invoke(
                {"prompt_name": "does-not-exist", "variables": {"invoice_pdf_text": "x"}}
            )
        finally:
            await engine.dispose()

    response = asyncio.run(run())
    assert response.status_code == 404


@pytest.fixture(autouse=True)
def _clear_overrides() -> Any:
    yield
    gateway_app.dependency_overrides.clear()
