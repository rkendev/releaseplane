# Scope (v1)

Locked 2026-06-23 by the Phase 0 council. Items here are binding for v1.

## In scope

- One MVP use case: Accounts Payable invoice extraction (PDF in, structured JSON out).
- One primary provider for production: Claude, via the SDK's structured-output / tool-use path. Production stays pinned to it; the second provider exists to make the routing and cost story real, not to split production traffic.
- Adapter Protocol: provider-agnostic `generate_structured(schema)` contract. Built out to two live providers (Claude and an OpenAI-compatible second) plus an offline dummy, selected per request through a provider registry (ADR 0007).
- Release lifecycle: states `draft`, `candidate`, `active`, `rolled-back`. `canary` is defined in the state diagram but not wired at v1.
- Eval harness: deterministic checks only. Three metrics: JSON Schema validity, arithmetic consistency (±0.01 currency tolerance), checksum exact-match on `invoice_number`, `invoice_date`, `currency`, `total`.
- Eval dataset: 30 cases minimum, generator-script-emitted with a fixed seed. Three tiers: 10 clean, 10 moderate, 10 hard.
- Policies at v1: JSON-schema validation (output), arithmetic-consistency rule (output), prompt-injection regex filter (input).
- Schema language: Pydantic v2 models as the single source of truth. JSON Schema is auto-generated.
- Observability: OTel traces with `releaseplane.release_id` on every span; Grafana for request rate, p95 latency, error rate; Jaeger for trace inspection.
- Deployment: Docker Compose locally. The demo ships as a recording against the local stack, plus a live read-only observability surface: Grafana and Jaeger behind a reverse proxy, showing real data from one prior population run (ADR 0009). Nothing publicly reachable can write state or call a provider.
- Multi-provider routing: a restricted JSON predicate DSL, one rule set per use case, matched deterministically first-by-priority (ADR 0005). Latency- and cost-aware routing stay out.

## Out of scope (v1)

- A publicly reachable write path: the control-plane API, the gateway `/invoke`, or anything else a visitor could use to create a release, promote one, or cause a provider call. That endpoint would need a spend cap, a per-IP rate limit, and a kill switch to be safe in public, and none of that carries the narrative. The live surface added in ADR 0009 is read-only observability and creates none of those risks; the write path stays out.
- Multi-tenant or per-tenant policy isolation.
- A web admin UI beyond a single server-rendered list-of-prompts / list-of-releases page with one Promote button.
- PII redaction policies beyond the prompt-injection regex filter. Vendor tax IDs and bank details flow through the gateway unredacted at v1; traces record release identity and counters, not the invoice text. See `docs/SECURITY.md` for the inventory and the trigger to move redaction in.
- Online evaluation, A/B testing, shadow traffic replay (shadow mode; see below).
- Cost-aware dynamic routing.
- LLM-as-judge metrics.
- Approval workflows or signed policy bundles.
- Failure-clustering with embeddings.
- Kubernetes manifests beyond documentation.
- Fine-tuning of any kind.
- A TypeScript SDK port.
- A second use case beyond AP invoice extraction.

## Out-of-scope rationale

Every extra dimension at v1 inflates the eval surface before the harness is proven. The KB entry `[system_design] GenAI Evaluation and Monitoring` and the project canon (`RoadMap.txt > Phase 0`) both anchor on "lock the thin vertical slice." Nothing on the out-of-scope list is killed; each item is deferred and moves in only under a trigger below.

## Phase-out triggers

An out-of-scope item moves in when one of the following holds:

- A live demo run surfaces a regression that the v1 gates miss.
- The hiring-narrative review judges the v1 demo undersells a specific signal.
- A council pass dedicated to that decision ratifies the move with explicit KB and project-doc anchors.

No item moves in by drift.

## Shadow mode (deferred)

Shadow mode would run a candidate release (or a routed alternate provider) against
live traffic in parallel with the active release, scoring the shadow output without
serving it, to gather pre-promotion signal on real requests. The Phase 5 entry
council kept it deferred: the routing engine and the policy engine give the
per-request signal the demo needs, and shadow mode doubles the live spend on every
request it shadows.

Trigger to build it: a candidate that passes the offline eval gate still regresses
on live traffic in a way the gate did not catch, and the regression is one that a
parallel scored shadow run would have surfaced before promotion. Until then,
pre-promotion confidence comes from the eval harness on the golden set, not from
live shadowing.
