"""Prompt-injection check: deterministic regex over the untrusted input.

Patterns come from the policy bundle (not hard-coded), so the coverage is tuned
as data without a deploy. A malformed pattern is skipped rather than failing the
request. The classifier is deferred to a later phase behind a measured trigger.
"""

from __future__ import annotations

import re

from .base import PROMPT_INJECTION, PolicyOutcome


def check_prompt_injection(text: str, patterns: list[str]) -> PolicyOutcome:
    """Pass iff none of the bundle's patterns match the input text."""
    matched: list[str] = []
    for pattern in patterns:
        try:
            if re.search(pattern, text, re.IGNORECASE):
                matched.append(pattern)
        except re.error:
            # A malformed pattern is a bundle config error, not an injection; skip
            # it so one bad pattern cannot flag (or crash) every request.
            continue
    if not matched:
        return PolicyOutcome(PROMPT_INJECTION, True, {})
    return PolicyOutcome(PROMPT_INJECTION, False, {"matched_patterns": matched})
