# ADR 0007: A provider registry selects the adapter per request

Date: 2026-06-26
Status: Accepted

## Context

Through Phase 4 the gateway built one provider at startup
(`app.state.provider`) chosen by `GATEWAY_PROVIDER`. Phase 5 adds a second
provider (OpenAI) and routing, so a single request must be able to reach Claude or
OpenAI depending on the model config it resolves or routes to. A single startup
provider cannot express per-request selection.

## Decision

A `ProviderRegistry` maps a provider name to an adapter instance. It is built once
at startup (`build_registry`): the dummy adapter is always present; the Claude and
OpenAI adapters are added only when their key is configured, so the stack starts
key-free and an unconfigured provider fails at request time with a clear message
rather than at boot.

On `/invoke` the gateway selects the adapter from the chosen model config's
`provider` field. `GATEWAY_PROVIDER`, when set, is an optional force-override that
the dev stack uses to pin `dummy` for zero spend; unset means select by the config.
The model config carries `provider` already, threaded through resolution into the
value object the registry reads.

The OpenAI adapter satisfies the same `generate_structured` contract as Claude, via
a forced function call built from the release output schema (decision
D-OPENAI-STRUCT), mirroring the Claude tool-use guarantee of schema-shaped output.

## Rationale

- Per-request selection is what routing and multi-provider need; a registry is the
  minimal structure that provides it without a factory call on every request.
- Building real clients only when their key is present keeps the zero-spend default
  and the key-free startup, and keeps the offline tests honest (a dummy key
  constructs a client but makes no call).

## Consequences

- `app.state.provider` and `build_provider` are removed; selection lives in the
  invoke path.
- The CI zero-API grep guard is extended to `api.openai.com` alongside
  `api.anthropic.com`, and the OpenAI adapter is tested with a stubbed client and a
  dummy key. The only live OpenAI spend is the gated `run_openai_smoke.py`.
