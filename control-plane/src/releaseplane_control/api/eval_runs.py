"""Eval run routes: open a run, complete it with results, and read back.

The evals runner orchestrates the scoring (it drives the gateway per case and
runs the metric scorers), so these routes are pure persistence. A run opens in
the running state, then a single complete call writes all results and stamps the
terminal status, finished_at, and the per-tier summary the promotion gate reads.
A run can only be completed once.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..db import SessionDep
from ..models import EvalRunStatus
from ..schemas import EvalResultRead, EvalRunComplete, EvalRunCreate, EvalRunRead

router = APIRouter(prefix="/eval-runs", tags=["eval-runs"])


async def _require_run(session: AsyncSession, run_id: uuid.UUID) -> models.EvalRun:
    run = await session.get(models.EvalRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "eval run not found")
    return run


@router.post("", response_model=EvalRunRead, status_code=status.HTTP_201_CREATED)
async def create_eval_run(body: EvalRunCreate, session: SessionDep) -> models.EvalRun:
    if await session.get(models.Release, body.release_id) is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown release_id: {body.release_id}"
        )
    if await session.get(models.EvalDataset, body.dataset_id) is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown dataset_id: {body.dataset_id}"
        )
    run = models.EvalRun(
        release_id=body.release_id,
        dataset_id=body.dataset_id,
        status=EvalRunStatus.running,
    )
    session.add(run)
    await session.commit()
    await session.refresh(run)
    return run


@router.post("/{run_id}/complete", response_model=EvalRunRead)
async def complete_eval_run(
    run_id: uuid.UUID, body: EvalRunComplete, session: SessionDep
) -> models.EvalRun:
    run = await _require_run(session, run_id)
    if run.status is not EvalRunStatus.running:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"eval run already completed: {run.status.value}"
        )
    for result in body.results:
        session.add(
            models.EvalResult(
                run_id=run_id,
                case_id=result.case_id,
                metric_name=result.metric_name,
                metric_value=result.metric_value,
                pass_fail=result.pass_fail,
                notes=result.notes,
            )
        )
    run.status = EvalRunStatus(body.status)
    run.finished_at = datetime.now(UTC)
    run.summary_json = body.summary_json
    await session.commit()
    await session.refresh(run)
    return run


@router.get("", response_model=list[EvalRunRead])
async def list_eval_runs(
    session: SessionDep, release_id: uuid.UUID | None = None
) -> Sequence[models.EvalRun]:
    stmt = select(models.EvalRun).order_by(models.EvalRun.started_at.desc())
    if release_id is not None:
        stmt = stmt.where(models.EvalRun.release_id == release_id)
    result = await session.scalars(stmt)
    return result.all()


@router.get("/{run_id}", response_model=EvalRunRead)
async def get_eval_run(run_id: uuid.UUID, session: SessionDep) -> models.EvalRun:
    return await _require_run(session, run_id)


@router.get("/{run_id}/results", response_model=list[EvalResultRead])
async def list_eval_results(run_id: uuid.UUID, session: SessionDep) -> Sequence[models.EvalResult]:
    await _require_run(session, run_id)
    stmt = (
        select(models.EvalResult)
        .where(models.EvalResult.run_id == run_id)
        .order_by(models.EvalResult.case_id, models.EvalResult.metric_name)
    )
    result = await session.scalars(stmt)
    return result.all()
