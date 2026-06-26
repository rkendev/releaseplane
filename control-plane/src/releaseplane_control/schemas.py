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

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import EvalRunStatus, ReleaseStage

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


# --- routing_rules ----------------------------------------------------------


class RoutingField(str, enum.Enum):
    """The closed set of named request fields a routing predicate may reference.

    Anything outside this set is rejected on create, so a rule can never name an
    arbitrary attribute and the gateway matcher only ever reads these keys from a
    plain dict (no attribute or callable access).
    """

    input_length = "input_length"
    routing_hint = "routing_hint"
    use_case = "use_case"


_NUMERIC_FIELDS = frozenset({RoutingField.input_length})


class RoutingOp(str, enum.Enum):
    """The closed operator set for a routing predicate."""

    eq = "eq"
    ne = "ne"
    lt = "lt"
    lte = "lte"
    gt = "gt"
    gte = "gte"
    in_ = "in"


_ORDERING_OPS = frozenset({RoutingOp.lt, RoutingOp.lte, RoutingOp.gt, RoutingOp.gte})


class RoutingRulePredicate(BaseModel):
    """A single restricted predicate: field <op> value.

    The closed field and op enums reject unknown names at parse time (a hostile
    field name is a 422, not an attribute lookup). The model validator rejects
    malformed pairings: ordering ops need a numeric field and a numeric value,
    and `in` needs a non-empty list.
    """

    model_config = ConfigDict(extra="forbid")

    field: RoutingField
    op: RoutingOp
    value: int | float | str | list[int | float | str]

    @model_validator(mode="after")
    def _check_op_value(self) -> RoutingRulePredicate:
        if self.op is RoutingOp.in_:
            if not isinstance(self.value, list) or not self.value:
                raise ValueError("op 'in' requires a non-empty list value")
            return self
        if isinstance(self.value, list):
            raise ValueError(f"op {self.op.value!r} does not take a list value")
        if self.op in _ORDERING_OPS:
            if self.field not in _NUMERIC_FIELDS:
                raise ValueError(f"op {self.op.value!r} requires a numeric field")
            if isinstance(self.value, str):
                raise ValueError(f"op {self.op.value!r} requires a numeric value")
        return self


class RoutingRuleCreate(BaseModel):
    use_case: str = Field(..., min_length=1, max_length=200)
    predicate: RoutingRulePredicate
    target_model_config_id: uuid.UUID
    priority: int = Field(..., ge=0)


class RoutingRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    use_case: str
    predicate: RoutingRulePredicate
    target_model_config_id: uuid.UUID
    priority: int
    created_at: datetime


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


class ResolvedReleaseRead(BaseModel):
    """The active release for a prompt, flattened for the execution plane.

    The gateway resolves a prompt name to exactly one active release and needs
    the prompt text, the variable and output schemas, and the model parameters in
    a single response. This composes those fields across the release, its prompt
    version and definition, and the referenced model config so the gateway makes
    one call rather than walking the registry.
    """

    release_id: uuid.UUID
    prompt_version_id: uuid.UUID
    prompt_name: str
    use_case: str
    system_prompt: str
    developer_prompt: str
    variables_schema_json: dict[str, Any]
    output_schema_json: dict[str, Any]
    model: ModelConfigRead


# --- eval datasets / cases --------------------------------------------------


class EvalCaseCreate(BaseModel):
    """One golden case in a dataset-load payload.

    expected_json is the ground-truth extraction (decimals and dates already
    rendered as strings, matching the committed JSON). input_text is the OCR
    rendering the runner feeds to the gateway; input_path is the source artifact
    kept for provenance and as the per-dataset natural key.
    """

    input_path: str = Field(..., min_length=1, max_length=256)
    input_text: str = Field(..., min_length=1)
    expected_json: dict[str, Any]
    tier: int = Field(..., ge=1, le=3)
    metadata_json: dict[str, Any] | None = None


class EvalDatasetCreate(BaseModel):
    """Load payload: dataset metadata plus all of its cases.

    The control plane stores this verbatim; it has no knowledge of invoices or
    the generator, keeping the plane separation. row_count is server-derived from
    the case list rather than client-supplied.
    """

    name: str = Field(..., min_length=1, max_length=200)
    domain: str = Field(..., min_length=1, max_length=200)
    source: str = Field(..., min_length=1, max_length=256)
    generator_seed: int
    cases: list[EvalCaseCreate] = Field(..., min_length=1)


class EvalDatasetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    domain: str
    source: str
    row_count: int
    generator_seed: int


class EvalCaseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_id: uuid.UUID
    input_path: str
    input_text: str
    expected_json: dict[str, Any]
    tier: int
    metadata_json: dict[str, Any] | None


class EvalDatasetLoadResult(BaseModel):
    """Outcome of a load: the dataset plus how many cases were newly written.

    cases_created is 0 on an idempotent reload, so a caller can tell a fresh load
    from a no-op without diffing the case list.
    """

    dataset: EvalDatasetRead
    cases_total: int
    cases_created: int


# --- eval runs / results ----------------------------------------------------


class EvalRunCreate(BaseModel):
    """Open a run for a release over a dataset. The run starts in running."""

    release_id: uuid.UUID
    dataset_id: uuid.UUID


class EvalResultCreate(BaseModel):
    """One metric outcome the runner computed for one case."""

    case_id: uuid.UUID
    metric_name: str = Field(..., min_length=1, max_length=64)
    metric_value: float | None = None
    pass_fail: bool
    notes: dict[str, Any] | None = None


class EvalRunComplete(BaseModel):
    """Finalize a run: terminal status, the per-tier summary, and all results.

    status is succeeded or failed; running is not a terminal state. summary_json
    is the per-tier, per-metric pass-rate structure the promotion gate reads.
    """

    status: Literal["succeeded", "failed"]
    summary_json: dict[str, Any]
    results: list[EvalResultCreate] = Field(default_factory=list)


class EvalRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    release_id: uuid.UUID
    dataset_id: uuid.UUID
    started_at: datetime
    finished_at: datetime | None
    status: EvalRunStatus
    summary_json: dict[str, Any] | None


class EvalResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    case_id: uuid.UUID
    metric_name: str
    metric_value: Decimal | None
    pass_fail: bool
    notes: dict[str, Any] | None
