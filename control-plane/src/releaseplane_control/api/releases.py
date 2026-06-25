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
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import ColumnElement, Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..db import SessionDep
from ..models import ReleaseStage
from ..schemas import ModelConfigRead, ReleaseCreate, ReleaseRead, ResolvedReleaseRead
from ..services.eval_gate import eval_gate_ok
from ..services.state_machine import next_promote_stage

router = APIRouter(prefix="/releases", tags=["releases"])


def _active_unarchived() -> list[ColumnElement[bool]]:
    """The canonical 'currently serving' predicate, shared to avoid drift.

    A release is the live one for its prompt when it is in the active stage and
    has not been archived by a later promotion. Both the resolve endpoint and the
    supersede step filter on exactly this pair.
    """
    return [
        models.Release.stage == ReleaseStage.active,
        models.Release.archived_at.is_(None),
    ]


async def _archive_prior_active(session: AsyncSession, release: models.Release) -> None:
    """Archive any other active, unarchived release for the same prompt.

    Enforces one active release per prompt: the locked releases table has no
    prompt_id or environment column, so this resolves the prompt through the
    prompt version and stamps archived_at on the prior active release.
    """
    prompt_version = await session.get(models.PromptVersion, release.prompt_version_id)
    if prompt_version is None:
        return
    now = datetime.now(UTC)
    stmt = (
        select(models.Release)
        .join(models.PromptVersion, models.Release.prompt_version_id == models.PromptVersion.id)
        .where(
            *_active_unarchived(),
            models.PromptVersion.prompt_id == prompt_version.prompt_id,
            models.Release.id != release.id,
        )
    )
    for prior in (await session.scalars(stmt)).all():
        prior.archived_at = now


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


def _resolve_select() -> (
    Select[tuple[models.Release, models.PromptVersion, models.PromptDefinition, models.ModelConfig]]
):
    """Join a release to its prompt version, definition, and model config."""
    return (
        select(models.Release, models.PromptVersion, models.PromptDefinition, models.ModelConfig)
        .join(models.PromptVersion, models.Release.prompt_version_id == models.PromptVersion.id)
        .join(
            models.PromptDefinition,
            models.PromptVersion.prompt_id == models.PromptDefinition.id,
        )
        .join(models.ModelConfig, models.Release.model_config_id == models.ModelConfig.id)
    )


def _compose_resolved(
    release: models.Release,
    version: models.PromptVersion,
    definition: models.PromptDefinition,
    model_config: models.ModelConfig,
) -> ResolvedReleaseRead:
    return ResolvedReleaseRead(
        release_id=release.id,
        prompt_version_id=version.id,
        prompt_name=definition.name,
        use_case=definition.use_case,
        system_prompt=version.system_prompt,
        developer_prompt=version.developer_prompt,
        variables_schema_json=version.variables_schema_json,
        output_schema_json=version.output_schema_json,
        model=ModelConfigRead.model_validate(model_config),
    )


@router.get("/active", response_model=ResolvedReleaseRead)
async def resolve_active_release(prompt_name: str, session: SessionDep) -> ResolvedReleaseRead:
    """Resolve the single active release for a prompt name (404 if none).

    Declared before /{release_id} so the literal path is not parsed as a UUID.
    Filtered by the canonical active-and-unarchived predicate, so the execution
    plane gets everything it needs to render and call in one response.
    """
    stmt = _resolve_select().where(
        *_active_unarchived(), models.PromptDefinition.name == prompt_name
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"no active release for prompt {prompt_name!r}"
        )
    release, version, definition, model_config = row
    return _compose_resolved(release, version, definition, model_config)


@router.get("/{release_id}/resolved", response_model=ResolvedReleaseRead)
async def resolve_release_by_id(release_id: uuid.UUID, session: SessionDep) -> ResolvedReleaseRead:
    """Resolve a specific release by id, regardless of stage (the /invoke override).

    Unlike the active resolver this applies no stage filter: an operator pinning a
    release_id is choosing it explicitly, including a draft or candidate.
    """
    stmt = _resolve_select().where(models.Release.id == release_id)
    row = (await session.execute(stmt)).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no release with id {release_id}")
    release, version, definition, model_config = row
    return _compose_resolved(release, version, definition, model_config)


@router.get("/{release_id}", response_model=ReleaseRead)
async def get_release(release_id: uuid.UUID, session: SessionDep) -> models.Release:
    obj = await session.get(models.Release, release_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "release not found")
    return obj


@router.post("/{release_id}/promote", response_model=ReleaseRead)
async def promote_release(release_id: uuid.UUID, session: SessionDep) -> models.Release:
    """Advance a release one hop along the forward promotion path.

    Enforces the structural rules now: a legal forward transition must exist, the
    release must reference a valid model config, immutability is preserved (only
    the stage moves), and entering active supersedes the prior active release.
    The eval-gate check is the Phase 4 seam, bypassed by default in Phase 2.
    """
    release = await session.get(models.Release, release_id)
    if release is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "release not found")

    target = next_promote_stage(release.stage)
    if target is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"cannot promote a release in stage {release.stage.value}",
        )

    model_config = await session.get(models.ModelConfig, release.model_config_id)
    if model_config is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "release does not reference a valid model config"
        )

    gate = eval_gate_ok(release, target)
    if not gate.ok:
        raise HTTPException(status.HTTP_409_CONFLICT, f"promotion blocked: {gate.reason}")

    if target is ReleaseStage.active:
        await _archive_prior_active(session, release)
        release.activated_at = datetime.now(UTC)
    release.stage = target

    await session.commit()
    await session.refresh(release)
    return release
