"""Manual live smoke for the gateway Claude path. Not collected by pytest.

Runs one real structured-output call against the pinned production model
(claude-sonnet-4-6) on the deterministic Tier-1 baseline case (case_03), through
the same ClaudeProvider the gateway uses. This is the only intended live API
spend in Phase 3: it skips cleanly without a key and is never run by CI, and it
lives outside pytest's testpaths so the suite does not collect it.

Run from the repo root:
    PYTHONPATH=. ANTHROPIC_API_KEY=... uv run python gateway/scripts/smoke_invoke.py
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from decimal import Decimal
from pathlib import Path

import yaml
from anthropic import Anthropic
from releaseplane_evals.generator.invoices import get_case
from releaseplane_gateway.providers import ClaudeProvider, ModelInvocationConfig

from examples.invoice_extraction.models import InvoiceExtraction

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_PATH = REPO_ROOT / "examples" / "invoice_extraction" / "prompt_v1.yaml"
MODEL_CONFIG_PATH = REPO_ROOT / "infra" / "model_configs" / "v1_default.yaml"
PROBE_CASE = "case_03"


def _load_model_config() -> ModelInvocationConfig:
    data = yaml.safe_load(MODEL_CONFIG_PATH.read_text(encoding="utf-8"))
    return ModelInvocationConfig(
        model=data["model_name"],
        temperature=float(data["temperature"]),
        max_tokens=int(data["max_tokens"]),
        tool_mode=data["tool_mode"],
        cost_per_mtok_input_usd=Decimal(str(data["cost_per_mtok_input_usd"])),
        cost_per_mtok_output_usd=Decimal(str(data["cost_per_mtok_output_usd"])),
    )


def _render(developer_prompt: str, invoice_text: str) -> str:
    return re.sub(r"{{\s*invoice_pdf_text\s*}}", invoice_text, developer_prompt)


async def _run() -> None:
    prompt = yaml.safe_load(PROMPT_PATH.read_text(encoding="utf-8"))
    case = get_case(PROBE_CASE)
    developer = _render(prompt["developer_prompt"], case.pdf_text)
    provider = ClaudeProvider(Anthropic())
    result = await provider.generate_structured(
        system=prompt["system_prompt"],
        prompt=developer,
        model_config=_load_model_config(),
        output_schema=InvoiceExtraction.model_json_schema(),
    )
    print(f"model: {result.model}")
    print(f"tokens: in={result.input_tokens} out={result.output_tokens}")
    print(f"finish_reason: {result.finish_reason}")
    print(f"output: {result.output}")


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY unset; skipping live gateway smoke.")
        return 0
    asyncio.run(_run())
    return 0


if __name__ == "__main__":
    sys.exit(main())
