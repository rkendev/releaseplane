# Evaluation

## Axis label (Stanford CS230 frame)

All three v1 metrics sit on the same axis triple:

- **Objective** (not subjective): pass / fail is determined by code, not judgment.
- **Component** (not end-to-end): each metric scores a specific component of the extraction (the JSON shape, the arithmetic relationships, the checksum fields).
- **Quantitative** (not qualitative): the score is a number with a defined threshold.

This is the cheapest viable axis for AP invoice extraction. The failure modes that matter (schema-valid hallucinated totals, drift in field name handling, silent model retirement) are deterministic in shape and do not need an LLM judge. KB anchor: `[system_design] Beyond-LLM Optimization Stack ... Evaluation Axes (Stanford CS230)`.

## The three metrics

### 1. Schema validity

Pass iff the response parses as the Pydantic v2 invoice model and validates against the auto-generated JSON Schema.

- All required fields present.
- All field types correct.
- All enum-constrained fields (e.g., `currency`) within the allowed set.
- `line_items[]` shape conforms (each item has `description`, `qty`, `unit_price`).

### 2. Arithmetic consistency

Pass iff the following both hold within ±0.01 currency-unit tolerance:

- `sum(line_items[i].qty * line_items[i].unit_price for all i) == subtotal`
- `subtotal + tax == total`

Tolerance is fixed at 0.01 to absorb floating-point rounding from the model's output formatting. Larger drifts are real arithmetic failures.

### 3. Checksum exact-match

Pass iff every one of these matches the ground-truth string exactly:

- `invoice_number`
- `invoice_date` (after normalizing to ISO 8601)
- `currency`
- `total`

These four fields define the identity of an invoice post in the ERP. A miss on any of them is a wrong post.

## Per-tier thresholds (promotion gating)

| Tier | Cases | Schema validity | Arithmetic consistency | Checksum exact-match | Promotion gating |
|------|-------|-----------------|------------------------|----------------------|------------------|
| 1 (clean) | 10 | 100% required | 100% required | 100% required | Gating |
| 2 (moderate) | 10 | 100% required | 100% required | >= 80% required | Gating |
| 3 (hard) | 10 | Monitored only | Monitored only | Monitored only | Non-gating |

Tier-3 monitoring is for regression detection over time, not per-release gating. Rationale: even a strong prompt should fail some Tier-3 cases; the value is the trend, not the absolute pass rate. Tracked as Unresolved Disagreement U3 in the Phase 0 council transcript; revisit if a Tier-3 regression goes undetected in a live run.

## Promotion-block policy

`POST /releases/{id}/promote` rejects with `409 PromotionBlocked` if any of the following holds:

- No eval run exists for the release within the configured staleness window (default 24 hours).
- The most recent eval run did not complete (status != `succeeded`).
- Any Tier-1 or Tier-2 gating threshold above is unmet.

The rejection body returns the failing metrics and case IDs. No promotion can proceed without a passing eval run, no exceptions, no overrides at v1.

## Dataset

30 cases minimum, generator-script-emitted with a fixed seed (`evals/generator/invoices.py`). 10 Tier-1, 10 Tier-2, 10 Tier-3. PDFs and ground-truth JSON both committed to the repo (`evals/datasets/invoice_v1/`).

Rationale for floor of 30 (not 10): a 10-row eval set yields too small a denominator to distinguish a single-field regression from noise. KB anchor: `[production_eval] Minimal RAG Evaluation Pipeline` ("2-row demo dataset: structure is right, scale is not; production-realistic eval sets need thousands of rows").

The generator script itself is a portfolio artifact. Hiring managers see the test data pipeline, not just the test runner. Anchor: `Use_Case.txt > Your Concrete MVP Dataset`.

## What we are not measuring at v1

- Latency. Tracked in observability (Prometheus / Grafana), not in the eval gate. Phase 5 introduces latency-aware routing.
- Token cost. Tracked per request via OTel attributes, surfaced in Grafana; not gated.
- Politeness or style. Subjective + qualitative; out of scope.
- Refusal rate. Reserved for Phase 5 policy expansion.

## Eval lifecycle (as built, Phase 4)

```
operator loads the dataset -> POST /eval-datasets (idempotent)
runner scores a release    -> for each case: gateway POST /invoke -> three scorers
                           -> POST /eval-runs + /complete (eval_runs + 90 eval_results)
gate on promotion          -> POST /releases/{id}/promote checks the latest run:
                              succeeded, fresh (<= EVAL_STALENESS_HOURS), thresholds met
                           -> else 409 PromotionBlocked
```

The runner is the evals CLI (`python -m releaseplane_evals.cli run --release-id ... --dataset-id ...`), not CI: CI makes zero live API calls, so the suite drives the runner on DummyProvider and proves the gate with an injected bad output (the committed case_14 regression test). Per-case input/output artifacts land as JSONB on `eval_results` (MinIO archival is deferred to Phase 5). The eval gate is enforced by default (`EVAL_GATE_ENFORCED`, on).

The real baseline numbers come from one deliberate, gated live run against the pinned Sonnet 4.6 (`evals/scripts/run_eval_live.py`), run by an operator against a stack whose gateway uses the claude provider. It skips cleanly without a key and is never run by CI. Phase 0 locks the metric definitions and thresholds above.

## Future eval axes (deferred)

When v1 stabilizes, add:

- **Subjective + end-to-end + qualitative** axis via LLM-as-judge with a rubric, for free-text payment_terms quality (when the field gains downstream consumers).
- **Online** axis: user-marked corrections from the AP team, fed back as new eval cases.

Both are Phase 5+.
