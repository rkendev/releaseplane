"""Unit tests for the control-plane RoutingRulePredicate schema. No DB."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from releaseplane_control.schemas import RoutingRulePredicate


def _predicate(field: str, op: str, value: object) -> RoutingRulePredicate:
    return RoutingRulePredicate.model_validate({"field": field, "op": op, "value": value})


@pytest.mark.parametrize(
    ("field", "op", "value"),
    [
        ("input_length", "lt", 600),
        ("input_length", "gte", 0),
        ("input_length", "eq", 120),
        ("input_length", "in", [100, 200]),
        ("routing_hint", "eq", "cheap"),
        ("use_case", "ne", "other"),
        ("use_case", "in", ["a", "b"]),
    ],
)
def test_valid_predicates_accepted(field: str, op: str, value: object) -> None:
    pred = _predicate(field, op, value)
    assert pred.field.value == field
    assert pred.op.value == op


def test_hostile_field_name_rejected() -> None:
    for hostile in ("__class__", "os", "system"):
        with pytest.raises(ValidationError):
            _predicate(hostile, "eq", 1)


def test_unknown_op_rejected() -> None:
    with pytest.raises(ValidationError):
        _predicate("input_length", "regex", 1)


def test_extra_keys_forbidden() -> None:
    with pytest.raises(ValidationError):
        RoutingRulePredicate.model_validate(
            {"field": "input_length", "op": "lt", "value": 1, "evil": True}
        )


def test_in_requires_non_empty_list() -> None:
    with pytest.raises(ValidationError):
        _predicate("use_case", "in", "x")
    with pytest.raises(ValidationError):
        _predicate("use_case", "in", [])


def test_ordering_op_requires_numeric_field_and_value() -> None:
    with pytest.raises(ValidationError):
        _predicate("use_case", "lt", 5)
    with pytest.raises(ValidationError):
        _predicate("input_length", "lt", "600")


def test_scalar_op_rejects_list_value() -> None:
    with pytest.raises(ValidationError):
        _predicate("use_case", "eq", ["a"])
