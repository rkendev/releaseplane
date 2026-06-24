"""Model config routes plus a seed endpoint.

The seed endpoint loads the first model config from
infra/model_configs/v1_default.yaml (path configurable via MODEL_CONFIG_SEED_PATH)
and is idempotent by name: re-running it returns the existing row with 200.
Config names are unique; a collision on create returns 409.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .. import models
from ..db import SessionDep
from ..schemas import ModelConfigCreate, ModelConfigRead
from ..services.seed import seed_model_config, seed_path

router = APIRouter(prefix="/model-configs", tags=["model-configs"])


@router.post("", response_model=ModelConfigRead, status_code=status.HTTP_201_CREATED)
async def create_model_config(body: ModelConfigCreate, session: SessionDep) -> models.ModelConfig:
    obj = models.ModelConfig(**body.model_dump())
    session.add(obj)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"model config name already exists: {body.name}"
        ) from exc
    await session.refresh(obj)
    return obj


@router.post("/seed", response_model=ModelConfigRead)
async def seed(session: SessionDep, response: Response) -> models.ModelConfig:
    path = seed_path()
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"seed file not found: {path}")
    obj, created = await seed_model_config(session, path)
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return obj


@router.get("", response_model=list[ModelConfigRead])
async def list_model_configs(session: SessionDep) -> Sequence[models.ModelConfig]:
    result = await session.scalars(select(models.ModelConfig).order_by(models.ModelConfig.name))
    return result.all()


@router.get("/{model_config_id}", response_model=ModelConfigRead)
async def get_model_config(model_config_id: uuid.UUID, session: SessionDep) -> models.ModelConfig:
    obj = await session.get(models.ModelConfig, model_config_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "model config not found")
    return obj
