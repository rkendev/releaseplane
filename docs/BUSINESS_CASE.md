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
