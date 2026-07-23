"""Unit tests for the policy-bundle seeder's drift guard. No DB, no Postgres.

seed_policy_bundle drives the control-plane HTTP API through an injected client,
so the drift behaviour is exercised against an httpx MockTransport rather than a
live server: a matching stored bundle is a no-op, an absent one is created, and a
stored bundle whose content differs from the seed raises rather than skipping.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from releaseplane_control.services.bootstrap import (
    INVOICE_V1_BUNDLE,
    SeedDriftError,
    _bundle_drift,
    seed_policy_bundle,
)


def _stored_from_seed(**overrides: Any) -> dict[str, Any]:
    """A stored-bundle record shaped like PolicyBundleRead, seeded then overridden."""
    record = {
        "id": "00000000-0000-0000-0000-000000000001",
        "name": INVOICE_V1_BUNDLE["name"],
        "version": INVOICE_V1_BUNDLE["version"],
        "rules_json": INVOICE_V1_BUNDLE["rules_json"],
        "severity_mode": INVOICE_V1_BUNDLE["severity_mode"],
    }
    record.update(overrides)
    return record


def _client(existing: list[dict[str, Any]], posted: list[dict[str, Any]]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/policy-bundles":
            return httpx.Response(200, json=existing)
        if request.method == "POST" and request.url.path == "/policy-bundles":
            posted.append(json.loads(request.content))
            return httpx.Response(201, json=_stored_from_seed())
        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    return httpx.Client(base_url="http://cp", transport=httpx.MockTransport(handler))


def test_bundle_drift_detects_severity_and_rules() -> None:
    assert _bundle_drift(_stored_from_seed(), INVOICE_V1_BUNDLE) == []
    assert _bundle_drift(_stored_from_seed(severity_mode="warn"), INVOICE_V1_BUNDLE)
    assert _bundle_drift(_stored_from_seed(rules_json={}), INVOICE_V1_BUNDLE)


def test_seed_creates_when_absent() -> None:
    posted: list[dict[str, Any]] = []
    with _client(existing=[], posted=posted) as client:
        created = seed_policy_bundle(client, INVOICE_V1_BUNDLE)
    assert created is True
    assert len(posted) == 1
    assert posted[0]["name"] == INVOICE_V1_BUNDLE["name"]


def test_seed_is_noop_when_stored_matches() -> None:
    posted: list[dict[str, Any]] = []
    with _client(existing=[_stored_from_seed()], posted=posted) as client:
        created = seed_policy_bundle(client, INVOICE_V1_BUNDLE)
    assert created is False
    assert posted == []  # immutable: never rewrites a matching row


def test_seed_raises_on_single_field_drift() -> None:
    # Severity alone differs (rules match): the seeder must still refuse.
    drifted = _stored_from_seed(severity_mode="warn")
    posted: list[dict[str, Any]] = []
    with _client(existing=[drifted], posted=posted) as client:
        with pytest.raises(SeedDriftError) as excinfo:
            seed_policy_bundle(client, INVOICE_V1_BUNDLE)
    assert "severity_mode" in str(excinfo.value)
    assert "rules_json" not in str(excinfo.value)  # only the drifted field is named
    assert posted == []


def test_seed_raises_on_stale_empty_bundle() -> None:
    # The exact dev-volume failure: a row predating the policy engine with an
    # empty rules_json and a warn severity. The seeder must refuse, not skip.
    stale = _stored_from_seed(rules_json={}, severity_mode="warn")
    posted: list[dict[str, Any]] = []
    with _client(existing=[stale], posted=posted) as client:
        with pytest.raises(SeedDriftError) as excinfo:
            seed_policy_bundle(client, INVOICE_V1_BUNDLE)
    message = str(excinfo.value)
    assert "invoice_v1@v1" in message
    assert "severity_mode" in message
    assert "rules_json" in message
    assert posted == []  # nothing written on drift
