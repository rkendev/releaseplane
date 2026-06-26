"""Provider override guard: the dev stack forces dummy for zero spend.

GATEWAY_PROVIDER is an optional force-override of the serving provider. The dev
stack sets it to `dummy` so /invoke makes zero API calls regardless of the
resolved or routed model config; unset means select by the chosen config's
provider (the real multi-provider path). The registry build itself is covered in
test_registry.py.
"""

from __future__ import annotations

import pytest
from releaseplane_gateway.config import provider_override


def test_override_is_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GATEWAY_PROVIDER", raising=False)
    assert provider_override() is None


def test_override_is_none_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GATEWAY_PROVIDER", "")
    assert provider_override() is None


def test_override_forces_named_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GATEWAY_PROVIDER", "Dummy")
    assert provider_override() == "dummy"
