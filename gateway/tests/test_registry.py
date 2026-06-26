"""Provider registry tests: name resolution and key-driven build, all offline.

These lock the zero-API posture for the second provider: build_registry adds the
dummy adapter unconditionally and the real adapters only when their key is set,
and it constructs the SDK clients with dummy keys without any network call.
"""

from __future__ import annotations

import pytest
from releaseplane_gateway.app import build_registry
from releaseplane_gateway.providers import (
    ClaudeProvider,
    DummyProvider,
    OpenAiProvider,
    ProviderError,
    ProviderRegistry,
)


def test_select_resolves_a_present_provider() -> None:
    registry = ProviderRegistry({"dummy": DummyProvider()})
    assert isinstance(registry.select("dummy"), DummyProvider)


def test_select_unknown_provider_raises() -> None:
    registry = ProviderRegistry({"dummy": DummyProvider()})
    with pytest.raises(ProviderError):
        registry.select("openai")


def _clear_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "CLAUDE_API_KEY_FILE",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY_FILE",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)


def test_build_registry_with_no_keys_has_only_dummy(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_keys(monkeypatch)
    registry = build_registry()
    assert registry.available() == ["dummy"]
    assert isinstance(registry.select("dummy"), DummyProvider)


def test_build_registry_adds_real_adapters_when_keys_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_keys(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-anthropic")
    monkeypatch.setenv("OPENAI_API_KEY", "dummy-openai")
    registry = build_registry()
    assert registry.available() == ["claude", "dummy", "openai"]
    assert isinstance(registry.select("claude"), ClaudeProvider)
    assert isinstance(registry.select("openai"), OpenAiProvider)
    assert isinstance(registry.select("dummy"), DummyProvider)
