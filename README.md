# ReleasePlane

> A prompt change fires the CI eval run. The arithmetic gate catches a hallucinated total on Tier-2 case #14: model returns `total = 1,257.50` while `subtotal (1,150.00) + tax (97.50) = 1,247.50`. JSON Schema passed. The release is blocked before the wrong total can post to the ledger.

That moment is the project. ReleasePlane is the control plane that sits between an Accounts Payable LLM extraction pipeline and a production ERP, with a release lifecycle (draft / candidate / canary / active / rolled-back) and a regression gate (schema validity + arithmetic consistency + checksum exact-match) that a release cannot bypass.

## What this demonstrates

- Prompt and model versions are first-class artifacts. Every request carries the `release_id` that resolved it.
- The eval harness runs deterministic checks on a fixed 30-case golden set across three difficulty tiers. No LLM-as-judge at v1; the failure modes that matter for AP invoice extraction are objective and quantitative.
- Promotion is gated. A schema-valid response with a hallucinated total fails the arithmetic check and cannot promote.
- Multi-provider routing is wired through a provider-agnostic adapter Protocol. Claude is the v1 provider via its structured-output path; a second provider lands in Phase 5 with the secret-loading shape already reserved.

## Try it locally

Phase 1 brings up the dev stack:

```bash
docker compose -f infra/docker-compose.yml up -d
curl http://localhost:8001/healthz  # control-plane
curl http://localhost:8002/healthz  # gateway
open http://localhost:3000          # Grafana
```

Phase 0 ships scope, architecture, evaluation, demo, and the v1 prompt definition. See `docs/`.

## Layout

```
control-plane/  release registry, prompt versions, policy bundles, release lifecycle
gateway/        request execution, provider adapters, pre/post policies, OTel
evals/          datasets, runner, metrics (schema / arithmetic / checksum), promotion gate
sdk/            client library with release_id stamping and trace propagation
infra/          docker-compose, OTel collector, Prometheus, Grafana, model configs
docs/           SCOPE, ARCHITECTURE, EVALUATION, DEMO, BUSINESS_CASE, RUNBOOK, SECURITY, ADRs
examples/       invoice_extraction prompt and ground-truth dataset
```

## My role

End-to-end design and implementation: architecture, data model, eval harness, provider adapter contract, observability surface, release lifecycle, deployment topology.

## Status

Phase 0 complete (scope and skeleton). Phase 1 underway (Docker Compose dev kit). See `docs/SCOPE.md` for the explicit out-of-scope list.

## Honesty notes

ReleasePlane is a control-plane reference implementation built around one MVP use case. It is not a multi-tenant SaaS, not a hosted service, and not production-hardened beyond what the eval gates enforce. The hiring narrative is the engineering discipline, not the surface area.

## Claude Code lattice

The repo carries a minimum-viable Claude Code lattice, bootstrapped in one commit (see `docs/ADR/0008-claude-code-lattice-minimum-viable.md`). Each layer is exercised on creation rather than added speculatively:

- `CLAUDE.md`: project paragraph, the authoritative scope pointer (`docs/SCOPE.md`, `docs/ARCHITECTURE.md`), the in-session stack choices, the house style, and the citation rule.
- `.mcp.json`: one MCP server, `releaseplane-postgres` (crystaldba `postgres-mcp` over `uvx`, restricted access, credentials from the environment), for read-only inspection of the dev-stack database.
- `.claude/agents/code-reviewer.md`: the review subagent (eval gate, policy bundle, the shared predicate, Alembic no-drift, house style), invoked on this change as its first use.
- `.claude/hooks/session_start.sh`: a `SessionStart` hook that prints the branch, the uncommitted-changes count, the latest phase brief, and pointers to the scope docs and `CLAUDE.md`.

Rules that govern growth:

- **No ghost subagents**: every agent in `.claude/agents/` must be invoked at least once before the next release tag.
- **Each layer earns its place by use**: the next additions are deferred until a real recurring need fires their trigger (see ADR 0008): a `PostToolUse` ruff-format hook, a `Stop` hook, a `/close` slash command, and an eval-runner skill.

This bootstrap closes the gap recorded in the cross-project memory `claude_code_lattice_gap.md` (a capable harness with no persistent in-repo wiring).
