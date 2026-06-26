"""Gateway FastAPI app: health, tracing, metrics, and the /invoke route.

The execution plane resolves the active release for a prompt through the
control-plane HTTP API, renders the prompt, and calls a provider for structured
output. The provider is chosen at startup (dummy by default, so nothing needs an
API key); the control-plane client and resolver live on app state so tests can
swap in an in-process transport. /healthz reports liveness and /metrics exposes
Prometheus metrics for the dev stack.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from anthropic import Anthropic
from fastapi import FastAPI
from openai import OpenAI
from prometheus_client import make_asgi_app

from .config import anthropic_api_key, control_plane_url, openai_api_key, provider_name
from .invoke import router as invoke_router
from .providers import (
    ClaudeProvider,
    DummyProvider,
    OpenAiProvider,
    Provider,
    ProviderRegistry,
)
from .resolution import ReleaseResolver
from .telemetry import configure_tracing

SERVICE_NAME = "gateway"


def build_provider() -> Provider:
    """Select the provider from configuration; dummy keeps startup key-free."""
    if provider_name() == "claude":
        return ClaudeProvider(Anthropic(api_key=anthropic_api_key()))
    return DummyProvider()


def build_registry() -> ProviderRegistry:
    """Build the provider registry from the keys present at startup.

    The dummy adapter is always available; the real adapters are added only when
    their key is configured, so the stack starts key-free and an unconfigured
    provider fails at request time with a clear message rather than at boot. The
    SDK clients are constructed (not called), which makes zero network calls.
    """
    providers: dict[str, Provider] = {"dummy": DummyProvider()}
    anthropic_key = anthropic_api_key()
    if anthropic_key:
        providers["claude"] = ClaudeProvider(Anthropic(api_key=anthropic_key))
    openai_key = openai_api_key()
    if openai_key:
        providers["openai"] = OpenAiProvider(OpenAI(api_key=openai_key))
    return ProviderRegistry(providers)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    client = httpx.AsyncClient(base_url=control_plane_url())
    app.state.http_client = client
    app.state.resolver = ReleaseResolver(client)
    app.state.provider = build_provider()
    app.state.provider_registry = build_registry()
    try:
        yield
    finally:
        await client.aclose()


app = FastAPI(title="ReleasePlane Gateway", lifespan=lifespan)
configure_tracing(app, SERVICE_NAME)
app.mount("/metrics", make_asgi_app())
app.include_router(invoke_router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}
