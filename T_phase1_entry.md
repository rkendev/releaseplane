# ReleasePlane - Phase 1 Entry T-Prompt (for Claude Code on the VPS)

Hand this whole file to the executor as the task brief. It is self-contained: it does not depend on any workstation memory, chat history, or external note. Every path it names resolves inside the ReleasePlane repo or is established by Task 0. Inline facts are repeated here on purpose so the executor never has to reach back to a machine it cannot see.

---

## Session opener (do this before anything else)

1. **Substrate Pin.** State the model you are running as, verbatim from the model selector, as the first line of your first response (for example: `Model: claude-opus-4-8`). This project treats a silent change of model substrate as a first-class incident; the echo is how drift stays loud. If you cannot determine your model, say so and stop.
2. **Plan mode.** Use plan mode. Do not apply any edits, create any files, or run any state-changing command until the plan is reviewed and approved. The numeric and structural prescriptions below (image digests, token counts, test counts, field renames) are hypotheses to verify against the live repo during planning, not facts to apply blind. Where a prescription disagrees with what you find, surface the disagreement in the plan; do not silently follow either.

## Repository facts (inlined; verify in plan mode)

- The project is **ReleasePlane**, an LLMOps control plane whose MVP is Accounts Payable invoice extraction. Phase 0 is locked. This is the entry to Phase 1 (infra and dev kit).
- Repo layout already on disk: `control-plane/`, `gateway/`, `evals/`, `sdk/`, `infra/`, `docs/`, `tests/`, `examples/`, `tools/`, each Python package with its own `pyproject.toml`; root is a `uv` workspace.
- Canonical Phase 0 docs to read first, in this order: `docs/SCOPE.md`, `docs/EVALUATION.md`, `docs/DEMO.md`, `docs/ARCHITECTURE.md`, then `examples/invoice_extraction/prompt_v1.yaml` and `examples/invoice_extraction/models.py`. These define the contract you are building toward.
- The six locked Phase 0 verdicts (do not reopen; build to them):
  1. MVP use case is AP invoice extraction.
  2. Claude is the primary provider via an adapter Protocol method `generate_structured(schema)`, not raw completion. Second provider is Phase 5.
  3. Eval gates are deterministic: JSON-schema validity + arithmetic consistency (+/-0.01 currency tolerance) + checksum exact-match on `invoice_number`, `invoice_date`, `currency`, `total`. Tier 1 and Tier 2 gate promotion; Tier 3 is monitored only.
  4. v1 policies: JSON-schema + arithmetic-consistency (output side) + one prompt-injection regex filter (input side).
  5. Eval-set floor: 30 cases (10 Tier-1 / 10 Tier-2 / 10 Tier-3), generator-emitted, fixed seed.
  6. Pydantic v2 models are the single schema source of truth; JSON Schema is auto-generated from them.
- Production model is pinned in `infra/model_configs/v1_default.yaml` to `claude-sonnet-4-6`, temperature 0.0, structured-output mode. Do not change the pin in this phase.
- Verified API rates as of 2026-06-23 (use these for cost math, re-verify before any public claim): Sonnet 4.6 = $3.00 input / $15.00 output per million tokens; Opus 4.8 = $5.00 input / $25.00 output per million tokens.

## Working rules (binding for this phase)

- **House style:** no em-dashes; banned words = robust, leverage, seamless, holistic, delve, foster, "in order to", "it's worth noting". Applies to docs, comments, commit messages.
- **No AI-tool brand on public-facing surfaces.** Do not put tool brand names or `Co-Authored-By` trailers in commit messages, README, or any file a recruiter could read. Neutral phrasing only. The repo stays **private** until it is product-grade.
- **Pre-commit is via uv:** run `uv run pre-commit run --all-files` (not a bare `pre-commit`). `make check` lints `src` and `tests` only, so any file you add outside those trees must still pass the full `uv run pre-commit run --all-files`.
- **Test-count baselines** come from the `make check` summary, not from grepping `def test_`.
- **New runtime deps used under typed decorators** (`@app.get`, `@mcp.tool`, Pydantic-validated callables) must be added to the mypy hook's `additional_dependencies` in `.pre-commit-config.yaml`, or CI fails on an untyped-decorator error even when `make check` passes locally.
- **Anthropic SDK + tests:** the SDK validates the API key at constructor time, before any VCR/cassette interception. Any committed test that constructs a client must pass `Anthropic(api_key="dummy")` or set a non-empty `ANTHROPIC_API_KEY`. Live scripts that need the real key must skip cleanly when the key is absent, so CI never calls the API.

---

## Task 0 - Land the repo and confirm the VPS path (prerequisite)

If ReleasePlane is not yet a git repo with a remote and a VPS checkout, establish that first.

- Initialize git at the repo root if absent; create a **private** remote; push `main`.
- Clone or pull to the VPS under `/root/projects/AI-Engineering/releaseplane` (adjust to the actual convention if the plan finds a different one; state the resolved path in the plan).
- Acceptance: `git status` clean on both Windows mirror and VPS; `main` identical on both; remote is private.

## Task 1 - Eval dataset generator (FIRST real task)

Build `evals/generator/invoices.py` and generate the committed dataset. This unblocks the arithmetic-gate demo and the live Cost-Delta probe; nothing downstream is demonstrable without it.

- `fpdf2`-based generator, **fixed seed**, emits 30 invoice PDFs plus 30 ground-truth JSON files into `evals/datasets/invoice_v1/`, split 10 Tier-1 / 10 Tier-2 / 10 Tier-3.
- Ground-truth JSON must validate against `examples/invoice_extraction/models.py:InvoiceExtraction` (Pydantic v2). Generate the JSON by constructing the model and dumping it, so the ground truth cannot drift from the schema.
- Include the named cases the rest of the project already references (`examples/invoice_extraction/prompt_v1.yaml > regression_notes`):
  - `case_03` (Tier 1): single line item, clean baseline pass.
  - `case_14` (Tier 2): multi-line with a discount row. Ground truth: `subtotal = 1150.00`, `tax = 97.50`, `total = 1247.50`. This is the demo headline case; a later prompt regression makes the model return `1257.50` and the arithmetic gate must catch it.
  - `case_21` (Tier 2): vendor with leading zeros in `invoice_number`; the checksum exact-match catches OCR `0`/`O` confusion.
  - `case_27` (Tier 3): handwritten annotation on the subtotal row; monitored only.
- Commit both the PDFs and the JSON. Add a determinism test in `evals/tests/`: regenerating with the same seed yields byte-identical JSON (PDF byte-stability is acceptable to assert at the extracted-text level if `fpdf2` embeds timestamps; if so, strip or fix the timestamp and document it).
- Add `fpdf2` to the `evals` package deps; if mypy flags it, add to `additional_dependencies`.
- Acceptance: `ls evals/datasets/invoice_v1/` shows 30 PDFs + 30 JSON; every JSON validates against `InvoiceExtraction`; the determinism test passes; arithmetic holds in every Tier-1 and Tier-2 ground truth and case_14's ground truth sums to 1247.50.

## Task 2 - Live Cost-Delta Probe (SECOND real task; closes the deferred Phase 0 item)

Phase 0 deferred the measured half of the Cost-Delta probe for lack of an API credential and a committed case. Run it now on the VPS where the key lives.

- Add `evals/probes/cost_delta.py`. It is a **live integration script, not a pytest test**: exclude it from collection and make it skip cleanly if `ANTHROPIC_API_KEY` is unset.
- It loads `prompt_v1.yaml` (system + developer prompt), renders the developer prompt with the extracted text of one **deterministic** generated case (use `case_03`, the clean Tier-1 baseline), builds the tool/structured-output contract from `InvoiceExtraction.model_json_schema()`, and calls `claude-sonnet-4-6` at temperature 0.0 in structured-output (tool-use) mode.
- Record from the real response: `usage.input_tokens`, `usage.output_tokens`, wall-clock latency in ms, and computed cost using the verified Sonnet 4.6 rates ($3 / $15 per MTok).
- Repeat once against `claude-opus-4-8` (same case, same prompt) as a reference point only, to measure the real Opus-vs-Sonnet delta. Opus is not the production model; label the row clearly as reference.
- Write the measured numbers into a new `evals/probes/cost_delta_results_2026-06-23.md` and reconcile them against two prior figures: the 4.7 Cost Ledger estimate of $9-15/1k invoices, and the re-priced deterministic estimate of ~$27/1k (4k-in/1k-out assumption on verified Sonnet rates). Note whether the real per-case token counts match the 4k-in/1k-out planning assumption; correct the assumption if they do not.
- Acceptance: the results file carries real measured token counts, latency, and cost for one Sonnet 4.6 run and one Opus 4.8 reference run; the +67% Opus-vs-Sonnet reference delta is either confirmed or replaced with the measured delta; the script is skipped by CI.

## Task 3 - Correct two Phase 0 carry-over defects

- `infra/model_configs/v1_default.yaml`: the fields `cost_per_1k_input_tokens_usd: 3.00` and `cost_per_1k_output_tokens_usd: 15.00` carry per-million rates under per-thousand names. Rename the fields to `cost_per_mtok_input_usd` / `cost_per_mtok_output_usd` (values unchanged, they are the correct per-MTok rates), and update any reader of those fields. Do not silently divide; the values are right, the names are wrong.
- `README.md`: the banned-words pre-commit hook trips on the README's own line that lists the banned tokens. Keep the example token list only in `tools/banned_words.py`; remove or rephrase the README line so `uv run pre-commit run --all-files` is clean.
- Acceptance: pre-commit clean across the tree; no reader of the cost fields breaks; grep confirms no remaining `cost_per_1k_*` field name.

## Task 4 - Docker Compose dev kit: pin real image digests

- `infra/docker-compose.yml` ships `@sha256:PLACEHOLDER_DIGEST` on every image (postgres, minio, otel-collector, jaeger, prometheus, grafana, plus the two app services once built). Resolve each to a real digest via `docker manifest inspect <image:tag>` and pin it.
- Keep named volumes for stateful services; add healthchecks for postgres and minio.
- Acceptance: `docker compose config` validates; `docker compose pull` succeeds against the pinned digests; no `PLACEHOLDER` strings remain.

## Task 5 - Base services, health, and tracing

- `control-plane` and `gateway`: a `/healthz` endpoint each; control-plane connects to Postgres on startup (lifespan loader). Configure OpenTelemetry tracing in both, following GenAI span conventions, even if only the health path is instrumented at first.
- Tests: a healthcheck test per service; a DB-migration sanity test if Alembic is wired. Construct any Anthropic client in tests with `api_key="dummy"`.
- Acceptance: `docker compose up -d`, both `/healthz` return green, Grafana shows basic service metrics, the new tests pass, and the `make check` test-count summary rises by the number you reported in the plan.

## Task 6 - RUNBOOK.md (replace the placeholder)

- Cover: `docker compose up`, where the health checks are, Grafana and Jaeger URLs, and the common failure modes (port collisions, CPU baseline, stale volumes) with one-line fixes each.
- Acceptance: a reviewer can follow it from clone to green `/healthz` without prior context.

## Open question to flag, not resolve (U4)

The substrate-change re-validation surfaced that detection of an authoring-model change is currently manual (the Substrate Pin opener), not enforced by tooling. Do not build automation for it in this phase. Note in the plan whether a CI check that fails on an undeclared or changed substrate belongs at Phase 1 close or Phase 5 observability, and leave the decision to the project owner.

---

## Task close sequence (run after each task is approved and merged; do not make the owner ask)

For each task, after the work passes review:

```
# from the repo on the VPS, on the task branch:
uv run pre-commit run --all-files
make check
git checkout main && git merge --ff-only <task-branch>
git push origin main
# then on the Windows mirror:
git pull --ff-only
```

Do not run `git pull`, `git fetch`, or `git stash` against the Windows `*-from-git` mirror from inside a sandbox shell; the sandbox cannot clear lock files and leaves the mirror wedged. Pull the mirror from a normal Windows terminal.

## Phase 1 exit criterion (state it back at phase close)

A reviewer clones the private repo, runs `docker compose up -d`, and gets green `/healthz` from both `control-plane` and `gateway`; Grafana shows service metrics; the 30-case dataset is committed and schema-valid; the live Cost-Delta numbers are recorded; pre-commit and CI are green. At that point Phase 2 (prompt registry and releases) is unblocked.
