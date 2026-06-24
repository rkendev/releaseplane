"""Integration tests for the promote endpoint. Require Postgres."""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="integration test needs Postgres"
)

VERSION_BASE = {
    "variables_schema_json": {"type": "object"},
    "output_schema_json": {"type": "object"},
    "created_by": "tester",
}


def _scaffold(client: TestClient) -> dict[str, str]:
    """Create a prompt with two versions, a model config, and a policy bundle."""
    mc = client.post("/model-configs/seed").json()
    prompt = client.post(
        "/prompts", json={"name": f"prompt-{uuid.uuid4().hex[:10]}", "team": "ap", "use_case": "x"}
    ).json()
    v1 = client.post(
        f"/prompts/{prompt['id']}/versions",
        json={"version": "v1", "system_prompt": "s1", "developer_prompt": "d1", **VERSION_BASE},
    ).json()
    v2 = client.post(
        f"/prompts/{prompt['id']}/versions",
        json={"version": "v2", "system_prompt": "s2", "developer_prompt": "d2", **VERSION_BASE},
    ).json()
    pb = client.post(
        "/policy-bundles",
        json={
            "name": f"pb-{uuid.uuid4().hex[:8]}",
            "version": "v1",
            "rules_json": {},
            "severity_mode": "block",
        },
    ).json()
    return {"mc": mc["id"], "v1": v1["id"], "v2": v2["id"], "pb": pb["id"]}


def _release(client: TestClient, ids: dict[str, str], version_key: str) -> dict[str, object]:
    return client.post(
        "/releases",
        json={
            "prompt_version_id": ids[version_key],
            "model_config_id": ids["mc"],
            "policy_bundle_id": ids["pb"],
        },
    ).json()


def test_forward_walk_draft_candidate_active(client: TestClient) -> None:
    ids = _scaffold(client)
    rel = _release(client, ids, "v1")
    rid = rel["id"]

    to_candidate = client.post(f"/releases/{rid}/promote")
    assert to_candidate.status_code == 200
    assert to_candidate.json()["stage"] == "candidate"
    assert to_candidate.json()["activated_at"] is None

    to_active = client.post(f"/releases/{rid}/promote")
    assert to_active.status_code == 200
    assert to_active.json()["stage"] == "active"
    assert to_active.json()["activated_at"] is not None


def test_promoting_active_is_rejected(client: TestClient) -> None:
    ids = _scaffold(client)
    rel = _release(client, ids, "v1")
    rid = rel["id"]
    client.post(f"/releases/{rid}/promote")
    client.post(f"/releases/{rid}/promote")
    blocked = client.post(f"/releases/{rid}/promote")
    assert blocked.status_code == 409
    assert "stage active" in blocked.json()["detail"]


def test_promote_supersedes_prior_active(client: TestClient) -> None:
    ids = _scaffold(client)
    first = _release(client, ids, "v1")
    second = _release(client, ids, "v2")

    client.post(f"/releases/{first['id']}/promote")
    client.post(f"/releases/{first['id']}/promote")
    client.post(f"/releases/{second['id']}/promote")
    client.post(f"/releases/{second['id']}/promote")

    first_now = client.get(f"/releases/{first['id']}").json()
    second_now = client.get(f"/releases/{second['id']}").json()
    assert second_now["stage"] == "active" and second_now["archived_at"] is None
    assert first_now["stage"] == "active" and first_now["archived_at"] is not None


def test_promote_missing_release_is_404(client: TestClient) -> None:
    assert client.post(f"/releases/{uuid.uuid4()}/promote").status_code == 404


def test_eval_gate_enforced_blocks(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    ids = _scaffold(client)
    rel = _release(client, ids, "v1")
    monkeypatch.setenv("EVAL_GATE_ENFORCED", "true")
    blocked = client.post(f"/releases/{rel['id']}/promote")
    assert blocked.status_code == 409
    assert "no eval run found" in blocked.json()["detail"]
