"""Tests for the eval-gate seam. No database."""

from __future__ import annotations

import pytest
from releaseplane_control import models
from releaseplane_control.models import ReleaseStage
from releaseplane_control.services.eval_gate import eval_gate_ok


def _release() -> models.Release:
    # The placeholder ignores the release; a bare instance is enough.
    return models.Release()


def test_bypassed_when_not_enforced() -> None:
    result = eval_gate_ok(_release(), ReleaseStage.candidate, enforced=False)
    assert result.ok is True
    assert "bypassed" in result.reason


def test_blocks_when_enforced() -> None:
    result = eval_gate_ok(_release(), ReleaseStage.active, enforced=True)
    assert result.ok is False
    assert result.reason == "no eval run found"


def test_default_reads_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_GATE_ENFORCED", "true")
    assert eval_gate_ok(_release(), ReleaseStage.candidate).ok is False
    monkeypatch.setenv("EVAL_GATE_ENFORCED", "false")
    assert eval_gate_ok(_release(), ReleaseStage.candidate).ok is True
    monkeypatch.delenv("EVAL_GATE_ENFORCED", raising=False)
    assert eval_gate_ok(_release(), ReleaseStage.candidate).ok is True
