"""Structural promote guards that do not need a database.

The "release must reference a valid model config" guard cannot be reached over
HTTP (the foreign key plus the absence of a delete route make a dangling
reference unreachable), so it is exercised here with a stub session. The
immutability of a release's reference bundle is enforced by the absence of any
update route, which the second test asserts.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi import HTTPException
from releaseplane_control import models
from releaseplane_control.api.releases import promote_release
from releaseplane_control.app import app


class _StubSession:
    """Returns a draft release but no model config, to hit the guard branch."""

    def __init__(self, release: models.Release) -> None:
        self._release = release

    async def get(self, model: type[Any], pk: Any) -> Any:
        if model is models.Release:
            return self._release
        return None


@pytest.mark.asyncio
async def test_promote_rejects_unresolvable_model_config() -> None:
    release = models.Release()
    release.stage = models.ReleaseStage.draft
    release.model_config_id = uuid.uuid4()
    with pytest.raises(HTTPException) as exc:
        await promote_release(uuid.uuid4(), _StubSession(release))  # type: ignore[arg-type]
    assert exc.value.status_code == 409
    assert "valid model config" in exc.value.detail


def test_releases_expose_no_mutation_route() -> None:
    methods: set[str] = set()
    for route in app.routes:
        if getattr(route, "path", "").startswith("/releases"):
            methods |= getattr(route, "methods", set()) or set()
    # Reads and the create/promote posts only; nothing that edits the immutable
    # reference bundle.
    assert methods <= {"GET", "POST"}
