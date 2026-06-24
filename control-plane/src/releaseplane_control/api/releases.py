"""Release routes: create, list, get.

A release binds an existing prompt version, model config, and policy bundle; a
dangling reference to any of the three is rejected with 422. The bundle is
immutable once created, so there is no update route for the three references;
only the stage moves, through the promote endpoint (T4). New releases start in
the draft stage.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from .. import models
from ..db import SessionDep
from ..schemas import ReleaseCreate, ReleaseRead

router = APIRouter(prefix="/releases", tags=["releases"])


@router.post("", response_model=ReleaseRead, status_code=status.HTTP_201_CREATED)
async def create_release(body: ReleaseCreate, session: SessionDep) -> models.Release:
    prompt_version = await session.get(models.PromptVersion, body.prompt_version_id)
    if prompt_version is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"unknown prompt_version_id: {body.prompt_version_id}",
        )
    model_config = await session.get(models.ModelConfig, body.model_config_id)
    if model_config is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"unknown model_config_id: {body.model_config_id}",
        )
    policy_bundle = await session.get(models.PolicyBundle, body.policy_bundle_id)
    if policy_bundle is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"unknown policy_bundle_id: {body.policy_bundle_id}",
        )
    obj = models.Release(**body.model_dump())
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj


@router.get("", response_model=list[ReleaseRead])
async def list_releases(session: SessionDep) -> Sequence[models.Release]:
    result = await session.scalars(select(models.Release).order_by(models.Release.created_at))
    return result.all()


@router.get("/{release_id}", response_model=ReleaseRead)
async def get_release(release_id: uuid.UUID, session: SessionDep) -> models.Release:
    obj = await session.get(models.Release, release_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "release not found")
    return obj
