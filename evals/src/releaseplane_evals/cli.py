"""Eval harness CLI.

Run as a module from the repo root, the same way the generator runs, so the
implicit `examples` namespace package (a repo-root reference, not an installed
module) resolves on the path:

    uv run python -m releaseplane_evals.cli load

There is no console-script entry point on purpose: an installed entry point does
not put the repo root on sys.path, so `examples` would not import. `load` builds
the golden dataset payload and posts it to the control plane at CONTROL_PLANE_URL
(default http://localhost:8000), so the eval tables live in the control-plane DB
without the control plane importing the generator.
"""

from __future__ import annotations

import argparse
import asyncio
import os

import httpx

from .loader import DATASET_NAME, build_dataset_payload, load_dataset
from .runner import run_eval

DEFAULT_CONTROL_PLANE_URL = "http://localhost:8000"
DEFAULT_GATEWAY_URL = "http://localhost:8000"


def control_plane_url() -> str:
    return os.environ.get("CONTROL_PLANE_URL", DEFAULT_CONTROL_PLANE_URL)


def gateway_url() -> str:
    return os.environ.get("GATEWAY_URL", DEFAULT_GATEWAY_URL)


async def _run_load(base_url: str, dataset_name: str) -> None:
    payload = build_dataset_payload(dataset_name)
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        result = await load_dataset(client, payload)
    dataset = result["dataset"]
    print(
        f"loaded dataset {dataset['name']} (row_count={dataset['row_count']}): "
        f"cases_created={result['cases_created']} cases_total={result['cases_total']}"
    )


async def _run_eval(cp_url: str, gw_url: str, release_id: str, dataset_id: str) -> None:
    async with (
        httpx.AsyncClient(base_url=cp_url, timeout=60.0) as cp_client,
        httpx.AsyncClient(base_url=gw_url, timeout=60.0) as gw_client,
    ):
        run = await run_eval(
            cp_client=cp_client,
            gw_client=gw_client,
            release_id=release_id,
            dataset_id=dataset_id,
        )
    print(f"eval run {run['id']} status={run['status']}")
    for tier, summary in sorted(run.get("summary_json", {}).get("tiers", {}).items()):
        rates = {name: round(summary[name]["rate"], 3) for name in summary if name != "count"}
        print(f"  tier {tier} (n={summary['count']}): {rates}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="releaseplane-evals", description="ReleasePlane eval harness CLI."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    load_parser = sub.add_parser("load", help="Load the golden dataset into the control plane.")
    load_parser.add_argument("--control-plane-url", default=control_plane_url())
    load_parser.add_argument("--dataset-name", default=DATASET_NAME)

    run_parser = sub.add_parser("run", help="Score a release over a dataset and persist the run.")
    run_parser.add_argument("--release-id", required=True)
    run_parser.add_argument("--dataset-id", required=True)
    run_parser.add_argument("--control-plane-url", default=control_plane_url())
    run_parser.add_argument("--gateway-url", default=gateway_url())

    args = parser.parse_args(argv)
    if args.command == "load":
        asyncio.run(_run_load(args.control_plane_url, args.dataset_name))
    elif args.command == "run":
        asyncio.run(
            _run_eval(args.control_plane_url, args.gateway_url, args.release_id, args.dataset_id)
        )


if __name__ == "__main__":
    main()
