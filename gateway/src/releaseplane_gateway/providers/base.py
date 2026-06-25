"""Provider Protocol and the value objects it exchanges.

`generate_structured` is the single seam between the gateway and a model
provider. It takes the resolved model parameters and the release's output schema
(a JSON Schema dict from the registry, not a Pydantic class), and returns the
parsed object plus the call metadata the gateway records on its span.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol


class ProviderError(RuntimeError):
    """A provider call did not yield a usable structured result."""


@dataclass(frozen=True)
class ModelInvocationConfig:
    """Resolved model parameters for one call.

    Sourced from the registry `model_configs` row reached through the active
    release. The adapter passes `model`/`temperature`/`max_tokens` through to the
    API rather than hardcoding them; the cost rates ride along so the caller can
    estimate spend for the span.
    """

    model: str
    temperature: float
    max_tokens: int
    tool_mode: str
    cost_per_mtok_input_usd: Decimal
    cost_per_mtok_output_usd: Decimal


@dataclass(frozen=True)
class StructuredResult:
    """One structured generation: the parsed object plus call metadata."""

    output: dict[str, Any]
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    finish_reason: str | None


class Provider(Protocol):
    """A model provider that returns schema-shaped structured output."""

    name: str

    async def generate_structured(
        self,
        *,
        system: str,
        prompt: str,
        model_config: ModelInvocationConfig,
        output_schema: dict[str, Any],
    ) -> StructuredResult: ...
