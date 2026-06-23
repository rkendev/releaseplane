# ADR 0004: Arithmetic consistency as a first-class policy at v1

Date: 2026-06-23
Status: Accepted

## Context

The MVP eval surface for AP invoice extraction includes schema validity and arithmetic consistency. Schema validation is a standard policy primitive in any control plane. Arithmetic consistency is unusual: it is a domain-specific assertion that the extracted line items, subtotal, tax, and total form a coherent invoice.

The Phase 0 council debated whether arithmetic consistency belongs in the policy bundle (alongside JSON schema) or only in the eval harness.

## Decision

Arithmetic consistency lives in both:
- **Eval harness** (`evals/src/releaseplane_evals/metrics/arithmetic_consistency.py`): scored per case, gates promotion via the eval run.
- **Policy bundle** (`gateway/src/releaseplane_gateway/policies/arithmetic_consistency.py`): enforced per production request, fails the response if arithmetic does not hold within ±0.01.

## Rationale

- The eval gate catches regressions before promotion. The runtime policy catches per-request hallucinations on traffic that the eval set did not anticipate.
- Both surfaces share the same check function. The eval harness imports from the gateway policy module to guarantee they agree.
- A policy event (`policy_events` table) is emitted on every runtime failure, surfaced in the Grafana arithmetic-failure dashboard. The eval gate produces a different signal (release-level, not per-request) but uses the same predicate.

## Consequences

- The policy bundle at v1 has two output-side policies (JSON schema, arithmetic consistency) plus one input-side policy (prompt-injection regex filter). Not just one.
- Arithmetic failures at runtime are flagged and logged but **do not modify the response at v1**. The downstream ERP integration is the place to decide whether to halt the post or queue for human review. Reserve the response-transform policy for Phase 5.
- The shared check function makes arithmetic consistency the demo headline: the same code that blocks the release would have flagged the live request.
