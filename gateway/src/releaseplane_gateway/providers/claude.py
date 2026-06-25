"""Claude provider: structured output through the tool-use path.

Mirrors the request shaping proven in `evals/probes/cost_delta.py`: a single
forced tool call whose `input_schema` is the release's output schema, so the
model returns a schema-shaped object instead of free-text JSON. The Anthropic SDK
client is synchronous, so the call runs in a worker thread to keep the gateway
handler async.
"""

from __future__ import annotations

import time
from typing import Any, cast

import anyio.to_thread
from anthropic import Anthropic
from anthropic.types import Message, MessageParam, ToolChoiceToolParam, ToolParam

from .base import ModelInvocationConfig, ProviderError, StructuredResult

TOOL_NAME = "emit_structured_output"


class ClaudeProvider:
    """Adapter over the Anthropic SDK that forces one structured tool call.

    The client is injected so tests can pass a stub; construct the real client
    with a valid (or dummy) `api_key`, which the SDK validates at build time.
    """

    name = "claude"

    def __init__(self, client: Anthropic) -> None:
        self._client = client

    async def generate_structured(
        self,
        *,
        system: str,
        prompt: str,
        model_config: ModelInvocationConfig,
        output_schema: dict[str, Any],
    ) -> StructuredResult:
        # output_schema is an arbitrary JSON Schema dict from the registry, so the
        # tool param is cast to the SDK TypedDict rather than reconstructed field
        # by field; tool_choice and the message use the SDK param types directly.
        tool = cast(
            ToolParam,
            {
                "name": TOOL_NAME,
                "description": "Return the structured result as a single object.",
                "input_schema": output_schema,
            },
        )
        tool_choice: ToolChoiceToolParam = {"type": "tool", "name": TOOL_NAME}
        messages: list[MessageParam] = [{"role": "user", "content": prompt}]

        def _call() -> Message:
            return self._client.messages.create(
                model=model_config.model,
                max_tokens=model_config.max_tokens,
                temperature=model_config.temperature,
                system=system,
                tools=[tool],
                tool_choice=tool_choice,
                messages=messages,
            )

        start = time.perf_counter()
        response = await anyio.to_thread.run_sync(_call)
        latency_ms = (time.perf_counter() - start) * 1000
        return StructuredResult(
            output=_first_tool_input(response),
            model=model_config.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=latency_ms,
            finish_reason=response.stop_reason,
        )


def _first_tool_input(response: Message) -> dict[str, Any]:
    """Return the input of the first tool_use block, or fail loudly."""
    for block in response.content:
        if block.type == "tool_use":
            return cast(dict[str, Any], block.input)
    raise ProviderError("claude response carried no tool_use block")
