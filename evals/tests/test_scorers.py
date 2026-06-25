"""Unit tests for the three eval metrics. Pure: no model, no network, no database.

Ground truth comes from the generator (the same source the loader uses) and the
schema from InvoiceExtraction.model_json_schema(), so the fixtures match what a
real run scores against.
"""

from __future__ import annotations

import copy
from typing import Any

from releaseplane_evals.generator.invoices import get_case
from releaseplane_evals.scorers import (
    ARITHMETIC_CONSISTENCY,
    CHECKSUM_MATCH,
    SCHEMA_VALIDITY,
    score_arithmetic_consistency,
    score_case,
    score_checksum_match,
    score_schema_validity,
)

from examples.invoice_extraction.models import InvoiceExtraction

SCHEMA: dict[str, Any] = InvoiceExtraction.model_json_schema()


def _ground_truth(case_id: str) -> dict[str, Any]:
    """A fresh, mutable copy of a case's ground-truth extraction as a JSON dict."""
    return copy.deepcopy(get_case(case_id).extraction.model_dump(mode="json"))


# --- schema validity --------------------------------------------------------


def test_ground_truth_passes_schema() -> None:
    assert score_schema_validity(_ground_truth("case_14"), SCHEMA).passed


def test_missing_required_field_fails_schema() -> None:
    output = _ground_truth("case_01")
    del output["currency"]
    result = score_schema_validity(output, SCHEMA)
    assert not result.passed
    assert result.name == SCHEMA_VALIDITY
    assert result.detail["errors"]


def test_currency_outside_enum_fails_schema() -> None:
    output = _ground_truth("case_01")
    output["currency"] = "XYZ"
    assert not score_schema_validity(output, SCHEMA).passed


def test_empty_line_items_fails_schema() -> None:
    output = _ground_truth("case_01")
    output["line_items"] = []
    assert not score_schema_validity(output, SCHEMA).passed


# --- arithmetic consistency -------------------------------------------------


def test_ground_truth_passes_arithmetic() -> None:
    assert score_arithmetic_consistency(_ground_truth("case_14")).passed


def test_case_14_hallucinated_total_fails_arithmetic() -> None:
    # The demo headline: subtotal 1150.00 + tax 97.50 = 1247.50, but the
    # regressed prompt returns 1257.50. The arithmetic gate must catch it.
    output = _ground_truth("case_14")
    output["total"] = "1257.50"
    result = score_arithmetic_consistency(output)
    assert not result.passed
    assert result.detail["total_matches_subtotal_plus_tax"] is False
    assert result.detail["subtotal_matches_line_items"] is True


def test_line_items_not_summing_fails_arithmetic() -> None:
    output = _ground_truth("case_14")
    output["line_items"][0]["unit_price"] = "999.00"
    assert not score_arithmetic_consistency(output).passed


def test_arithmetic_tolerance_is_one_cent() -> None:
    within = _ground_truth("case_14")
    within["total"] = "1247.51"  # off by exactly 0.01
    assert score_arithmetic_consistency(within).passed
    beyond = _ground_truth("case_14")
    beyond["total"] = "1247.52"  # off by 0.02
    assert not score_arithmetic_consistency(beyond).passed


def test_arithmetic_on_missing_field_fails_cleanly() -> None:
    output = _ground_truth("case_01")
    del output["subtotal"]
    result = score_arithmetic_consistency(output)
    assert not result.passed
    assert "error" in result.detail


# --- checksum exact-match ---------------------------------------------------


def test_ground_truth_passes_checksum() -> None:
    gt = _ground_truth("case_21")
    assert score_checksum_match(gt, gt).passed


def test_case_21_dropped_leading_zero_fails_checksum() -> None:
    expected = _ground_truth("case_21")  # invoice_number "007341"
    output = copy.deepcopy(expected)
    output["invoice_number"] = "7341"
    result = score_checksum_match(output, expected)
    assert not result.passed
    assert result.name == CHECKSUM_MATCH
    assert "invoice_number" in result.detail["mismatches"]


def test_checksum_total_compares_decimal_value() -> None:
    expected = _ground_truth("case_14")  # total "1247.50"
    output = copy.deepcopy(expected)
    output["total"] = "1247.5"  # same value, different string
    assert score_checksum_match(output, expected).passed


def test_checksum_normalizes_non_iso_date() -> None:
    expected = _ground_truth("case_14")  # invoice_date "2026-05-14"
    output = copy.deepcopy(expected)
    output["invoice_date"] = "05/14/2026"
    assert score_checksum_match(output, expected).passed


def test_checksum_catches_wrong_total() -> None:
    expected = _ground_truth("case_14")
    output = copy.deepcopy(expected)
    output["total"] = "1257.50"
    result = score_checksum_match(output, expected)
    assert not result.passed
    assert "total" in result.detail["mismatches"]


# --- aggregate --------------------------------------------------------------


def test_score_case_returns_three_metrics_in_order() -> None:
    gt = _ground_truth("case_03")
    results = score_case(output=gt, expected=gt, output_schema=SCHEMA)
    assert [r.name for r in results] == [
        SCHEMA_VALIDITY,
        ARITHMETIC_CONSISTENCY,
        CHECKSUM_MATCH,
    ]
    assert all(r.passed for r in results)
