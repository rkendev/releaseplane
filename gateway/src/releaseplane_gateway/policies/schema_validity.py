"""Schema-validity check: validate the model output against the release schema.

Uses the 2020-12 validator (the dialect Pydantic v2 emits), mirroring the eval
scorer so the runtime check and the gate agree on what a valid object is.
"""

from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from .base import SCHEMA_VALIDITY, PolicyOutcome


def check_schema_validity(output: dict[str, Any], output_schema: dict[str, Any]) -> PolicyOutcome:
    """Pass iff output validates against the release's output JSON Schema."""
    validator = Draft202012Validator(output_schema)
    errors = sorted(validator.iter_errors(output), key=lambda e: list(e.absolute_path))
    if not errors:
        return PolicyOutcome(SCHEMA_VALIDITY, True, {})
    detail = {
        "errors": [
            {"path": list(error.absolute_path), "message": error.message} for error in errors[:10]
        ]
    }
    return PolicyOutcome(SCHEMA_VALIDITY, False, detail)
