"""The runtime policy engine for the execution plane.

Three deterministic checks applied on /invoke: prompt-injection regex (pre-call),
output schema validity, and output arithmetic consistency (post-call). The
arithmetic check imports the neutral shared predicate the eval scorer also uses,
so the gate and the runtime policy cannot drift. v1 flags but never transforms:
the output is identical between monitor and enforce; only the status differs.
"""

from .base import (
    ARITHMETIC_CONSISTENCY,
    PROMPT_INJECTION,
    SCHEMA_VALIDITY,
    PolicyOutcome,
)
from .engine import (
    ENFORCE,
    MONITOR,
    STATUS_FAILED,
    STATUS_MONITORED,
    STATUS_NOT_APPLIED,
    STATUS_PASSED,
    PolicyBundleRules,
    parse_rules,
    policy_status,
    post_call_outcomes,
    pre_call_outcomes,
)

__all__ = [
    "ARITHMETIC_CONSISTENCY",
    "ENFORCE",
    "MONITOR",
    "PROMPT_INJECTION",
    "SCHEMA_VALIDITY",
    "STATUS_FAILED",
    "STATUS_MONITORED",
    "STATUS_NOT_APPLIED",
    "STATUS_PASSED",
    "PolicyBundleRules",
    "PolicyOutcome",
    "parse_rules",
    "policy_status",
    "post_call_outcomes",
    "pre_call_outcomes",
]
