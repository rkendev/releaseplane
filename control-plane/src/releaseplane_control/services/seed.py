"""Seed the first model_configs row from infra/model_configs/v1_default.yaml.

The YAML carries exactly the model_configs fields (provider, model_name, the
version pin, cost-per-mtok rates, and so on), so it validates straight into the
ModelConfigCreate schema. Seeding is idempotent by name: if a config with the
seed's name already exists it is returned unchanged. The path is resolved from
MODEL_CONFIG_SEED_PATH, defaulting to the repo-relative location.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..schemas import ModelConfigCreate

DEFAULT_SEED_PATH = Path("infra/model_configs/v1_default.yaml")


def seed_path() -> Path:
    """Resolve the seed file path from the environment or the default."""
    return Path(os.environ.get("MODEL_CONFIG_SEED_PATH", str(DEFAULT_SEED_PATH)))


def load_model_config_seed(path: Path) -> ModelConfigCreate:
    """Read and validate the seed YAML into a ModelConfigCreate."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ModelConfigCreate.model_validate(data)


async def seed_model_config(session: AsyncSession, path: Path) -> tuple[models.ModelConfig, bool]:
    """Insert the seed model config if absent. Returns (row, created)."""
    payload = load_model_config_seed(path)
    existing = await session.scalar(
        select(models.ModelConfig).where(models.ModelConfig.name == payload.name)
    )
    if existing is not None:
        return existing, False
    obj = models.ModelConfig(**payload.model_dump())
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj, True
