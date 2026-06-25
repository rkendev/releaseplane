"""Unit tests for the runner's per-tier summary aggregation. Pure, no I/O."""

from __future__ import annotations

from releaseplane_evals.runner import summarize
from releaseplane_evals.scorers import (
    ARITHMETIC_CONSISTENCY,
    CHECKSUM_MATCH,
    SCHEMA_VALIDITY,
)


def _all_pass() -> dict[str, bool]:
    return {SCHEMA_VALIDITY: True, ARITHMETIC_CONSISTENCY: True, CHECKSUM_MATCH: True}


def test_summary_groups_by_tier_with_counts() -> None:
    scored = [(1, _all_pass()) for _ in range(10)]
    scored += [(2, _all_pass()) for _ in range(10)]
    scored += [(3, _all_pass()) for _ in range(10)]
    summary = summarize(scored)
    assert set(summary["tiers"]) == {"1", "2", "3"}
    assert summary["tiers"]["1"]["count"] == 10
    assert summary["tiers"]["1"][SCHEMA_VALIDITY]["rate"] == 1.0


def test_summary_computes_partial_rate() -> None:
    # 8 of 10 tier-2 cases pass checksum.
    scored = []
    for index in range(10):
        metrics = _all_pass()
        if index < 2:
            metrics[CHECKSUM_MATCH] = False
        scored.append((2, metrics))
    tier2 = summarize(scored)["tiers"]["2"]
    assert tier2[CHECKSUM_MATCH]["passed"] == 8
    assert tier2[CHECKSUM_MATCH]["rate"] == 0.8
    assert tier2[ARITHMETIC_CONSISTENCY]["rate"] == 1.0


def test_summary_of_empty_run_has_no_tiers() -> None:
    assert summarize([]) == {"tiers": {}}
