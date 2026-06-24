"""Content checksum for prompt versions.

The checksum makes a version's content verifiable and immutable: it hashes the
system prompt, the developer prompt, and the three schema documents over a
canonical JSON encoding (sorted keys, compact separators) so the same content
always yields the same digest regardless of field order. Computed once on create
and never recomputed.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def compute_checksum(
    *,
    system_prompt: str,
    developer_prompt: str,
    variables_schema_json: dict[str, Any],
    output_schema_json: dict[str, Any],
    tool_schema_json: dict[str, Any] | None,
) -> str:
    """Return the sha256 hex digest of a prompt version's content."""
    payload = {
        "system_prompt": system_prompt,
        "developer_prompt": developer_prompt,
        "variables_schema_json": variables_schema_json,
        "output_schema_json": output_schema_json,
        "tool_schema_json": tool_schema_json,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
