"""The gated OpenAI smoke must skip cleanly with no key, so CI cannot spend.

Imports the script's main() and runs it with the OpenAI key vars cleared,
asserting it returns 0 without making any call. Mirrors the safety the live-eval
script has for the Anthropic path.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SMOKE = Path(__file__).resolve().parents[1] / "scripts" / "run_openai_smoke.py"


def _load_smoke() -> object:
    spec = importlib.util.spec_from_file_location("run_openai_smoke", _SMOKE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_openai_smoke"] = module
    spec.loader.exec_module(module)
    return module


def test_smoke_skips_without_a_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY_FILE", raising=False)
    smoke = _load_smoke()
    assert smoke.main([]) == 0  # type: ignore[attr-defined]
    assert "skipping smoke" in capsys.readouterr().out
