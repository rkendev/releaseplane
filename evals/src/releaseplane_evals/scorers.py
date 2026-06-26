"""The three deterministic eval metrics, as pure functions.

Each scorer takes plain dicts and returns a MetricResult; no model call and no
I/O, so they are cheap to unit-test on fixtures and run identically on a
DummyProvider output or a real one. The metric definitions and the per-tier
thresholds live in docs/EVALUATION.md; this module is the executable form of the
three axes there (schema validity, arithmetic consistency, checksum exact-match).

Decimal handling: invoice money fields arrive as strings ("1150.00") in the
ground truth and may arrive as strings or numbers from a model, so every numeric
comparison goes through Decimal(str(value)). Arithmetic uses a fixed 0.01
tolerance; the total checksum compares Decimal values (so 1247.50 == 1247.5),
while invoice_number and currency compare as exact strings and invoice_date
compares after normalizing to ISO 8601.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from jsonschema import Draft202012Validator
from releaseplane_shared.arithmetic import evaluate_arithmetic

SCHEMA_VALIDITY = "schema_validity"
ARITHMETIC_CONSISTENCY = "arithmetic_consistency"
CHECKSUM_MATCH = "checksum_match"

# The four fields whose exact match defines an invoice's identity in the ERP.
CHECKSUM_FIELDS = ("invoice_number", "invoice_date", "currency", "total")

# Date formats accepted by the ISO normalizer beyond ISO 8601 itself, so a model
# that emits a common non-ISO date does not fail the checksum on formatting alone.
_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d", "%d-%b-%Y", "%B %d, %Y")


@dataclass(frozen=True)
class MetricResult:
    """One metric outcome: a name, the gating boolean, a 0/1 score, and detail.

    detail is JSON-serializable so the runner can persist it on eval_results.notes
    and a human can see why a case failed without rerunning anything.
    """

    name: str
    passed: bool
    value: float
    detail: dict[str, Any] = field(default_factory=dict)


def _dec(value: object) -> Decimal:
    """Parse a money value to Decimal via its string form. Raises on garbage."""
    return Decimal(str(value))


def _result(name: str, passed: bool, detail: dict[str, Any]) -> MetricResult:
    return MetricResult(name=name, passed=passed, value=1.0 if passed else 0.0, detail=detail)


def score_schema_validity(output: dict[str, Any], output_schema: dict[str, Any]) -> MetricResult:
    """Pass iff output validates against the release's output JSON Schema.

    Uses the 2020-12 validator (the dialect Pydantic v2 emits). Format keywords
    like date are annotation-only here by design: date correctness is the
    checksum's job, not schema validity's.
    """
    validator = Draft202012Validator(output_schema)
    errors = sorted(validator.iter_errors(output), key=lambda e: list(e.absolute_path))
    if not errors:
        return _result(SCHEMA_VALIDITY, True, {})
    detail = {
        "errors": [
            {"path": list(error.absolute_path), "message": error.message} for error in errors[:10]
        ]
    }
    return _result(SCHEMA_VALIDITY, False, detail)


def score_arithmetic_consistency(output: dict[str, Any]) -> MetricResult:
    """Pass iff sum(qty*unit_price) == subtotal and subtotal + tax == total (+/-0.01).

    Delegates to the shared predicate so the eval gate and the runtime policy
    score identical arithmetic; this wraps the result as a MetricResult.
    """
    result = evaluate_arithmetic(output)
    return _result(ARITHMETIC_CONSISTENCY, result.consistent, result.detail)


def _normalize_iso_date(value: object) -> str | None:
    """Normalize a date string to ISO 8601 (YYYY-MM-DD), or None if unparseable."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _checksum_field_matches(field_name: str, got: object, expected: object) -> bool:
    if field_name == "invoice_date":
        got_norm = _normalize_iso_date(got)
        expected_norm = _normalize_iso_date(expected)
        return got_norm is not None and got_norm == expected_norm
    if field_name == "total":
        try:
            return _dec(got) == _dec(expected)
        except (InvalidOperation, TypeError):
            return False
    return got == expected


def score_checksum_match(output: dict[str, Any], expected: dict[str, Any]) -> MetricResult:
    """Pass iff invoice_number, invoice_date (ISO), currency, and total all match."""
    mismatches: dict[str, dict[str, Any]] = {}
    for field_name in CHECKSUM_FIELDS:
        got = output.get(field_name)
        want = expected.get(field_name)
        if not _checksum_field_matches(field_name, got, want):
            mismatches[field_name] = {"expected": want, "got": got}
    detail = {"mismatches": mismatches} if mismatches else {}
    return _result(CHECKSUM_MATCH, not mismatches, detail)


def score_case(
    *, output: dict[str, Any], expected: dict[str, Any], output_schema: dict[str, Any]
) -> list[MetricResult]:
    """Run all three metrics for one case, in eval_results order."""
    return [
        score_schema_validity(output, output_schema),
        score_arithmetic_consistency(output),
        score_checksum_match(output, expected),
    ]
