"""Tests for the Pydantic API schemas. No database."""

from __future__ import annotations

import uuid
import warnings
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from releaseplane_control.schemas import (
    ModelConfigCreate,
    PromptCreate,
    PromptRead,
    ReleaseCreate,
)


def test_prompt_create_rejects_blank_name() -> None:
    with pytest.raises(ValidationError):
        PromptCreate(name="", team="t", use_case="u")


def test_prompt_read_from_attributes() -> None:
    obj = SimpleNamespace(
        id=uuid.uuid4(), name="n", team="t", use_case="u", created_at=datetime.now(UTC)
    )
    read = PromptRead.model_validate(obj)
    assert read.name == "n"


def test_model_config_allows_model_prefixed_fields_without_warning() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        cfg = ModelConfigCreate(
            name="v1_default",
            provider="claude",
            model_name="claude-sonnet-4-6",
            model_version_pin="claude-sonnet-4-6",
            temperature="0.0",
            max_tokens=4096,
            timeout_ms=30000,
            tool_mode="structured_output",
            cost_per_mtok_input_usd="3.00",
            cost_per_mtok_output_usd="15.00",
        )
    assert cfg.model_name == "claude-sonnet-4-6"
    assert cfg.active is False


def test_release_create_rollout_percent_bounds() -> None:
    ids = {
        "prompt_version_id": uuid.uuid4(),
        "model_config_id": uuid.uuid4(),
        "policy_bundle_id": uuid.uuid4(),
    }
    assert ReleaseCreate(**ids).rollout_percent is None
    with pytest.raises(ValidationError):
        ReleaseCreate(**ids, rollout_percent=150)
