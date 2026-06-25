"""Runtime configuration read from the environment.

EVAL_GATE_ENFORCED controls the eval-gate seam. Phase 4 fills the gate body and
flips the default on, so a promotion now requires a recent passing eval run
unless an operator explicitly sets EVAL_GATE_ENFORCED=false. EVAL_STALENESS_HOURS
is the window within which the latest eval run must have finished.
"""

from __future__ import annotations

import os

# Default staleness window: the latest eval run must have finished within this
# many hours for the gate to consider it fresh.
EVAL_STALENESS_HOURS_DEFAULT = 24


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def eval_gate_enforced() -> bool:
    """Whether the eval gate blocks promotions. On by default from Phase 4."""
    return _truthy(os.environ.get("EVAL_GATE_ENFORCED", "true"))


def eval_staleness_hours() -> int:
    """How many hours a passing eval run stays fresh for the gate."""
    raw = os.environ.get("EVAL_STALENESS_HOURS")
    if raw is None:
        return EVAL_STALENESS_HOURS_DEFAULT
    try:
        return int(raw)
    except ValueError:
        return EVAL_STALENESS_HOURS_DEFAULT
