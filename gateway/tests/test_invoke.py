"""Route tests for POST /invoke.

These drive the full handler (resolve -> render -> provider -> span) against a
DummyProvider and a fake resolver, so no database, control-plane, or network is
involved. Spans are captured with an in-memory exporter to assert the release
identity and gen_ai.* attributes the audit trail depends on.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from opentelemetry import trace
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from releaseplane_gateway.app import app
from releaseplane_gateway.invoke import get_provider, get_resolver
from releaseplane_gateway.providers import DummyProvider
from releaseplane_gateway.resolution import PromptNotFoundError, ResolvedRelease

RELEASE_ID = "11111111-1111-1111-1111-111111111111"
PROMPT_VERSION_ID = "22222222-2222-2222-2222-222222222222"

RESOLVED_PAYLOAD: dict[str, Any] = {
    "release_id": RELEASE_ID,
    "prompt_version_id": PROMPT_VERSION_ID,
    "prompt_name": "invoice-extraction",
    "use_case": "ap_invoice_extraction",
    "system_prompt": "You extract invoices.",
    "developer_prompt": "Extract from:\n{{ invoice_pdf_text }}",
    "variables_schema_json": {
        "type": "object",
        "properties": {"invoice_pdf_text": {"type": "string"}},
        "required": ["invoice_pdf_text"],
    },
    "output_schema_json": {"type": "object", "properties": {}},
    "model": {
        "provider": "claude",
        "model_name": "claude-sonnet-4-6",
        "temperature": "0.0",
        "max_tokens": 4096,
        "tool_mode": "structured_output",
        "cost_per_mtok_input_usd": "3.0000",
        "cost_per_mtok_output_usd": "15.0000",
    },
}

DUMMY_OUTPUT = {"vendor_name": "Riverside Office Supplies", "total": "542.50"}


class _FakeResolver:
    def __init__(
        self, resolved: ResolvedRelease | None = None, error: Exception | None = None
    ) -> None:
        self._resolved = resolved
        self._error = error
        self.calls: list[tuple[str, object]] = []

    async def resolve_active(self, prompt_name: str) -> ResolvedRelease:
        self.calls.append(("active", prompt_name))
        return self._return()

    async def resolve_by_id(self, release_id: uuid.UUID) -> ResolvedRelease:
        self.calls.append(("by_id", release_id))
        return self._return()

    def _return(self) -> ResolvedRelease:
        if self._error is not None:
            raise self._error
        assert self._resolved is not None
        return self._resolved


def _exporter() -> InMemorySpanExporter:
    exporter = InMemorySpanExporter()
    provider = trace.get_tracer_provider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))  # type: ignore[attr-defined]
    return exporter


def _install(resolver: _FakeResolver, provider: DummyProvider) -> None:
    app.dependency_overrides[get_resolver] = lambda: resolver
    app.dependency_overrides[get_provider] = lambda: provider


def test_invoke_end_to_end_emits_span() -> None:
    exporter = _exporter()
    resolver = _FakeResolver(resolved=ResolvedRelease.model_validate(RESOLVED_PAYLOAD))
    provider = DummyProvider(output=DUMMY_OUTPUT)
    _install(resolver, provider)

    with TestClient(app) as client:
        response = client.post(
            "/invoke",
            json={
                "prompt_name": "invoice-extraction",
                "variables": {"invoice_pdf_text": "Riverside Office Supplies\nTotal 542.50"},
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["output"] == DUMMY_OUTPUT
    meta = body["metadata"]
    assert meta["release_id"] == RELEASE_ID
    assert meta["prompt_version_id"] == PROMPT_VERSION_ID
    assert meta["use_case"] == "ap_invoice_extraction"
    assert meta["model"] == "claude-sonnet-4-6"
    assert meta["input_tokens"] > 0
    assert meta["output_tokens"] > 0
    assert meta["cost_estimate_usd"] >= 0
    assert resolver.calls == [("active", "invoice-extraction")]

    spans = [s for s in exporter.get_finished_spans() if s.name == "gateway.invoke"]
    assert len(spans) == 1
    attrs = spans[0].attributes or {}
    assert attrs["releaseplane.release_id"] == RELEASE_ID
    assert attrs["releaseplane.prompt_version_id"] == PROMPT_VERSION_ID
    assert attrs["releaseplane.use_case"] == "ap_invoice_extraction"
    assert attrs["gen_ai.system"] == "dummy"
    assert attrs["gen_ai.request.model"] == "claude-sonnet-4-6"
    assert attrs["gen_ai.usage.input_tokens"] > 0
    assert attrs["gen_ai.usage.output_tokens"] > 0
    assert attrs["gen_ai.response.finish_reason"] == "tool_use"


def test_invoke_honors_release_id_override() -> None:
    resolver = _FakeResolver(resolved=ResolvedRelease.model_validate(RESOLVED_PAYLOAD))
    provider = DummyProvider(output=DUMMY_OUTPUT)
    _install(resolver, provider)

    with TestClient(app) as client:
        response = client.post(
            "/invoke",
            json={
                "prompt_name": "invoice-extraction",
                "variables": {"invoice_pdf_text": "x"},
                "release_id": RELEASE_ID,
            },
        )

    assert response.status_code == 200
    assert resolver.calls == [("by_id", uuid.UUID(RELEASE_ID))]


def test_invoke_prompt_not_found_returns_404() -> None:
    resolver = _FakeResolver(error=PromptNotFoundError("no active release for prompt 'nope'"))
    provider = DummyProvider(output=DUMMY_OUTPUT)
    _install(resolver, provider)

    with TestClient(app) as client:
        response = client.post(
            "/invoke",
            json={"prompt_name": "nope", "variables": {"invoice_pdf_text": "x"}},
        )

    assert response.status_code == 404


def test_invoke_missing_required_variable_returns_422() -> None:
    resolver = _FakeResolver(resolved=ResolvedRelease.model_validate(RESOLVED_PAYLOAD))
    provider = DummyProvider(output=DUMMY_OUTPUT)
    _install(resolver, provider)

    with TestClient(app) as client:
        response = client.post(
            "/invoke",
            json={"prompt_name": "invoice-extraction", "variables": {}},
        )

    assert response.status_code == 422


def test_invoke_records_prometheus_metrics() -> None:
    resolver = _FakeResolver(resolved=ResolvedRelease.model_validate(RESOLVED_PAYLOAD))
    provider = DummyProvider(output=DUMMY_OUTPUT)
    _install(resolver, provider)

    with TestClient(app) as client:
        client.post(
            "/invoke",
            json={"prompt_name": "invoice-extraction", "variables": {"invoice_pdf_text": "x"}},
        )
        metrics = client.get("/metrics").text

    assert 'gateway_invoke_requests_total{outcome="success",provider="dummy"}' in metrics
    assert "gateway_invoke_latency_seconds_bucket" in metrics


@pytest.fixture(autouse=True)
def _clear_overrides() -> Any:
    yield
    app.dependency_overrides.clear()
