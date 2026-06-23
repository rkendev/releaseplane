# Cost-Delta Probe Results (2026-06-23)

Live measurement closing the deferred Phase 0 Cost-Delta probe. One run of
the pinned production model and one reference run of Opus on `case_03`
(the deterministic Tier-1 baseline), structured-output (tool-use) mode,
temperature 0.0 for the production model.

Rates used (verified 2026-06-23, per MTok): Sonnet 4.6 $3.00 in / $15.00 out; Opus 4.8 $5.00 in / $25.00 out.

## Measured

| Model | Role | Input tok | Output tok | Latency (ms) | Cost/invoice | Cost/1k |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `claude-sonnet-4-6` | production | 1750 | 228 | 3021 | $0.008670 | $8.67 |
| `claude-opus-4-8` | reference only | 1976 | 284 | 3145 | $0.016980 | $16.98 |

## Reconciliation

- Prior ledger estimate: $9-15 / 1k invoices (4.7 Cost Ledger estimate).
- Re-priced deterministic estimate: ~$27 / 1k invoices, on a 4000-in / 1000-out assumption at the verified Sonnet rates (4000/1e6*3 + 1000/1e6*15 = $0.027/invoice).
- Measured Sonnet 4.6: 1750 in / 228 out tokens, $8.67 / 1k invoices.
- The real baseline usage (1750 in / 228 out) is well below the 4000-in / 1000-out planning assumption, so the re-priced ~$27/1k figure is a conservative overestimate; the measured baseline is $8.67/1k, near the low end of the 4.7 ledger range. Multi-line Tier-2/3 invoices carry more input tokens, so keep $27/1k as the conservative planning number until measured across all tiers.
- Opus-vs-Sonnet reference delta: measured at +95.8% on this case (prior reference figure was +67%). Opus is reference only; production stays on Sonnet.

Tool-use returned a structured object: Sonnet=True, Opus=True. Latency is a single uncached sample and is noisy.

Substrate note: claude-opus-4-8 rejects the `temperature` parameter (deprecated for that model), so the reference run omits it; the production Sonnet run pins temperature 0.0.
