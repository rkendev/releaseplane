"""Prometheus metrics for the control plane.

Served on /metrics (the default registry) and scraped by the dev-stack Prometheus
control-plane job, so the eval dashboard reads pass rates and run counts without
the OTel metrics pipeline. The pass-rate gauge is labeled by release so the
dashboard can show per-release outcomes; release count stays small in the dev
stack, so the label cardinality is acceptable.
"""

from __future__ import annotations

from typing import Any

from prometheus_client import Counter, Gauge

EVAL_RUNS = Counter(
    "control_plane_eval_runs_total",
    "Eval runs completed, by terminal status.",
    ["status"],
)

EVAL_PASS_RATE = Gauge(
    "control_plane_eval_pass_rate",
    "Latest completed eval run pass rate, by release, tier, and metric (0..1).",
    ["release_id", "tier", "metric"],
)


def record_eval_run(release_id: str, status: str, summary_json: dict[str, Any] | None) -> None:
    """Emit run-count and per-tier pass-rate metrics for a completed run."""
    EVAL_RUNS.labels(status=status).inc()
    tiers = (summary_json or {}).get("tiers", {})
    for tier, metrics in tiers.items():
        for metric, stats in metrics.items():
            if isinstance(stats, dict) and "rate" in stats:
                EVAL_PASS_RATE.labels(release_id=release_id, tier=tier, metric=metric).set(
                    float(stats["rate"])
                )
