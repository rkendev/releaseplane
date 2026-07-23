"""Thin console CLI over the control-plane HTTP API.

Four demo verbs, each a single httpx call against the control plane, so the CLI
carries no business logic of its own and cannot drift from the API:

    releaseplane prompts list
    releaseplane releases list
    releaseplane releases promote <release_id>
    releaseplane eval status --release-id <release_id>

The base URL resolves from --url, then the RELEASEPLANE_URL environment
variable, then the host-published control-plane port (see docs/RUNBOOK.md). No
verb reaches a provider, so the CLI has no live-call surface.

`eval status` reads the latest run and its per-tier pass rates but reports no
gate verdict: the thresholds live in the control plane (services/eval_gate.py),
and restating them here would be a second copy that could drift. The verdict is
surfaced where it is enforced, by `releases promote` returning the 409 reason.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Callable
from typing import Any

import httpx

DEFAULT_URL = "http://localhost:8001"
CONNECT_TIMEOUT_S = 30.0

# Print order for the per-tier metric rates, so output is stable regardless of
# dict ordering in the summary. Mirrors releaseplane_evals.scorers metric names.
METRIC_ORDER = ["schema_validity", "arithmetic_consistency", "checksum_match"]

ClientFactory = Callable[[str], httpx.Client]


def _default_client_factory(base_url: str) -> httpx.Client:
    return httpx.Client(base_url=base_url, timeout=CONNECT_TIMEOUT_S)


def _base_url(args: argparse.Namespace) -> str:
    # --url is attached to both the top-level parser and every subcommand (via a
    # shared parent), so it is accepted on either side of the verb. The parent
    # uses SUPPRESS as its default so an absent --url never clobbers a value the
    # other parser already set; hence getattr rather than a plain attribute read.
    url = getattr(args, "url", None)
    if url:
        return str(url)
    return os.environ.get("RELEASEPLANE_URL", DEFAULT_URL)


def _detail(response: httpx.Response) -> str:
    """The control plane's error detail, or a fallback if the body is not JSON."""
    try:
        body = response.json()
    except ValueError:
        return response.text.strip() or f"HTTP {response.status_code}"
    if isinstance(body, dict) and "detail" in body:
        return str(body["detail"])
    return f"HTTP {response.status_code}"


def _cmd_prompts_list(client: httpx.Client, args: argparse.Namespace) -> int:
    response = client.get("/prompts")
    response.raise_for_status()
    prompts: list[dict[str, Any]] = response.json()
    if not prompts:
        print("no prompts")
        return 0
    for prompt in prompts:
        print(f"{prompt['id']}  {prompt['name']}  ({prompt['use_case']})")
    return 0


def _cmd_releases_list(client: httpx.Client, args: argparse.Namespace) -> int:
    response = client.get("/releases")
    response.raise_for_status()
    releases: list[dict[str, Any]] = response.json()
    if not releases:
        print("no releases")
        return 0
    for release in releases:
        print(f"{release['id']}  {release['stage']}  (created {release['created_at']})")
    return 0


def _cmd_releases_promote(client: httpx.Client, args: argparse.Namespace) -> int:
    response = client.post(f"/releases/{args.release_id}/promote")
    if response.status_code == httpx.codes.CONFLICT:
        # The gate (or an illegal transition) blocked the promotion. This is an
        # expected outcome, not a crash: print the reason on one line, exit 1.
        print(_detail(response))
        return 1
    response.raise_for_status()
    release: dict[str, Any] = response.json()
    print(f"{release['id']}  promoted to {release['stage']}")
    return 0


def _cmd_eval_status(client: httpx.Client, args: argparse.Namespace) -> int:
    response = client.get("/eval-runs", params={"release_id": args.release_id})
    response.raise_for_status()
    runs: list[dict[str, Any]] = response.json()
    if not runs:
        print(f"no eval runs for release {args.release_id}")
        return 0
    # The control plane orders runs started_at descending, so the latest is first.
    run = runs[0]
    print(f"run {run['id']}  status={run['status']}")
    summary = run.get("summary_json")
    if not summary:
        print("  (no summary; run has not completed)")
        return 0
    for tier, tier_summary in sorted(summary.get("tiers", {}).items()):
        rates = " ".join(
            f"{metric.split('_')[0]} {tier_summary[metric]['rate']:.0%}"
            for metric in METRIC_ORDER
            if metric in tier_summary
        )
        print(f"  tier {tier} (n={tier_summary.get('count', 0)}): {rates}")
    return 0


def _url_parent() -> argparse.ArgumentParser:
    """A shared parent carrying --url, so it is accepted before or after the verb."""
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "--url",
        default=argparse.SUPPRESS,
        help="Control-plane base URL (default: $RELEASEPLANE_URL, then http://localhost:8001).",
    )
    return parent


def _build_parser() -> argparse.ArgumentParser:
    url = _url_parent()
    parser = argparse.ArgumentParser(
        prog="releaseplane",
        parents=[url],
        description="Thin client for the ReleasePlane control plane.",
    )
    top = parser.add_subparsers(dest="group", required=True)

    prompts = top.add_parser("prompts", help="Prompt registry.").add_subparsers(
        dest="command", required=True
    )
    prompts.add_parser("list", parents=[url], help="List prompt definitions.").set_defaults(
        func=_cmd_prompts_list
    )

    releases = top.add_parser("releases", help="Release lifecycle.").add_subparsers(
        dest="command", required=True
    )
    releases.add_parser("list", parents=[url], help="List releases.").set_defaults(
        func=_cmd_releases_list
    )
    promote = releases.add_parser(
        "promote", parents=[url], help="Promote a release one hop toward active."
    )
    promote.add_argument("release_id", help="The release id to promote.")
    promote.set_defaults(func=_cmd_releases_promote)

    evals = top.add_parser("eval", help="Eval runs.").add_subparsers(dest="command", required=True)
    status = evals.add_parser(
        "status", parents=[url], help="Show the latest eval run for a release."
    )
    status.add_argument("--release-id", required=True, help="The release id to report on.")
    status.set_defaults(func=_cmd_eval_status)

    return parser


def main(argv: list[str] | None = None, *, client_factory: ClientFactory | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    factory = client_factory or _default_client_factory
    base_url = _base_url(args)
    try:
        with factory(base_url) as client:
            handler: Callable[[httpx.Client, argparse.Namespace], int] = args.func
            return handler(client, args)
    except httpx.HTTPStatusError as exc:
        print(f"error: {_detail(exc.response)}")
        return 1
    except httpx.HTTPError as exc:
        # Connection refused, timeout, DNS, etc. Report the target rather than a traceback.
        print(f"error: cannot reach control plane at {base_url}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
