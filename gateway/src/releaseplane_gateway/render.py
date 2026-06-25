"""Render a developer prompt from request variables.

Templating is a deliberate minimum: validate the request variables against the
version's JSON Schema (required keys and basic types, no new dependency), then
substitute `{{ name }}` placeholders. A placeholder with no matching variable is
an error rather than a silent empty string, so a misnamed variable fails loud.
"""

from __future__ import annotations

import re
from typing import Any

_PLACEHOLDER = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")

_JSON_TYPES: dict[str, type | tuple[type, ...]] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


class RenderError(ValueError):
    """Request variables did not satisfy the schema, or the template referenced
    a variable that was not provided."""


def validate_variables(variables: dict[str, Any], schema: dict[str, Any]) -> None:
    """Check required keys are present and declared types match (best effort)."""
    for key in schema.get("required", []):
        if key not in variables:
            raise RenderError(f"missing required variable: {key!r}")
    properties = schema.get("properties", {})
    for key, value in variables.items():
        spec = properties.get(key)
        if spec is None:
            continue
        expected = _JSON_TYPES.get(spec.get("type"))
        if expected is not None and not isinstance(value, expected):
            raise RenderError(f"variable {key!r} must be of type {spec.get('type')!r}")


def render_prompt(template: str, variables: dict[str, Any]) -> str:
    """Substitute `{{ name }}` placeholders; fail on an unprovided reference."""

    def _sub(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in variables:
            raise RenderError(f"template references unprovided variable: {name!r}")
        return str(variables[name])

    return _PLACEHOLDER.sub(_sub, template)


def render(template: str, variables: dict[str, Any], schema: dict[str, Any]) -> str:
    """Validate variables against the schema, then render the template."""
    validate_variables(variables, schema)
    return render_prompt(template, variables)
