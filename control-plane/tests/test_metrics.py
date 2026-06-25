"""Unit tests for the control-plane eval metrics. No database."""

from __future__ import annotations

from prometheus_client import REGISTRY
from releaseplane_control.metrics import record_eval_run

_SUMMARY = {
    "tiers": {
        "1": {
            "count": 10,
            "schema_validity": {"rate": 1.0},
            "arithmetic_consistency": {"rate": 0.9},
        }
    }
}


def test_record_eval_run_counts_and_sets_pass_rate() -> None:
    before = (
        REGISTRY.get_sample_value("control_plane_eval_runs_total", {"status": "succeeded"}) or 0.0
    )
    record_eval_run("rel-metrics-test", "succeeded", _SUMMARY)

    after = REGISTRY.get_sample_value("control_plane_eval_runs_total", {"status": "succeeded"})
    assert after == before + 1

    rate = REGISTRY.get_sample_value(
        "control_plane_eval_pass_rate",
        {"release_id": "rel-metrics-test", "tier": "1", "metric": "arithmetic_consistency"},
    )
    assert rate == 0.9


def test_record_eval_run_tolerates_missing_summary() -> None:
    # No tiers and a None summary must not raise.
    record_eval_run("rel-empty", "failed", None)
    record_eval_run("rel-empty", "failed", {})
