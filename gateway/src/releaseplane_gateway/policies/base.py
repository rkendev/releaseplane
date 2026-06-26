"""Shared value objects and check names for the runtime policy engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Check names. schema_validity and arithmetic_consistency match the eval scorer
# names so a failure reads the same in the gate and at runtime.
PROMPT_INJECTION = "prompt_injection"
SCHEMA_VALIDITY = "schema_validity"
ARITHMETIC_CONSISTENCY = "arithmetic_consistency"


@dataclass(frozen=True)
class PolicyOutcome:
    """One check's result: its name, pass/fail, and JSON-serializable evidence."""

    check: str
    passed: bool
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"check": self.check, "passed": self.passed, "detail": self.detail}
