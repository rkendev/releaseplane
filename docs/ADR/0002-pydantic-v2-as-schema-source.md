# ADR 0002: Pydantic v2 models as the single source of schema truth

Date: 2026-06-23
Status: Accepted

## Context

Prompt templates need a variable schema (placeholders the gateway substitutes) and an output schema (the structured response the model must produce). The eval harness, the JSON Schema validation policy, and the Claude adapter's tool-use call all need to agree on these schemas.

Two candidate sources of truth:
- Raw JSON Schema files committed in `examples/<use_case>/`.
- Pydantic v2 models in Python with JSON Schema auto-generated.

## Decision

Use Pydantic v2 models as the source of truth. JSON Schema is generated from `Model.model_json_schema()` at startup and cached.

## Rationale

- One definition, two consumers (the Python SDK and the JSON Schema policy).
- Pydantic v2 validates at parse time with helpful errors; the JSON Schema validator does not.
- The Claude adapter's tool-use path takes a JSON Schema directly; auto-generating it from Pydantic removes a manual sync step.

## Consequences

- The SDK is Python-only at v1.
- A future TypeScript SDK port would need to either consume the auto-generated JSON Schema or regenerate from a shared spec. Tracked as Unresolved Disagreement U1 in the Phase 0 council transcript.
- Prompt versions store `variables_schema_json` and `output_schema_json` in Postgres as the generated artifacts, with the Pydantic model class reference (module path) recorded for regeneration.
