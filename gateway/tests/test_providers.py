"""Unit tests for the provider adapters.

The Claude adapter is tested with a stubbed SDK client so the suite makes no
network call; the dummy adapter is tested directly. Coroutines are driven with
asyncio.run to avoid a pytest-asyncio mode dependency.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

import pytest
from releaseplane_gateway.providers import (
    ClaudeProvider,
    DummyProvider,
    ModelInvocationConfig,
    ProviderError,
)
from releaseplane_gateway.providers.claude import TOOL_NAME

MODEL_CONFIG = ModelInvocationConfig(
    model="claude-sonnet-4-6",
    temperature=0.0,
    max_tokens=4096,
    tool_mode="structured_output",
    cost_per_mtok_input_usd=Decimal("3.00"),
    cost_per_mtok_output_usd=Decimal("15.00"),
)

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"vendor_name": {"type": "string"}},
    "required": ["vendor_name"],
}


class _Block:
    def __init__(self, type_: str, input_: dict[str, Any] | None = None) -> None:
        self.type = type_
        self.input = input_


class _Usage:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _Response:
    def __init__(self, content: list[_Block], usage: _Usage, stop_reason: str) -> None:
        self.content = content
        self.usage = usage
        self.stop_reason = stop_reason


class _Messages:
    def __init__(self, response: _Response) -> None:
        self._response = response
        self.captured: dict[str, Any] | None = None

    def create(self, **kwargs: Any) -> _Response:
        self.captured = kwargs
        return self._response


class _FakeAnthropic:
    """Stub standing in for anthropic.Anthropic; records the request."""

    def __init__(self, response: _Response) -> None:
        self.messages = _Messages(response)


def test_claude_provider_forces_tool_call_and_reads_usage() -> None:
    response = _Response(
        content=[_Block("tool_use", {"vendor_name": "Acme"})],
        usage=_Usage(120, 45),
        stop_reason="tool_use",
    )
    fake = _FakeAnthropic(response)
    provider = ClaudeProvider(client=fake)

    result = asyncio.run(
        provider.generate_structured(
            system="sys",
            prompt="render me",
            model_config=MODEL_CONFIG,
            output_schema=OUTPUT_SCHEMA,
        )
    )

    assert result.output == {"vendor_name": "Acme"}
    assert result.input_tokens == 120
    assert result.output_tokens == 45
    assert result.finish_reason == "tool_use"
    assert result.model == "claude-sonnet-4-6"

    req = fake.messages.captured
    assert req is not None
    assert req["model"] == "claude-sonnet-4-6"
    assert req["max_tokens"] == 4096
    assert req["temperature"] == 0.0
    assert req["system"] == "sys"
    assert req["tool_choice"] == {"type": "tool", "name": TOOL_NAME}
    assert req["tools"][0]["name"] == TOOL_NAME
    assert req["tools"][0]["input_schema"] == OUTPUT_SCHEMA
    assert req["messages"] == [{"role": "user", "content": "render me"}]


def test_claude_provider_raises_without_tool_use() -> None:
    response = _Response(
        content=[_Block("text")],
        usage=_Usage(1, 1),
        stop_reason="end_turn",
    )
    provider = ClaudeProvider(client=_FakeAnthropic(response))

    with pytest.raises(ProviderError):
        asyncio.run(
            provider.generate_structured(
                system="s",
                prompt="p",
                model_config=MODEL_CONFIG,
                output_schema=OUTPUT_SCHEMA,
            )
        )


def test_dummy_provider_returns_canned_output() -> None:
    provider = DummyProvider(output={"vendor_name": "Dummy Co"})

    result = asyncio.run(
        provider.generate_structured(
            system="system text",
            prompt="hello world prompt",
            model_config=MODEL_CONFIG,
            output_schema=OUTPUT_SCHEMA,
        )
    )

    assert result.output == {"vendor_name": "Dummy Co"}
    assert result.model == "claude-sonnet-4-6"
    assert result.input_tokens > 0
    assert result.output_tokens > 0
    assert result.finish_reason == "tool_use"


def test_dummy_provider_default_output_is_non_empty() -> None:
    provider = DummyProvider()

    result = asyncio.run(
        provider.generate_structured(
            system="",
            prompt="",
            model_config=MODEL_CONFIG,
            output_schema={},
        )
    )

    assert result.output == {"ok": True}
    assert result.input_tokens >= 1
