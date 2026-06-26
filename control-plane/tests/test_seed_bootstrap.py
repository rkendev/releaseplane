"""Integration tests for the invoice_v1 seeding bootstrap. Require Postgres.

Drives the host-op bootstrap against the control-plane app over a TestClient. The
seed uses fixed names (invoice_v1, invoice-extraction), so the assertions hold
whether the DB was clean or already seeded: the second run must create nothing,
and the final registry state must be exactly one bundle, one prompt, two versions.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from releaseplane_control.services.bootstrap import seed_invoice_v1

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="integration test needs Postgres"
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS = REPO_ROOT / "examples" / "invoice_extraction"


def test_seed_is_idempotent_and_registers_invoice_v1(client: TestClient) -> None:
    kwargs = {
        "prompt_v1_path": PROMPTS / "prompt_v1.yaml",
        "prompt_v2_path": PROMPTS / "prompt_v2.yaml",
    }
    seed_invoice_v1(client, **kwargs)  # type: ignore[arg-type]
    second = seed_invoice_v1(client, **kwargs)  # type: ignore[arg-type]

    # The second run registers nothing new.
    assert second.bundle_created is False
    assert second.versions_created == {"v1": False, "v2": False}

    bundles = [b for b in client.get("/policy-bundles").json() if b["name"] == "invoice_v1"]
    assert len(bundles) == 1
    assert bundles[0]["severity_mode"] == "enforce"
    assert bundles[0]["rules_json"]["checks"] == [
        "prompt_injection",
        "schema_validity",
        "arithmetic_consistency",
    ]
    assert bundles[0]["rules_json"]["injection_patterns"]

    prompts = [p for p in client.get("/prompts").json() if p["name"] == "invoice-extraction"]
    assert len(prompts) == 1
    versions = client.get(f"/prompts/{prompts[0]['id']}/versions").json()
    by_version = {v["version"]: v for v in versions}
    assert {"v1", "v2"} <= set(by_version)

    # v2 carries the discount paragraph that fixed case_14; v1 does not. (The
    # phrase is one the YAML literal block keeps on a single line.)
    assert "are not separate line items" in by_version["v2"]["system_prompt"]
    assert "are not separate line items" not in by_version["v1"]["system_prompt"]
    assert by_version["v1"]["checksum"] != by_version["v2"]["checksum"]

    # The output schema was resolved from the Pydantic model, not hand-written.
    assert "line_items" in by_version["v1"]["output_schema_json"]["properties"]
