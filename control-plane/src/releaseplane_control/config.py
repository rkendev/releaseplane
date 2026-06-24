"""Runtime configuration read from the environment.

EVAL_GATE_ENFORCED controls the eval-gate seam. In Phase 2 there is no eval
runner, so the gate defaults to off (bypassed) and the structural promote rules
are what get exercised. Phase 4 flips the default on and fills the gate body;
nothing else in the promote path changes.
"""

from __future__ import annotations

import os

# Staleness window the Phase 4 eval gate will enforce. Defined here so the seam
# is visible now; unused until the eval runner lands.
EVAL_STALENESS_HOURS_DEFAULT = 24


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def eval_gate_enforced() -> bool:
    """Whether the eval gate blocks promotions. Off by default in Phase 2."""
    return _truthy(os.environ.get("EVAL_GATE_ENFORCED", "false"))
