"""Eval-gate check for promotion.

docs/EVALUATION.md requires a recent passing eval run before a release can move
toward candidate or active. This is the executable form of the promotion-block
policy there: take the most recent eval run for the release, and block unless it
succeeded, finished within the staleness window, and met the Tier-1 and Tier-2
gating thresholds. Tier 3 is monitored only, never gating.

The threshold check reads the per-tier summary the runner wrote on the run
(summary_json), keyed by the metric names the evals scorers emit. Those names are
a cross-plane string contract, restated here so the control plane does not import
the evals package.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import config, models
from ..models import EvalRunStatus, ReleaseStage

# Metric-name keys in summary_json, mirroring releaseplane_evals.scorers.
SCHEMA_VALIDITY = "schema_validity"
ARITHMETIC_CONSISTENCY = "arithmetic_consistency"
CHECKSUM_MATCH = "checksum_match"

# Per-tier gating thresholds from docs/EVALUATION.md. Tier 3 is absent: monitored
# only, never gating.
TIER_THRESHOLDS: dict[str, dict[str, float]] = {
    "1": {SCHEMA_VALIDITY: 1.0, ARITHMETIC_CONSISTENCY: 1.0, CHECKSUM_MATCH: 1.0},
    "2": {SCHEMA_VALIDITY: 1.0, ARITHMETIC_CONSISTENCY: 1.0, CHECKSUM_MATCH: 0.8},
}


@dataclass(frozen=True)
class GateResult:
    ok: bool
    reason: str


def _rate(summary: dict[str, Any], tier: str, metric: str) -> float:
    tier_summary = summary.get("tiers", {}).get(tier, {})
    value = tier_summary.get(metric, {}).get("rate", 0.0)
    return float(value)


def check_thresholds(summary_json: dict[str, Any] | None) -> GateResult:
    """Pure threshold check over a run's summary_json. No I/O."""
    summary = summary_json or {}
    failures: list[str] = []
    for tier, metrics in TIER_THRESHOLDS.items():
        for metric, minimum in metrics.items():
            rate = _rate(summary, tier, metric)
            if rate < minimum:
                failures.append(f"tier {tier} {metric} {rate:.0%} < {minimum:.0%}")
    if failures:
        return GateResult(ok=False, reason="; ".join(failures))
    return GateResult(ok=True, reason="eval thresholds met")


async def _latest_run(session: AsyncSession, release_id: uuid.UUID) -> models.EvalRun | None:
    stmt = (
        select(models.EvalRun)
        .where(models.EvalRun.release_id == release_id)
        .order_by(models.EvalRun.started_at.desc())
        .limit(1)
    )
    run: models.EvalRun | None = await session.scalar(stmt)
    return run


async def eval_gate_ok(
    session: AsyncSession,
    release: models.Release,
    target: ReleaseStage,
    *,
    enforced: bool | None = None,
    now: datetime | None = None,
) -> GateResult:
    """Whether the eval gate permits promoting release toward target.

    enforced defaults to EVAL_GATE_ENFORCED. When enforced, block unless the most
    recent eval run for this release succeeded, finished within the staleness
    window, and met the Tier-1/Tier-2 thresholds. now is injectable for testing
    the staleness window.
    """
    if enforced is None:
        enforced = config.eval_gate_enforced()
    if not enforced:
        return GateResult(ok=True, reason="bypassed: eval gate disabled")

    run = await _latest_run(session, release.id)
    if run is None:
        return GateResult(ok=False, reason="no eval run found for this release")
    if run.status is not EvalRunStatus.succeeded:
        return GateResult(
            ok=False, reason=f"latest eval run did not complete (status={run.status.value})"
        )

    now = now or datetime.now(UTC)
    window = timedelta(hours=config.eval_staleness_hours())
    if run.finished_at is None or now - run.finished_at > window:
        return GateResult(
            ok=False,
            reason=f"latest eval run is stale (older than {config.eval_staleness_hours()}h)",
        )

    return check_thresholds(run.summary_json)
