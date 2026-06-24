"""Release lifecycle state machine.

The legal transitions mirror the state diagram in docs/ARCHITECTURE.md:

    draft      -> candidate
    candidate  -> active | draft
    active     -> rolled_back | active   (active -> active is supersede)
    rolled_back-> draft
    canary     -> (none; reserved but inert at v1)

POST /releases/{id}/promote advances along the forward promotion path only
(draft -> candidate -> active). The full transition table is exposed for
validation and for a future demotion or rollback endpoint; the promote endpoint
uses next_promote_stage. Promoting a release that has no forward stage (active,
rolled_back, canary) is rejected.
"""

from __future__ import annotations

from ..models import ReleaseStage

LEGAL_TRANSITIONS: dict[ReleaseStage, frozenset[ReleaseStage]] = {
    ReleaseStage.draft: frozenset({ReleaseStage.candidate}),
    ReleaseStage.candidate: frozenset({ReleaseStage.active, ReleaseStage.draft}),
    ReleaseStage.active: frozenset({ReleaseStage.rolled_back, ReleaseStage.active}),
    ReleaseStage.rolled_back: frozenset({ReleaseStage.draft}),
    ReleaseStage.canary: frozenset(),
}

# The forward promotion path the promote endpoint walks, one hop per call.
PROMOTE_PATH: dict[ReleaseStage, ReleaseStage] = {
    ReleaseStage.draft: ReleaseStage.candidate,
    ReleaseStage.candidate: ReleaseStage.active,
}


def is_legal_transition(src: ReleaseStage, dst: ReleaseStage) -> bool:
    """Whether moving a release from src to dst is allowed by the diagram."""
    return dst in LEGAL_TRANSITIONS.get(src, frozenset())


def next_promote_stage(src: ReleaseStage) -> ReleaseStage | None:
    """The next stage a forward promotion moves to, or None if not promotable."""
    return PROMOTE_PATH.get(src)
