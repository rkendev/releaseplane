"""Load a golden dataset and its cases, idempotently.

The eval CLI builds the payload from the generator and posts it here, so the
control plane persists the dataset without importing the generator or examples
packages. Idempotent on two keys: the dataset by name, and each case by
(dataset_id, input_path). A reload updates the dataset metadata, inserts only the
cases that are missing, and leaves existing rows untouched, so it doubles as a
self-heal for a partially loaded dataset.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import models
from ..schemas import EvalDatasetCreate


@dataclass(frozen=True)
class LoadOutcome:
    dataset: models.EvalDataset
    created_dataset: bool
    cases_total: int
    cases_created: int


async def load_dataset(session: AsyncSession, payload: EvalDatasetCreate) -> LoadOutcome:
    """Upsert the dataset and insert any missing cases. Returns the outcome."""
    dataset = await session.scalar(
        select(models.EvalDataset).where(models.EvalDataset.name == payload.name)
    )
    created_dataset = dataset is None
    if dataset is None:
        dataset = models.EvalDataset(
            name=payload.name,
            domain=payload.domain,
            source=payload.source,
            row_count=len(payload.cases),
            generator_seed=payload.generator_seed,
        )
        session.add(dataset)
        await session.flush()
    else:
        dataset.domain = payload.domain
        dataset.source = payload.source
        dataset.generator_seed = payload.generator_seed
        dataset.row_count = len(payload.cases)

    existing_paths = set(
        await session.scalars(
            select(models.EvalCase.input_path).where(models.EvalCase.dataset_id == dataset.id)
        )
    )
    cases_created = 0
    for case in payload.cases:
        if case.input_path in existing_paths:
            continue
        session.add(models.EvalCase(dataset_id=dataset.id, **case.model_dump()))
        cases_created += 1

    await session.commit()
    await session.refresh(dataset)
    return LoadOutcome(
        dataset=dataset,
        created_dataset=created_dataset,
        cases_total=len(payload.cases),
        cases_created=cases_created,
    )
