"""Integration tests for the registry routes. Require Postgres."""

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


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def test_seed_is_idempotent(client: TestClient) -> None:
    first = client.post("/model-configs/seed")
    assert first.status_code in (200, 201)
    body = first.json()
    assert body["model_name"] == "claude-sonnet-4-6"
    again = client.post("/model-configs/seed")
    assert again.status_code == 200
    assert again.json()["id"] == body["id"]


def test_create_prompt_version_release_happy_path(client: TestClient) -> None:
    mc = client.post("/model-configs/seed").json()
    prompt = client.post(
        "/prompts", json={"name": _unique("prompt"), "team": "ap", "use_case": "x"}
    ).json()

    v1 = client.post(
        f"/prompts/{prompt['id']}/versions",
        json={"version": "v1", "system_prompt": "s1", "developer_prompt": "d1", **VERSION_BASE},
    )
    v2 = client.post(
        f"/prompts/{prompt['id']}/versions",
        json={"version": "v2", "system_prompt": "s2", "developer_prompt": "d2", **VERSION_BASE},
    )
    assert v1.status_code == 201 and v2.status_code == 201
    assert v1.json()["checksum"] and v1.json()["checksum"] != v2.json()["checksum"]

    pb = client.post(
        "/policy-bundles",
        json={"name": _unique("pb"), "version": "v1", "rules_json": {}, "severity_mode": "block"},
    ).json()

    release = client.post(
        "/releases",
        json={
            "prompt_version_id": v1.json()["id"],
            "model_config_id": mc["id"],
            "policy_bundle_id": pb["id"],
        },
    )
    assert release.status_code == 201
    assert release.json()["stage"] == "draft"
    assert release.json()["activated_at"] is None


def test_duplicate_prompt_name_conflicts(client: TestClient) -> None:
    name = _unique("prompt")
    body = {"name": name, "team": "a", "use_case": "b"}
    assert client.post("/prompts", json=body).status_code == 201
    assert client.post("/prompts", json=body).status_code == 409


def test_duplicate_version_conflicts(client: TestClient) -> None:
    prompt = client.post(
        "/prompts", json={"name": _unique("prompt"), "team": "a", "use_case": "b"}
    ).json()
    body = {"version": "v1", "system_prompt": "s", "developer_prompt": "d", **VERSION_BASE}
    assert client.post(f"/prompts/{prompt['id']}/versions", json=body).status_code == 201
    assert client.post(f"/prompts/{prompt['id']}/versions", json=body).status_code == 409


def test_version_on_missing_prompt_is_404(client: TestClient) -> None:
    body = {"version": "v1", "system_prompt": "s", "developer_prompt": "d", **VERSION_BASE}
    resp = client.post(f"/prompts/{uuid.uuid4()}/versions", json=body)
    assert resp.status_code == 404


def test_release_with_dangling_reference_is_422(client: TestClient) -> None:
    mc = client.post("/model-configs/seed").json()
    pb = client.post(
        "/policy-bundles",
        json={"name": _unique("pb"), "version": "v1", "rules_json": {}, "severity_mode": "block"},
    ).json()
    resp = client.post(
        "/releases",
        json={
            "prompt_version_id": str(uuid.uuid4()),
            "model_config_id": mc["id"],
            "policy_bundle_id": pb["id"],
        },
    )
    assert resp.status_code == 422


def test_get_missing_release_is_404(client: TestClient) -> None:
    assert client.get(f"/releases/{uuid.uuid4()}").status_code == 404
