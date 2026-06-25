"""Live eval run against the real model, to record the baseline numbers.

This is the one deliberate live-spend path in Phase 4. It is not a pytest test
(it lives outside testpaths) and CI never runs it. It skips cleanly when no
Anthropic key is configured, so it cannot spend by accident.

It drives the running dev stack: it loads the golden dataset into the control
plane (idempotent) and runs the evals runner, which calls the gateway POST
/invoke per case. The spend happens in the gateway, so the gateway must be
started with GATEWAY_PROVIDER=claude and a valid key; this script's key check is
the safety that you meant to spend. Expected cost for the 30 cases is roughly
$0.26 to $0.81 against Sonnet 4.6.

Run from the repo root with PYTHONPATH=. (so the reference examples package
resolves, as the cost-delta probe needs), against a stack whose gateway uses the
claude provider:

    PYTHONPATH=. CLAUDE_API_KEY_FILE=infra/secrets/claude_api_key \
    CONTROL_PLANE_URL=http://localhost:8001 GATEWAY_URL=http://localhost:8002 \
    uv run python evals/scripts/run_eval_live.py --release-id <RELEASE_ID>
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import httpx
from releaseplane_evals.loader import DATASET_NAME, build_dataset_payload, load_dataset
from releaseplane_evals.runner import run_eval


def _has_anthropic_key() -> bool:
    """Mirror the gateway's key resolution: secret file, then env."""
    key_file = os.environ.get("CLAUDE_API_KEY_FILE")
    if key_file and Path(key_file).exists() and Path(key_file).read_text(encoding="utf-8").strip():
        return True
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY"))


async def _run(cp_url: str, gw_url: str, release_id: str, dataset_name: str) -> None:
    async with (
        httpx.AsyncClient(base_url=cp_url, timeout=120.0) as cp_client,
        httpx.AsyncClient(base_url=gw_url, timeout=120.0) as gw_client,
    ):
        load = await load_dataset(cp_client, build_dataset_payload(dataset_name))
        dataset_id = load["dataset"]["id"]
        print(f"dataset {dataset_name} ready (id={dataset_id}); running live eval ...")
        run = await run_eval(
            cp_client=cp_client,
            gw_client=gw_client,
            release_id=release_id,
            dataset_id=dataset_id,
        )
    print(f"\neval run {run['id']} status={run['status']}")
    for tier, summary in sorted(run.get("summary_json", {}).get("tiers", {}).items()):
        rates = {name: round(summary[name]["rate"], 3) for name in summary if name != "count"}
        print(f"  tier {tier} (n={summary['count']}): {rates}")
    print("\nPer-request cost is recorded on the gateway invoke spans and Grafana.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a live eval against the real model.")
    parser.add_argument("--release-id", required=True, help="Release to evaluate (any stage).")
    parser.add_argument("--dataset-name", default=DATASET_NAME)
    parser.add_argument(
        "--control-plane-url", default=os.environ.get("CONTROL_PLANE_URL", "http://localhost:8001")
    )
    parser.add_argument(
        "--gateway-url", default=os.environ.get("GATEWAY_URL", "http://localhost:8002")
    )
    args = parser.parse_args(argv)

    if not _has_anthropic_key():
        print(
            "no Anthropic key configured (CLAUDE_API_KEY_FILE / ANTHROPIC_API_KEY); "
            "skipping live eval."
        )
        return 0

    asyncio.run(_run(args.control_plane_url, args.gateway_url, args.release_id, args.dataset_name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
