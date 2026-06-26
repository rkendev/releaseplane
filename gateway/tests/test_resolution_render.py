"""Unit tests for release resolution and prompt rendering.

Resolution is tested against an httpx MockTransport so no control-plane process
or database is needed; rendering is tested directly.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import httpx
import pytest
from releaseplane_gateway.render import RenderError, render, validate_variables
from releaseplane_gateway.resolution import (
    ControlPlaneUnavailableError,
    PromptNotFoundError,
    ReleaseResolver,
)

RELEASE_ID = "11111111-1111-1111-1111-111111111111"

RESOLVED_PAYLOAD: dict[str, Any] = {
    "release_id": RELEASE_ID,
    "prompt_version_id": "22222222-2222-2222-2222-222222222222",
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
        "id": "33333333-3333-3333-3333-333333333333",
        "name": "v1_default",
        "provider": "claude",
        "model_name": "claude-sonnet-4-6",
        "model_version_pin": "claude-sonnet-4-6",
        "temperature": "0.0",
        "max_tokens": 4096,
        "timeout_ms": 30000,
        "tool_mode": "structured_output",
        "active": True,
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


def _resolver(handler: httpx.MockTransport) -> ReleaseResolver:
    return ReleaseResolver(httpx.AsyncClient(transport=handler, base_url="http://control-plane"))


def test_resolve_active_returns_composed_release() -> None:
    captured: dict[str, str] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=RESOLVED_PAYLOAD)

    resolver = _resolver(httpx.MockTransport(handle))
    resolved = asyncio.run(resolver.resolve_active("invoice-extraction"))

    assert str(resolved.release_id) == RELEASE_ID
    assert resolved.prompt_name == "invoice-extraction"
    assert "/releases/active" in captured["url"]
    assert "prompt_name=invoice-extraction" in captured["url"]

    cfg = resolved.invocation_config()
    assert cfg.model == "claude-sonnet-4-6"
    assert cfg.temperature == 0.0
    assert cfg.max_tokens == 4096
    assert cfg.tool_mode == "structured_output"
    assert str(cfg.cost_per_mtok_input_usd) == "3.0000"


def test_resolve_by_id_targets_resolved_path() -> None:
    captured: dict[str, str] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=RESOLVED_PAYLOAD)

    resolver = _resolver(httpx.MockTransport(handle))
    asyncio.run(resolver.resolve_by_id(uuid.UUID(RELEASE_ID)))

    assert captured["url"].endswith(f"/releases/{RELEASE_ID}/resolved")


def test_resolve_active_maps_404_to_prompt_not_found() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "no active release for prompt 'nope'"})

    resolver = _resolver(httpx.MockTransport(handle))
    with pytest.raises(PromptNotFoundError):
        asyncio.run(resolver.resolve_active("nope"))


def test_resolve_maps_transport_error_to_unavailable() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    resolver = _resolver(httpx.MockTransport(handle))
    with pytest.raises(ControlPlaneUnavailableError):
        asyncio.run(resolver.resolve_active("invoice-extraction"))


def test_resolve_maps_unexpected_status_to_unavailable() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "database not configured"})

    resolver = _resolver(httpx.MockTransport(handle))
    with pytest.raises(ControlPlaneUnavailableError):
        asyncio.run(resolver.resolve_active("invoice-extraction"))


SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"invoice_pdf_text": {"type": "string"}},
    "required": ["invoice_pdf_text"],
}


def test_render_substitutes_placeholder() -> None:
    out = render(
        "Extract from:\n{{ invoice_pdf_text }}\n----",
        {"invoice_pdf_text": "ACME Co\nTotal 10"},
        SCHEMA,
    )
    assert out == "Extract from:\nACME Co\nTotal 10\n----"


def test_render_missing_required_variable_raises() -> None:
    with pytest.raises(RenderError):
        render("{{ invoice_pdf_text }}", {}, SCHEMA)


def test_render_unprovided_placeholder_raises() -> None:
    schema: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
    with pytest.raises(RenderError):
        render("hello {{ name }}", {}, schema)


def test_validate_variables_type_mismatch_raises() -> None:
    with pytest.raises(RenderError):
        validate_variables({"invoice_pdf_text": 123}, SCHEMA)
