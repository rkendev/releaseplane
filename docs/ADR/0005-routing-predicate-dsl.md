# ADR 0005: A restricted JSON predicate DSL for routing rules

Date: 2026-06-26
Status: Accepted

## Context

Phase 5 adds routing rules that send a request to a model config based on request
attributes (input length, a caller hint, the use case). A rule needs a condition.
The options were a general expression language (evaluated with `eval` or a parser)
or a small closed predicate described as data.

A general expression language is a remote-code-execution surface and is hard to
validate or reason about. The control plane stores rules that the gateway
evaluates on every request, so the condition must be safe to store and safe to run.

## Decision

A routing rule carries one restricted predicate stored as JSON:
`{"field": <name>, "op": <operator>, "value": <scalar|list>}`.

- `field` is a closed enum of named request attributes (`input_length`,
  `routing_hint`, `use_case`). An unknown field is rejected at create time.
- `op` is a closed enum (`eq`, `ne`, `lt`, `lte`, `gt`, `gte`, `in`). Ordering ops
  require a numeric field and value; `in` requires a non-empty list. Malformed
  pairings are rejected at create time by the `RoutingRulePredicate` schema.
- The gateway matcher (`gateway/.../routing/matcher.py`) is a pure function that
  reads the field value from a plain mapping by key and compares it. No `eval`, no
  attribute or callable access, so a hostile field name cannot reach arbitrary
  state. The matcher re-parses the stored JSON into its own predicate model rather
  than importing the control-plane schema, keeping the planes decoupled.

Rules are ordered by `priority` ascending; the first match wins; an unmatched
request falls through to the release's own model config. Routing applies to
`/invoke` only; a pinned `release_id` (the eval runner's path) never routes.

## Rationale

- A closed enum over named fields plus a closed operator set is expressive enough
  for the v1 signals (a length heuristic and a hint override by priority) while
  being trivially safe to validate and store.
- Validating on create means a bad rule never reaches the hot path.
- The threshold lives in the predicate value (data), so it is tunable through the
  routing-rules API without a redeploy.

## Consequences

- No boolean composition (AND/OR) at v1: one predicate per rule. Composite
  conditions are expressed as several rules ordered by priority. If a real case
  needs composition, it is an additive change to the predicate schema and matcher.
- The gateway and control plane each define the predicate shape. The duplication
  is small and deliberate (the established "each plane models what it needs"
  pattern, as with the resolved model config).
