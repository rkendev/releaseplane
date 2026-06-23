# Demo Script (3-5 minutes)

The demo is the acceptance criterion for v1. Every other artifact is in support of this script landing.

## The headline moment

A prompt change is merged. CI fires the eval run. The arithmetic gate catches a hallucinated total on Tier-2 case #14: model returns `total = 1,257.50` while `subtotal (1,150.00) + tax (97.50) = 1,247.50`. JSON Schema passed. The release is blocked before the wrong total can post to the ledger.

This is the only moment that has to land. Everything else is framing.

## The second beat - the control plane caught its own substrate change

> "The same discipline that catches a bad prompt caught a change to the model underneath the project. The design substrate moved from one model version to the next between sessions. Instead of building on top of it, the control-plane process flagged the change, re-ran the six locked design verdicts against the new substrate, kept all six (one with a noted assumption), and shipped the audit trail before the next line of code."

Show: `substrate_change_2026-06-23.md` (the verdict table and the decision) and the CHANGELOG entry. Point out that production stays pinned to `claude-sonnet-4-6`, so the inference layer never moved; what moved was the model reasoning about the design.

Builder's note (do not voice over, keep honest for the panel): in v1 the catch and the re-validation are a documented process step, not yet automated. Detection was manual via the session model echo (Substrate Pin), and the verdict re-validation is a council pass, not a live eval re-run. Automating both (a CI authoring-substrate pin check, and re-running the eval gate on a model change once the dataset exists) is roadmap, tracked as U4 and Phase 4. Do not claim a live automated eval re-run until `evals/datasets/invoice_v1/` exists.

## Script

### 0:00 - 0:45: The problem

> "Accounts Payable runs LLM extraction on incoming invoices and posts the structured JSON to the ERP. Schema validity is 100 percent. The model returns a total of 1,257.50. The real total is 1,247.50. The schema check has no opinion on whether the arithmetic adds up. The wrong number posts. No one notices until the vendor reconciles next month."

Show: a sample invoice (PDF render). Show: the extracted JSON. Highlight the wrong `total`. Note: schema is valid.

### 0:45 - 1:45: The control plane

> "ReleasePlane treats every prompt change like a code change. The prompt is versioned. The model is pinned to an exact version string. The release is an immutable bundle of (prompt version, model config, policy bundle)."

Show: `releaseplane releases list`. Active release is `invoice-extraction@v1.0.3`. Show the git diff of a PR proposing `v1.0.4` (one wording change in the extraction prompt). Show: PR triggers CI.

### 1:45 - 3:00: The gate

> "CI runs the eval harness against the 30-case golden dataset. Three deterministic metrics: JSON Schema validity, arithmetic consistency, checksum exact-match. Tier-1 and Tier-2 cases gate promotion. Tier-3 is monitored."

Show: CI logs streaming. Schema: 30/30 pass. Checksum: 30/30 pass. Arithmetic: 29/30 pass. Case #14 fails. Click into the failure.

> "Subtotal plus tax equals 1,247.50. The model returned 1,257.50. The arithmetic check caught what the schema could not."

Show: the promotion API rejecting `POST /releases/{id}/promote` with a 409 `PromotionBlocked` and the failing-case payload.

### 3:00 - 4:00: The audit

> "Every request the gateway processed during the eval run is traced. Jaeger has the full timeline; MinIO has the full request and response payload. The release ID is on every span."

Show: Jaeger trace for the failed case. Show: the MinIO object. Point out the `releaseplane.release_id` attribute. Note the model version pin and the prompt version checksum.

### 4:00 - 5:00: The story

> "This is the control plane that ensures an Accounts Payable LLM pipeline cannot silently ship a broken prompt, cannot have a silent model retirement go undetected, and cannot post a hallucinated invoice total to the ledger. Every release goes through a version gate, an arithmetic-consistency eval, and an audit log before it reaches production."

Show: the README's opening paragraph (which is this paragraph). Show: the architecture diagram from `docs/ARCHITECTURE.md`.

Close on the four-plane diagram.

## What not to do in the demo

- Do not show the admin UI as a feature. It is a single page; opening it loses time.
- Do not explain the eval-axes triage (objective + component + quantitative) in prose. It is in `EVALUATION.md` for the panel; mention only if asked.
- Do not start with the architecture diagram. Start with the wrong total. The diagram is the closer, not the opener.
- Do not talk about multi-provider routing. It is reserved (Phase 5) and showing it without it being implemented reads as overselling.

## Recording notes

- Resolution: 1920x1080 minimum.
- Cursor highlighting on.
- Two terminals visible (one for git / CI, one for `releaseplane` CLI).
- Browser windows: Grafana, Jaeger, the admin page, the rejected promotion API response.
- Voice-over scripted from this file. No improvisation on the headline moment.
