"""Resolve a prompt name (or a pinned release id) to a ready-to-call release.

The gateway reads the registry through the control-plane HTTP API rather than the
database, keeping the execution plane decoupled from the registry schema. The
httpx client is injected so production points it at CONTROL_PLANE_URL and tests
point it at an in-process ASGI transport over the control-plane app.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

from .providers import ModelInvocationConfig
from .routing import RoutingRule


class ResolutionError(RuntimeError):
    """Base class for failures resolving a release."""


class PromptNotFoundError(ResolutionError):
    """No active release exists for the prompt (or the pinned id is unknown)."""


class ControlPlaneUnavailableError(ResolutionError):
    """The control-plane could not be reached or returned an unexpected status."""


class ResolvedModelConfig(BaseModel):
    """The model parameters carried on a resolved release.

    Extra registry fields (id, timeout_ms, ...) are ignored; only what the
    provider call and the registry selection need is modelled here. `provider`
    names the adapter the gateway registry resolves the call to.
    """

    model_config = ConfigDict(protected_namespaces=())

    provider: str
    model_name: str
    temperature: Decimal
    max_tokens: int
    tool_mode: str
    cost_per_mtok_input_usd: Decimal
    cost_per_mtok_output_usd: Decimal

    def to_invocation_config(self) -> ModelInvocationConfig:
        """Project this model config onto the provider's value object.

        Used both for the release's own config and for a config a routing rule
        diverts to, so the registry picks the adapter from `provider` either way.
        """
        return ModelInvocationConfig(
            provider=self.provider,
            model=self.model_name,
            temperature=float(self.temperature),
            max_tokens=self.max_tokens,
            tool_mode=self.tool_mode,
            cost_per_mtok_input_usd=self.cost_per_mtok_input_usd,
            cost_per_mtok_output_usd=self.cost_per_mtok_output_usd,
        )


class ResolvedPolicyBundle(BaseModel):
    """The policy bundle carried on a resolved release.

    The gateway applies the bundle's checks at runtime; only the rule payload and
    the severity mode are needed here (the registry id is ignored).
    """

    name: str
    version: str
    rules_json: dict[str, Any]
    severity_mode: str


class ResolvedRelease(BaseModel):
    """The control-plane's composed view of the release the gateway will call."""

    release_id: uuid.UUID
    prompt_version_id: uuid.UUID
    prompt_name: str
    use_case: str
    system_prompt: str
    developer_prompt: str
    variables_schema_json: dict[str, Any]
    output_schema_json: dict[str, Any]
    model: ResolvedModelConfig
    policy_bundle: ResolvedPolicyBundle

    def invocation_config(self) -> ModelInvocationConfig:
        """Project the release's own model config onto the provider value object."""
        return self.model.to_invocation_config()


class ReleaseResolver:
    """Fetches resolved releases from the control-plane over an injected client."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def resolve_active(self, prompt_name: str) -> ResolvedRelease:
        return await self._get("/releases/active", params={"prompt_name": prompt_name})

    async def resolve_by_id(self, release_id: uuid.UUID) -> ResolvedRelease:
        return await self._get(f"/releases/{release_id}/resolved")

    async def _get(self, path: str, params: dict[str, str] | None = None) -> ResolvedRelease:
        try:
            response = await self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise ControlPlaneUnavailableError(f"control-plane unreachable: {exc}") from exc
        if response.status_code == httpx.codes.NOT_FOUND:
            raise PromptNotFoundError(response.json().get("detail", "release not found"))
        if response.status_code != httpx.codes.OK:
            raise ControlPlaneUnavailableError(
                f"control-plane returned {response.status_code} for {path}"
            )
        return ResolvedRelease.model_validate(response.json())

    async def list_routing_rules(self, use_case: str) -> list[RoutingRule]:
        """Fetch the routing rules for a use case, ordered by priority ascending.

        Routing applies to /invoke only; an empty list means the request falls
        through to the release's own model config.
        """
        try:
            response = await self._client.get("/routing-rules", params={"use_case": use_case})
        except httpx.HTTPError as exc:
            raise ControlPlaneUnavailableError(f"control-plane unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise ControlPlaneUnavailableError(
                f"control-plane returned {response.status_code} for /routing-rules"
            )
        return [RoutingRule.model_validate(row) for row in response.json()]

    async def resolve_model_config(self, model_config_id: uuid.UUID) -> ResolvedModelConfig:
        """Fetch a model config by id (the target a routing rule diverts to)."""
        path = f"/model-configs/{model_config_id}"
        try:
            response = await self._client.get(path)
        except httpx.HTTPError as exc:
            raise ControlPlaneUnavailableError(f"control-plane unreachable: {exc}") from exc
        if response.status_code != httpx.codes.OK:
            raise ControlPlaneUnavailableError(
                f"control-plane returned {response.status_code} for {path}"
            )
        return ResolvedModelConfig.model_validate(response.json())
