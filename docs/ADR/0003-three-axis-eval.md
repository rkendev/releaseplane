# ADR 0003: Three-axis evaluation (objective + component + quantitative) at v1

Date: 2026-06-23
Status: Accepted

## Context

The Stanford CS230 LLM applications lecture frames evaluation as three orthogonal axes: objective vs subjective, component vs end-to-end, quantitative vs qualitative. Picking the cheapest axis that distinguishes the failure mode is the discipline.

AP invoice extraction failure modes (schema-valid hallucinated totals, prompt drift, silent model retirement) are deterministic in shape.

## Decision

All three v1 metrics sit on the same axis triple: **objective + component + quantitative**.

- Schema validity: pass / fail by Pydantic model validation.
- Arithmetic consistency: pass / fail by `sum(qty * unit_price) == subtotal` and `subtotal + tax == total` within ±0.01.
- Checksum exact-match: pass / fail by string equality on `invoice_number`, `invoice_date`, `currency`, `total`.

No LLM-as-judge at v1.

## Rationale

- Cheap: no model inference cost on the eval path.
- Fast: deterministic checks run in under a second per case.
- CI-friendly: no flakiness from rubric drift.
- Honest: the failure modes that matter for AP extraction are objective; using an LLM judge would be overengineering.

KB anchor: `[system_design] Beyond-LLM Optimization Stack ... Evaluation Axes (Stanford CS230)`.

## Consequences

- The eval harness is a deterministic Python runner, not an LLM-judging service.
- Subjective failure modes (politeness, tone, free-text quality) are out of scope at v1.
- A future axis expansion (Phase 5+) for free-text `payment_terms` quality would add a subjective + end-to-end + qualitative channel via LLM-as-judge with a rubric.
- Tier-3 cases are monitored, not gating, because even a strong prompt is expected to fail some of them. Tracked as Unresolved Disagreement U3.
