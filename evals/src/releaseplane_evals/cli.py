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

DEFAULT_CONTROL_PLANE_URL = "http://localhost:8000"


def control_plane_url() -> str:
    return os.environ.get("CONTROL_PLANE_URL", DEFAULT_CONTROL_PLANE_URL)


async def _run_load(base_url: str, dataset_name: str) -> None:
    payload = build_dataset_payload(dataset_name)
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        result = await load_dataset(client, payload)
    dataset = result["dataset"]
    print(
        f"loaded dataset {dataset['name']} (row_count={dataset['row_count']}): "
        f"cases_created={result['cases_created']} cases_total={result['cases_total']}"
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="releaseplane-evals", description="ReleasePlane eval harness CLI."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    load_parser = sub.add_parser("load", help="Load the golden dataset into the control plane.")
    load_parser.add_argument("--control-plane-url", default=control_plane_url())
    load_parser.add_argument("--dataset-name", default=DATASET_NAME)

    args = parser.parse_args(argv)
    if args.command == "load":
        asyncio.run(_run_load(args.control_plane_url, args.dataset_name))


if __name__ == "__main__":
    main()
