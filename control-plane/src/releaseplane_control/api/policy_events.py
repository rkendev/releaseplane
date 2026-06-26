"""Policy event routes.

The gateway records one event per policy-check failure on an /invoke request; the
dashboard and the demo read them back. Events are append-only (no update/delete).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from .. import models
from ..db import SessionDep
from ..schemas import PolicyEventCreate, PolicyEventRead

router = APIRouter(prefix="/policy-events", tags=["policy-events"])


@router.post("", response_model=PolicyEventRead, status_code=status.HTTP_201_CREATED)
async def create_policy_event(body: PolicyEventCreate, session: SessionDep) -> models.PolicyEvent:
    obj = models.PolicyEvent(**body.model_dump())
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return obj


@router.get("", response_model=list[PolicyEventRead])
async def list_policy_events(
    session: SessionDep, request_id: Annotated[uuid.UUID | None, Query()] = None
) -> Sequence[models.PolicyEvent]:
    stmt = select(models.PolicyEvent)
    if request_id is not None:
        stmt = stmt.where(models.PolicyEvent.request_id == request_id)
    stmt = stmt.order_by(models.PolicyEvent.created_at)
    result = await session.scalars(stmt)
    return result.all()
