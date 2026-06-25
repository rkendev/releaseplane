"""Offline provider for tests and the zero-spend default.

Returns a fixed object without any network call, so CI and the gateway
integration tests exercise the full `/invoke` path while making zero API calls.
The canned output is supplied at construction so a test can assert an exact
payload flows end to end; a token estimate is derived from the prompt length so
spans carry plausible, non-zero usage.
"""

from __future__ import annotations

from typing import Any

from .base import ModelInvocationConfig, StructuredResult

_DEFAULT_OUTPUT: dict[str, Any] = {"ok": True}


def _estimate_tokens(text: str) -> int:
    """Rough char/4 token estimate; only needs to be deterministic and non-zero."""
    return max(1, len(text) // 4)


class DummyProvider:
    """A provider that echoes a canned object instead of calling a model."""

    name = "dummy"

    def __init__(self, output: dict[str, Any] | None = None) -> None:
        self._output = dict(output) if output is not None else dict(_DEFAULT_OUTPUT)

    async def generate_structured(
        self,
        *,
        system: str,
        prompt: str,
        model_config: ModelInvocationConfig,
        output_schema: dict[str, Any],
    ) -> StructuredResult:
        output = dict(self._output)
        return StructuredResult(
            output=output,
            model=model_config.model,
            input_tokens=_estimate_tokens(system) + _estimate_tokens(prompt),
            output_tokens=_estimate_tokens(str(output)),
            latency_ms=0.0,
            finish_reason="tool_use",
        )
