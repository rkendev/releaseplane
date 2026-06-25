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


class ResolutionError(RuntimeError):
    """Base class for failures resolving a release."""


class PromptNotFoundError(ResolutionError):
    """No active release exists for the prompt (or the pinned id is unknown)."""


class ControlPlaneUnavailableError(ResolutionError):
    """The control-plane could not be reached or returned an unexpected status."""


class ResolvedModelConfig(BaseModel):
    """The model parameters carried on a resolved release.

    Extra registry fields (id, provider, timeout_ms, ...) are ignored; only what
    the provider call needs is modelled here.
    """

    model_config = ConfigDict(protected_namespaces=())

    model_name: str
    temperature: Decimal
    max_tokens: int
    tool_mode: str
    cost_per_mtok_input_usd: Decimal
    cost_per_mtok_output_usd: Decimal


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

    def invocation_config(self) -> ModelInvocationConfig:
        """Project the resolved model config onto the provider's value object."""
        return ModelInvocationConfig(
            model=self.model.model_name,
            temperature=float(self.model.temperature),
            max_tokens=self.model.max_tokens,
            tool_mode=self.model.tool_mode,
            cost_per_mtok_input_usd=self.model.cost_per_mtok_input_usd,
            cost_per_mtok_output_usd=self.model.cost_per_mtok_output_usd,
        )


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
