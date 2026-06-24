"""Prompt definition and prompt version routes.

Versions are nested under their prompt. On create the content checksum is
computed server-side and stored, so a version's content is verifiable and
immutable. A prompt's name and a (prompt, version) pair are each unique; a
collision returns 409.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .. import models
from ..db import SessionDep
from ..schemas import PromptCreate, PromptRead, PromptVersionCreate, PromptVersionRead
from ..services.checksum import compute_checksum

router = APIRouter(prefix="/prompts", tags=["prompts"])


@router.post("", response_model=PromptRead, status_code=status.HTTP_201_CREATED)
async def create_prompt(body: PromptCreate, session: SessionDep) -> models.PromptDefinition:
    obj = models.PromptDefinition(**body.model_dump())
    session.add(obj)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"prompt name already exists: {body.name}"
        ) from exc
    await session.refresh(obj)
    return obj


@router.get("", response_model=list[PromptRead])
async def list_prompts(session: SessionDep) -> Sequence[models.PromptDefinition]:
    result = await session.scalars(
        select(models.PromptDefinition).order_by(models.PromptDefinition.created_at)
    )
    return result.all()


@router.get("/{prompt_id}", response_model=PromptRead)
async def get_prompt(prompt_id: uuid.UUID, session: SessionDep) -> models.PromptDefinition:
    obj = await session.get(models.PromptDefinition, prompt_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "prompt not found")
    return obj


@router.post(
    "/{prompt_id}/versions",
    response_model=PromptVersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_version(
    prompt_id: uuid.UUID, body: PromptVersionCreate, session: SessionDep
) -> models.PromptVersion:
    prompt = await session.get(models.PromptDefinition, prompt_id)
    if prompt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "prompt not found")
    checksum = compute_checksum(
        system_prompt=body.system_prompt,
        developer_prompt=body.developer_prompt,
        variables_schema_json=body.variables_schema_json,
        output_schema_json=body.output_schema_json,
        tool_schema_json=body.tool_schema_json,
    )
    obj = models.PromptVersion(prompt_id=prompt_id, checksum=checksum, **body.model_dump())
    session.add(obj)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"version already exists for this prompt: {body.version}"
        ) from exc
    await session.refresh(obj)
    return obj


@router.get("/{prompt_id}/versions", response_model=list[PromptVersionRead])
async def list_versions(
    prompt_id: uuid.UUID, session: SessionDep
) -> Sequence[models.PromptVersion]:
    prompt = await session.get(models.PromptDefinition, prompt_id)
    if prompt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "prompt not found")
    result = await session.scalars(
        select(models.PromptVersion)
        .where(models.PromptVersion.prompt_id == prompt_id)
        .order_by(models.PromptVersion.created_at)
    )
    return result.all()


@router.get("/{prompt_id}/versions/{version_id}", response_model=PromptVersionRead)
async def get_version(
    prompt_id: uuid.UUID, version_id: uuid.UUID, session: SessionDep
) -> models.PromptVersion:
    obj = await session.get(models.PromptVersion, version_id)
    if obj is None or obj.prompt_id != prompt_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "prompt version not found")
    return obj
