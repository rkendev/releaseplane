"""Routing rule routes.

A rule carries a single restricted predicate validated by RoutingRulePredicate;
the predicate is stored as JSONB and re-parsed on read. The target model config
must exist (a dangling reference is 422, mirroring the releases route). The
gateway reads these on /invoke only, ordered by priority ascending.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from .. import models
from ..db import SessionDep
from ..schemas import RoutingRuleCreate, RoutingRulePredicate, RoutingRuleRead

router = APIRouter(prefix="/routing-rules", tags=["routing-rules"])


def _to_read(obj: models.RoutingRule) -> RoutingRuleRead:
    return RoutingRuleRead(
        id=obj.id,
        use_case=obj.use_case,
        predicate=RoutingRulePredicate.model_validate(obj.predicate_json),
        target_model_config_id=obj.target_model_config_id,
        priority=obj.priority,
        created_at=obj.created_at,
    )


@router.post("", response_model=RoutingRuleRead, status_code=status.HTTP_201_CREATED)
async def create_routing_rule(body: RoutingRuleCreate, session: SessionDep) -> RoutingRuleRead:
    target = await session.get(models.ModelConfig, body.target_model_config_id)
    if target is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"target model config does not exist: {body.target_model_config_id}",
        )
    obj = models.RoutingRule(
        use_case=body.use_case,
        predicate_json=body.predicate.model_dump(mode="json"),
        target_model_config_id=body.target_model_config_id,
        priority=body.priority,
    )
    session.add(obj)
    await session.commit()
    await session.refresh(obj)
    return _to_read(obj)


@router.get("", response_model=list[RoutingRuleRead])
async def list_routing_rules(
    session: SessionDep, use_case: str | None = Query(default=None)
) -> Sequence[RoutingRuleRead]:
    stmt = select(models.RoutingRule)
    if use_case is not None:
        stmt = stmt.where(models.RoutingRule.use_case == use_case)
    stmt = stmt.order_by(models.RoutingRule.priority, models.RoutingRule.created_at)
    result = await session.scalars(stmt)
    return [_to_read(obj) for obj in result.all()]


@router.get("/{routing_rule_id}", response_model=RoutingRuleRead)
async def get_routing_rule(routing_rule_id: uuid.UUID, session: SessionDep) -> RoutingRuleRead:
    obj = await session.get(models.RoutingRule, routing_rule_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "routing rule not found")
    return _to_read(obj)
