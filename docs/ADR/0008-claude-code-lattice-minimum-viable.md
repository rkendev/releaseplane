# ADR 0008: Bootstrap a minimum-viable Claude Code lattice

Date: 2026-06-26
Status: Accepted

## Context

ReleasePlane was built with Claude Code but carried no repo-level Claude Code
scaffolding: no `CLAUDE.md`, no MCP server, no committed subagent or hook. Project
conventions (scope, stack, house style, the eval gate, the shared predicate) lived
only in `docs/` and in session memory, so each session re-derived them. The
cross-project memory `claude_code_lattice_gap.md` names this gap: a capable harness
with no persistent, in-repo wiring.

The risk in closing it is the opposite failure: a sprawl of agents, hooks, and slash
commands that are never used (ghost lattice), which reads as cargo-culting rather than
engineering discipline.

## Decision

Bootstrap a **minimum-viable** lattice in one commit, and stop there:

- `CLAUDE.md` (project paragraph, authoritative scope pointer, in-session stack
  choices, house style, citation rule, cross-project KB pointer).
- One MCP server: `releaseplane-postgres` (crystaldba `postgres-mcp` via `uvx`,
  restricted access, `DATABASE_URI` sourced from the environment / `.env`).
- One subagent: `code-reviewer`.
- One hook: `SessionStart` (branch, uncommitted summary, latest `T_phaseN` brief,
  scope pointer).

Two rules govern growth:

- **No ghost subagents**: every agent in `.claude/agents/` must be invoked at least
  once before the next release tag. The `code-reviewer`'s first invocation is the
  review of this very change.
- **Each layer earns its place by use**: the MCP server is added only after a real
  `tools/list` verification; further layers are added only when a recurring need
  appears, not preemptively.

### MCP server choice

`postgres-mcp` (crystaldba) is the only server in `.mcp.json`. It reads `DATABASE_URI`
from the environment, which matches the "credentials from a file, never hard-coded"
rule (the password expands from `${POSTGRES_PASSWORD}` with the dev placeholder as the
default). If it ever fails `tools/list`, the build halts and surfaces the failure
rather than silently switching servers.

A commented fallback, kept here only (not in `.mcp.json`), is the official reference
server:

```
# fallback (do not add to .mcp.json without re-verifying tools/list):
#   "command": "npx",
#   "args": ["-y", "@modelcontextprotocol/server-postgres",
#            "postgresql://releaseplane:${POSTGRES_PASSWORD:-changeme-local-dev}@localhost:5432/releaseplane"]
# Note: this server takes the connection URL as a positional arg, not an env var,
# so it does not match the env-from-file rule as cleanly as postgres-mcp.
```

## Named phase-out triggers (deferred lattice growth)

Each of these is deferred until the named trigger fires, so the lattice stays earned:

- **`PostToolUse` ruff-format hook**: add when a formatting miss reaches a commit or CI
  despite `make check` (for example a file outside the `make check` format target, as
  happened with `evals/scripts/`). The hook formats on every edit so the gap cannot
  recur.
- **`Stop` hook**: add when a session repeatedly ends with an unrun gate (uncommitted
  work, an unrun `make check`, a stale graph). The hook runs the closing checklist.
- **`/close` slash command**: add when the per-task close sequence (pre-commit, check,
  ff-merge, push, CI watch, graphify-refresh, memory update) is run often enough that
  encoding it once beats retyping it.
- **eval-runner skill**: add when launching the gated eval/live runs is a recurring,
  multi-step task worth a single skill entry point.
- **Additional subagents**: add only when a distinct, recurring review or research lens
  appears that `code-reviewer` does not cover, and it will be invoked before the next
  release tag.

## Consequences

- The lattice is small and every piece is exercised on creation, so it reads as used
  infrastructure rather than scaffolding.
- `.claude/settings.json` (tracked, hooks) coexists with the gitignored
  `settings.local.json` (permissions only).
- A `tests/test_claude_lattice.py` (run via `make lattice`, outside the default
  `pytest` collection) asserts the artifacts stay present, so a later edit cannot
  silently delete a layer.
- Growth is gated by the triggers above; adding a layer without its trigger is the
  ghost-lattice failure this ADR exists to prevent.
