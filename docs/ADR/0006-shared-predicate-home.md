# ADR 0006: The shared arithmetic predicate lives in a neutral package

Date: 2026-06-26
Status: Accepted

## Context

ADR 0004 requires one arithmetic-consistency check shared by the eval gate and the
runtime policy so they cannot drift. It predicted the predicate would live in the
gateway policy module, with the eval harness importing it.

As Phase 5 built this out, that direction would make the evaluation package depend
on the gateway package: a plane crossing the wrong way (evals should not import the
execution plane), and the gateway container does not have the evals package either.
Decision D-PRED-HOME asked where the one predicate should live.

## Decision

The predicate lives in a new neutral workspace package, `releaseplane-shared`
(`shared/src/releaseplane_shared/arithmetic.py`), with no dependencies. Both planes
import it:

- the eval scorer (`evals/.../scorers.py`) wraps it into a `MetricResult`;
- the gateway policy (`gateway/.../policies/arithmetic_consistency.py`) wraps it
  into a `PolicyOutcome`.

Neither plane imports the other. A committed shared-fixture test on case_14 pins
that both call sites agree on ground truth and on the regressed total.

## Rationale

- Plane separation: a neutral package both planes depend on keeps the dependency
  graph acyclic and the evaluation harness independent of the execution plane.
- One source of truth: the predicate, its tolerance, and its detail shape exist
  once, so the gate and the runtime check produce identical evidence.

## Consequences

- The gateway image build widens to the repo root so the shared package ships in
  the image alongside the gateway (the runtime policy imports it). This is the one
  build cost of the neutral-package choice; it is contained in the gateway
  Dockerfile and the compose build context.
- `shared/src` is added to the workspace, the mypy path, and the lint/type targets
  so both `make check` and the pre-commit hook resolve it the same way.
- ADR 0004's predicted paths are superseded by this ADR; ADR 0004 carries a
  reconciliation note.
