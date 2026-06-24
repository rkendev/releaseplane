"""Pydantic v2 request/response schemas for the control-plane API.

These are the API contract, kept distinct from the SQLAlchemy storage models in
models.py but aligned field-for-field. Create schemas carry only client-supplied
fields; server-computed values (id, checksum, created_at, stage, timestamps) live
on the Read schemas, which read straight off ORM instances via from_attributes.

The release stage enum is reused from models.py so the storage and API layers
cannot drift apart. ModelConfig schemas disable Pydantic's model_ protected
namespace because model_name and model_version_pin are legitimate field names.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .models import ReleaseStage

# --- prompt_definitions -----------------------------------------------------


class PromptCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    team: str = Field(..., min_length=1, max_length=200)
    use_case: str = Field(..., min_length=1, max_length=200)


class PromptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    team: str
    use_case: str
    created_at: datetime


# --- prompt_versions --------------------------------------------------------


class PromptVersionCreate(BaseModel):
    version: str = Field(..., min_length=1, max_length=64)
    system_prompt: str = Field(..., min_length=1)
    developer_prompt: str = Field(..., min_length=1)
    variables_schema_json: dict[str, Any]
    output_schema_json: dict[str, Any]
    tool_schema_json: dict[str, Any] | None = None
    status: str = Field("draft", min_length=1, max_length=32)
    created_by: str = Field(..., min_length=1, max_length=200)


class PromptVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prompt_id: uuid.UUID
    version: str
    system_prompt: str
    developer_prompt: str
    variables_schema_json: dict[str, Any]
    output_schema_json: dict[str, Any]
    tool_schema_json: dict[str, Any] | None
    status: str
    checksum: str
    created_by: str
    created_at: datetime


# --- model_configs ----------------------------------------------------------


class ModelConfigCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    name: str = Field(..., min_length=1, max_length=200)
    provider: str = Field(..., min_length=1, max_length=64)
    model_name: str = Field(..., min_length=1, max_length=128)
    model_version_pin: str = Field(..., min_length=1, max_length=128)
    temperature: Decimal = Field(..., ge=0, le=2)
    max_tokens: int = Field(..., gt=0)
    timeout_ms: int = Field(..., gt=0)
    tool_mode: str = Field(..., min_length=1, max_length=64)
    active: bool = False
    cost_per_mtok_input_usd: Decimal = Field(..., ge=0)
    cost_per_mtok_output_usd: Decimal = Field(..., ge=0)


class ModelConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: uuid.UUID
    name: str
    provider: str
    model_name: str
    model_version_pin: str
    temperature: Decimal
    max_tokens: int
    timeout_ms: int
    tool_mode: str
    active: bool
    cost_per_mtok_input_usd: Decimal
    cost_per_mtok_output_usd: Decimal


# --- policy_bundles ---------------------------------------------------------


class PolicyBundleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    version: str = Field(..., min_length=1, max_length=64)
    rules_json: dict[str, Any]
    severity_mode: str = Field(..., min_length=1, max_length=32)


class PolicyBundleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    version: str
    rules_json: dict[str, Any]
    severity_mode: str


# --- releases ---------------------------------------------------------------


class ReleaseCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    prompt_version_id: uuid.UUID
    model_config_id: uuid.UUID
    policy_bundle_id: uuid.UUID
    rollout_percent: int | None = Field(None, ge=0, le=100)


class ReleaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: uuid.UUID
    prompt_version_id: uuid.UUID
    model_config_id: uuid.UUID
    policy_bundle_id: uuid.UUID
    stage: ReleaseStage
    rollout_percent: int | None
    created_at: datetime
    activated_at: datetime | None
    archived_at: datetime | None
