"""Shared fixtures for the gateway tests.

The eval gate defaults on from Phase 4, but the gateway integration tests promote
a release to active only as setup for the resolve/invoke path, which the gate is
not part of. Default the gate off here so that setup is not blocked; a test that
exercises the gate itself re-enables it explicitly.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _eval_gate_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_GATE_ENFORCED", "false")
