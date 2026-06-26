"""OpenAI provider: structured output through a forced function call.

The OpenAI-compatible mirror of the Claude tool-use path (decision D-OPENAI-STRUCT):
one function built from the release's output schema, forced with tool_choice, so
the model returns a schema-shaped object in the call arguments rather than
free-text JSON. The SDK client is synchronous, so the call runs in a worker thread
to keep the handler async. The client is injected so tests pass a stub; the real
client is constructed with a (dummy in tests) api_key, which the SDK accepts at
build time without a network call.
"""

from __future__ import annotations

import json
import time
from typing import Any, cast

import anyio.to_thread
from openai import OpenAI
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionMessageParam,
    ChatCompletionToolChoiceOptionParam,
    ChatCompletionToolParam,
)

from .base import ModelInvocationConfig, ProviderError, StructuredResult

TOOL_NAME = "emit_structured_output"


class OpenAiProvider:
    """Adapter over the OpenAI SDK that forces one structured function call."""

    name = "openai"

    def __init__(self, client: OpenAI) -> None:
        self._client = client

    async def generate_structured(
        self,
        *,
        system: str,
        prompt: str,
        model_config: ModelInvocationConfig,
        output_schema: dict[str, Any],
    ) -> StructuredResult:
        # output_schema is an arbitrary JSON Schema dict from the registry, used
        # directly as the function parameters; the params are cast to the SDK
        # TypedDicts rather than reconstructed field by field.
        tool = cast(
            ChatCompletionToolParam,
            {
                "type": "function",
                "function": {
                    "name": TOOL_NAME,
                    "description": "Return the structured result as a single object.",
                    "parameters": output_schema,
                },
            },
        )
        tool_choice = cast(
            ChatCompletionToolChoiceOptionParam,
            {"type": "function", "function": {"name": TOOL_NAME}},
        )
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]

        def _call() -> ChatCompletion:
            return self._client.chat.completions.create(
                model=model_config.model,
                max_tokens=model_config.max_tokens,
                temperature=model_config.temperature,
                messages=messages,
                tools=[tool],
                tool_choice=tool_choice,
            )

        start = time.perf_counter()
        response = await anyio.to_thread.run_sync(_call)
        latency_ms = (time.perf_counter() - start) * 1000

        choice = response.choices[0]
        usage = response.usage
        if usage is None:
            raise ProviderError("openai response carried no usage")
        return StructuredResult(
            output=_first_tool_arguments(response),
            model=response.model,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            latency_ms=latency_ms,
            finish_reason=choice.finish_reason,
        )


def _first_tool_arguments(response: ChatCompletion) -> dict[str, Any]:
    """Parse the arguments of the first tool call, or fail loudly."""
    tool_calls = response.choices[0].message.tool_calls
    if not tool_calls:
        raise ProviderError("openai response carried no tool call")
    call = tool_calls[0]
    if call.type != "function":
        raise ProviderError(f"openai returned an unexpected tool-call type: {call.type!r}")
    try:
        parsed = json.loads(call.function.arguments)
    except json.JSONDecodeError as exc:
        raise ProviderError(f"openai tool arguments were not valid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ProviderError("openai tool arguments were not a JSON object")
    return cast(dict[str, Any], parsed)
