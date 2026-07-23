# ReleasePlane

> A prompt change fires the eval run. The arithmetic gate catches a hallucinated total on Tier-2 case #14: model returns `total = 1,257.50` while `subtotal (1,150.00) + tax (97.50) = 1,247.50`. JSON Schema passed. The release is blocked before the wrong total can post to the ledger.

That moment is the project. ReleasePlane is the control plane that sits between an Accounts Payable LLM extraction pipeline and a production ERP. Releases move forward through a lifecycle (draft, then candidate, then active) behind a regression gate (schema validity, arithmetic consistency, checksum exact-match) that a release cannot bypass. Entering active archives the prior active release for that prompt, under a prompt-scoped advisory lock so two concurrent promotions cannot both win.

**Live demo:** [releaseplane.85-215-55-99.sslip.io](https://releaseplane.85-215-55-99.sslip.io) opens on the eval dashboard, where the v1 prompt sits below the gate threshold on Tier-2 and the v2 prompt clears it, from one real run. Traces at [releaseplane-traces.85-215-55-99.sslip.io](https://releaseplane-traces.85-215-55-99.sslip.io). Both are read-only and anonymous: nothing reachable there writes state or calls a provider (ADR 0009). The recorded walkthrough tells the story; this lets you click through the numbers behind it.

## What this demonstrates

- **Versioned artifacts.** Prompt versions, model configs, and policy bundles are first-class rows. Each prompt version carries a sha256 over its prompts and schemas, and each model config names an exact model string rather than a floating alias, so what served a given request is recoverable rather than inferred. A release is an immutable bundle of the three, and every request carries the `release_id` that resolved it.
- **A gate that blocks its own author.** The eval harness runs three deterministic checks over a fixed 30-case golden set across three difficulty tiers. No LLM-as-judge at v1: the failure modes that matter for AP invoice extraction are objective and quantitative. The gate blocked this project's own v1 prompt, and the fix was a prompt change, not a threshold change (see Honesty notes).
- **Routing across providers.** A restricted JSON predicate DSL selects a model config per request, matched by a pure deterministic matcher, first match by priority (ADR 0005). A provider registry resolves the chosen config to an adapter: Claude via its tool-use path, an OpenAI-compatible second provider, or an offline dummy (ADR 0007). A pinned `release_id` never routes, so a release is always scored on its own model config.
- **One predicate, two planes.** The runtime policy engine (prompt-injection regex on the input, schema validity and arithmetic consistency on the output) imports the same neutral arithmetic predicate the eval scorer uses (ADR 0006), so the runtime check and the promotion gate cannot drift apart. A policy failure is recorded, never silently repaired: the response object is identical between monitor and enforce mode.
- **Measured cost, not estimated cost.** One gated live call on `gpt-4o-mini` cost $0.000178 for case_03, which blends to roughly $0.18 per 1,000 invoices against roughly $8.67 per 1,000 for the pinned `claude-sonnet-4-6`. That spread is the argument for routing by tier rather than serving every invoice on the strongest model.
- **An audit trail.** OpenTelemetry spans carry the release identity, token counts, the cost estimate, the routing decision, and the policy status, with latency as the span duration. Prometheus and Grafana chart request rate, latency quantiles, routing decisions, and policy events; Jaeger holds the per-request timeline.

## Try it locally

The dev stack runs on Docker Compose and makes zero provider API calls by default: the gateway is pinned to `DummyProvider`, so a full bring-up costs nothing.

```bash
cp infra/.env.example .env    # then fill in the passwords
make secrets                  # writes infra/secrets/* from .env
docker compose -f infra/docker-compose.yml up -d
make migrate                  # Alembic does not run on container start
```

Confirm both services are healthy, then seed the invoice use case (the policy bundle plus prompt v1 and v2):

```bash
curl http://localhost:8001/healthz   # control-plane
curl http://localhost:8002/healthz   # gateway
CONTROL_PLANE_URL=http://localhost:8001 uv run python control-plane/scripts/seed_invoice_v1.py
```

Seeding registers the prompts, not a release. Walking one through the gate takes a model config, a release, a loaded dataset, and an eval run before the two promote hops will move it to active. `docs/RUNBOOK.md` has that sequence as runnable commands, along with the service URL table and the failure modes worth knowing (port conflicts, stale images, a lagging migration).

Worth knowing before you run it: the dev stack pins the gateway to `DummyProvider`, which returns a canned object rather than calling a model. An eval run on that stack therefore fails schema validity on every case and the gate blocks promotion. That is the zero-spend way to watch the gate do its job. Passing rates need a real provider key, which is a deliberate, operator-run step, never an automatic one.

Grafana is at `http://localhost:3000`, Jaeger at `http://localhost:16686`. The same two surfaces are public and read-only at the live demo links above; `docs/RUNBOOK.md` has the demo overlay that binds everything else to loopback and the exposure boundary behind it.

## Layout

```
control-plane/  release registry, prompt versions, policy bundles, release lifecycle, eval gate
gateway/        request execution, routing, provider adapters, runtime policy engine, OTel
evals/          datasets, runner, metrics (schema / arithmetic / checksum)
shared/         the neutral arithmetic predicate both planes import
sdk/            the installable `releaseplane` package
infra/          docker-compose, OTel collector, Prometheus, Grafana, model configs
docs/           SCOPE, ARCHITECTURE, EVALUATION, DEMO, BUSINESS_CASE, RUNBOOK, SECURITY, ADRs
examples/       invoice_extraction prompts and the reference schema
```

## My role

End-to-end design and implementation: architecture, data model, eval harness, provider adapter contract, routing and policy engines, observability surface, release lifecycle, deployment topology.

## Status

Complete through the v1 engine scope. The control plane carries the registry and the release lifecycle with the eval gate enforced by default. The gateway resolves, routes, applies policy, and calls a provider through the registry. The eval harness scores a release over the golden set and persists per-case results. Observability is wired end to end.

Outstanding against `docs/SCOPE.md`: the single-page admin view with a promote button, the SDK client surface, and the demo recording. The live read-only demo surface (ADR 0009) is up at the links above.

`docs/SCOPE.md` holds the explicit out-of-scope list. `docs/ARCHITECTURE.md` is the as-built design and data model. Both are authoritative; the ADRs in `docs/ADR/` record the decisions behind the current shape.

## Honesty notes

ReleasePlane is a control-plane reference implementation built around one MVP use case. It is not a multi-tenant SaaS, not a hosted service, and not production-hardened beyond what the gates enforce. The hiring narrative is the engineering discipline, not the surface area.

Two claims deserve their exact provenance:

- **The gate blocked its own v1.** The first live baseline run against `claude-sonnet-4-6` failed Tier 2 at 90 percent on both schema validity and arithmetic consistency. Both failures were the same case: the model represented a volume discount as a negative line item instead of netting it into the line items. That is a real model failure found by a real run, not a scripted one. The fix was a principled discount paragraph added to the system prompt and persisted as `prompt_v2.yaml`; the re-run passed all three metrics at 100 percent in every tier. The thresholds never moved.
- **The build makes zero live API calls.** CI runs the whole suite on offline providers (the dummy adapter, and a scripted one where a test needs an exact payload), and a grep guard fails the run if any test reaches a provider endpoint. Every live number quoted here comes from a deliberate, gated, operator-run script that skips cleanly without a key. The `total = 1,257.50` figure in the opening is the committed regression test, which proves the gate offline by injecting that output; the live model failed differently, as described above.
