"""Presence and wiring checks for the minimum-viable Claude Code lattice.

Asserts the four lattice artifacts exist, the SessionStart hook is executable, and
settings.json wires the hook, so a later edit cannot silently delete a layer (the
no-ghost-subagent rule, ADR 0008). Lives outside the pytest testpaths; run it with
`make lattice`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

ARTIFACTS = [
    "CLAUDE.md",
    ".mcp.json",
    ".claude/agents/code-reviewer.md",
    ".claude/hooks/session_start.sh",
]


def test_lattice_artifacts_present() -> None:
    missing = [name for name in ARTIFACTS if not (REPO_ROOT / name).is_file()]
    assert missing == [], f"missing lattice artifacts: {missing}"


def test_session_start_hook_is_executable() -> None:
    hook = REPO_ROOT / ".claude/hooks/session_start.sh"
    assert os.access(hook, os.X_OK), "session_start.sh is not executable"


def test_settings_registers_session_start_hook() -> None:
    settings = json.loads((REPO_ROOT / ".claude/settings.json").read_text(encoding="utf-8"))
    groups = settings.get("hooks", {}).get("SessionStart", [])
    commands = [h.get("command", "") for group in groups for h in group.get("hooks", [])]
    assert any(
        "session_start.sh" in command for command in commands
    ), "SessionStart is not wired to session_start.sh in settings.json"


def test_mcp_pins_the_single_postgres_server() -> None:
    mcp = json.loads((REPO_ROOT / ".mcp.json").read_text(encoding="utf-8"))
    servers = mcp.get("mcpServers", {})
    assert list(servers) == ["releaseplane-postgres"], "expected exactly one MCP server"
    assert servers["releaseplane-postgres"]["command"] == "uvx"
