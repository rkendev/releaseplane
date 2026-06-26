#!/usr/bin/env bash
# SessionStart hook: a four-line orientation for a new ReleasePlane session.
# Read-only and fast. Output is added to the session context by Claude Code.
set -euo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null || echo .)"

branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '(no git)')"
dirty="$(git status --short 2>/dev/null | wc -l | tr -d ' ')"
brief="$(ls -t T_phase*entry*.md 2>/dev/null | head -1 || true)"
[ -n "$brief" ] || brief='(none)'

echo "ReleasePlane | branch: ${branch} | uncommitted changes: ${dirty}"
echo "latest phase brief: ${brief}"
echo "scope: docs/SCOPE.md and docs/ARCHITECTURE.md are authoritative"
echo "conventions: CLAUDE.md (stack, house style, citation rule)"
