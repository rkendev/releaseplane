"""Unit tests for the pure routing matcher: operator set, malformed rules, and
the hostile-field-name path. No DB and no API calls."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError
from releaseplane_gateway.routing import (
    RoutingPredicate,
    RoutingRule,
    RoutingSignal,
    evaluate,
    first_match,
)

SIGNAL = RoutingSignal(input_length=120, routing_hint=None, use_case="ap_invoice_extraction")


def _predicate(field: str, op: str, value: object) -> RoutingPredicate:
    return RoutingPredicate.model_validate({"field": field, "op": op, "value": value})


@pytest.mark.parametrize(
    ("field", "op", "value", "expected"),
    [
        ("input_length", "lt", 600, True),
        ("input_length", "lt", 120, False),
        ("input_length", "lte", 120, True),
        ("input_length", "gt", 100, True),
        ("input_length", "gt", 120, False),
        ("input_length", "gte", 120, True),
        ("input_length", "eq", 120, True),
        ("input_length", "ne", 120, False),
        ("input_length", "in", [100, 120, 140], True),
        ("input_length", "in", [1, 2, 3], False),
        ("use_case", "eq", "ap_invoice_extraction", True),
        ("use_case", "eq", "other", False),
        ("use_case", "ne", "other", True),
        ("use_case", "in", ["ap_invoice_extraction", "x"], True),
        ("use_case", "in", ["x", "y"], False),
    ],
)
def test_operator_set(field: str, op: str, value: object, expected: bool) -> None:
    assert evaluate(_predicate(field, op, value), SIGNAL.as_fields()) is expected


def test_routing_hint_none_never_equals_a_string() -> None:
    pred = _predicate("routing_hint", "eq", "cheap")
    assert evaluate(pred, SIGNAL.as_fields()) is False


def test_routing_hint_match_when_supplied() -> None:
    signal = RoutingSignal(input_length=10, routing_hint="cheap", use_case="x")
    assert evaluate(_predicate("routing_hint", "eq", "cheap"), signal.as_fields()) is True


def test_hostile_field_name_is_rejected_at_parse() -> None:
    # A closed field enum means an attacker-supplied attribute name cannot route
    # to arbitrary access; it fails validation rather than reaching getattr.
    for hostile in ("__class__", "os", "model.__globals__"):
        with pytest.raises(ValidationError):
            _predicate(hostile, "eq", 1)


def test_unknown_op_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _predicate("input_length", "regex", 1)


def test_extra_keys_are_forbidden() -> None:
    with pytest.raises(ValidationError):
        RoutingPredicate.model_validate(
            {"field": "input_length", "op": "lt", "value": 1, "evil": True}
        )


def test_in_requires_non_empty_list() -> None:
    with pytest.raises(ValidationError):
        _predicate("use_case", "in", "not-a-list")
    with pytest.raises(ValidationError):
        _predicate("use_case", "in", [])


def test_ordering_op_requires_numeric_field_and_value() -> None:
    with pytest.raises(ValidationError):
        _predicate("use_case", "lt", 5)  # non-numeric field
    with pytest.raises(ValidationError):
        _predicate("input_length", "lt", "600")  # non-numeric value


def test_non_list_value_rejected_for_scalar_ops_when_list_given() -> None:
    with pytest.raises(ValidationError):
        _predicate("use_case", "eq", ["a", "b"])


def _rule(priority: int, field: str, op: str, value: object) -> RoutingRule:
    return RoutingRule(
        id=uuid.uuid4(),
        use_case="ap_invoice_extraction",
        predicate=_predicate(field, op, value),
        target_model_config_id=uuid.uuid4(),
        priority=priority,
    )


def test_first_match_wins_by_ascending_priority() -> None:
    low = _rule(10, "input_length", "lt", 600)
    high = _rule(1, "input_length", "lt", 600)
    # Both match; the lower priority number wins regardless of input order.
    assert first_match([low, high], SIGNAL) is high
    assert first_match([high, low], SIGNAL) is high


def test_first_match_returns_none_on_no_match() -> None:
    rule = _rule(1, "input_length", "gt", 10_000)
    assert first_match([rule], SIGNAL) is None


def test_first_match_skips_non_matching_lower_priority() -> None:
    miss = _rule(1, "input_length", "gt", 10_000)
    hit = _rule(2, "input_length", "lt", 600)
    assert first_match([miss, hit], SIGNAL) is hit
