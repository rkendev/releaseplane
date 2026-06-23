"""OpenTelemetry tracing setup for the control plane.

Traces are exported over OTLP/gRPC to the collector (which forwards to Jaeger)
when OTEL_EXPORTER_OTLP_ENDPOINT is set; otherwise the provider runs with no
exporter, which keeps local tests and unconfigured runs quiet. GenAI semantic
conventions (gen_ai.* span attributes) attach to the gateway model-call path in
a later phase; here the foundation and the health path are instrumented.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def configure_tracing(app: FastAPI, service_name: str) -> None:
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if endpoint:
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app)
