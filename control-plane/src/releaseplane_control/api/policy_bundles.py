"""Policy bundle routes. A (name, version) pair is unique; a collision is 409."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .. import models
from ..db import SessionDep
from ..schemas import PolicyBundleCreate, PolicyBundleRead

router = APIRouter(prefix="/policy-bundles", tags=["policy-bundles"])


@router.post("", response_model=PolicyBundleRead, status_code=status.HTTP_201_CREATED)
async def create_policy_bundle(
    body: PolicyBundleCreate, session: SessionDep
) -> models.PolicyBundle:
    obj = models.PolicyBundle(**body.model_dump())
    session.add(obj)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"policy bundle already exists: {body.name} {body.version}",
        ) from exc
    await session.refresh(obj)
    return obj


@router.get("", response_model=list[PolicyBundleRead])
async def list_policy_bundles(session: SessionDep) -> Sequence[models.PolicyBundle]:
    result = await session.scalars(
        select(models.PolicyBundle).order_by(models.PolicyBundle.name, models.PolicyBundle.version)
    )
    return result.all()


@router.get("/{policy_bundle_id}", response_model=PolicyBundleRead)
async def get_policy_bundle(
    policy_bundle_id: uuid.UUID, session: SessionDep
) -> models.PolicyBundle:
    obj = await session.get(models.PolicyBundle, policy_bundle_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "policy bundle not found")
    return obj
