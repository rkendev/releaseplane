"""The /invoke route: resolve a release, render, call the provider, trace it.

This is the execution-plane entry point. It resolves the active release for a
prompt name (or a pinned release_id), renders the developer prompt from the
request variables, calls the configured provider for structured output, and
returns the parsed object with metadata. The provider call is wrapped in a span
carrying the gen_ai.* semantic-convention attributes plus the release identity,
so every call is auditable by release in Jaeger.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from opentelemetry import trace
from opentelemetry.trace import Span
from pydantic import BaseModel, ConfigDict, Field

from .providers import Provider, ProviderError
from .render import RenderError, render
from .resolution import (
    ControlPlaneUnavailableError,
    PromptNotFoundError,
    ReleaseResolver,
    ResolvedRelease,
)

router = APIRouter(tags=["invoke"])
tracer = trace.get_tracer("releaseplane.gateway")


class InvokeRequest(BaseModel):
    prompt_name: str = Field(..., min_length=1)
    variables: dict[str, Any] = Field(default_factory=dict)
    release_id: uuid.UUID | None = None


class InvokeMetadata(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    release_id: uuid.UUID
    prompt_version_id: uuid.UUID
    use_case: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_estimate_usd: float


class InvokeResponse(BaseModel):
    output: dict[str, Any]
    metadata: InvokeMetadata


def get_resolver(request: Request) -> ReleaseResolver:
    resolver: ReleaseResolver | None = getattr(request.app.state, "resolver", None)
    if resolver is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "resolver not configured")
    return resolver


def get_provider(request: Request) -> Provider:
    provider: Provider | None = getattr(request.app.state, "provider", None)
    if provider is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "provider not configured")
    return provider


ResolverDep = Annotated[ReleaseResolver, Depends(get_resolver)]
ProviderDep = Annotated[Provider, Depends(get_provider)]


def _estimate_cost_usd(resolved: ResolvedRelease, input_tokens: int, output_tokens: int) -> float:
    cfg = resolved.model
    million = Decimal(1_000_000)
    cost = (
        Decimal(input_tokens) / million * cfg.cost_per_mtok_input_usd
        + Decimal(output_tokens) / million * cfg.cost_per_mtok_output_usd
    )
    return float(cost)


async def _resolve(resolver: ReleaseResolver, body: InvokeRequest) -> ResolvedRelease:
    try:
        if body.release_id is not None:
            return await resolver.resolve_by_id(body.release_id)
        return await resolver.resolve_active(body.prompt_name)
    except PromptNotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ControlPlaneUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc


def _record_release_identity(span: Span, resolved: ResolvedRelease) -> None:
    span.set_attribute("releaseplane.release_id", str(resolved.release_id))
    span.set_attribute("releaseplane.prompt_version_id", str(resolved.prompt_version_id))
    span.set_attribute("releaseplane.use_case", resolved.use_case)


@router.post("/invoke", response_model=InvokeResponse)
async def invoke(
    body: InvokeRequest, resolver: ResolverDep, provider: ProviderDep
) -> InvokeResponse:
    resolved = await _resolve(resolver, body)

    try:
        prompt = render(resolved.developer_prompt, body.variables, resolved.variables_schema_json)
    except RenderError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    model_config = resolved.invocation_config()
    with tracer.start_as_current_span("gateway.invoke") as span:
        _record_release_identity(span, resolved)
        span.set_attribute("gen_ai.system", provider.name)
        span.set_attribute("gen_ai.request.model", model_config.model)
        try:
            result = await provider.generate_structured(
                system=resolved.system_prompt,
                prompt=prompt,
                model_config=model_config,
                output_schema=resolved.output_schema_json,
            )
        except ProviderError as exc:
            span.record_exception(exc)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

        cost = _estimate_cost_usd(resolved, result.input_tokens, result.output_tokens)
        span.set_attribute("gen_ai.usage.input_tokens", result.input_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", result.output_tokens)
        if result.finish_reason is not None:
            span.set_attribute("gen_ai.response.finish_reason", result.finish_reason)
        span.set_attribute("releaseplane.cost_estimate_usd", cost)

    return InvokeResponse(
        output=result.output,
        metadata=InvokeMetadata(
            release_id=resolved.release_id,
            prompt_version_id=resolved.prompt_version_id,
            use_case=resolved.use_case,
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=result.latency_ms,
            cost_estimate_usd=cost,
        ),
    )
