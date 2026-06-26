"""The shared arithmetic-consistency predicate.

One pure source of truth for the invoice arithmetic identity, imported by both the
eval scorer (evals/.../scorers.py) and the runtime policy
(gateway/.../policies/arithmetic_consistency.py), so the gate that blocks a
release and the check that flags a live request can never drift (ADR 0004,
decision D-PRED-HOME). No I/O and no model call: plain dict in, a result out.

Money fields arrive as strings ("1150.00") in ground truth and may arrive as
strings or numbers from a model, so every comparison goes through Decimal(str(x)).
The tolerance is one currency cent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

# Tolerance for the arithmetic identities, fixed at one currency cent.
ARITHMETIC_TOLERANCE = Decimal("0.01")


@dataclass(frozen=True)
class ArithmeticResult:
    """Whether the identities hold, plus JSON-serializable detail for either plane.

    The eval scorer wraps this into a MetricResult; the runtime policy wraps the
    same detail into a policy_event, so a human sees identical evidence in both.
    """

    consistent: bool
    detail: dict[str, Any] = field(default_factory=dict)


def _dec(value: object) -> Decimal:
    """Parse a money value to Decimal via its string form. Raises on garbage."""
    return Decimal(str(value))


def evaluate_arithmetic(output: dict[str, Any]) -> ArithmeticResult:
    """Check sum(qty*unit_price) == subtotal and subtotal + tax == total (+/-0.01)."""
    try:
        line_items = output["line_items"]
        line_sum = sum(
            (_dec(item["qty"]) * _dec(item["unit_price"]) for item in line_items),
            Decimal(0),
        )
        subtotal = _dec(output["subtotal"])
        tax = _dec(output["tax"])
        total = _dec(output["total"])
    except (KeyError, TypeError, InvalidOperation) as exc:
        return ArithmeticResult(
            consistent=False,
            detail={"error": f"missing or non-numeric field: {type(exc).__name__}"},
        )

    subtotal_ok = abs(line_sum - subtotal) <= ARITHMETIC_TOLERANCE
    total_ok = abs((subtotal + tax) - total) <= ARITHMETIC_TOLERANCE
    detail = {
        "line_items_sum": str(line_sum),
        "subtotal": str(subtotal),
        "tax": str(tax),
        "total": str(total),
        "subtotal_matches_line_items": subtotal_ok,
        "total_matches_subtotal_plus_tax": total_ok,
    }
    return ArithmeticResult(consistent=subtotal_ok and total_ok, detail=detail)


def arithmetic_consistent(output: dict[str, Any]) -> bool:
    """The bare boolean predicate, for callers that only need pass/fail."""
    return evaluate_arithmetic(output).consistent
