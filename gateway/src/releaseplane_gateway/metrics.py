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

ROUTING_DECISIONS = Counter(
    "gateway_routing_decisions_total",
    "Routing decisions on /invoke, by whether a rule matched and the serving provider.",
    ["decision", "provider"],
)

POLICY_EVENTS = Counter(
    "gateway_policy_events_total",
    "Policy-check failures on /invoke, by check, outcome, and the bundle severity mode.",
    ["check", "outcome", "severity_mode"],
)
