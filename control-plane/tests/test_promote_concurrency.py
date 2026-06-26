"""The one-active invariant under concurrent promotes. Requires Postgres.

Two releases of the same prompt are promoted to active at the same time over
separate sessions. The prompt-scoped advisory lock in promote_release serializes
the archive-and-activate, so exactly one release ends up active and unarchived.
Without the lock both archive-scans would see no committed active release and both
would activate, leaving two.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

DATABASE_URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="integration test needs Postgres")

VERSION_BASE = {
    "variables_schema_json": {"type": "object"},
    "output_schema_json": {"type": "object"},
    "created_by": "tester",
}


def _make_app() -> Any:
    from releaseplane_control import models  # noqa: F401  (register tables)
    from releaseplane_control.app import app as cp_app
    from releaseplane_control.db import make_engine, make_sessionmaker

    engine = make_engine(DATABASE_URL or "")
    cp_app.state.engine = engine
    cp_app.state.sessionmaker = make_sessionmaker(engine)
    cp_app.state.db_ok = True
    return cp_app, engine


async def _create_schema(engine: Any) -> None:
    from releaseplane_control.db import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _seed_two_candidate_releases(cp: httpx.AsyncClient) -> tuple[str, list[str]]:
    """One prompt, two versions, two releases, both promoted to candidate."""
    mc = (
        await cp.post(
            "/model-configs",
            json={
                "name": f"mc-{uuid.uuid4().hex[:10]}",
                "provider": "claude",
                "model_name": "claude-sonnet-4-6",
                "model_version_pin": "claude-sonnet-4-6",
                "temperature": 0.0,
                "max_tokens": 4096,
                "timeout_ms": 30000,
                "tool_mode": "structured_output",
                "active": True,
                "cost_per_mtok_input_usd": 3.00,
                "cost_per_mtok_output_usd": 15.00,
            },
        )
    ).json()
    pb = (
        await cp.post(
            "/policy-bundles",
            json={
                "name": f"pb-{uuid.uuid4().hex[:10]}",
                "version": "v1",
                "rules_json": {},
                "severity_mode": "monitor",
            },
        )
    ).json()
    prompt = (
        await cp.post(
            "/prompts",
            json={"name": f"p-{uuid.uuid4().hex[:10]}", "team": "ap", "use_case": "x"},
        )
    ).json()

    release_ids: list[str] = []
    for version in ("v1", "v2"):
        ver = (
            await cp.post(
                f"/prompts/{prompt['id']}/versions",
                json={
                    "version": version,
                    "system_prompt": f"s-{version}",
                    "developer_prompt": f"d-{version}",
                    **VERSION_BASE,
                },
            )
        ).json()
        rel = (
            await cp.post(
                "/releases",
                json={
                    "prompt_version_id": ver["id"],
                    "model_config_id": mc["id"],
                    "policy_bundle_id": pb["id"],
                },
            )
        ).json()
        await cp.post(f"/releases/{rel['id']}/promote")  # draft -> candidate
        release_ids.append(rel["id"])
    return prompt["id"], release_ids


async def _count_active_unarchived(engine: Any, prompt_id: str) -> int:
    from releaseplane_control import models
    from releaseplane_control.db import make_sessionmaker
    from releaseplane_control.models import ReleaseStage

    sessionmaker = make_sessionmaker(engine)
    async with sessionmaker() as session:
        stmt = (
            select(func.count())
            .select_from(models.Release)
            .join(models.PromptVersion, models.Release.prompt_version_id == models.PromptVersion.id)
            .where(
                models.PromptVersion.prompt_id == uuid.UUID(prompt_id),
                models.Release.stage == ReleaseStage.active,
                models.Release.archived_at.is_(None),
            )
        )
        return int((await session.execute(stmt)).scalar_one())


def test_concurrent_promotes_leave_one_active(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVAL_GATE_ENFORCED", "false")

    async def run() -> int:
        cp_app, engine = _make_app()
        await _create_schema(engine)
        try:
            transport = httpx.ASGITransport(app=cp_app)
            async with httpx.AsyncClient(transport=transport, base_url="http://cp") as cp:
                prompt_id, release_ids = await _seed_two_candidate_releases(cp)
                # Promote both candidate releases to active at the same time.
                responses = await asyncio.gather(
                    *(cp.post(f"/releases/{rid}/promote") for rid in release_ids)
                )
                assert all(r.status_code == 200 for r in responses)
                return await _count_active_unarchived(engine, prompt_id)
        finally:
            await engine.dispose()

    assert asyncio.run(run()) == 1
