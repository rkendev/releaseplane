"""Prometheus metrics for the gateway.

These are served on /metrics (the default registry) and scraped directly by the
dev-stack Prometheus `gateway` job, so the gateway dashboard reads request rate,
latency quantiles, and error rate without depending on the OTel metrics pipeline.
Labels stay low-cardinality: provider and a success/error outcome.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

INVOKE_REQUESTS = Counter(
    "gateway_invoke_requests_total",
    "Total POST /invoke requests, by provider and outcome.",
    ["provider", "outcome"],
)

INVOKE_LATENCY = Histogram(
    "gateway_invoke_latency_seconds",
    "End-to-end POST /invoke latency in seconds, by provider.",
    ["provider"],
)
