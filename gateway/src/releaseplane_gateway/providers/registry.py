"""The provider registry: map a model config's provider name to an adapter.

The registry is a plain name to adapter mapping built once at startup. The build
step (in app.py) adds the dummy adapter unconditionally and the real adapters only
when their key is present, so the stack starts key-free and a request for a
provider with no configured key fails with a clear message rather than at startup.
"""

from __future__ import annotations

from collections.abc import Mapping

from .base import Provider, ProviderError


class ProviderRegistry:
    """Resolve a provider name to its adapter instance."""

    def __init__(self, providers: Mapping[str, Provider]) -> None:
        self._providers = dict(providers)

    def available(self) -> list[str]:
        return sorted(self._providers)

    def select(self, name: str) -> Provider:
        provider = self._providers.get(name)
        if provider is None:
            raise ProviderError(
                f"no provider adapter configured for {name!r}; available: {self.available()}"
            )
        return provider
