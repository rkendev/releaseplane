# Scope (v1)

Locked 2026-06-23 by the Phase 0 council. Items here are binding for v1.

## In scope

- One MVP use case: Accounts Payable invoice extraction (PDF in, structured JSON out).
- One primary provider: Claude, via the SDK's structured-output / tool-use path.
- Adapter Protocol: provider-agnostic `generate_structured(schema)` contract. Second provider is reserved (Phase 5), not implemented.
- Release lifecycle: states `draft`, `candidate`, `active`, `rolled-back`. `canary` is defined in the state diagram but not wired at v1.
- Eval harness: deterministic checks only. Three metrics: JSON Schema validity, arithmetic consistency (±0.01 currency tolerance), checksum exact-match on `invoice_number`, `invoice_date`, `currency`, `total`.
- Eval dataset: 30 cases minimum, generator-script-emitted with a fixed seed. Three tiers: 10 clean, 10 moderate, 10 hard.
- Policies at v1: JSON-schema validation (output), arithmetic-consistency rule (output), prompt-injection regex filter (input).
- Schema language: Pydantic v2 models as the single source of truth. JSON Schema is auto-generated.
- Observability: OTel traces with `releaseplane.release_id` on every span; Grafana for request rate, p95 latency, error rate; Jaeger for trace inspection.
- Deployment: Docker Compose locally; single VPS for the public demo URL.

## Out of scope (v1)

- Multi-provider routing logic (Phase 5).
- Multi-tenant or per-tenant policy isolation.
- A web admin UI beyond a single server-rendered list-of-prompts / list-of-releases page with one Promote button.
- PII redaction policies beyond the prompt-injection regex filter (Phase 4 closes the gap for vendor tax IDs and bank details).
- Online evaluation, A/B testing, shadow traffic replay.
- Cost-aware dynamic routing.
- LLM-as-judge metrics.
- Approval workflows or signed policy bundles.
- Failure-clustering with embeddings.
- Kubernetes manifests beyond documentation.
- Fine-tuning of any kind.
- A TypeScript SDK port.
- A second use case beyond AP invoice extraction.

## Out-of-scope rationale

Every extra dimension at v1 inflates the eval surface before the harness is proven. The KB entry `[system_design] GenAI Evaluation and Monitoring` and the project canon (`RoadMap.txt > Phase 0`) both anchor on "lock the thin vertical slice." Items above with a phase tag are not killed, only deferred.

## Phase-out triggers

An out-of-scope item moves in when one of the following holds:

- A live demo run surfaces a regression that the v1 gates miss.
- The hiring-narrative review judges the v1 demo undersells a specific signal.
- A council pass dedicated to that decision ratifies the move with explicit KB and project-doc anchors.

No item moves in by drift.
