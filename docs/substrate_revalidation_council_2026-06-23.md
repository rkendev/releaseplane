# ReleasePlane - Substrate-Change Re-Validation Council

Date: 2026-06-23
Project: ReleasePlane (Phase 0 locked; Phase 1 not yet entered)
Authoring substrate this session: claude-opus-4-8 (declared per Substrate Pin rule)
Prior authoring substrate: claude-opus-4-7 (recorded in workflow_phase0_locked.txt, renamed this session from workflow_opus_4_7.txt so the substrate is not encoded in the filename)
Production inference substrate (pinned): claude-sonnet-4-6 (infra/model_configs/v1_default.yaml) - UNCHANGED

## The event under review

The prior Phase 0 session ran on Opus 4.7. This session runs on Opus 4.8. Per ReleasePlane's own thesis (`Use_Case.txt > silent model retirements mean the substrate changes whether teams opt in or not`), the swap is treated as the project's first real model-retirement event. The council re-validates each of the six locked Phase 0 verdicts against the new substrate before any Phase 1 work proceeds.

## The decoupling that frames every verdict

One observation governs the whole pass and is stated once here rather than repeated under each verdict. The substrate that changed is the **authoring** model (the model running this design session). Every one of the six verdicts governs either the **production inference layer** (pinned to Sonnet 4.6, unchanged) or a **deterministic, model-independent** layer (Pydantic schemas, code-computed gates, dataset sizing, regex filters). The authoring layer and the layers the verdicts govern are decoupled. A change in the model that *reasons about* the architecture does not, on its own, change whether an architecture decision is correct. The verdicts therefore survive not because the council waved them through, but because the event landed on a layer none of them depend on. The single place a substrate change could bite (structured-output and tool-use reliability, and unit cost) is governed by the pinned production model, which did not move. That is the load-bearing reason, and it is why one verdict (V2) is qualified rather than clean: it is the only verdict that makes a substantive assumption about model behavior, and intellectual honesty requires flagging that the assumption is version-scoped even though the current pin holds.

Re-Validation Budget: one round per verdict. No verdict required a second round; none is marked defer-to-Phase-1-entry on budget grounds. The Cost-Delta Probe's *measured* (live) portion is deferred for a credential reason, documented below.

---

## Round 1 - advisor verdicts (per-decision schema, verdict-anchored)

### V1 - MVP use case = AP invoice extraction

**AI Engineering Lead**
1. Verdict: YES, unchanged.
2. Why: Use-case selection is a domain and hiring-narrative decision with no dependency on any model generation. The documented failure modes (schema-valid hallucinated totals, prompt drift, silent model retirement) are properties of LLM extraction in general, not of Opus 4.7 versus 4.8. Nothing in the swap touches why AP extraction is the right MVP.
3. KB-for: `[system_design] GenAI Evaluation and Monitoring` - "Eval dataset must exist before optimization, or nothing is measurable." (`domains/system_design.md`)
4. KB-against: none found.
5. Project-doc anchor: `Use_Case.txt > MVP Use Case`; `RoadMap.txt > Phase 0`.
6. Next action: none; verdict stands.
7. Effort: S. 8. Confidence: 5.

**Hiring-Manager Proxy**
1. Verdict: YES, unchanged.
2. Why: The credibility of the AP use case to a hiring panel does not move with the authoring model. If anything the substrate-change event itself becomes a second demo beat that strengthens the narrative. The MVP framing is safe.
3. KB-for: `[system_design] MLOps Lifecycle ... (Databricks frame)` - "Four LLMOps components as triage axes ... prevent the typical 'tune the prompt' reflex." (`domains/system_design.md`)
4. KB-against: none found.
5. Project-doc anchor: `Project_Description.txt > 3.3 Target Users & Value > CTO / hiring manager`.
6. Next action: fold the substrate-change event into DEMO.md as beat two.
7. Effort: S. 8. Confidence: 5.

Strongest reason the substrate did not move the answer: use-case choice is model-agnostic; the failure modes that justify it are generation-independent.

### V2 - Claude primary; adapter Protocol exposes `generate_structured(schema)`

**Claude Ecosystem Specialist**
1. Verdict: QUALIFIED-YES.
2. Why: The verdict holds and is in fact the verdict best designed to absorb a substrate change, because the `generate_structured(schema)` Protocol decouples the system from any one model's completion idiom. The qualification: the verdict embeds an assumption that the production model's structured-output and tool-use semantics are reliable, and that assumption is scoped to the pinned model (Sonnet 4.6), not to the authoring model that changed. The pin held this session, so the assumption holds, but the durability of the verdict depends on the pin, and this session is the proof that pins can move silently.
3. KB-for: `[system_design] Guardrails and Safety for LLM Systems` - "Logit-masked structured output guarantees schema but constrains expressiveness; post-hoc validation + retry is looser but simpler." (`domains/system_design.md`)
4. KB-against: none found.
5. Project-doc anchor: `Use_Case.txt > What Makes This the Perfect Eval Target > Schema validity`; `Project_Description.txt > 3.4 > Execution plane`.
6. Next action: add a one-line note to ADR 0002 / the adapter contract that structured-output reliability is asserted against `claude-sonnet-4-6`; re-test the tool-use path if the production pin is ever bumped (for example to Opus 4.8 Fast Mode on Tier-3).
7. Effort: S. 8. Confidence: 4.

Assumption the prior verdict made about the model that a substrate change could touch: structured-output / tool-use reliability. It was not touched this session because that property belongs to the production pin (Sonnet 4.6), which did not change. The qualification records that the verdict's safety is conditional on the pin, which is exactly what the project exists to monitor.

### V3 - Eval gates: schema + arithmetic (+/-0.01) + checksum exact-match; Tier 1+2 gating, Tier 3 monitored

**Evaluation Specialist**
1. Verdict: YES, unchanged.
2. Why: All three gates are deterministic code checks over output values; none reads any model property. A substrate change is precisely the regression class the arithmetic gate exists to catch, so the event strengthens the verdict rather than weakening it. The three-axis label (objective + component + quantitative) is unchanged.
3. KB-for: `[system_design] Beyond-LLM Optimization Stack ... Evaluation Axes (Stanford CS230)` - "objective + Python check beats LLM-as-judge when the failure is deterministic." (`domains/system_design.md`)
4. KB-against: `[system_design] GenAI Evaluation and Monitoring` - "Automated metrics ... undercount stylistic and factual drift; pair with periodic human audits." Counterweight, not blocker.
5. Project-doc anchor: `Use_Case.txt > What Makes This the Perfect Eval Target`.
6. Next action: none for the verdict. Note: the dataset that feeds these gates does not exist yet (see risks); building it is Phase 4 and is what makes the gate demonstrable.
7. Effort: S. 8. Confidence: 5.

**QA / Test Engineer**
1. Verdict: YES, unchanged.
2. Why: Tier gating thresholds are statistical and model-independent. A substrate change does not alter the denominator logic or the per-tier cut. U3 (Tier-3 monitored vs gating) remains open on its original trigger, unaffected by the swap.
3. KB-for: `[production_eval] Minimal RAG Evaluation Pipeline` - "production-realistic eval sets need thousands of rows." (`domains/production_eval.md`)
4. KB-against: none found.
5. Project-doc anchor: `Use_Case.txt > Your Concrete MVP Dataset`.
6. Next action: none; verdict stands.
7. Effort: S. 8. Confidence: 5.

Strongest reason the substrate did not move the answer: the gates assert properties of the output, not of the model; they are the substrate-independence mechanism itself.

### V4 - Policies v1: JSON-schema + arithmetic (output) + prompt-injection regex (input)

**Security / AppSec Engineer**
1. Verdict: YES, unchanged.
2. Why: A regex deny-list and two output-side validators execute in application code with no model dependency. The injection surface (external vendor PDFs) is unchanged by the authoring swap. U2 (regex vs classifier) remains open on its original Phase 5 trigger.
3. KB-for: `[system_design] Guardrails and Safety for LLM Systems` - "Input: prompt-injection detection and PII scrubbing before anything reaches the model." (`domains/system_design.md`)
4. KB-against: none found.
5. Project-doc anchor: `Use_Case.txt > The One-Line System Narrative`; `Project_Description.txt > 3.6 > Routing & Policy Engine > pre-call checks`.
6. Next action: none; verdict stands.
7. Effort: S. 8. Confidence: 4.

Strongest reason the substrate did not move the answer: the policies are deterministic and execute outside the model boundary.

### V5 - Eval-set floor: 30 cases (10/10/10), generator-emitted, fixed seed

**QA / Test Engineer**
1. Verdict: YES, unchanged.
2. Why: Dataset sizing and reproducibility are measurement-rigor decisions about the denominator needed to separate a single-field regression from noise. Neither the floor nor the fixed-seed reproducibility argument references a model. The swap is irrelevant to the count.
3. KB-for: `[production_eval] Minimal RAG Evaluation Pipeline` - "2-row demo dataset: structure is right, scale is not." (`domains/production_eval.md`)
4. KB-against: none found.
5. Project-doc anchor: `Use_Case.txt > Your Concrete MVP Dataset`.
6. Next action: the floor only becomes real once `evals/generator/invoices.py` exists; it does not yet (see risks). Verdict unchanged; build is Phase 4.
7. Effort: M. 8. Confidence: 5.

Strongest reason the substrate did not move the answer: a denominator is a denominator regardless of which model produces the answers being scored.

### V6 - Schema language: Pydantic v2 as source of truth; JSON Schema auto-generated

**Platform Engineer**
1. Verdict: YES, unchanged.
2. Why: Pydantic v2 as the single schema source is a tooling and code-organization decision in the application layer; JSON Schema generation is a library call. No part of it depends on the model. U1 (Pydantic vs raw JSON Schema for a future TypeScript port) remains open on its original trigger.
3. KB-for: `[system_design] MLOps Lifecycle ... (Databricks frame)` - "deploy-code ... reproducibility + prod-data isolation + normal code review." (`domains/system_design.md`)
4. KB-against: none found.
5. Project-doc anchor: `Project_Description.txt > 3.6 > Prompt Registry & Versioning > prompt_versions(... variables_schema ...)`.
6. Next action: none; verdict stands.
7. Effort: S. 8. Confidence: 5.

Strongest reason the substrate did not move the answer: schema-source choice is a software-engineering decision, fully outside the model boundary.

---

## Round 2 - peer review (anonymous, themed)

1. **Is the "decoupling" argument a rationalization?** One seat pressed the council on whether "the authoring model changed, not the inference model" is a convenient way to rubber-stamp everything. Counter from three seats: the test is whether any verdict makes a claim about model behavior. Five do not (V1, V3, V4, V5, V6) and are clean. One does (V2, structured-output reliability) and was marked qualified-yes for exactly that reason. A uniform YES would have been the rationalization; the non-uniform result is the evidence the test was applied.

2. **Should the production model itself be reconsidered now that Opus 4.8 is cheaper than 4.7 in Fast Mode?** Raised against V2. Resolution: that is a Phase 5 routing decision (which model serves which tier), not a change to V2 (Claude primary + `generate_structured` adapter). The new Opus 4.8 Fast Mode pricing enriches the deferred routing story; it does not reopen V2. Logged as a Phase 5 input, not a Phase 0 change.

3. **The Cost Ledger genuinely moved.** Unanimous. Verified current Sonnet 4.6 pricing recomputes the transcript's own 4k-in / 1k-out assumption to ~$27 / 1k invoices, not the $9-15 / 1k the transcript stated. This is a numbers correction, not a verdict change, and it is where the substrate-change event actually leaves a mark. See Cost-Delta Probe.

4. **`v1_default.yaml` field-label bug.** Two seats flagged that `cost_per_1k_input_tokens_usd: 3.00` / `cost_per_1k_output_tokens_usd: 15.00` carry the per-million rates under a per-thousand field name. Any cost dashboard reading the field at face value would be off by 1000x. Filed as a risk; documentation correction recommended now, not deferred.

5. **Detection was manual.** One seat noted that ReleasePlane did not catch its own substrate change; a human did. The Substrate Pin rule (echo the model in every session opener) is a convention, not enforcement. No seat claimed the tooling caught it. This constrains the interview sound-bite to a truthful form.

---

## Round 3 - Chairman synthesis (locked)

| # | Verdict | Re-validation result | Load-bearing reason |
|---|---|---|---|
| V1 | AP invoice extraction MVP | **YES, unchanged** | Use-case choice is model-agnostic; the failure modes that justify it are generation-independent. |
| V2 | Claude primary; `generate_structured(schema)` adapter | **QUALIFIED-YES** | Holds, and is the verdict built to absorb substrate change. Assumption flagged: structured-output / tool-use reliability is scoped to the pinned production model (Sonnet 4.6), not the authoring model that changed. Durability is conditional on the pin. |
| V3 | Schema + arithmetic + checksum gates; T1+T2 gating, T3 monitored | **YES, unchanged** | Gates are deterministic checks on output; the arithmetic gate is exactly what catches a substrate-induced regression. |
| V4 | JSON-schema + arithmetic (output) + injection regex (input) | **YES, unchanged** | Deterministic policies execute outside the model boundary. |
| V5 | 30-case floor (10/10/10), generator-emitted, fixed seed | **YES, unchanged** | Dataset sizing is measurement rigor; a denominator does not depend on the model. |
| V6 | Pydantic v2 source of truth; JSON Schema generated | **YES, unchanged** | Schema-source choice is a software-engineering decision outside the model boundary. |

Five clean, one qualified. No verdict marked defer-to-Phase-1-entry. No verdict overturned. The single qualification (V2) does not block Phase 1; it adds a one-line assumption note to the adapter contract / ADR 0002 and a re-test trigger keyed to any future change of the production pin.

### Unresolved disagreements (carried forward, unchanged by the swap)
- **U1**: Pydantic v2 vs raw JSON Schema files (revisit if a TypeScript SDK port lands).
- **U2**: regex-list vs classifier-grade injection filter (escalate at Phase 5 on a false negative).
- **U3**: Tier-3 monitored-only vs gating (revisit at Phase 4 close).

None of the three is affected by the substrate change. They retain their original triggers.

### New disagreement surfaced this session
- **U4 (new)**: detection of an authoring-substrate change is manual (the Substrate Pin opener), not enforced by tooling. One seat wants an automated pin check in CI before Phase 1 close; others scope it to Phase 5 observability. Logged, not resolved.

---

## Cost-Delta Probe (Cloud Engineer + Evaluation Specialist, joint)

Mandated form: run one deterministic Phase 0 eval case end-to-end on Opus 4.8 and report token-in / token-out / latency / cost against the 4.7 baseline as concrete numbers.

**What could not be run, and why (stated plainly, not worked around).**
- No Anthropic API credential is present in the workstation sandbox (`env` shows only `CLAUDE_TMPDIR` / `CLAUDE_CODE_TMPDIR`; the SDK is not installed). Network egress to `api.anthropic.com:443` is open, but authentication is impossible from here. A real, billed end-to-end run with measured latency cannot be produced this session.
- There is no committed Phase 0 eval case to run. `evals/generator/invoices.py` and `evals/datasets/invoice_v1/` were action-plan items #6 and #7, tagged Phase 0 -> Phase 2 / Phase 4; the `evals/` package today holds only `pyproject.toml` and empty `src` / `tests`. The deterministic case is therefore reconstructed from the DEMO.md headline case (#14).

Per the Re-Validation Budget and the project's anti-puffery rule, the **measured (live) latency and billed-cost portion is marked defer-to-Phase-1-entry**, to run on the VPS where the credential lives, against the generated dataset once it exists. No latency number is invented.

**What was computed deterministically (verifiable now).**

Current per-MTok pricing, web-verified 2026-06-23: Sonnet 4.6 = $3.00 in / $15.00 out; Opus 4.8 = $5.00 in / $25.00 out (same headline rate as Opus 4.7; Opus 4.8 Fast Mode $10/$50, down from $30/$150 on 4.7).

| Quantity | Value | Basis |
|---|---|---|
| Fixed prompt scaffold (system + developer, excl. invoice body + JSON schema) | ~214 tokens (approx, char/4; Anthropic tokenizer not bundled) | computed from `prompt_v1.yaml` |
| Planning assumption per invoice | 4,000 in / 1,000 out | inherited from the 4.7 Cost Ledger; unverified until a real case is tokenized |
| Production unit cost recomputed on verified Sonnet 4.6 | **$27.00 / 1k invoices** | 4k*$3/MTok + 1k*$15/MTok |
| Transcript's stated figure | $9-15 / 1k invoices | council_transcript Cost Ledger |
| Opus 4.8 as inference model (reference only; not the production path) | $45.00 / 1k invoices | 4k*$5/MTok + 1k*$25/MTok |
| Delta if the authoring model were ever used as the inference model | **+67%** vs Sonnet 4.6 | $45 vs $27 |

**Findings.**
1. The 4.7-era Cost Ledger is internally inconsistent: under its own 4k-in/1k-out assumption and verified Sonnet pricing it is ~$27/1k, roughly double the $9-15/1k it reported. The prior figure understated production cost.
2. The substrate change does **not** move the production Cost Ledger at the inference layer, because production is pinned to Sonnet 4.6 and Sonnet pricing is unchanged. The Ledger correction above is a re-pricing of a stale estimate, not an effect of the Opus swap.
3. The only Opus-4.8 cost relevance is hypothetical: if the authoring model were ever confused for the inference model, unit cost rises +67%. The adapter Protocol and the pinned `v1_default.yaml` are what prevent that confusion, which ties back to V2.
4. `infra/model_configs/v1_default.yaml` mislabels per-million rates as `cost_per_1k_*` fields. Correct before any public cost claim or automated dashboard read.

All cost figures [volatile: 2026-06-23].

---

## Phase-Gate Auditor (non-voting)

Decision: **proceed to Phase 1.** The six verdicts hold (five clean, one qualified). No verdict requires re-doing Phase 0. The only Phase 0 artifacts touched by this pass are documentation: the Cost Ledger (re-priced + label-bug noted), DEMO.md (substrate-change beat added), and a one-line assumption note for V2. Phase 1 (Docker Compose dev-kit hardening) remains unblocked and is the entry point.

Carried into Phase 1 as backlog, not blockers: build `evals/generator/invoices.py` + `datasets/invoice_v1/` (needed before the arithmetic-gate demo or any live Cost-Delta run); run the deferred live Cost-Delta Probe on the VPS; fix the `v1_default.yaml` cost-field labels; decide U4 (automated authoring-substrate pin check).

End of re-validation pass.
