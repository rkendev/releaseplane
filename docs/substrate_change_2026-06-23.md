# Substrate Change - Re-Validation Record

Date: 2026-06-23
Author substrate this session: claude-opus-4-8
Full council transcript: `substrate_revalidation_council_2026-06-23.md`

## The event

The prior Phase 0 session for ReleasePlane ran on an unintended authoring substrate, Opus 4.7. This session runs on Opus 4.8. Rather than ignore the swap, the project treats it as the first real model-retirement event it has to handle, which is the exact failure class the system is built around (`Use_Case.txt`: "silent model retirements mean the substrate changes whether teams opt in or not, and they only find out through user complaints"). The handover to Phase 1 was held until the six locked Phase 0 verdicts were re-validated against the new substrate.

Detection was manual: the change was noticed from the model selector and recorded, not caught by ReleasePlane tooling. The Substrate Pin rule (echo the active model in every session opener) is now in force as a convention. Automating that check is logged as open item U4.

## The decoupling that determines the result

The substrate that changed is the **authoring** model, the one reasoning about the design. The six verdicts govern either the **production inference layer**, which is pinned to `claude-sonnet-4-6` and did not change, or **deterministic, model-independent** layers (Pydantic schemas, code-computed gates, dataset sizing, regex filters). The layer that changed and the layers the verdicts depend on are decoupled. That is why the verdicts hold, and it is a real finding rather than a wave-through: the one verdict that does make a claim about model behavior was marked qualified, not clean.

## The six re-validation verdicts

| # | Verdict | Result | Reason it held |
|---|---|---|---|
| V1 | AP invoice extraction MVP | YES, unchanged | Use-case choice is model-agnostic; its justifying failure modes are generation-independent. |
| V2 | Claude primary; `generate_structured(schema)` adapter | QUALIFIED-YES | Holds, and is the verdict designed to absorb a substrate change. Assumption flagged: structured-output / tool-use reliability is scoped to the pinned production model (Sonnet 4.6), not the authoring model that changed. Durability is conditional on the pin holding. |
| V3 | Schema + arithmetic (+/-0.01) + checksum gates; T1+T2 gating, T3 monitored | YES, unchanged | Deterministic checks on output; the arithmetic gate is precisely what would catch a substrate-induced regression. |
| V4 | JSON-schema + arithmetic (output) + injection regex (input) | YES, unchanged | Policies execute outside the model boundary. |
| V5 | 30-case floor (10/10/10), generator-emitted, fixed seed | YES, unchanged | Dataset sizing is measurement rigor; a denominator does not depend on the model. |
| V6 | Pydantic v2 source of truth; JSON Schema generated | YES, unchanged | Schema-source choice is a software-engineering decision outside the model boundary. |

The qualification on V2 is the only model-behavior assumption in the set: the prior verdict assumed the production model's structured-output reliability. The substrate that changed does not carry that property (the production pin does), so the assumption held this session. The qualification records that the verdict's safety is conditional on the pin, which is the thing this project exists to watch. Action: a one-line note on the adapter contract / ADR 0002 stating the assertion is against `claude-sonnet-4-6`, with a re-test trigger keyed to any future change of the production pin.

Three prior unresolved disagreements (U1 Pydantic vs raw JSON Schema, U2 regex vs classifier, U3 Tier-3 gating) carry forward unchanged with their original triggers. One new item surfaced: U4, automating authoring-substrate detection rather than relying on the manual pin.

## Cost Ledger delta

The substrate change does not move the production Cost Ledger at the inference layer, because production is pinned to Sonnet 4.6 and Sonnet pricing is unchanged. Two corrections did surface during re-pricing:

- Re-pricing the transcript's own 4k-in / 1k-out assumption on verified current Sonnet 4.6 rates ($3 / $15 per MTok) yields **~$27 / 1k invoices**, against the **$9-15 / 1k** the 4.7-era Ledger stated. The prior figure understated production cost. [volatile: 2026-06-23]
- Opus 4.8 as an inference model (reference only, not the production path) would cost ~$45 / 1k invoices, a +67% delta over Sonnet 4.6. This matters only as the cost of ever confusing the authoring model for the inference model, which the pinned config and the adapter Protocol prevent. [volatile: 2026-06-23]

The live, measured portion of the Cost-Delta Probe (real token counts, latency, billed cost) could not run this session: no API credential exists in the design-session sandbox, and no eval case is committed yet. It is marked defer-to-Phase-1-entry, to run on the VPS against the generated dataset. No latency or billed-cost number was invented.

## Newly-surfaced risks

1. **Manual detection (U4).** ReleasePlane did not catch its own substrate change; a human did. The Substrate Pin is a convention, not enforcement. Until a CI check exists, a future drift can still pass unnoticed if a session opener omits the model echo.
2. **`v1_default.yaml` cost-field label bug (fixed in Phase 1).** The cost fields held the per-million rates under per-thousand field names, so a dashboard reading them literally was off by 1000x. Renamed to `cost_per_mtok_input_usd` / `cost_per_mtok_output_usd` (values unchanged).
3. **Missing eval dataset and generator.** `evals/generator/invoices.py` and `datasets/invoice_v1/` do not exist yet. Until they do, neither the arithmetic-gate demo headline nor a live Cost-Delta run can execute. This is Phase 4 work but it gates the demo.
4. **Opus 4.7 artifacts are now unauditable on their original substrate.** Any 4.7-specific reasoning in Phase 0 cannot be re-run on 4.7. Mitigation applied: prior-session record renamed from `workflow_opus_4_7.txt` to `workflow_phase0_locked.txt` so the substrate is not encoded in the filename of an artifact meant to outlive it; Cost Ledger marked volatile and superseded.

## Decision

**Proceed to Phase 1.** All six verdicts survive (five unchanged, one qualified-yes that does not block). No part of Phase 0 needs to be re-done. The only Phase 0 changes are documentation: Cost Ledger re-priced and marked, DEMO.md given a substrate-change beat, V2 assumption note, and the four risks above filed as Phase 1 backlog. ReleasePlane is ready to hand to the Phase 1 executor for dev-kit hardening.

---

> "I caught my own platform's first model substrate change at Phase 0 and shipped the audit trail before writing the next line of code."

(Truthful as written: the change was caught at the design gate, the six verdicts were re-validated, and this record plus the council transcript and CHANGELOG entry were committed before any Phase 1 code. The catch was manual, by the engineer, not yet by ReleasePlane's own tooling; automating it is open item U4.)
