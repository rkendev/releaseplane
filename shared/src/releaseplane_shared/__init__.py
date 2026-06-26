"""Plane-neutral pure predicates shared across ReleasePlane.

A small dependency-free package both the eval harness (releaseplane-evals) and the
gateway (releaseplane-gateway) import, so a check that gates a release and the
runtime policy that flags a live request use one source of truth and cannot drift.
Neither plane imports the other; both import here (decision D-PRED-HOME).
"""

__version__ = "0.0.0"
