"""The shared-predicate agreement test (ADR 0004, decision D-PRED-HOME).

The eval scorer and the runtime policy both wrap the one neutral predicate in
releaseplane_shared, so they must agree on every input. This pins that agreement
on case_14, the demo headline: the ground truth is arithmetically consistent, and
the regressed total (1247.50 -> 1257.50) is caught by both call sites.
"""

from __future__ import annotations

import copy
from typing import Any

from releaseplane_evals.generator.invoices import get_case
from releaseplane_evals.scorers import score_arithmetic_consistency
from releaseplane_gateway.policies.arithmetic_consistency import check_arithmetic_consistency


def _case_14() -> dict[str, Any]:
    return copy.deepcopy(get_case("case_14").extraction.model_dump(mode="json"))


def test_scorer_and_policy_agree_on_ground_truth() -> None:
    output = _case_14()
    scorer = score_arithmetic_consistency(output)
    policy = check_arithmetic_consistency(output)
    assert scorer.passed is True
    assert policy.passed is True
    assert scorer.passed == policy.passed


def test_scorer_and_policy_agree_on_regressed_total() -> None:
    output = _case_14()
    output["total"] = "1257.50"  # ground truth is 1247.50
    scorer = score_arithmetic_consistency(output)
    policy = check_arithmetic_consistency(output)
    assert scorer.passed is False
    assert policy.passed is False
    assert scorer.passed == policy.passed
    # The shared predicate produces identical evidence on both sides.
    assert scorer.detail == policy.detail
