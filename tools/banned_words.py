#!/usr/bin/env python3
"""Banned-words guard for ReleasePlane docs.

Sourced from the user's standing feedback memory (feedback_no_ai_slop). Run by
.pre-commit-config.yaml on top-level docs only. Code and tests are excluded.

Exit non-zero on first match; print file + line + offending token.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Each entry is (regex, label). Use word boundaries to avoid false positives.
BANNED = [
    (r"\bin order to\b", "in order to"),
    (r"\bit'?s worth noting\b", "it's worth noting"),
    (r"\brobust\b", "robust"),
    (r"\bleverage[sd]?\b", "leverage"),
    (r"\bseamless(ly)?\b", "seamless"),
    (r"\bholistic(ally)?\b", "holistic"),
    (r"\bdelve[sd]?\b", "delve"),
    (r"\bfoster(s|ed|ing)?\b", "foster"),
    (r"—", "em-dash"),  # U+2014
    (r" -- ", "double-hyphen as em-dash"),
]


def scan(path: Path) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    text = path.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), start=1):
        for pattern, label in BANNED:
            if re.search(pattern, line, flags=re.IGNORECASE):
                hits.append((lineno, label))
    return hits


def main(argv: list[str]) -> int:
    fail = False
    for arg in argv[1:]:
        path = Path(arg)
        if not path.exists():
            continue
        for lineno, label in scan(path):
            print(f"{path}:{lineno}: banned token '{label}'", file=sys.stderr)
            fail = True
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
