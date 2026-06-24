"""Eval-gate seam for promotion.

docs/EVALUATION.md requires a recent passing eval run before a release can move
toward candidate or active. The eval runner is Phase 4, so this is a deliberate,
tested placeholder: a single function the promote endpoint calls. Phase 4
replaces only this function body (query eval_runs / eval_results, enforce the
per-tier thresholds and the staleness window) without touching the state machine
or the promote endpoint.

In Phase 2 the gate is off by default (EVAL_GATE_ENFORCED), so it returns ok and
the structural promote rules are what get exercised. When enforced it blocks
with a clear reason, which the structural tests use to cover the blocked path.
"""

from __future__ import annotations

from dataclasses import dataclass

from .. import config, models
from ..models import ReleaseStage


@dataclass(frozen=True)
class GateResult:
    ok: bool
    reason: str


def eval_gate_ok(
    release: models.Release, target: ReleaseStage, *, enforced: bool | None = None
) -> GateResult:
    """Whether the eval gate permits promoting release toward target.

    enforced defaults to the EVAL_GATE_ENFORCED config. The release and target
    are unused in Phase 2; Phase 4 fills the body against the eval tables.
    """
    if enforced is None:
        enforced = config.eval_gate_enforced()
    if not enforced:
        return GateResult(ok=True, reason="bypassed: eval runner is Phase 4")
    # TODO(phase-4): look up the most recent eval run for this release, require
    # status == succeeded within EVAL_STALENESS_HOURS, and enforce the Tier-1
    # and Tier-2 gating thresholds from docs/EVALUATION.md.
    return GateResult(ok=False, reason="no eval run found")
