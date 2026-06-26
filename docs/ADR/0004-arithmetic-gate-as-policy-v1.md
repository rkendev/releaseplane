# ADR 0004: Arithmetic consistency as a first-class policy at v1

Date: 2026-06-23
Status: Accepted

## Context

The MVP eval surface for AP invoice extraction includes schema validity and arithmetic consistency. Schema validation is a standard policy primitive in any control plane. Arithmetic consistency is unusual: it is a domain-specific assertion that the extracted line items, subtotal, tax, and total form a coherent invoice.

The Phase 0 council debated whether arithmetic consistency belongs in the policy bundle (alongside JSON schema) or only in the eval harness.

## Decision

Arithmetic consistency lives in both:
- **Eval harness** (`evals/src/releaseplane_evals/scorers.py`, `score_arithmetic_consistency`): scored per case, gates promotion via the eval run.
- **Policy bundle** (`gateway/src/releaseplane_gateway/policies/arithmetic_consistency.py`): applied per production request, recorded on the response if arithmetic does not hold within +/-0.01.

Both call sites import one neutral predicate (`releaseplane_shared.arithmetic`); see the reconciliation below and ADR 0006.

## Rationale

- The eval gate catches regressions before promotion. The runtime policy catches per-request hallucinations on traffic that the eval set did not anticipate.
- Both surfaces share the same check function so they cannot drift (the agreement is pinned by a committed shared-fixture test on case_14).
- A policy event (`policy_events` table) is emitted on every runtime failure, surfaced in the Grafana arithmetic-failure dashboard. The eval gate produces a different signal (release-level, not per-request) but uses the same predicate.

## Consequences

- The policy bundle at v1 has two output-side policies (JSON schema, arithmetic consistency) plus one input-side policy (prompt-injection regex filter). Not just one.
- Arithmetic failures at runtime are flagged and logged but **do not modify the response at v1**. The downstream ERP integration is the place to decide whether to halt the post or queue for human review. Reserve the response-transform policy for Phase 5.
- The shared check function makes arithmetic consistency the demo headline: the same code that blocks the release would have flagged the live request.

## Reconciliation (Phase 5, 2026-06-26)

The as-built paths differ from the ones this ADR predicted, and the shared-function direction changed:

- The eval scorer is `evals/src/releaseplane_evals/scorers.py` (`score_arithmetic_consistency`), not a `metrics/arithmetic_consistency.py` module.
- The shared predicate does **not** live in the gateway policy module with the eval harness importing it (that would couple the evals package to the gateway). Per decision D-PRED-HOME (ADR 0006), the predicate lives in a neutral `releaseplane-shared` workspace package that **both** planes import, keeping plane separation. The gateway policy (`policies/arithmetic_consistency.py`) and the eval scorer each wrap the same `releaseplane_shared.arithmetic.evaluate_arithmetic`.
- The runtime policy's monitor/enforce behavior is specified in ADR (Phase 5 policy engine): v1 records the failure (`policy_events`, `policy_status`) and never transforms the output. This ADR's "do not modify the response at v1" stands.
