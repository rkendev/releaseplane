"""Environment configuration for the gateway.

The gateway reaches the control-plane over HTTP and calls a provider selected at
startup. The Anthropic key is read from a mounted secret file when present (the
dev-stack pattern) and falls back to the environment, mirroring how the
control-plane resolves its database password.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_CONTROL_PLANE_URL = "http://control-plane:8000"


def control_plane_url() -> str:
    return os.environ.get("CONTROL_PLANE_URL", DEFAULT_CONTROL_PLANE_URL)


def provider_override() -> str | None:
    """An optional force-override of the serving provider for every request.

    When GATEWAY_PROVIDER names a provider (the dev stack sets it to `dummy` for
    zero spend), the registry serves that adapter regardless of the resolved or
    routed model config. Unset or empty means select the provider from the chosen
    model config's `provider`, which is the real multi-provider path.
    """
    value = os.environ.get("GATEWAY_PROVIDER", "").strip().lower()
    return value or None


def anthropic_api_key() -> str:
    # The dev stack mounts the key as a secret file referenced by
    # CLAUDE_API_KEY_FILE; fall back to the SDK's ANTHROPIC_API_KEY for local use.
    key_file = os.environ.get("CLAUDE_API_KEY_FILE")
    if key_file and Path(key_file).exists():
        return Path(key_file).read_text(encoding="utf-8").strip()
    return os.environ.get("ANTHROPIC_API_KEY", "")


def openai_api_key() -> str:
    # Same secret-file pattern as the Anthropic key: the dev stack mounts it at
    # OPENAI_API_KEY_FILE; fall back to the SDK's OPENAI_API_KEY. Absent by
    # default, so the registry simply omits the OpenAI adapter (clean skip).
    key_file = os.environ.get("OPENAI_API_KEY_FILE")
    if key_file and Path(key_file).exists():
        return Path(key_file).read_text(encoding="utf-8").strip()
    return os.environ.get("OPENAI_API_KEY", "")
