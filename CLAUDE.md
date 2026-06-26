# ReleasePlane

ReleasePlane is an LLMOps control plane; the MVP use case is Accounts Payable
invoice extraction (PDF text in, structured JSON out). It is organized as four
planes: a control plane (versioned prompts, model configs, policy bundles, routing
rules, releases; FastAPI + Postgres), an execution plane (the gateway that resolves
the active release, routes, applies policy, and calls a provider), an ingestion /
eval plane (golden datasets, eval runs and results, the promotion gate), and an
observability plane (OpenTelemetry traces, Prometheus + Grafana, Jaeger).

## Authoritative scope

`docs/SCOPE.md` (what is in and out of scope for v1) and `docs/ARCHITECTURE.md` (the
as-built design and data model) are authoritative. When this file or any assumption
conflicts with them, they win; update them rather than working around them. The ADRs
in `docs/ADR/` record the decisions behind the current shape.

## Stack choices (in-session decisions)

- FastAPI for both services; Postgres for state (SQLAlchemy 2.0 async + asyncpg,
  schema changes through Alembic migrations only).
- pgvector is reserved for the deferred embedding-based failure-clustering work and is
  not yet wired (see the out-of-scope list in `docs/SCOPE.md`); do not assume vector
  search exists today.
- The Claude API direct through the SDK tool-use path is the primary provider; an
  OpenAI-compatible second provider was added in Phase 5 behind a provider registry.
- No LangChain (or other orchestration framework); the provider contract is the small
  `generate_structured` Protocol.

## House style (binding on tracked files, comments, commits)

- No em-dashes. Banned words: robust, leverage, seamless, holistic, delve, foster,
  "in order to", "it's worth noting". Enforced on docs by `tools/banned_words.py`
  (the pre-commit `banned-words` hook, scoped to `README.md` and `docs/*.md`); keep
  code and commits to the same style by hand.
- No `Co-Authored-By` trailers in any commit message, and no gratuitous AI-tool brand
  names in tracked files. The Claude Code lattice files (`CLAUDE.md`, `.claude/`, the
  README "Claude Code lattice" section, and `docs/ADR/0008-...`) are the deliberate,
  documented exception, since they cannot be written without naming the harness. The
  repo stays private until product-grade.
- The whole build and CI make zero live provider API calls; tests run on the dummy
  provider, and a CI grep guard fails the run on `api.anthropic.com` or `api.openai.com`.

## Citation rule

Cite the authoritative source for non-obvious design claims: the relevant ADR
(`docs/ADR/`), a `docs/` section, or a Knowledge Base anchor. Do not assert design
facts from memory; if a claim is not backed by the code or a doc, verify it first.
`docs/ARCHITECTURE.md` and `docs/SCOPE.md` win on any conflict.

## Cross-project knowledge

Cross-project patterns and council/KB anchors live on the Windows mirror under
`<mirror>\Knowledge_Base\`. Reach for it for
shared design knowledge that is not specific to this repo.

See `README.md` (the "Claude Code lattice" section) and
`docs/ADR/0008-claude-code-lattice-minimum-viable.md` for the repo's Claude Code
wiring and the rule that every layer must be used before it grows.
