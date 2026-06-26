"""Arithmetic-consistency check: the shared predicate, as a runtime policy.

Imports the one neutral predicate (releaseplane_shared) that the eval scorer also
imports, so the gate that blocks a release and this runtime check cannot drift
(ADR 0004, decision D-PRED-HOME).
"""

from __future__ import annotations

from typing import Any

from releaseplane_shared.arithmetic import evaluate_arithmetic

from .base import ARITHMETIC_CONSISTENCY, PolicyOutcome


def check_arithmetic_consistency(output: dict[str, Any]) -> PolicyOutcome:
    """Pass iff the invoice arithmetic identities hold (the shared predicate)."""
    result = evaluate_arithmetic(output)
    return PolicyOutcome(ARITHMETIC_CONSISTENCY, result.consistent, result.detail)
