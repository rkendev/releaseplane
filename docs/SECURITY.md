# Security

Scope: the v1 AP invoice-extraction slice as built through Phase 5. This documents
the threat model, the controls in place, what is deferred, and the trigger that
moves a deferred control in.

## Threat model

The untrusted input is the vendor-supplied invoice text (`invoice_pdf_text`). A
vendor (or whoever controls the document) can plant instructions in the text to try
to subvert the extraction, or send malformed content to break parsing or arithmetic.
The trust boundary is the gateway `/invoke` call: everything inside the prompt
template and the model config is operator-controlled; the variable values are not.

The principal risks:

- **Prompt injection**: text in the invoice that tries to override the system
  instructions (for example "ignore previous instructions and ...").
- **Output integrity**: a model that returns a structurally valid object whose
  arithmetic does not hold, or that does not match the schema at all.
- **Secret exposure**: provider API keys leaking into logs, the repo, or container
  environments.
- **Data exposure**: invoice PII (vendor tax IDs, bank details) in traces or logs.

## Controls in place (v1)

- **Input-side, prompt injection**: a deterministic regex check
  (`gateway/src/releaseplane_gateway/policies/prompt_injection.py`). The patterns
  are stored in the policy bundle (`invoice_v1`), not hard-coded, so coverage is
  tuned as data. A committed test asserts no benign invoice in the 30-case set
  trips the patterns, and that a planted injection is caught. A hit emits a
  `policy_event`; the bundle severity mode decides whether the request is marked
  `failed` (enforce) or only `monitored`.
- **Output-side, schema validity**: the model output is validated against the
  release's JSON Schema (`policies/schema_validity.py`).
- **Output-side, arithmetic consistency**: the shared predicate
  (`releaseplane_shared.arithmetic`) checks the invoice identities within +/-0.01;
  the same predicate gates promotion in the eval harness (ADR 0004, ADR 0006).
- **No content transformation at v1**: a policy failure is recorded
  (`policy_events`, `policy_status` on the response, Grafana), but the output object
  is never modified. The downstream ERP integration decides whether to halt a post
  or queue for human review.
- **Secrets**: provider keys are file-mounted (`*_API_KEY_FILE`), never set as
  environment values in compose and never committed; see `infra/secrets.md`. CI
  runs `detect-private-key` on every change, and a grep guard fails the build if any
  test reaches `api.anthropic.com` or `api.openai.com`.

## PII inventory

AP invoices carry vendor names, addresses, tax/registration IDs, bank account and
routing details, and line-item descriptions. At v1 this data flows through the
gateway and appears in the model call. It is not redacted. Traces record release
identity, token counts, latency, cost, routing decision, and policy status; they do
not record the invoice text or the extracted PII fields. Policy event detail is the
check's evidence (for example which arithmetic identity failed, or which injection
pattern matched), not the invoice content.

## Deferred and the trigger to move it in

- **Injection classifier**: the regex filter is v1. A learned classifier is deferred
  behind a measured trigger: it moves in when the regex filter's false-negative rate
  on a labeled injection set, or a missed live injection, justifies the added cost
  and latency. Until then the patterns are extended as data in the bundle.
- **PII redaction** beyond injection filtering, **RBAC** on the admin UI and the
  promotion API, **audit-log retention** policy, and **signed policy bundles** are
  out of scope for v1 (see `docs/SCOPE.md`) and follow the same no-drift phase-out
  rule.
