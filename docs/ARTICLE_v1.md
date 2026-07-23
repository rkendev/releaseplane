# A gate that blocked its own author

> Held draft, not published. An engineering writeup of ReleasePlane v1, built from
> numbers the repository already records (`docs/EVALUATION.md`, `README.md`). No
> marketing copy, no live run behind it.

The first time ReleasePlane ran its own quality gate against a real model, the gate
blocked the prompt its author had just written. That is the moment the project is
about, and it is worth staying with, because a gate that cannot block the person who
built it is not a gate. It is a suggestion.

ReleasePlane is a control plane that sits between an Accounts Payable LLM extraction
pipeline and a production ERP. The pipeline reads invoice PDFs and returns structured
JSON: vendor, invoice number, line items, subtotal, tax, total. A wrong total posts a
wrong number to the ledger, so the interesting failure is not a crash but a
confident, well-formed answer that happens to be wrong. Releases move through a
lifecycle, draft to candidate to active, behind a regression gate they cannot bypass,
and every request carries the `release_id` that resolved it. The system is four
planes: a control plane for versioned prompts, model configs, policy bundles, and
releases; an execution plane that resolves the active release, routes, applies
policy, and calls a provider; an ingestion and evaluation plane with the golden
datasets and the promotion gate; and an observability plane that stamps `release_id`
on every span.

## The gate blocked v1

The gate scores a candidate release against a fixed 30-case golden set across three
difficulty tiers, on three deterministic metrics: JSON Schema validity, arithmetic
consistency within a one-cent tolerance, and exact-match on the four fields that
define an invoice's identity in the ERP. No LLM-as-judge. The failure modes that
matter for AP invoice extraction are objective and quantitative, so the checks are
code, not another model's opinion. Tier 1 and Tier 2 gate a promotion; Tier 3 is
monitored for regressions but never blocks.

The first live run scored the v1 prompt against `claude-sonnet-4-6` over all 30
cases. Tier 1 passed clean. Tier 3, the hard tier and monitored rather than gating, scored
clean too. Tier 2 came back at 90
percent on schema validity and 90 percent on arithmetic consistency, below the 100
percent both metrics require, and the promotion was refused with a 409 naming the
tier and the two metrics.

Both Tier-2 failures were the same case, and it is a good failure. The invoice
carried a volume discount, and the model represented it as a negative line item,
`unit_price = -100.00`, rather than netting the discount into the positive line items.
That one choice tripped two metrics at once. Schema validity failed because
`unit_price` is constrained non-negative, so the negative row is not a valid invoice
line at all. Arithmetic consistency failed because the extra row pulled the line-item
sum to 1,050.00 against a stated subtotal of 1,150.00. The response was fluent,
plausible, and would have posted a defensible-looking record. The gate did not care
that it looked right; it cared that the numbers did not reconcile and the shape did
not validate.

## The fix was to the prompt, not the bar

The temptation, when your own gate blocks you, is to move the bar. The Tier-2
threshold could have dropped to 90 percent and the release would have promoted. That
is the failure mode a gate exists to prevent, so the fix went the other way. The v1
prompt did not tell the model what to do with a discount, so the model guessed, and
its guess was structurally wrong. The v2 prompt added a discount paragraph: net
discounts into positive line items that sum to the subtotal, never emit a negative or
zero `unit_price`. A prompt change, persisted as `prompt_v2.yaml`, and a new release
bound to it.

The v2 run cleared every metric at 100 percent in every tier. The discount case that
had failed twice now landed with a line-item sum of 1,150.01 against a subtotal of
1,150.00, inside the one-cent tolerance, because the model netted the discount as
instructed and the residual was floating-point rounding rather than a missing hundred
dollars. v1 could not promote. v2 could. The thresholds never moved. The record of
both runs is two rows in `docs/EVALUATION.md`, one blocked and one passed, and the
difference between them is a paragraph of prompt.

Worth being precise about what proves the gate on every build, since it is a
different thing from the live failure above. The 30-case live runs cost real
provider credit and are operator-run, so they are not in the loop that runs on every
push. What runs in CI is a committed regression test that injects a hallucinated
`total` of 1,257.50 on the same discount case through a scripted provider and asserts
the gate blocks it. That injected failure is caught by arithmetic alone; the live one
was caught by schema and arithmetic together. Two failure modes, both blocked, one
proving the gate offline on every commit and one found by a real model on a real run.

## The cost of the strongest model, measured

An extraction pipeline does not have to serve every invoice on the most capable
model, and the argument for not doing so is a number rather than an intuition. One
gated live call routed a case to `gpt-4o-mini` and recorded the cost: $0.000178 for
that extraction, which blends to roughly $0.18 per 1,000 invoices. The same workload
on the pinned `claude-sonnet-4-6` blends to roughly $8.67 per 1,000. That is close to
a fiftyfold spread on the same task.

The spread is the case for routing by tier: send the clean, unambiguous invoices to
the cheap model and reserve the strong one for the cases that need it, scored on the
same gate so the routing decision is auditable rather than a matter of trust. v1
ships the mechanism that makes such routing possible, a restricted predicate DSL that
selects a model config per request and a provider registry that resolves the choice
to an adapter, and it ships the measurement that says the routing is worth doing.
What it does not ship is a cost-aware dynamic router that makes the tiering decision
on its own; that is deliberately out of scope at v1. The number is here to make the
case, not to stand in for an optimizer that is not built.

## What is real, and what is not

Every live number in this writeup came from a deliberate, gated, operator-run script
that skips cleanly when no provider key is present. The build itself makes zero live
provider calls: CI runs the whole suite on an offline dummy provider, and a grep
guard fails the run if any test so much as reaches a provider endpoint. The two eval
runs behind the v1-to-v2 story were recorded once against the pinned Sonnet and are
quoted from the record, not re-run to write this. A reader who wants to see the
numbers rather than read them can click through the live read-only demo, which serves
the eval dashboard and the traces with nothing reachable that writes state or calls a
provider.

v1 is one MVP use case, AP invoice extraction, built to depth rather than breadth. It
is not multi-tenant, it carries no LLM-as-judge metric, its routing is deterministic
rather than cost-aware, and it holds one use case rather than a catalog. Those are
choices, listed with their triggers in `docs/SCOPE.md`, not gaps left by accident.
The whole of it is one sentence: a control plane that versions what served a request,
scores a release before it can serve one, and records what happened when it did.
