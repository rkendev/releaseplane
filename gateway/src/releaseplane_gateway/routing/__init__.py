"""Deterministic routing for the execution plane.

The gateway parses routing rules from the control plane into RoutingPredicate /
RoutingRule value objects and evaluates them with a pure matcher (no eval, no
attribute or callable access). Rules are tried in priority order, first match
wins, and an unmatched request falls through to the release's own model config.
"""

from .matcher import (
    RoutingField,
    RoutingOp,
    RoutingPredicate,
    RoutingRule,
    RoutingSignal,
    evaluate,
    first_match,
)

__all__ = [
    "RoutingField",
    "RoutingOp",
    "RoutingPredicate",
    "RoutingRule",
    "RoutingSignal",
    "evaluate",
    "first_match",
]
