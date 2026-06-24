"""Tests for the prompt-version content checksum. No database."""

from __future__ import annotations

from releaseplane_control.services.checksum import compute_checksum

BASE = {
    "system_prompt": "sys",
    "developer_prompt": "dev",
    "variables_schema_json": {"a": 1, "b": 2},
    "output_schema_json": {"type": "object"},
    "tool_schema_json": None,
}


def test_is_deterministic_and_key_order_independent() -> None:
    first = compute_checksum(**BASE)
    reordered = dict(BASE)
    reordered["variables_schema_json"] = {"b": 2, "a": 1}
    assert compute_checksum(**reordered) == first


def test_changes_when_content_changes() -> None:
    baseline = compute_checksum(**BASE)
    changed = dict(BASE)
    changed["system_prompt"] = "different"
    assert compute_checksum(**changed) != baseline


def test_tool_schema_none_differs_from_empty() -> None:
    none_tool = compute_checksum(**BASE)
    empty_tool = compute_checksum(**{**BASE, "tool_schema_json": {}})
    assert none_tool != empty_tool


def test_is_sha256_hex() -> None:
    digest = compute_checksum(**BASE)
    assert len(digest) == 64
    assert all(ch in "0123456789abcdef" for ch in digest)
