"""Pure-logic tests for the release state machine. No database."""

from __future__ import annotations

import itertools

import pytest
from releaseplane_control.models import ReleaseStage
from releaseplane_control.services.state_machine import (
    LEGAL_TRANSITIONS,
    is_legal_transition,
    next_promote_stage,
)

# The legal transitions per docs/ARCHITECTURE.md, restated independently here so
# the test fails if the table drifts from the diagram.
LEGAL_PAIRS = {
    (ReleaseStage.draft, ReleaseStage.candidate),
    (ReleaseStage.candidate, ReleaseStage.active),
    (ReleaseStage.candidate, ReleaseStage.draft),
    (ReleaseStage.active, ReleaseStage.rolled_back),
    (ReleaseStage.active, ReleaseStage.active),
    (ReleaseStage.rolled_back, ReleaseStage.draft),
}


def test_legal_transition_table_matches_diagram() -> None:
    actual = {(src, dst) for src, dsts in LEGAL_TRANSITIONS.items() for dst in dsts}
    assert actual == LEGAL_PAIRS


@pytest.mark.parametrize(("src", "dst"), list(itertools.product(ReleaseStage, repeat=2)))
def test_every_pair_legal_iff_in_table(src: ReleaseStage, dst: ReleaseStage) -> None:
    assert is_legal_transition(src, dst) is ((src, dst) in LEGAL_PAIRS)


def test_promote_path_is_forward_only() -> None:
    assert next_promote_stage(ReleaseStage.draft) is ReleaseStage.candidate
    assert next_promote_stage(ReleaseStage.candidate) is ReleaseStage.active
    assert next_promote_stage(ReleaseStage.active) is None
    assert next_promote_stage(ReleaseStage.rolled_back) is None


def test_canary_is_inert() -> None:
    assert LEGAL_TRANSITIONS[ReleaseStage.canary] == frozenset()
    assert next_promote_stage(ReleaseStage.canary) is None
    # nothing transitions into canary either
    assert all(ReleaseStage.canary not in dsts for dsts in LEGAL_TRANSITIONS.values())
