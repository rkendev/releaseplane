# ReleasePlane v1.0.0

An LLMOps control plane for versioned, gated, observable LLM releases, built to depth
on one use case: Accounts Payable invoice extraction, PDF text in and structured JSON
out.

> Prepared ahead of the `v1.0.0` tag, which is cut by hand once the pre-flip checks
> pass. This file describes what that tag marks.

## What v1.0.0 is

A release cannot reach production without passing a deterministic quality gate, and
what served any given request is recoverable rather than inferred. Prompt versions,
model configs, and policy bundles are first-class versioned rows; a release is an
immutable bundle of the three; and every request carries the `release_id` that
resolved it. The MVP use case is AP invoice extraction, where a confident wrong total
posts a wrong number to the ledger, so the gate scores arithmetic and identity, not
just shape.

## The four planes

- **Control plane.** Versioned prompt definitions, model configs, policy bundles, and
  releases, plus the release state machine. FastAPI and Postgres.
- **Execution plane.** The gateway: resolves the active release, routes across
  providers, applies pre- and post-call policy, calls the provider, emits traces.
- **Ingestion and evaluation.** Golden datasets, eval runs, per-case results, and the
  promotion gate that reads them.
- **Observability.** OpenTelemetry traces through a collector to Jaeger, Prometheus
  and Grafana for metrics, with `release_id` stamped on every span.

## The eval gate

Three deterministic metrics over a fixed 30-case golden set across three difficulty
tiers: JSON Schema validity, arithmetic consistency within a one-cent tolerance, and
exact-match on the four fields that identify an invoice in the ERP. Tier 1 and Tier 2
gate a promotion; Tier 3 is monitored, never blocking. No LLM-as-judge.

The gate blocked this project's own v1 prompt. On a live run against
`claude-sonnet-4-6` the v1 prompt failed Tier 2 at 90 percent on both schema validity
and arithmetic consistency, from a single case where the model rendered a volume
discount as a negative line item. The fix was a prompt change, not a lowered
threshold: a discount paragraph added to the system prompt, persisted as
`prompt_v2.yaml`. The v2 run cleared every metric at 100 percent in every tier. Both
runs are recorded in `docs/EVALUATION.md`; the thresholds never moved.

## Live demo (read-only)

Two surfaces are public, both read-only and anonymous:

- **[releaseplane.85-215-55-99.sslip.io](https://releaseplane.85-215-55-99.sslip.io)**
  opens on the eval dashboard, where the v1 prompt sits below the gate threshold on
  Tier 2 and v2 clears it, from one real population run.
- **[releaseplane-traces.85-215-55-99.sslip.io](https://releaseplane-traces.85-215-55-99.sslip.io)**
  serves the Jaeger trace view.

Nothing publicly reachable can write state or call a provider: the control-plane API,
the gateway, and the datastores are bound to loopback behind the reverse proxy. The
decision and its exposure boundary are recorded in
`docs/ADR/0009-live-read-only-demo-surface.md`, with the probed boundary in
`docs/SECURITY.md`.

## Deliberately out of scope

v1 is one use case built to depth, not a broad surface. Left out on purpose, each with
a documented trigger in `docs/SCOPE.md`: a publicly reachable write path, multi-tenant
isolation, an admin UI beyond a single page, PII redaction beyond the injection filter,
online evaluation and A/B and shadow traffic, cost-aware dynamic routing, LLM-as-judge
metrics, approval workflows and signed policy bundles, failure-clustering with
embeddings, Kubernetes manifests beyond documentation, fine-tuning, a TypeScript SDK,
and any second use case.

The measured cost spread is the one worth calling out among these. One gated live call
on `gpt-4o-mini` cost $0.000178 and blends to roughly $0.18 per 1,000 invoices against
roughly $8.67 per 1,000 for the pinned `claude-sonnet-4-6`. v1 ships the routing
mechanism and the measurement that argues for tiering; the dynamic router that would
act on it stays out.

## Build discipline

The whole build and CI make zero live provider API calls. The suite runs on an offline
dummy provider, and a CI grep guard fails the run if any test reaches a provider
endpoint. Every live number quoted comes from a deliberate, gated, operator-run script
that skips cleanly without a key. House style (no em-dashes, a banned-word list) and a
brand guard run in pre-commit and again in CI; a gitleaks secret scan runs over the
full commit history on every push.

## Pointers

- `docs/ARCHITECTURE.md`: the as-built design and data model.
- `docs/SCOPE.md`: what is in and out of scope for v1, with rationale.
- `docs/EVALUATION.md`: the three metrics, the tier thresholds, and the recorded
  baseline runs.
- `docs/SECURITY.md`: the threat model, the PII inventory, and the public-surface
  boundary.
- `docs/RUNBOOK.md`: bringing up the stack, the release walkthrough, and the demo
  overlay.
- `docs/ADR/`: the decisions behind the current shape, 0001 through 0009.
