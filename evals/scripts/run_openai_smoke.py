"""The one deliberate OpenAI live-spend path: a single /invoke on case_03.

This is the only place in Phase 5 that may reach api.openai.com. It is not a
pytest test (it lives outside testpaths) and CI never runs it. It skips cleanly
when no OpenAI key is configured, so it cannot spend by accident.

It drives the running dev stack: it POSTs one /invoke for case_03 and prints the
serving provider, the model, token usage, the estimated cost, and a blended
cost-per-1k-invoices figure. To route the request to gpt-4o-mini the gateway must
be started with the OpenAI key and GATEWAY_PROVIDER unset (so selection follows
the model config), and the control plane must carry an OpenAI gpt-4o-mini model
config plus a routing rule that diverts this input to it (a routing_hint rule is
the simplest). Confirm the printed provider is "openai" before trusting the cost.

Run from the repo root with PYTHONPATH=. (so the reference examples package
resolves), against a stack whose gateway has the OpenAI key:

    PYTHONPATH=. OPENAI_API_KEY_FILE=infra/secrets/openai_api_key \
    GATEWAY_URL=http://localhost:8002 \
    uv run python evals/scripts/run_openai_smoke.py --routing-hint openai
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

import httpx
from releaseplane_evals.generator.invoices import get_case


def _has_openai_key() -> bool:
    """Mirror the gateway's key resolution: secret file, then env."""
    key_file = os.environ.get("OPENAI_API_KEY_FILE")
    if key_file and Path(key_file).exists() and Path(key_file).read_text(encoding="utf-8").strip():
        return True
    return bool(os.environ.get("OPENAI_API_KEY"))


def _invoke(
    gw_url: str, prompt_name: str, case_id: str, routing_hint: str | None
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "prompt_name": prompt_name,
        "variables": {"invoice_pdf_text": get_case(case_id).pdf_text},
    }
    if routing_hint is not None:
        body["routing_hint"] = routing_hint
    with httpx.Client(base_url=gw_url, timeout=120.0) as client:
        response = client.post("/invoke", json=body)
        response.raise_for_status()
        return dict(response.json())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="One gated OpenAI /invoke smoke on case_03.")
    parser.add_argument("--prompt-name", default="invoice-extraction")
    parser.add_argument("--case-id", default="case_03")
    parser.add_argument("--routing-hint", default=None, help="Caller hint to force the route.")
    parser.add_argument(
        "--gateway-url", default=os.environ.get("GATEWAY_URL", "http://localhost:8002")
    )
    args = parser.parse_args(argv)

    if not _has_openai_key():
        print("no OpenAI key configured (OPENAI_API_KEY_FILE / OPENAI_API_KEY); skipping smoke.")
        return 0

    result = _invoke(args.gateway_url, args.prompt_name, args.case_id, args.routing_hint)
    meta = result["metadata"]
    cost = float(meta["cost_estimate_usd"])
    print(f"served by provider : {meta['provider']}")
    print(f"model              : {meta['model']}")
    print(f"routing rule        : {meta['routing_rule_id']}")
    print(f"tokens (in/out)    : {meta['input_tokens']} / {meta['output_tokens']}")
    print(f"policy status      : {meta['policy_status']}")
    print(f"cost estimate (usd): {cost:.6f}")
    print(f"blended per 1k     : {cost * 1000:.2f}")
    if meta["provider"] != "openai":
        print("\nWARNING: the request did not route to the OpenAI adapter; check the routing rule.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
