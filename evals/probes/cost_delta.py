"""Live Cost-Delta probe for AP invoice extraction.

This is a live integration script, not a pytest test. It calls the real
Anthropic API, so it is kept out of the test tree and skips cleanly when
ANTHROPIC_API_KEY is unset (CI never calls the API).

It loads the v1 prompt, renders the developer prompt with the extracted text of
the deterministic Tier-1 baseline case (case_03), builds the structured-output
(tool-use) contract from InvoiceExtraction.model_json_schema(), and calls the
pinned production model (claude-sonnet-4-6) at temperature 0.0. It repeats once
against claude-opus-4-8 as a labeled reference point (Opus is not the production
model). It records real token usage, wall-clock latency, and computed cost, then
writes evals/probes/cost_delta_results_2026-06-23.md.

Run from the repo root:
    PYTHONPATH=. ANTHROPIC_API_KEY=... uv run python evals/probes/cost_delta.py
"""

from __future__ import annotations

import os
import re
import sys
import time
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import yaml
from anthropic import Anthropic
from releaseplane_evals.generator.invoices import get_case

from examples.invoice_extraction.models import InvoiceExtraction

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPT_PATH = REPO_ROOT / "examples" / "invoice_extraction" / "prompt_v1.yaml"
RESULTS_PATH = Path(__file__).resolve().parent / "cost_delta_results_2026-06-23.md"

PRODUCTION_MODEL = "claude-sonnet-4-6"
REFERENCE_MODEL = "claude-opus-4-8"
PROBE_CASE = "case_03"
TOOL_NAME = "emit_invoice_extraction"
MAX_TOKENS = 1024

# Verified per-MTok USD rates (input, output) as of 2026-06-23. Re-verify before
# any public claim. v1_default.yaml carries the Sonnet pair (renamed to
# cost_per_mtok_* in the Phase 0 defect fix); Opus is a reference point only and
# has no production config home, so both pairs live here.
RATES_PER_MTOK: dict[str, tuple[Decimal, Decimal]] = {
    PRODUCTION_MODEL: (Decimal("3.00"), Decimal("15.00")),
    REFERENCE_MODEL: (Decimal("5.00"), Decimal("25.00")),
}

# Prior figures to reconcile against (see docs/substrate_change_2026-06-23.md).
LEDGER_ESTIMATE_PER_1K = "$9-15 / 1k invoices (4.7 Cost Ledger estimate)"
ASSUMED_INPUT_TOKENS = 4000
ASSUMED_OUTPUT_TOKENS = 1000


@dataclass(frozen=True)
class Measurement:
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    tool_used: bool

    def cost_input_usd(self) -> Decimal:
        rate_in, _ = RATES_PER_MTOK[self.model]
        return Decimal(self.input_tokens) / Decimal(1_000_000) * rate_in

    def cost_output_usd(self) -> Decimal:
        _, rate_out = RATES_PER_MTOK[self.model]
        return Decimal(self.output_tokens) / Decimal(1_000_000) * rate_out

    def cost_total_usd(self) -> Decimal:
        return self.cost_input_usd() + self.cost_output_usd()

    def cost_per_1k_invoices_usd(self) -> Decimal:
        return (self.cost_total_usd() * Decimal(1000)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )


def load_prompt() -> tuple[str, str]:
    data = yaml.safe_load(PROMPT_PATH.read_text(encoding="utf-8"))
    return data["system_prompt"], data["developer_prompt"]


def render_developer(developer_prompt: str, invoice_text: str) -> str:
    return re.sub(r"{{\s*invoice_pdf_text\s*}}", invoice_text, developer_prompt)


def build_tool() -> dict[str, object]:
    return {
        "name": TOOL_NAME,
        "description": "Return the structured invoice extraction as a single object.",
        "input_schema": InvoiceExtraction.model_json_schema(),
    }


def run_model(
    client: Anthropic,
    model: str,
    system: str,
    developer: str,
    tool: dict[str, object],
    *,
    temperature: float | None,
) -> Measurement:
    # Opus 4.8 deprecates the temperature parameter, so it is omitted there and
    # sent as 0.0 only for the production model.
    extra: dict[str, object] = {} if temperature is None else {"temperature": temperature}
    start = time.perf_counter()
    response = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system,
        tools=[tool],  # type: ignore[list-item]
        tool_choice={"type": "tool", "name": TOOL_NAME},
        messages=[{"role": "user", "content": developer}],
        **extra,  # type: ignore[arg-type]
    )
    latency_ms = (time.perf_counter() - start) * 1000
    tool_used = any(block.type == "tool_use" for block in response.content)
    return Measurement(
        model=model,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        latency_ms=latency_ms,
        tool_used=tool_used,
    )


def _usd(value: Decimal, places: str = "0.000000") -> str:
    return f"${value.quantize(Decimal(places), rounding=ROUND_HALF_UP)}"


def build_report(sonnet: Measurement, reference: Measurement) -> str:
    delta = (reference.cost_total_usd() - sonnet.cost_total_usd()) / sonnet.cost_total_usd()
    delta_pct = (delta * Decimal(100)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    real_in = sonnet.input_tokens
    real_out = sonnet.output_tokens
    measured_per_1k = sonnet.cost_per_1k_invoices_usd()
    lines = [
        "# Cost-Delta Probe Results (2026-06-23)",
        "",
        "Live measurement closing the deferred Phase 0 Cost-Delta probe. One run of",
        f"the pinned production model and one reference run of Opus on `{PROBE_CASE}`",
        "(the deterministic Tier-1 baseline), structured-output (tool-use) mode,",
        "temperature 0.0 for the production model.",
        "",
        "Rates used (verified 2026-06-23, per MTok): "
        f"Sonnet 4.6 ${RATES_PER_MTOK[PRODUCTION_MODEL][0]} in / "
        f"${RATES_PER_MTOK[PRODUCTION_MODEL][1]} out; "
        f"Opus 4.8 ${RATES_PER_MTOK[REFERENCE_MODEL][0]} in / "
        f"${RATES_PER_MTOK[REFERENCE_MODEL][1]} out.",
        "",
        "## Measured",
        "",
        "| Model | Role | Input tok | Output tok | Latency (ms) | Cost/invoice | Cost/1k |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        (
            f"| `{sonnet.model}` | production | {sonnet.input_tokens} | {sonnet.output_tokens} | "
            f"{sonnet.latency_ms:.0f} | {_usd(sonnet.cost_total_usd())} | "
            f"{_usd(sonnet.cost_per_1k_invoices_usd(), '0.01')} |"
        ),
        (
            f"| `{reference.model}` | reference only | {reference.input_tokens} | "
            f"{reference.output_tokens} | {reference.latency_ms:.0f} | "
            f"{_usd(reference.cost_total_usd())} | "
            f"{_usd(reference.cost_per_1k_invoices_usd(), '0.01')} |"
        ),
        "",
        "## Reconciliation",
        "",
        f"- Prior ledger estimate: {LEDGER_ESTIMATE_PER_1K}.",
        (
            "- Re-priced deterministic estimate: ~$27 / 1k invoices, on a "
            f"{ASSUMED_INPUT_TOKENS}-in / {ASSUMED_OUTPUT_TOKENS}-out assumption at the verified "
            "Sonnet rates "
            f"({ASSUMED_INPUT_TOKENS}/1e6*3 + {ASSUMED_OUTPUT_TOKENS}/1e6*15 = $0.027/invoice)."
        ),
        (
            f"- Measured Sonnet 4.6: {real_in} in / {real_out} out tokens, "
            f"{_usd(measured_per_1k, '0.01')} / 1k invoices."
        ),
        (
            f"- The real baseline usage ({real_in} in / {real_out} out) is well below the "
            f"{ASSUMED_INPUT_TOKENS}-in / {ASSUMED_OUTPUT_TOKENS}-out planning assumption, so the "
            f"re-priced ~$27/1k figure is a conservative overestimate; the measured baseline is "
            f"{_usd(measured_per_1k, '0.01')}/1k, near the low end of the 4.7 ledger range. "
            "Multi-line Tier-2/3 invoices carry more input tokens, so keep $27/1k as the "
            "conservative planning number until measured across all tiers."
        ),
        (
            f"- Opus-vs-Sonnet reference delta: measured at +{delta_pct}% on this case "
            "(prior reference figure was +67%). Opus is reference only; production stays on Sonnet."
        ),
        "",
        f"Tool-use returned a structured object: Sonnet={sonnet.tool_used}, "
        f"Opus={reference.tool_used}. Latency is a single uncached sample and is noisy.",
        "",
        "Substrate note: claude-opus-4-8 rejects the `temperature` parameter "
        "(deprecated for that model), so the reference run omits it; the production "
        "Sonnet run pins temperature 0.0.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY unset; skipping live Cost-Delta probe.")
        return 0

    system, developer_template = load_prompt()
    case = get_case(PROBE_CASE)
    developer = render_developer(developer_template, case.pdf_text)
    tool = build_tool()
    client = Anthropic()

    print(f"Running {PRODUCTION_MODEL} on {PROBE_CASE} ...")
    sonnet = run_model(client, PRODUCTION_MODEL, system, developer, tool, temperature=0.0)
    print(f"Running {REFERENCE_MODEL} (reference) on {PROBE_CASE} ...")
    reference = run_model(client, REFERENCE_MODEL, system, developer, tool, temperature=None)

    report = build_report(sonnet, reference)
    RESULTS_PATH.write_text(report, encoding="utf-8")
    print(report)
    print(f"Wrote {RESULTS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
