# invoice_extraction example

This directory carries the v1 prompt definition and the Pydantic v2 schema models for the AP invoice extraction use case.

## Files

- `models.py` - Pydantic v2 models: `InvoiceVariables`, `InvoiceExtraction`, `LineItem`.
- `prompt_v1.yaml` - v1 prompt definition referencing the models above.

## Schema flow

```
models.py (Pydantic v2)
   |
   |  Model.model_json_schema()  (auto-generated at startup)
   v
prompt_v1.yaml  ->  control-plane prompt_versions row
                       |
                       |  resolved at /invoke time
                       v
                    gateway -> ClaudeProvider.generate_structured(schema=InvoiceExtraction)
                       |
                       |  enforced by Claude's tool-use path
                       v
                    response -> JSON schema policy + arithmetic policy
```

## Adding a new prompt version

1. Edit `models.py` only if the schema shape changes. Otherwise leave the models alone.
2. Copy `prompt_v1.yaml` to `prompt_v2.yaml`, bump `version`, edit `system_prompt` or `developer_prompt`.
3. Commit. CI fires the eval run on the candidate.
4. If gates pass, the release transitions to `candidate`. Operator promotes to `active`.

## Why schemas live here, not in control-plane/

The example is the canonical reference. The control-plane bootstraps by reading the YAML, resolving the `source:` paths, and importing the Pydantic models. A future second use case lives in its own subdirectory under `examples/`.
