# Security

Placeholder. Filled in Phase 5 alongside policy expansion.

Sections planned:
- Threat model (vendor-supplied PDFs as untrusted input)
- Secrets handling (provider API keys, never committed)
- PII inventory for AP invoices (vendor tax IDs, bank details)
- Audit log retention
- Prompt-injection coverage (regex filter at v1; classifier deferred)
- RBAC on the admin UI and promotion API

Current v1 controls:
- Input-side: regex filter in `gateway/guards/prompt_injection.py`.
- Output-side: JSON Schema validation, arithmetic consistency rule.
- Secrets: loaded from environment, never logged; see `infra/secrets.md`.
