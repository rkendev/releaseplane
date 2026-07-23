"""The /invoke route: resolve, route, render, call the selected provider, trace it.

This is the execution-plane entry point. It resolves the active release for a
prompt name (or a pinned release_id), evaluates the use case's routing rules to
pick the serving model config (falling through to the release's own config on no
match), selects the provider adapter for that config from the registry, renders
the developer prompt, and calls the provider for structured output. The call is
wrapped in a span carrying the gen_ai.* attributes, the release identity, and the
routing decision (signal, matched rule, serving provider), so every call is
auditable by release and by routing outcome.

Routing applies to /invoke only. The eval runner pins the release's own model
config and never routes.
"""

from __future__ import annotations

import time
import uuid
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from opentelemetry import trace
from opentelemetry.trace import Span
from pydantic import BaseModel, ConfigDict, Field

from .config import provider_override
from .metrics import INVOKE_LATENCY, INVOKE_REQUESTS, POLICY_EVENTS, ROUTING_DECISIONS
from .policies import (
    PolicyOutcome,
    parse_rules,
    policy_status,
    post_call_outcomes,
    pre_call_outcomes,
)
from .providers import ModelInvocationConfig, Provider, ProviderError, ProviderRegistry
from .render import RenderError, render
from .resolution import (
    ControlPlaneUnavailableError,
    PromptNotFoundError,
    ReleaseResolver,
    ResolvedRelease,
)
from .routing import RoutingRule, RoutingSignal, first_match

router = APIRouter(tags=["invoke"])
tracer = trace.get_tracer("releaseplane.gateway")

# The request variable whose length feeds the routing input-length signal.
ROUTING_INPUT_VARIABLE = "invoice_pdf_text"


class InvokeRequest(BaseModel):
    prompt_name: str = Field(..., min_length=1)
    variables: dict[str, Any] = Field(default_factory=dict)
    release_id: uuid.UUID | None = None
    # Optional caller routing hint; a rule on the routing_hint field can match it
    # at a higher priority than the length heuristic to override the routing.
    routing_hint: str | None = None


class InvokeMetadata(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    release_id: uuid.UUID
    prompt_version_id: uuid.UUID
    use_case: str
    provider: str
    model: str
    routing_rule_id: str | None
    request_id: uuid.UUID
    policy_status: str
    # How many checks the bundle actually applied. Zero means no check ran, which
    # pairs with a not_applied status so a stale or empty bundle is visible rather
    # than reading as a clean pass.
    policy_checks_applied: int
    policy_outcomes: list[dict[str, Any]]
    input_tokens: int
    output_tokens: int
    latency_ms: float
    cost_estimate_usd: float


class InvokeResponse(BaseModel):
    output: dict[str, Any]
    metadata: InvokeMetadata


class _Served:
    """Carries the serving provider name out to the metrics wrapper.

    Provider selection happens after resolution, so the metric labels cannot be
    set up front; this holder lets the finally block label latency and request
    counters with the provider that actually served (or 'none' on an early error).
    """

    def __init__(self) -> None:
        self.name = "none"


def get_resolver(request: Request) -> ReleaseResolver:
    resolver: ReleaseResolver | None = getattr(request.app.state, "resolver", None)
    if resolver is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "resolver not configured")
    return resolver


def get_registry(request: Request) -> ProviderRegistry:
    registry: ProviderRegistry | None = getattr(request.app.state, "provider_registry", None)
    if registry is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "provider registry not configured")
    return registry


ResolverDep = Annotated[ReleaseResolver, Depends(get_resolver)]
RegistryDep = Annotated[ProviderRegistry, Depends(get_registry)]


def _estimate_cost_usd(
    config: ModelInvocationConfig, input_tokens: int, output_tokens: int
) -> float:
    million = Decimal(1_000_000)
    cost = (
        Decimal(input_tokens) / million * config.cost_per_mtok_input_usd
        + Decimal(output_tokens) / million * config.cost_per_mtok_output_usd
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


def _routing_signal(body: InvokeRequest, resolved: ResolvedRelease) -> RoutingSignal:
    raw = body.variables.get(ROUTING_INPUT_VARIABLE, "")
    text = raw if isinstance(raw, str) else str(raw)
    return RoutingSignal(
        input_length=len(text),
        routing_hint=body.routing_hint,
        use_case=resolved.use_case,
    )


def _injection_input(body: InvokeRequest) -> str:
    """The untrusted text the injection check scans: the request's string variables."""
    return "\n".join(str(value) for value in body.variables.values() if isinstance(value, str))


async def _emit_failures(
    resolver: ReleaseResolver, request_id: uuid.UUID, outcomes: list[PolicyOutcome]
) -> None:
    """Record a policy_event per failure. Best-effort: the output already succeeded."""
    for outcome in outcomes:
        if outcome.passed:
            continue
        try:
            await resolver.emit_policy_event(
                request_id=request_id,
                rule_id=outcome.check,
                outcome="failed",
                detail=outcome.detail,
            )
        except ControlPlaneUnavailableError:
            # Recording is observability; failing to record must not fail a request
            # whose output is already produced.
            continue


async def _select_config(
    resolver: ReleaseResolver,
    body: InvokeRequest,
    resolved: ResolvedRelease,
    signal: RoutingSignal,
) -> tuple[ModelInvocationConfig, RoutingRule | None]:
    """Pick the serving config: first matching rule by priority, else the release's own.

    A pinned release_id never routes: pinning selects an exact release (the path
    the eval runner uses to score a release's own config), so the release's own
    model config serves unconditionally.
    """
    if body.release_id is not None:
        return resolved.invocation_config(), None
    try:
        rules = await resolver.list_routing_rules(resolved.use_case)
    except ControlPlaneUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    match = first_match(rules, signal)
    if match is None:
        return resolved.invocation_config(), None
    try:
        target = await resolver.resolve_model_config(match.target_model_config_id)
    except ControlPlaneUnavailableError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return target.to_invocation_config(), match


def _select_provider(registry: ProviderRegistry, config: ModelInvocationConfig) -> Provider:
    # An explicit GATEWAY_PROVIDER override (the dev stack's zero-spend dummy) wins;
    # otherwise the adapter is the chosen config's provider.
    name = provider_override() or config.provider
    try:
        return registry.select(name)
    except ProviderError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


def _record_release_identity(span: Span, resolved: ResolvedRelease) -> None:
    span.set_attribute("releaseplane.release_id", str(resolved.release_id))
    span.set_attribute("releaseplane.prompt_version_id", str(resolved.prompt_version_id))
    span.set_attribute("releaseplane.use_case", resolved.use_case)


def _record_routing(
    span: Span,
    signal: RoutingSignal,
    config: ModelInvocationConfig,
    matched: RoutingRule | None,
) -> None:
    span.set_attribute("releaseplane.routing.signal.input_length", signal.input_length)
    if signal.routing_hint is not None:
        span.set_attribute("releaseplane.routing.signal.routing_hint", signal.routing_hint)
    span.set_attribute("releaseplane.routing.matched", matched is not None)
    if matched is not None:
        span.set_attribute("releaseplane.routing.rule_id", str(matched.id))
    span.set_attribute("releaseplane.model_config.provider", config.provider)


@router.post("/invoke", response_model=InvokeResponse)
async def invoke(
    body: InvokeRequest, resolver: ResolverDep, registry: RegistryDep
) -> InvokeResponse:
    start = time.perf_counter()
    outcome = "error"
    served = _Served()
    try:
        response = await _invoke(body, resolver, registry, served)
        outcome = "success"
        return response
    finally:
        INVOKE_LATENCY.labels(provider=served.name).observe(time.perf_counter() - start)
        INVOKE_REQUESTS.labels(provider=served.name, outcome=outcome).inc()


async def _invoke(
    body: InvokeRequest,
    resolver: ReleaseResolver,
    registry: ProviderRegistry,
    served: _Served,
) -> InvokeResponse:
    request_id = uuid.uuid4()
    resolved = await _resolve(resolver, body)

    try:
        prompt = render(resolved.developer_prompt, body.variables, resolved.variables_schema_json)
    except RenderError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    rules = parse_rules(resolved.policy_bundle.rules_json)
    pre_outcomes = pre_call_outcomes(rules, _injection_input(body))

    signal = _routing_signal(body, resolved)
    config, matched = await _select_config(resolver, body, resolved, signal)
    provider = _select_provider(registry, config)
    served.name = provider.name

    with tracer.start_as_current_span("gateway.invoke") as span:
        _record_release_identity(span, resolved)
        _record_routing(span, signal, config, matched)
        span.set_attribute("releaseplane.request_id", str(request_id))
        span.set_attribute("gen_ai.system", provider.name)
        span.set_attribute("gen_ai.request.model", config.model)
        try:
            result = await provider.generate_structured(
                system=resolved.system_prompt,
                prompt=prompt,
                model_config=config,
                output_schema=resolved.output_schema_json,
            )
        except ProviderError as exc:
            span.record_exception(exc)
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

        cost = _estimate_cost_usd(config, result.input_tokens, result.output_tokens)
        span.set_attribute("gen_ai.usage.input_tokens", result.input_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", result.output_tokens)
        if result.finish_reason is not None:
            span.set_attribute("gen_ai.response.finish_reason", result.finish_reason)
        span.set_attribute("releaseplane.cost_estimate_usd", cost)

        # Apply the bundle's checks; v1 never transforms the output, only records.
        outcomes = pre_outcomes + post_call_outcomes(
            rules, result.output, resolved.output_schema_json
        )
        status_label = policy_status(outcomes, resolved.policy_bundle.severity_mode)
        span.set_attribute("releaseplane.policy.status", status_label)
        span.set_attribute("releaseplane.policy.checks_applied", len(outcomes))
        span.set_attribute("releaseplane.policy.failures", sum(1 for o in outcomes if not o.passed))

    ROUTING_DECISIONS.labels(
        decision="matched" if matched is not None else "fallthrough", provider=provider.name
    ).inc()
    for outcome in outcomes:
        if not outcome.passed:
            POLICY_EVENTS.labels(
                check=outcome.check,
                outcome="failed",
                severity_mode=resolved.policy_bundle.severity_mode,
            ).inc()

    await _emit_failures(resolver, request_id, outcomes)

    return InvokeResponse(
        output=result.output,
        metadata=InvokeMetadata(
            release_id=resolved.release_id,
            prompt_version_id=resolved.prompt_version_id,
            use_case=resolved.use_case,
            provider=provider.name,
            model=result.model,
            routing_rule_id=str(matched.id) if matched is not None else None,
            request_id=request_id,
            policy_status=status_label,
            policy_checks_applied=len(outcomes),
            policy_outcomes=[outcome.as_dict() for outcome in outcomes],
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            latency_ms=result.latency_ms,
            cost_estimate_usd=cost,
        ),
    )
