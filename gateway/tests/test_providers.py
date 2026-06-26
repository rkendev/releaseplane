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
    OpenAiProvider,
    ProviderError,
)
from releaseplane_gateway.providers.claude import TOOL_NAME
from releaseplane_gateway.providers.openai import TOOL_NAME as OPENAI_TOOL_NAME

MODEL_CONFIG = ModelInvocationConfig(
    provider="claude",
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


# --- OpenAI adapter (stubbed SDK client; no network) ------------------------


class _OAFunction:
    def __init__(self, arguments: str) -> None:
        self.name = OPENAI_TOOL_NAME
        self.arguments = arguments


class _OAToolCall:
    def __init__(self, arguments: str, type_: str = "function") -> None:
        self.type = type_
        self.function = _OAFunction(arguments)


class _OAMessage:
    def __init__(self, tool_calls: list[_OAToolCall] | None) -> None:
        self.tool_calls = tool_calls


class _OAChoice:
    def __init__(self, message: _OAMessage, finish_reason: str) -> None:
        self.message = message
        self.finish_reason = finish_reason


class _OAUsage:
    def __init__(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class _OAResponse:
    def __init__(self, choices: list[_OAChoice], usage: _OAUsage | None, model: str) -> None:
        self.choices = choices
        self.usage = usage
        self.model = model


class _OACompletions:
    def __init__(self, response: _OAResponse) -> None:
        self._response = response
        self.captured: dict[str, Any] | None = None

    def create(self, **kwargs: Any) -> _OAResponse:
        self.captured = kwargs
        return self._response


class _FakeOpenAI:
    """Stub standing in for openai.OpenAI; records the request."""

    def __init__(self, response: _OAResponse) -> None:
        self.chat = type("Chat", (), {"completions": _OACompletions(response)})()


def _openai_response(arguments: str, finish_reason: str = "tool_calls") -> _OAResponse:
    return _OAResponse(
        choices=[_OAChoice(_OAMessage([_OAToolCall(arguments)]), finish_reason)],
        usage=_OAUsage(80, 25),
        model="gpt-4o-mini",
    )


def test_openai_provider_forces_function_call_and_reads_usage() -> None:
    fake = _FakeOpenAI(_openai_response('{"vendor_name": "Acme"}'))
    provider = OpenAiProvider(client=fake)

    result = asyncio.run(
        provider.generate_structured(
            system="sys",
            prompt="render me",
            model_config=MODEL_CONFIG,
            output_schema=OUTPUT_SCHEMA,
        )
    )

    assert result.output == {"vendor_name": "Acme"}
    assert result.input_tokens == 80
    assert result.output_tokens == 25
    assert result.finish_reason == "tool_calls"
    assert result.model == "gpt-4o-mini"

    req = fake.chat.completions.captured
    assert req is not None
    assert req["model"] == "claude-sonnet-4-6"
    assert req["max_tokens"] == 4096
    assert req["tool_choice"] == {"type": "function", "function": {"name": OPENAI_TOOL_NAME}}
    assert req["tools"][0]["function"]["name"] == OPENAI_TOOL_NAME
    assert req["tools"][0]["function"]["parameters"] == OUTPUT_SCHEMA
    assert req["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "render me"},
    ]


def test_openai_provider_raises_without_tool_call() -> None:
    response = _OAResponse(
        choices=[_OAChoice(_OAMessage(None), "stop")],
        usage=_OAUsage(1, 1),
        model="gpt-4o-mini",
    )
    provider = OpenAiProvider(client=_FakeOpenAI(response))

    with pytest.raises(ProviderError):
        asyncio.run(
            provider.generate_structured(
                system="s",
                prompt="p",
                model_config=MODEL_CONFIG,
                output_schema=OUTPUT_SCHEMA,
            )
        )


def test_openai_provider_raises_on_non_json_arguments() -> None:
    provider = OpenAiProvider(client=_FakeOpenAI(_openai_response("not json")))

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
