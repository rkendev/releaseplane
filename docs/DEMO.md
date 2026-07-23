# Demo Script (3-5 minutes)

The demo is the acceptance criterion for v1. Every other artifact is in support of this
script landing. It runs on recorded numbers: no live provider call happens during the
recording, and none is needed. The commands below drive the local stack, and the eval
results they reference come from two recorded baseline runs (see `docs/EVALUATION.md`).

A live read-only dashboard sits alongside this recording (ADR 0009), at
[releaseplane.85-215-55-99.sslip.io](https://releaseplane.85-215-55-99.sslip.io) with
traces at
[releaseplane-traces.85-215-55-99.sslip.io](https://releaseplane-traces.85-215-55-99.sslip.io):
Grafana and Jaeger, public through a reverse proxy, carrying real numbers from one prior
population run. It is the clickable companion, not a replacement. What it shows is the
measured pass rate per release, tier, and metric, plotted against the gate threshold, so
the v1 series sits
under the line on Tier-2 and the v2 series sits on it. The gate decision itself is not a
metric; a visitor reads the rates and the threshold, and this script supplies the 409 and
the reason string. That is the division of labour: the dashboard shows the numbers, the
script shows why they mattered. Nothing on the public surface can write state or call a
provider; `docs/SECURITY.md` has the boundary and `docs/RUNBOOK.md` has the bring-up.

## The headline moment

A prompt change produces a new release. The eval runner scored it against the 30-case
golden dataset. The arithmetic gate catches a hallucinated total on Tier-2 case #14: the
model returns `total = 1,257.50` while `subtotal (1,150.00) + tax (97.50) = 1,247.50`.
JSON Schema passed. Promotion is blocked with a 409 before the wrong total can post to
the ledger.

This is the only moment that has to land. Everything else is framing.

## Builder's note (do not voice over; keep honest for the panel)

The eval harness and the gate are built and are the load-bearing parts of this demo. The
headline `total = 1,257.50` catch is a committed regression test
(`test_eval_gate_regression`): it injects that output through a scripted provider and
runs offline, so CI proves the gate on every push while making zero live API calls. The
per-tier numbers in the v1-to-v2 beat below come from two deliberate, gated live runs
against the pinned Sonnet 4.6, recorded once and replayed here. The recording itself runs
the dummy-pinned stack, so nothing spends while the camera rolls.

## Script

### 0:00 - 0:45: The problem

> "Accounts Payable runs LLM extraction on incoming invoices and posts the structured
> JSON to the ERP. Schema validity is 100 percent. The model returns a total of 1,257.50.
> The real total is 1,247.50. The schema check has no opinion on whether the arithmetic
> adds up. The wrong number posts. No one notices until the vendor reconciles next month."

Show: a sample invoice (PDF render). Show: the extracted JSON. Highlight the wrong
`total`. Note: schema is valid.

### 0:45 - 1:45: The control plane

> "ReleasePlane treats every prompt change like a code change. The prompt is versioned
> with a checksum. The model is pinned to an exact version string. The release is an
> immutable bundle of prompt version, model config, and policy bundle, and every request
> the gateway serves carries the release id that resolved it."

Show: `releaseplane releases list` and `releaseplane prompts list`. Show the git diff of a
PR proposing a new prompt version (one wording change in the extraction prompt). Show: the
PR triggers CI.

### 1:45 - 3:15: The gate blocked its own v1

This is the strongest beat, because the failure is real, not scripted.

> "The first time this project ran its own eval against the live model, the gate blocked
> it. Not a synthetic case: the model represented a volume discount on case #14 as a
> negative line item, which broke schema validity and arithmetic consistency at once.
> Tier 2 came in at 90 percent on both. The gate refused the promotion."

Show: the recorded v1 run (`da53ec97`). Tier 1: 100 / 100 / 100. Tier 2: 90 / 90 / 100.
Tier 3: 100 / 100 / 100. Click into the failing case.

> "The fix was a prompt change, not a threshold change. A discount paragraph told the
> model to net discounts into the positive line items so they sum to the subtotal. That
> is `prompt_v2`. The re-run passed every metric in every tier, zero of ninety rows
> failing, and the same gate that blocked v1 let v2 through."

Show: the `prompt_v1` to `prompt_v2` diff (the added discount paragraph). Show: the
recorded v2 run (`ef6a27d8`), 100 across the board. Then show the block and the pass at
the API, using the CLI:

```
releaseplane releases promote <v1-release-id>
# promotion blocked: tier 2 schema_validity 90% < 100%; tier 2 arithmetic_consistency 90% < 100%   (exit 1)

releaseplane releases promote <v2-release-id>
# <id>  promoted to candidate
```

The block prints the reason on one line and exits non-zero. The v1 detail names both
failing metrics, because the negative line item broke schema and arithmetic at once; that
is the live failure mode, distinct from the headline regression test, which injects a
wrong total and so trips arithmetic alone. Either way the gate is legible from the
terminal.

### 3:15 - 4:00: Routing and measured cost

> "Serving every invoice on the strongest model is the expensive default. ReleasePlane
> routes per request on the input, and it measures what each provider costs. One call on a
> cheaper provider cost a fraction of a cent."

Show: the recorded cost figures. One `gpt-4o-mini` call on case_03 cost $0.000178, which
blends to about $0.18 per 1,000 invoices, against about $8.67 per 1,000 for the pinned
Sonnet 4.6. Show: the routing rule that diverts a request to the cheaper model config, and
the `serving_provider` on the span.

> "The point is not that the cheap model is good enough. The point is that the question is
> answerable. The golden set prices the tradeoff instead of leaving it to opinion, and the
> gate makes sure whatever config a release is bound to has passed on that release's data."

### 4:00 - 4:40: The audit

> "Every request the gateway processed during a run is traced. Jaeger has the timeline;
> the per-case input and output are stored as JSONB on the eval results. The release id is
> on every span, alongside the routing decision and the policy status."

Show: the Jaeger trace for a case. Show: the failing case's `eval_results` row with the
model output in its notes. Point out the `releaseplane.release_id` attribute, the model
version pin, and the prompt version checksum. Full payload archival to object storage is a
documented deferral, not part of v1.

### 4:40 - 5:00: The story

> "This is the control plane that keeps an Accounts Payable LLM pipeline from silently
> shipping a broken prompt, from missing a model retirement, and from posting a
> hallucinated invoice total to the ledger. Every release goes through a version gate, an
> arithmetic-consistency eval, and an audit log before it reaches production. That same
> insistence on catching silent change carried into the design process: when the model
> reasoning about this design shifted between sessions, the design review re-ran its
> locked verdicts against the new substrate and recorded the audit trail before the next
> line of code."

Show: the README opening paragraph. Show: the four-plane overview and the request-flow
diagram in `docs/ARCHITECTURE.md`.

Close on the four planes: control, execution, ingestion and eval, observability.

## What not to do in the demo

- Do not show the admin UI as a feature. It is a single page; opening it loses time.
- Do not explain the eval-axes triage (objective + component + quantitative) in prose. It
  is in `EVALUATION.md` for the panel; mention only if asked.
- Do not start with the architecture diagram. Start with the wrong total. The diagram is
  the closer, not the opener.
- Do not claim a live eval is running. The numbers are recorded and labeled as such; the
  stack on camera is dummy-pinned.

## Before you record

The policy engine runs nothing if the seeded bundle is stale, and a stale stack still
looks healthy. Confirm the `invoice_v1` bundle is current before recording:

```
curl -s $CP/policy-bundles | jq '.[] | select(.name=="invoice_v1") | {severity_mode, rules_json}'
```

It must show `severity_mode: "enforce"` and a `rules_json.checks` list. If `rules_json` is
empty, the row predates the policy engine; see the stale-bundle failure mode in
`docs/RUNBOOK.md`. Bring the stack up from source, migrate, and re-seed per the RUNBOOK so
the demo shows current routes and a current bundle.

## Recording notes

- Resolution: 1920x1080 minimum.
- Cursor highlighting on.
- Two terminals visible: one for git and CI, one for the `releaseplane` CLI.
- Browser windows: Grafana, Jaeger, and the rejected promotion at the API.
- Voice-over scripted from this file. No improvisation on the headline moment.
