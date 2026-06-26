"""Route tests for POST /invoke.

These drive the full handler (resolve -> route -> select provider -> render ->
call -> span) against a DummyProvider registry and a fake resolver, so no
database, control-plane, or network is involved. Spans are captured with an
in-memory exporter to assert the release identity, gen_ai.* attributes, and the
routing decision the audit trail depends on.
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
from releaseplane_gateway.invoke import get_registry, get_resolver
from releaseplane_gateway.providers import DummyProvider, ProviderRegistry
from releaseplane_gateway.resolution import (
    PromptNotFoundError,
    ResolvedModelConfig,
    ResolvedRelease,
)
from releaseplane_gateway.routing import RoutingRule

RELEASE_ID = "11111111-1111-1111-1111-111111111111"
PROMPT_VERSION_ID = "22222222-2222-2222-2222-222222222222"
ALT_CONFIG_ID = "33333333-3333-3333-3333-333333333333"
RULE_ID = "44444444-4444-4444-4444-444444444444"

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
    "policy_bundle": {
        "name": "invoice_v1",
        "version": "v1",
        "rules_json": {},
        "severity_mode": "monitor",
    },
}

ALT_MODEL_CONFIG: dict[str, Any] = {
    "provider": "openai",
    "model_name": "gpt-4o-mini",
    "temperature": "0.0",
    "max_tokens": 4096,
    "tool_mode": "structured_output",
    "cost_per_mtok_input_usd": "0.1500",
    "cost_per_mtok_output_usd": "0.6000",
}

DUMMY_OUTPUT = {"vendor_name": "Riverside Office Supplies", "total": "542.50"}


def _length_rule(threshold: int) -> RoutingRule:
    return RoutingRule.model_validate(
        {
            "id": RULE_ID,
            "use_case": "ap_invoice_extraction",
            "predicate": {"field": "input_length", "op": "lt", "value": threshold},
            "target_model_config_id": ALT_CONFIG_ID,
            "priority": 10,
        }
    )


class _FakeResolver:
    def __init__(
        self,
        resolved: ResolvedRelease | None = None,
        error: Exception | None = None,
        rules: list[RoutingRule] | None = None,
        target: ResolvedModelConfig | None = None,
    ) -> None:
        self._resolved = resolved
        self._error = error
        self._rules = rules or []
        self._target = target
        self.calls: list[tuple[str, object]] = []

    async def resolve_active(self, prompt_name: str) -> ResolvedRelease:
        self.calls.append(("active", prompt_name))
        return self._return()

    async def resolve_by_id(self, release_id: uuid.UUID) -> ResolvedRelease:
        self.calls.append(("by_id", release_id))
        return self._return()

    async def list_routing_rules(self, use_case: str) -> list[RoutingRule]:
        self.calls.append(("rules", use_case))
        return self._rules

    async def resolve_model_config(self, model_config_id: uuid.UUID) -> ResolvedModelConfig:
        self.calls.append(("model_config", model_config_id))
        assert self._target is not None
        return self._target

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


def _registry(**named: DummyProvider) -> ProviderRegistry:
    # Map each provider name a test may select to a (possibly renamed) dummy, so
    # selection-by-config resolves without any real client. Defaults cover the
    # release's own claude config.
    providers = {"claude": DummyProvider(output=DUMMY_OUTPUT), "dummy": DummyProvider()}
    providers.update(named)
    return ProviderRegistry(providers)


def _install(resolver: _FakeResolver, registry: ProviderRegistry) -> None:
    app.dependency_overrides[get_resolver] = lambda: resolver
    app.dependency_overrides[get_registry] = lambda: registry


def test_invoke_end_to_end_emits_span() -> None:
    exporter = _exporter()
    resolver = _FakeResolver(resolved=ResolvedRelease.model_validate(RESOLVED_PAYLOAD))
    _install(resolver, _registry())

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
    assert meta["provider"] == "dummy"
    assert meta["model"] == "claude-sonnet-4-6"
    assert meta["routing_rule_id"] is None
    assert meta["input_tokens"] > 0
    assert meta["output_tokens"] > 0
    assert meta["cost_estimate_usd"] >= 0
    assert ("active", "invoice-extraction") in resolver.calls

    spans = [s for s in exporter.get_finished_spans() if s.name == "gateway.invoke"]
    assert len(spans) == 1
    attrs = spans[0].attributes or {}
    assert attrs["releaseplane.release_id"] == RELEASE_ID
    assert attrs["releaseplane.use_case"] == "ap_invoice_extraction"
    assert attrs["releaseplane.routing.matched"] is False
    assert attrs["releaseplane.model_config.provider"] == "claude"
    assert attrs["gen_ai.system"] == "dummy"
    assert attrs["gen_ai.request.model"] == "claude-sonnet-4-6"
    assert attrs["gen_ai.usage.input_tokens"] > 0
    assert attrs["gen_ai.response.finish_reason"] == "tool_use"


def test_invoke_routes_short_input_to_alternate_config() -> None:
    exporter = _exporter()
    resolver = _FakeResolver(
        resolved=ResolvedRelease.model_validate(RESOLVED_PAYLOAD),
        rules=[_length_rule(600)],
        target=ResolvedModelConfig.model_validate(ALT_MODEL_CONFIG),
    )
    openai_dummy = DummyProvider(output=DUMMY_OUTPUT)
    openai_dummy.name = "openai"
    _install(resolver, _registry(openai=openai_dummy))

    with TestClient(app) as client:
        response = client.post(
            "/invoke",
            json={
                "prompt_name": "invoice-extraction",
                "variables": {"invoice_pdf_text": "short invoice"},
            },
        )

    assert response.status_code == 200
    meta = response.json()["metadata"]
    # The short input matched the rule and diverted to the OpenAI alternate config,
    # served (in this zero-spend test) by the dummy registered under that name.
    assert meta["provider"] == "openai"
    assert meta["model"] == "gpt-4o-mini"
    assert meta["routing_rule_id"] == RULE_ID
    assert ("model_config", uuid.UUID(ALT_CONFIG_ID)) in resolver.calls

    attrs = [s for s in exporter.get_finished_spans() if s.name == "gateway.invoke"][
        -1
    ].attributes or {}
    assert attrs["releaseplane.routing.matched"] is True
    assert attrs["releaseplane.routing.rule_id"] == RULE_ID
    assert attrs["releaseplane.routing.signal.input_length"] == len("short invoice")
    assert attrs["releaseplane.model_config.provider"] == "openai"
    assert attrs["gen_ai.system"] == "openai"


def test_invoke_falls_through_when_no_rule_matches() -> None:
    resolver = _FakeResolver(
        resolved=ResolvedRelease.model_validate(RESOLVED_PAYLOAD),
        rules=[_length_rule(5)],  # input is longer than 5, so no match
        target=ResolvedModelConfig.model_validate(ALT_MODEL_CONFIG),
    )
    _install(resolver, _registry())

    with TestClient(app) as client:
        response = client.post(
            "/invoke",
            json={
                "prompt_name": "invoice-extraction",
                "variables": {"invoice_pdf_text": "a clearly longer than five invoice"},
            },
        )

    assert response.status_code == 200
    meta = response.json()["metadata"]
    assert meta["provider"] == "dummy"
    assert meta["model"] == "claude-sonnet-4-6"
    assert meta["routing_rule_id"] is None
    assert ("model_config", uuid.UUID(ALT_CONFIG_ID)) not in resolver.calls


def test_invoke_honors_release_id_override() -> None:
    resolver = _FakeResolver(resolved=ResolvedRelease.model_validate(RESOLVED_PAYLOAD))
    _install(resolver, _registry())

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
    assert ("by_id", uuid.UUID(RELEASE_ID)) in resolver.calls


def test_invoke_prompt_not_found_returns_404() -> None:
    resolver = _FakeResolver(error=PromptNotFoundError("no active release for prompt 'nope'"))
    _install(resolver, _registry())

    with TestClient(app) as client:
        response = client.post(
            "/invoke",
            json={"prompt_name": "nope", "variables": {"invoice_pdf_text": "x"}},
        )

    assert response.status_code == 404


def test_invoke_missing_required_variable_returns_422() -> None:
    resolver = _FakeResolver(resolved=ResolvedRelease.model_validate(RESOLVED_PAYLOAD))
    _install(resolver, _registry())

    with TestClient(app) as client:
        response = client.post(
            "/invoke",
            json={"prompt_name": "invoice-extraction", "variables": {}},
        )

    assert response.status_code == 422


def test_invoke_records_prometheus_metrics() -> None:
    resolver = _FakeResolver(resolved=ResolvedRelease.model_validate(RESOLVED_PAYLOAD))
    _install(resolver, _registry())

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
