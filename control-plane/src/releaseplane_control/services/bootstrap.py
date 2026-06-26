"""Idempotent seeding of the invoice_v1 policy bundle and the two prompts.

Run as a host op (decision D-SEED-HOME): resolving the prompt schemas imports the
reference `examples` package, which is not on the control-plane image, so this
drives the control-plane HTTP API from the dev environment rather than the
container. It is idempotent: re-running registers nothing new (the bundle is
matched by name+version, the prompt by name, each version by its (prompt,
version) pair), so a clean DB and an already-seeded DB converge to the same state.

The httpx client is injected (the host script passes httpx.Client; tests pass a
TestClient), so this module needs httpx only for typing.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import yaml

if TYPE_CHECKING:
    import httpx

# The invoice_v1 bundle: the three checks plus the injection patterns. The
# patterns target instruction-injection phrasings and are tuned not to trip any
# benign invoice in the 30-case set (vendor names, amounts, dates, terms).
INVOICE_V1_BUNDLE: dict[str, Any] = {
    "name": "invoice_v1",
    "version": "v1",
    "severity_mode": "enforce",
    "rules_json": {
        "checks": ["prompt_injection", "schema_validity", "arithmetic_consistency"],
        "injection_patterns": [
            r"ignore (all |any |the )?(previous|prior|above) (instruction|prompt|direction)",
            r"disregard (all |the )?(previous|above|prior|earlier)",
            r"you are now (a |an )?",
            r"reveal (your |the )?(system )?prompt",
            r"system prompt",
        ],
    },
}


@dataclass(frozen=True)
class SeedSummary:
    """What a seed run registered (True) versus found already present (False)."""

    bundle_created: bool
    prompt_id: str
    versions_created: dict[str, bool]


def _resolve_schema(source: str) -> dict[str, Any]:
    """Resolve a `module.path:Model` reference to its JSON Schema.

    Generic (importlib, no static `examples` import), so the control-plane image
    never needs the reference package and mypy needs no per-module exclusion.
    """
    module_path, _, attr = source.partition(":")
    model = getattr(import_module(module_path), attr)
    return cast(dict[str, Any], model.model_json_schema())


def _load_prompt(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], yaml.safe_load(path.read_text(encoding="utf-8")))


def seed_policy_bundle(client: httpx.Client, bundle: dict[str, Any]) -> bool:
    """Register a policy bundle if absent (matched by name+version). Returns created."""
    existing = client.get("/policy-bundles").json()
    if any(b["name"] == bundle["name"] and b["version"] == bundle["version"] for b in existing):
        return False
    response = client.post(
        "/policy-bundles",
        json={
            "name": bundle["name"],
            "version": bundle["version"],
            "rules_json": bundle["rules_json"],
            "severity_mode": bundle["severity_mode"],
        },
    )
    response.raise_for_status()
    return True


def seed_prompt_definition(client: httpx.Client, *, name: str, team: str, use_case: str) -> str:
    """Register a prompt definition if absent (matched by name). Returns its id."""
    response = client.post("/prompts", json={"name": name, "team": team, "use_case": use_case})
    if response.status_code == 201:
        return str(response.json()["id"])
    if response.status_code == 409:
        for prompt in client.get("/prompts").json():
            if prompt["name"] == name:
                return str(prompt["id"])
    response.raise_for_status()
    raise RuntimeError(f"could not resolve prompt id for {name!r}")


def seed_prompt_version(client: httpx.Client, prompt_id: str, prompt: dict[str, Any]) -> bool:
    """Register one prompt version if absent (matched by (prompt, version)). Returns created."""
    payload = {
        "version": prompt["version"],
        "system_prompt": prompt["system_prompt"],
        "developer_prompt": prompt["developer_prompt"],
        "variables_schema_json": _resolve_schema(prompt["variables_schema"]["source"]),
        "output_schema_json": _resolve_schema(prompt["output_schema"]["source"]),
        "status": prompt.get("status", "draft"),
        "created_by": prompt["created_by"],
    }
    response = client.post(f"/prompts/{prompt_id}/versions", json=payload)
    if response.status_code == 201:
        return True
    if response.status_code == 409:
        return False
    response.raise_for_status()
    return False


def seed_invoice_v1(
    client: httpx.Client, *, prompt_v1_path: Path, prompt_v2_path: Path
) -> SeedSummary:
    """Seed the invoice_v1 bundle and both prompt versions. Idempotent."""
    bundle_created = seed_policy_bundle(client, INVOICE_V1_BUNDLE)
    v1 = _load_prompt(prompt_v1_path)
    v2 = _load_prompt(prompt_v2_path)
    prompt_id = seed_prompt_definition(
        client, name=v1["name"], team=v1["team"], use_case=v1["use_case"]
    )
    versions_created = {
        str(v1["version"]): seed_prompt_version(client, prompt_id, v1),
        str(v2["version"]): seed_prompt_version(client, prompt_id, v2),
    }
    return SeedSummary(
        bundle_created=bundle_created,
        prompt_id=prompt_id,
        versions_created=versions_created,
    )
