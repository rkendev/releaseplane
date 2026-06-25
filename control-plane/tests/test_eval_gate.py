"""Tests for the eval gate.

The threshold check is pure and tested without a database. The full gate (latest
run lookup, status, staleness, thresholds) is tested against Postgres with seeded
eval-run rows, so it needs DATABASE_URL.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from releaseplane_control import models
from releaseplane_control.db import make_engine, make_sessionmaker
from releaseplane_control.models import EvalRunStatus, ReleaseStage
from releaseplane_control.services.eval_gate import check_thresholds, eval_gate_ok

DATABASE_URL = os.environ.get("DATABASE_URL")


# --- pure threshold check ---------------------------------------------------


def _summary(t1: tuple[float, float, float], t2: tuple[float, float, float]) -> dict:
    def tier(schema: float, arith: float, checksum: float) -> dict:
        return {
            "count": 10,
            "schema_validity": {"rate": schema},
            "arithmetic_consistency": {"rate": arith},
            "checksum_match": {"rate": checksum},
        }

    return {"tiers": {"1": tier(*t1), "2": tier(*t2), "3": tier(0.5, 0.5, 0.5)}}


def test_thresholds_pass_when_all_met() -> None:
    summary = _summary((1.0, 1.0, 1.0), (1.0, 1.0, 0.8))
    assert check_thresholds(summary).ok


def test_tier1_checksum_below_100_blocks() -> None:
    result = check_thresholds(_summary((1.0, 1.0, 0.9), (1.0, 1.0, 1.0)))
    assert not result.ok
    assert "tier 1 checksum_match" in result.reason


def test_tier2_checksum_at_80_passes_but_below_blocks() -> None:
    assert check_thresholds(_summary((1.0, 1.0, 1.0), (1.0, 1.0, 0.8))).ok
    blocked = check_thresholds(_summary((1.0, 1.0, 1.0), (1.0, 1.0, 0.7)))
    assert not blocked.ok
    assert "tier 2 checksum_match" in blocked.reason


def test_tier3_failure_does_not_block() -> None:
    # Tier 3 is all zeros in _summary; the gate ignores it.
    assert check_thresholds(_summary((1.0, 1.0, 1.0), (1.0, 1.0, 1.0))).ok


def test_missing_summary_blocks() -> None:
    assert not check_thresholds(None).ok
    assert not check_thresholds({}).ok


# --- full gate against the database -----------------------------------------

pg = pytest.mark.skipif(not DATABASE_URL, reason="integration test needs Postgres")


async def _session() -> tuple[object, object]:
    engine = make_engine(DATABASE_URL or "")
    from releaseplane_control.db import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, make_sessionmaker(engine)


async def _release_with_run(
    session: object,
    *,
    status: EvalRunStatus,
    summary: dict | None,
    finished_offset: timedelta | None,
) -> models.Release:
    """Seed a minimal release plus one eval run; return the release.

    The release references real foreign keys (prompt version, model config, policy
    bundle) so it can be inserted; the gate only needs its id.
    """
    prompt = models.PromptDefinition(name=f"p-{uuid.uuid4().hex[:8]}", team="ap", use_case="x")
    session.add(prompt)
    await session.flush()
    version = models.PromptVersion(
        prompt_id=prompt.id,
        version="v1",
        system_prompt="s",
        developer_prompt="d",
        variables_schema_json={},
        output_schema_json={},
        status="draft",
        checksum="c",
        created_by="t",
    )
    mc = models.ModelConfig(
        name=f"mc-{uuid.uuid4().hex[:8]}",
        provider="claude",
        model_name="m",
        model_version_pin="m",
        temperature=0,
        max_tokens=1,
        timeout_ms=1,
        tool_mode="structured_output",
        cost_per_mtok_input_usd=0,
        cost_per_mtok_output_usd=0,
    )
    pb = models.PolicyBundle(
        name=f"pb-{uuid.uuid4().hex[:8]}", version="v1", rules_json={}, severity_mode="warn"
    )
    session.add_all([version, mc, pb])
    await session.flush()
    release = models.Release(
        prompt_version_id=version.id, model_config_id=mc.id, policy_bundle_id=pb.id
    )
    dataset = models.EvalDataset(
        name=f"ds-{uuid.uuid4().hex[:8]}", domain="x", source="x", row_count=0, generator_seed=0
    )
    session.add_all([release, dataset])
    await session.flush()
    finished = None if finished_offset is None else datetime.now(UTC) - finished_offset
    run = models.EvalRun(
        release_id=release.id,
        dataset_id=dataset.id,
        status=status,
        finished_at=finished,
        summary_json=summary,
    )
    session.add(run)
    await session.flush()
    return release


_FRESH = timedelta(hours=1)
_STALE = timedelta(hours=48)
_PASS = {
    "tiers": {
        "1": {
            "count": 10,
            "schema_validity": {"rate": 1.0},
            "arithmetic_consistency": {"rate": 1.0},
            "checksum_match": {"rate": 1.0},
        },
        "2": {
            "count": 10,
            "schema_validity": {"rate": 1.0},
            "arithmetic_consistency": {"rate": 1.0},
            "checksum_match": {"rate": 1.0},
        },
    }
}


@pg
@pytest.mark.asyncio
async def test_gate_bypassed_when_not_enforced() -> None:
    engine, sm = await _session()
    try:
        async with sm() as session:
            release = models.Release()
            result = await eval_gate_ok(session, release, ReleaseStage.candidate, enforced=False)
            assert result.ok
    finally:
        await engine.dispose()


@pg
@pytest.mark.asyncio
async def test_gate_blocks_with_no_run() -> None:
    engine, sm = await _session()
    try:
        async with sm() as session:
            release = models.Release(id=uuid.uuid4())
            result = await eval_gate_ok(session, release, ReleaseStage.candidate, enforced=True)
            assert not result.ok
            assert "no eval run" in result.reason
    finally:
        await engine.dispose()


@pg
@pytest.mark.asyncio
async def test_gate_blocks_incomplete_run() -> None:
    engine, sm = await _session()
    try:
        async with sm() as session:
            release = await _release_with_run(
                session, status=EvalRunStatus.running, summary=_PASS, finished_offset=None
            )
            result = await eval_gate_ok(session, release, ReleaseStage.candidate, enforced=True)
            assert not result.ok
            assert "did not complete" in result.reason
    finally:
        await engine.dispose()


@pg
@pytest.mark.asyncio
async def test_gate_blocks_stale_run() -> None:
    engine, sm = await _session()
    try:
        async with sm() as session:
            release = await _release_with_run(
                session, status=EvalRunStatus.succeeded, summary=_PASS, finished_offset=_STALE
            )
            result = await eval_gate_ok(session, release, ReleaseStage.candidate, enforced=True)
            assert not result.ok
            assert "stale" in result.reason
    finally:
        await engine.dispose()


@pg
@pytest.mark.asyncio
async def test_gate_blocks_failing_thresholds() -> None:
    engine, sm = await _session()
    try:
        failing = _summary((1.0, 1.0, 1.0), (1.0, 0.9, 1.0))
        async with sm() as session:
            release = await _release_with_run(
                session, status=EvalRunStatus.succeeded, summary=failing, finished_offset=_FRESH
            )
            result = await eval_gate_ok(session, release, ReleaseStage.candidate, enforced=True)
            assert not result.ok
            assert "tier 2 arithmetic_consistency" in result.reason
    finally:
        await engine.dispose()


@pg
@pytest.mark.asyncio
async def test_gate_allows_fresh_passing_run() -> None:
    engine, sm = await _session()
    try:
        async with sm() as session:
            release = await _release_with_run(
                session, status=EvalRunStatus.succeeded, summary=_PASS, finished_offset=_FRESH
            )
            result = await eval_gate_ok(session, release, ReleaseStage.active, enforced=True)
            assert result.ok
    finally:
        await engine.dispose()
