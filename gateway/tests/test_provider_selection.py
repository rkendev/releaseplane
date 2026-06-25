"""Provider selection guards: CI must default to the offline provider.

These lock the zero-API-call posture: with no GATEWAY_PROVIDER set, the gateway
builds a DummyProvider, so CI never constructs an Anthropic client or makes a
call. The claude branch is exercised with a dummy key (the SDK validates the key
at construction, before any network).
"""

from __future__ import annotations

import pytest
from releaseplane_gateway.app import build_provider
from releaseplane_gateway.config import provider_name
from releaseplane_gateway.providers import ClaudeProvider, DummyProvider


def test_default_provider_is_dummy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GATEWAY_PROVIDER", raising=False)
    assert provider_name() == "dummy"
    assert isinstance(build_provider(), DummyProvider)


def test_claude_provider_built_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GATEWAY_PROVIDER", "claude")
    monkeypatch.delenv("CLAUDE_API_KEY_FILE", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy")
    assert isinstance(build_provider(), ClaudeProvider)
