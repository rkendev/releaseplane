"""Eval dataset routes: load (idempotent) and read.

The load endpoint persists a dataset plus all of its cases in one transaction.
It is idempotent by dataset name and by (dataset_id, input_path) per case, so a
reload returns 200 with cases_created 0 rather than duplicating rows. The runner
reads cases back through GET /eval-datasets/{id}/cases.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from .. import models
from ..db import SessionDep
from ..schemas import EvalCaseRead, EvalDatasetCreate, EvalDatasetLoadResult, EvalDatasetRead
from ..services.eval_dataset import load_dataset

router = APIRouter(prefix="/eval-datasets", tags=["eval-datasets"])


@router.post("", response_model=EvalDatasetLoadResult)
async def load(
    body: EvalDatasetCreate, session: SessionDep, response: Response
) -> EvalDatasetLoadResult:
    outcome = await load_dataset(session, body)
    response.status_code = (
        status.HTTP_201_CREATED if outcome.created_dataset else status.HTTP_200_OK
    )
    return EvalDatasetLoadResult(
        dataset=EvalDatasetRead.model_validate(outcome.dataset),
        cases_total=outcome.cases_total,
        cases_created=outcome.cases_created,
    )


@router.get("", response_model=list[EvalDatasetRead])
async def list_datasets(session: SessionDep) -> Sequence[models.EvalDataset]:
    result = await session.scalars(select(models.EvalDataset).order_by(models.EvalDataset.name))
    return result.all()


@router.get("/{dataset_id}", response_model=EvalDatasetRead)
async def get_dataset(dataset_id: uuid.UUID, session: SessionDep) -> models.EvalDataset:
    obj = await session.get(models.EvalDataset, dataset_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "eval dataset not found")
    return obj


@router.get("/{dataset_id}/cases", response_model=list[EvalCaseRead])
async def list_cases(dataset_id: uuid.UUID, session: SessionDep) -> Sequence[models.EvalCase]:
    if await session.get(models.EvalDataset, dataset_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "eval dataset not found")
    stmt = (
        select(models.EvalCase)
        .where(models.EvalCase.dataset_id == dataset_id)
        .order_by(models.EvalCase.input_path)
    )
    result = await session.scalars(stmt)
    return result.all()
