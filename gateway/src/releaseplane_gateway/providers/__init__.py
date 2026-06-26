"""Provider adapters for the execution plane.

The gateway resolves a release to a model config and an output schema, then calls
a provider through the `generate_structured` Protocol. Claude is the primary
provider (structured output via tool use); `DummyProvider` is the offline default
that keeps CI and the test suite at zero API calls.
"""

from .base import ModelInvocationConfig, Provider, ProviderError, StructuredResult
from .claude import ClaudeProvider
from .dummy import DummyProvider
from .openai import OpenAiProvider
from .registry import ProviderRegistry

__all__ = [
    "ClaudeProvider",
    "DummyProvider",
    "ModelInvocationConfig",
    "OpenAiProvider",
    "Provider",
    "ProviderError",
    "ProviderRegistry",
    "StructuredResult",
]
