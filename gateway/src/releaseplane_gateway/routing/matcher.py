"""The routing predicate value objects and the pure deterministic matcher.

This mirrors the control-plane RoutingRulePredicate contract rather than importing
it, keeping plane separation (the gateway models only what it evaluates). The
closed field and op enums mean a hostile field name fails to parse; evaluate()
reads field values from a plain mapping by key, so there is no attribute or
callable access and no eval.
"""

from __future__ import annotations

import enum
import uuid
from collections.abc import Iterable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class RoutingField(str, enum.Enum):
    """The closed set of named request fields a predicate may reference."""

    input_length = "input_length"
    routing_hint = "routing_hint"
    use_case = "use_case"


_NUMERIC_FIELDS = frozenset({RoutingField.input_length})


class RoutingOp(str, enum.Enum):
    """The closed operator set."""

    eq = "eq"
    ne = "ne"
    lt = "lt"
    lte = "lte"
    gt = "gt"
    gte = "gte"
    in_ = "in"


_ORDERING_OPS = frozenset({RoutingOp.lt, RoutingOp.lte, RoutingOp.gt, RoutingOp.gte})


class RoutingPredicate(BaseModel):
    """A single restricted predicate: field <op> value."""

    model_config = ConfigDict(extra="forbid")

    field: RoutingField
    op: RoutingOp
    value: int | float | str | list[int | float | str]

    @model_validator(mode="after")
    def _check_op_value(self) -> RoutingPredicate:
        if self.op is RoutingOp.in_:
            if not isinstance(self.value, list) or not self.value:
                raise ValueError("op 'in' requires a non-empty list value")
            return self
        if isinstance(self.value, list):
            raise ValueError(f"op {self.op.value!r} does not take a list value")
        if self.op in _ORDERING_OPS:
            if self.field not in _NUMERIC_FIELDS:
                raise ValueError(f"op {self.op.value!r} requires a numeric field")
            if isinstance(self.value, str):
                raise ValueError(f"op {self.op.value!r} requires a numeric value")
        return self


class RoutingRule(BaseModel):
    """A routing rule as the gateway reads it from the control plane."""

    model_config = ConfigDict(protected_namespaces=())

    id: uuid.UUID
    use_case: str
    predicate: RoutingPredicate
    target_model_config_id: uuid.UUID
    priority: int


class RoutingSignal(BaseModel):
    """The named request fields a predicate evaluates against.

    Built per /invoke from the rendered request: input_length is the character
    length of the routing input (the invoice text), routing_hint is the optional
    caller override, and use_case comes from the resolved release.
    """

    input_length: int
    routing_hint: str | None
    use_case: str

    def as_fields(self) -> dict[str, Any]:
        return {
            RoutingField.input_length.value: self.input_length,
            RoutingField.routing_hint.value: self.routing_hint,
            RoutingField.use_case.value: self.use_case,
        }


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def evaluate(predicate: RoutingPredicate, fields: Mapping[str, Any]) -> bool:
    """Return whether the predicate holds for the given request fields.

    The field value is read from the mapping by key (never by attribute), and any
    type mismatch resolves to False rather than raising, so a rule can never crash
    the request path.
    """
    actual = fields.get(predicate.field.value, None)
    value = predicate.value

    if predicate.op is RoutingOp.eq:
        return bool(actual == value)
    if predicate.op is RoutingOp.ne:
        return bool(actual != value)
    if predicate.op is RoutingOp.in_:
        return isinstance(value, list) and actual in value
    # Ordering ops: both sides must be real numbers.
    if not (_is_number(actual) and _is_number(value)):
        return False
    left, right = float(actual), float(value)  # type: ignore[arg-type]
    if predicate.op is RoutingOp.lt:
        return left < right
    if predicate.op is RoutingOp.lte:
        return left <= right
    if predicate.op is RoutingOp.gt:
        return left > right
    return left >= right  # RoutingOp.gte


def first_match(rules: Iterable[RoutingRule], signal: RoutingSignal) -> RoutingRule | None:
    """Return the first rule (by ascending priority) whose predicate matches.

    Ties on priority are broken by the order the rules arrive, which the control
    plane already returns priority-then-created_at. Returns None on no match, so
    the caller falls through to the release's own model config.
    """
    fields = signal.as_fields()
    for rule in sorted(rules, key=lambda r: r.priority):
        if evaluate(rule.predicate, fields):
            return rule
    return None
