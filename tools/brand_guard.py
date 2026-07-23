#!/usr/bin/env python3
"""Brand guard: keep the cross-project brand and the external KB path out of the repo.

The repo is going public. One cross-project brand token and one Windows-mirror
Knowledge Base directory path were neutralized when the docs were brought to
as-built; this guard fails the commit (and CI) if either creeps back into any
tracked file, so the neutralization cannot silently regress.

Unlike the banned-words guard (docs only), this runs over all tracked text files,
because the reference it guards lived in `CLAUDE.md`, which the banned-words hook
does not scan. Naming the harness itself (Claude, the lattice) stays allowed in
the documented harness config; this guard targets only the two tokens below, so
those files pass unless they name the cross-project brand or the mirror path.

Both the file contents and the file path are checked, so a token in a filename is
caught as well as one in the text. This file necessarily contains the tokens it
searches for, so it excludes itself by resolved path.

Two modes:
  - default: `brand_guard.py <path> ...` scans the given files (the pre-commit and
    CI use), covering the working tree.
  - `brand_guard.py --history` scans every commit reachable from all refs for the
    tokens. The working-tree scan cannot see history, and the tokens do sit in
    early commits, so this is the pre-flip check the owner runs before making the
    repo public. It is deliberately not a CI gate: it would fail on the current
    history until that history is scrubbed.

Exit non-zero on the first offending file (or historical location); print the
location + token.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# Each entry is (regex, label).
#   - the cross-project brand token (also catches the "Claude-<brand>" compound)
#   - the Windows-mirror Knowledge Base root directory the old cross-project path named
DENIED = [
    (re.compile(r"cowork", re.IGNORECASE), "cross-project brand token"),
    (re.compile(r"Architecting_Domain_Driven"), "external KB directory path"),
]

# Files exempt from the scan: this guard, which must contain the tokens it denies.
ALLOWLIST = {Path(__file__).resolve()}


def scan(path: Path) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        # Binary or unreadable file (for example a committed PDF): nothing to scan.
        return hits
    for lineno, line in enumerate(text.splitlines(), start=1):
        for pattern, label in DENIED:
            if pattern.search(line):
                hits.append((lineno, label))
    return hits


def _path_hits(arg: str) -> list[str]:
    """Denied tokens present in the file path itself (a brand token in a filename)."""
    return [label for pattern, label in DENIED if pattern.search(arg)]


def scan_history() -> int:
    """Scan every commit reachable from all refs for the denied tokens.

    Returns 1 if any historical blob carries a token, 0 if history is clean. This
    guard's own source is excluded, since it contains the tokens by necessity.
    """
    revs = subprocess.run(
        ["git", "rev-list", "--all"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    if not revs:
        return 0
    grep = subprocess.run(
        [
            "git",
            "grep",
            "-I",
            "-n",
            "-i",
            "-e",
            "cowork",
            "-e",
            "Architecting_Domain_Driven",
            *revs,
            "--",
            ":!tools/brand_guard.py",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    # git grep exits 0 when it finds matches, 1 when it finds none.
    if grep.returncode == 1:
        return 0
    if grep.returncode != 0:
        sys.stderr.write(grep.stderr)
        return grep.returncode
    locations = sorted({":".join(line.split(":", 2)[:2]) for line in grep.stdout.splitlines()})
    for location in locations:
        print(f"{location}: brand guard: denied token in history", file=sys.stderr)
    print(
        f"brand guard: {len(locations)} historical location(s) carry a denied token; "
        "scrub history before making the repo public",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] == "--history":
        return scan_history()
    fail = False
    for arg in argv[1:]:
        path = Path(arg)
        if path.resolve() in ALLOWLIST:
            continue
        for label in _path_hits(arg):
            print(f"{arg}: brand guard: {label} (in path)", file=sys.stderr)
            fail = True
        if not path.is_file():
            continue
        for lineno, label in scan(path):
            print(f"{arg}:{lineno}: brand guard: {label}", file=sys.stderr)
            fail = True
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
