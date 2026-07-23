"""The policy engine: parse a bundle's rules and apply the checks.

The bundle's rules_json names which checks are active and carries the injection
patterns. Pre-call checks run on the untrusted input; post-call checks run on the
model output. v1 never transforms content: the output object is identical between
monitor and enforce, only the derived status differs (passed / monitored /
failed), so a reviewer sees the same response with different metadata.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from .arithmetic_consistency import check_arithmetic_consistency
from .base import (
    ARITHMETIC_CONSISTENCY,
    PROMPT_INJECTION,
    SCHEMA_VALIDITY,
    PolicyOutcome,
)
from .prompt_injection import check_prompt_injection
from .schema_validity import check_schema_validity

ENFORCE = "enforce"
MONITOR = "monitor"

STATUS_PASSED = "passed"
STATUS_MONITORED = "monitored"
STATUS_FAILED = "failed"
# No check ran, so there is nothing to pass or fail. Kept distinct from passed so
# a bundle with no configured checks (for example a stale row whose rules_json
# predates the engine) cannot masquerade as a clean pass.
STATUS_NOT_APPLIED = "not_applied"


class PolicyBundleRules(BaseModel):
    """The gateway's view of a policy bundle's rules_json.

    Unknown keys are ignored so the bundle can carry control-plane-only fields.
    """

    checks: list[str] = []
    injection_patterns: list[str] = []


def parse_rules(rules_json: dict[str, Any]) -> PolicyBundleRules:
    return PolicyBundleRules.model_validate(rules_json)


def pre_call_outcomes(rules: PolicyBundleRules, input_text: str) -> list[PolicyOutcome]:
    """Checks that run before the model call, on the untrusted input."""
    outcomes: list[PolicyOutcome] = []
    if PROMPT_INJECTION in rules.checks:
        outcomes.append(check_prompt_injection(input_text, rules.injection_patterns))
    return outcomes


def post_call_outcomes(
    rules: PolicyBundleRules, output: dict[str, Any], output_schema: dict[str, Any]
) -> list[PolicyOutcome]:
    """Checks that run after the model call, on the output."""
    outcomes: list[PolicyOutcome] = []
    if SCHEMA_VALIDITY in rules.checks:
        outcomes.append(check_schema_validity(output, output_schema))
    if ARITHMETIC_CONSISTENCY in rules.checks:
        outcomes.append(check_arithmetic_consistency(output))
    return outcomes


def policy_status(outcomes: list[PolicyOutcome], severity_mode: str) -> str:
    """Derive the request's policy status from the outcomes and the severity mode.

    An empty outcome list means no check ran, which is reported as not_applied
    rather than passed: `all([])` is vacuously true, so without this guard a
    bundle with no configured checks would report a clean pass on any output.
    """
    if not outcomes:
        return STATUS_NOT_APPLIED
    if all(outcome.passed for outcome in outcomes):
        return STATUS_PASSED
    return STATUS_FAILED if severity_mode == ENFORCE else STATUS_MONITORED
