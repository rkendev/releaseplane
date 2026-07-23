"""Unit tests for the thin releaseplane CLI.

No network and no control plane: every verb is driven through main(argv) against
an httpx MockTransport injected via the client-factory seam, so the tests assert
the request the CLI makes and the output it prints without a live server.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from releaseplane.cli import main

Handler = Callable[[httpx.Request], httpx.Response]


def _factory(handler: Handler) -> Callable[[str], httpx.Client]:
    """A client factory that routes every request through the given handler."""

    def build(base_url: str) -> httpx.Client:
        return httpx.Client(base_url=base_url, transport=httpx.MockTransport(handler))

    return build


def _run(argv: list[str], handler: Handler) -> int:
    return main(argv, client_factory=_factory(handler))


# --- prompts list -----------------------------------------------------------


def test_prompts_list(capsys: pytest.CaptureFixture[str]) -> None:
    captured_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_paths.append(request.url.path)
        return httpx.Response(
            200,
            json=[
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "name": "invoice-extraction",
                    "team": "ap",
                    "use_case": "ap_invoice_extraction",
                    "created_at": "2026-07-01T00:00:00Z",
                }
            ],
        )

    code = _run(["prompts", "list"], handler)
    out = capsys.readouterr().out
    assert code == 0
    assert captured_paths == ["/prompts"]
    assert "invoice-extraction" in out
    assert "ap_invoice_extraction" in out


def test_prompts_list_empty(capsys: pytest.CaptureFixture[str]) -> None:
    code = _run(["prompts", "list"], lambda request: httpx.Response(200, json=[]))
    assert code == 0
    assert "no prompts" in capsys.readouterr().out


# --- releases list ----------------------------------------------------------


def test_releases_list(capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/releases"
        return httpx.Response(
            200,
            json=[
                {
                    "id": "22222222-2222-2222-2222-222222222222",
                    "prompt_version_id": "33333333-3333-3333-3333-333333333333",
                    "model_config_id": "44444444-4444-4444-4444-444444444444",
                    "policy_bundle_id": "55555555-5555-5555-5555-555555555555",
                    "stage": "draft",
                    "rollout_percent": None,
                    "created_at": "2026-07-02T00:00:00Z",
                    "activated_at": None,
                    "archived_at": None,
                }
            ],
        )

    code = _run(["releases", "list"], handler)
    out = capsys.readouterr().out
    assert code == 0
    assert "22222222-2222-2222-2222-222222222222" in out
    assert "draft" in out


# --- releases promote -------------------------------------------------------


def test_releases_promote_success(capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/releases/abc/promote"
        return httpx.Response(
            200,
            json={
                "id": "abc",
                "prompt_version_id": "x",
                "model_config_id": "y",
                "policy_bundle_id": "z",
                "stage": "candidate",
                "rollout_percent": None,
                "created_at": "2026-07-02T00:00:00Z",
                "activated_at": None,
                "archived_at": None,
            },
        )

    code = _run(["releases", "promote", "abc"], handler)
    out = capsys.readouterr().out
    assert code == 0
    assert "promoted to candidate" in out


def test_releases_promote_blocked_409(capsys: pytest.CaptureFixture[str]) -> None:
    """A 409 is an expected outcome: print the reason on one line, exit 1, no traceback."""
    detail = "promotion blocked: tier 2 arithmetic_consistency 90% < 100%"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/releases/abc/promote"
        return httpx.Response(409, json={"detail": detail})

    code = _run(["releases", "promote", "abc"], handler)
    out = capsys.readouterr().out
    assert code == 1
    assert out.strip() == detail
    assert "Traceback" not in out


def test_releases_promote_not_found_404(capsys: pytest.CaptureFixture[str]) -> None:
    """A 404 (unknown release id) surfaces cleanly through the top-level handler."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "release not found"})

    code = _run(["releases", "promote", "nope"], handler)
    out = capsys.readouterr().out
    assert code == 1
    assert "release not found" in out
    assert "Traceback" not in out


# --- eval status ------------------------------------------------------------


def test_eval_status(capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/eval-runs"
        assert request.url.params["release_id"] == "rel-1"
        tier = {
            "count": 10,
            "schema_validity": {"passed": 10, "total": 10, "rate": 1.0},
            "arithmetic_consistency": {"passed": 9, "total": 10, "rate": 0.9},
            "checksum_match": {"passed": 10, "total": 10, "rate": 1.0},
        }
        return httpx.Response(
            200,
            json=[
                {
                    "id": "run-latest",
                    "release_id": "rel-1",
                    "dataset_id": "ds-1",
                    "started_at": "2026-07-03T00:00:00Z",
                    "finished_at": "2026-07-03T00:01:00Z",
                    "status": "succeeded",
                    "summary_json": {"tiers": {"2": tier}},
                }
            ],
        )

    code = _run(["eval", "status", "--release-id", "rel-1"], handler)
    out = capsys.readouterr().out
    assert code == 0
    assert "run-latest" in out
    assert "status=succeeded" in out
    assert "arithmetic 90%" in out
    assert "schema 100%" in out


def test_eval_status_no_runs(capsys: pytest.CaptureFixture[str]) -> None:
    code = _run(
        ["eval", "status", "--release-id", "rel-x"],
        lambda request: httpx.Response(200, json=[]),
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "no eval runs for release rel-x" in out


def test_eval_status_running_no_summary(capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "id": "run-inflight",
                    "release_id": "rel-1",
                    "dataset_id": "ds-1",
                    "started_at": "2026-07-03T00:00:00Z",
                    "finished_at": None,
                    "status": "running",
                    "summary_json": None,
                }
            ],
        )

    code = _run(["eval", "status", "--release-id", "rel-1"], handler)
    out = capsys.readouterr().out
    assert code == 0
    assert "status=running" in out
    assert "no summary" in out


# --- transport-level failures -----------------------------------------------


def test_connection_refused_is_clean(capsys: pytest.CaptureFixture[str]) -> None:
    """A dead control plane reports the target, not a stack trace."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    code = _run(["prompts", "list"], handler)
    out = capsys.readouterr().out
    assert code == 1
    assert "cannot reach control plane" in out
    assert "Traceback" not in out


def test_unexpected_500_is_clean(capsys: pytest.CaptureFixture[str]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    code = _run(["releases", "list"], handler)
    out = capsys.readouterr().out
    assert code == 1
    assert "boom" in out
    assert "Traceback" not in out


# --- url resolution ---------------------------------------------------------


def test_url_flag_overrides_default() -> None:
    seen: list[str] = []

    def build(base_url: str) -> httpx.Client:
        seen.append(base_url)
        return httpx.Client(
            base_url=base_url,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])),
        )

    code = main(["--url", "http://cp.example:9000", "prompts", "list"], client_factory=build)
    assert code == 0
    assert seen == ["http://cp.example:9000"]


def test_url_flag_accepted_after_the_verb() -> None:
    """--url is on a shared parent, so it works on either side of the subcommand."""
    seen: list[str] = []

    def build(base_url: str) -> httpx.Client:
        seen.append(base_url)
        return httpx.Client(
            base_url=base_url,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])),
        )

    code = main(["prompts", "list", "--url", "http://after-verb:9000"], client_factory=build)
    assert code == 0
    assert seen == ["http://after-verb:9000"]


def test_env_var_sets_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RELEASEPLANE_URL", "http://from-env:8888")
    seen: list[str] = []

    def build(base_url: str) -> httpx.Client:
        seen.append(base_url)
        return httpx.Client(
            base_url=base_url,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[])),
        )

    code = main(["prompts", "list"], client_factory=build)
    assert code == 0
    assert seen == ["http://from-env:8888"]
