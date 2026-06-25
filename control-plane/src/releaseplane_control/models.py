"""SQLAlchemy 2.0 models for the control-plane data model.

Shapes follow docs/ARCHITECTURE.md (the authoritative column source). The
model_configs table additionally carries name and the two cost-per-mtok columns:
the seed file infra/model_configs/v1_default.yaml and the cost probe both depend
on them, so they are stored rather than dropped on load. That deviation from the
terse column list in ARCHITECTURE.md is recorded in the doc itself.

Primary keys are UUIDs; releases.id doubles as the release_id audit key stamped
on every OTel span. The stage enum includes canary, which is reserved in the
data model but inert at v1 (no transition wires it).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class ReleaseStage(str, enum.Enum):
    """Release lifecycle stages per the ARCHITECTURE.md state diagram.

    canary is defined for the data model but inert at v1; no transition reaches
    it and no traffic-split logic is wired.
    """

    draft = "draft"
    candidate = "candidate"
    active = "active"
    rolled_back = "rolled_back"
    canary = "canary"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        Uuid(),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PromptDefinition(Base):
    __tablename__ = "prompt_definitions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    team: Mapped[str] = mapped_column(String, nullable=False)
    use_case: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = _created_at()


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("prompt_id", "version", name="uq_prompt_versions_prompt_version"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    prompt_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompt_definitions.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[str] = mapped_column(String, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    developer_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    variables_schema_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output_schema_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    tool_schema_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    checksum: Mapped[str] = mapped_column(String, nullable=False)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = _created_at()


class ModelConfig(Base):
    __tablename__ = "model_configs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model_name: Mapped[str] = mapped_column(String, nullable=False)
    model_version_pin: Mapped[str] = mapped_column(String, nullable=False)
    temperature: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    tool_mode: Mapped[str] = mapped_column(String, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    cost_per_mtok_input_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    cost_per_mtok_output_usd: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)


class PolicyBundle(Base):
    __tablename__ = "policy_bundles"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_policy_bundles_name_version"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[str] = mapped_column(String, nullable=False)
    rules_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    severity_mode: Mapped[str] = mapped_column(String, nullable=False)


class EvalRunStatus(str, enum.Enum):
    """Lifecycle of an eval run.

    The promotion gate requires the latest run to be succeeded; running and
    failed are both non-passing. Kept a Postgres enum so an out-of-range status
    cannot be written.
    """

    running = "running"
    succeeded = "succeeded"
    failed = "failed"


class EvalDataset(Base):
    """A named, versioned golden dataset (e.g. invoice_v1).

    Shapes follow docs/ARCHITECTURE.md > Data model (ingestion / eval). Unique by
    name so the loader is idempotent: reloading invoice_v1 finds the existing row
    rather than duplicating it.
    """

    __tablename__ = "eval_datasets"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    generator_seed: Mapped[int] = mapped_column(Integer, nullable=False)


class EvalCase(Base):
    """One golden case: the invoice input and its ground-truth extraction.

    input_path keeps the dataset-relative source artifact (e.g. case_14.pdf) for
    provenance; input_text carries the perfect-OCR rendering the runner feeds to
    the gateway as invoice_pdf_text. input_text is the one deviation from the
    terse column list in ARCHITECTURE.md (recorded in the doc): the runner needs
    the text inline, not a path to re-read. Unique by (dataset_id, input_path) so
    a reload upserts cases instead of duplicating them.
    """

    __tablename__ = "eval_cases"
    __table_args__ = (
        UniqueConstraint("dataset_id", "input_path", name="uq_eval_cases_dataset_path"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("eval_datasets.id", ondelete="CASCADE"), nullable=False
    )
    input_path: Mapped[str] = mapped_column(String, nullable=False)
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    expected_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class EvalRun(Base):
    """One scoring of a release over a dataset.

    summary_json holds the per-tier, per-metric pass rates the runner computes at
    finish time; the promotion gate reads it to enforce the Tier-1/Tier-2
    thresholds without re-aggregating the per-case rows. It is nullable while a
    run is in flight and the one deviation from the ARCHITECTURE.md sketch
    (recorded in the doc).
    """

    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    release_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("releases.id"), nullable=False)
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eval_datasets.id"), nullable=False)
    started_at: Mapped[datetime] = _created_at()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[EvalRunStatus] = mapped_column(
        SAEnum(
            EvalRunStatus,
            name="eval_run_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=EvalRunStatus.running,
    )
    summary_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class EvalResult(Base):
    """One metric outcome for one case in one run.

    Grain is (run, case, metric) per ARCHITECTURE.md, so a 30-case run over the
    three metrics writes 90 rows. metric_value carries the numeric score (1.0/0.0
    for the binary v1 metrics, room for fractional later); pass_fail is the gating
    boolean; notes is the scorer's per-case detail (expected vs got).
    """

    __tablename__ = "eval_results"

    id: Mapped[uuid.UUID] = _uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("eval_runs.id", ondelete="CASCADE"), nullable=False
    )
    case_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("eval_cases.id"), nullable=False)
    metric_name: Mapped[str] = mapped_column(String, nullable=False)
    metric_value: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    pass_fail: Mapped[bool] = mapped_column(Boolean, nullable=False)
    notes: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class Release(Base):
    __tablename__ = "releases"

    id: Mapped[uuid.UUID] = _uuid_pk()
    prompt_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompt_versions.id"), nullable=False
    )
    model_config_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_configs.id"), nullable=False
    )
    policy_bundle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("policy_bundles.id"), nullable=False
    )
    stage: Mapped[ReleaseStage] = mapped_column(
        SAEnum(ReleaseStage, name="release_stage", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ReleaseStage.draft,
    )
    rollout_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = _created_at()
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
