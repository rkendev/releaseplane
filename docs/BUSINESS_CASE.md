# Business Case

## The pain

A mid-size company runs an Accounts Payable automation pipeline. PDFs from vendors come in, an LLM extracts a structured JSON payload, the payload posts to an ERP. Field-level accuracy is roughly 90 percent. For a 10-field invoice, the probability of a fully correct multi-field extraction drops to about 35 percent.

The pain is not the accuracy number. The pain is the silence.

- A schema-valid JSON with a hallucinated total passes every traditional unit test and lands in the financial ledger.
- A prompt edit from two weeks ago changed behavior. No one knows which edit, when, or why.
- A model retirement changed the substrate. The team finds out from a vendor reconciliation a month later.

## What ReleasePlane does

ReleasePlane is the control plane between the AP pipeline and the ERP. It enforces:

- Versioned prompt artifacts with checksums.
- Pinned model versions (no silent retirement).
- A release lifecycle (draft / candidate / active / rolled-back) with promotion gated by an eval run.
- Three deterministic eval metrics: schema validity, arithmetic consistency, checksum exact-match.
- Full request and response audit with the release ID on every trace.

A schema-valid response with a wrong total fails the arithmetic check and cannot promote. A prompt edit that regresses on the golden set cannot reach production. A pinned model that the provider retires triggers a known failure, not a silent one.

## The cost argument for routing

Serving every invoice on the strongest available model is the default, and it is
expensive. One measured call on `gpt-4o-mini` cost $0.000178, which blends to roughly
$0.18 per 1,000 invoices. The same workload on the pinned `claude-sonnet-4-6` blends to
roughly $8.67 per 1,000. That is a factor of about 48 on the same extraction.

The point is not that the cheap model is good enough. The point is that the question is
answerable rather than a matter of opinion: point the golden set at a release bound to
the cheap config, read the per-tier pass rates, and the tradeoff is priced. Without an
eval harness the cost decision is a guess; with one it is a measurement.

One honest limit at v1: routing selects a model config per live request, but an eval run
pins the release and therefore never routes, so it scores the release's own config. A
routed alternate is measured by giving it its own release and its own run, not by
inferring its quality from the run of the release that routed away from it.

## Who uses it

- AI platform engineer: defines prompt configs, release workflows, policy gates.
- ML engineer: runs offline evals, compares prompt and model versions, inspects regressions.
- Product / AP team lead: safely tests a new prompt before rollout.
- Security and compliance: applies policy checks, audits release history, reviews promotion-block events.
- CTO: gets reproducibility, observability, release discipline, and cost / risk control on the LLM substrate.

## What ReleasePlane is not

- Not a multi-tenant SaaS.
- Not a hosted service.
- Not a chatbot.
- Not a prompt marketplace.

It is a reference implementation of an LLMOps control plane, built around one MVP use case, with the design choices visible and the engineering discipline auditable in code and docs.
