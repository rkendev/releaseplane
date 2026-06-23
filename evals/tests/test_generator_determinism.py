"""Tests for the invoice eval-dataset generator.

These assert the committed dataset is complete, schema-valid, arithmetically
consistent, and byte-for-byte reproducible from the fixed seed.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from pathlib import Path

from releaseplane_evals.generator.invoices import (
    DEFAULT_OUT_DIR,
    build_cases,
    generate_dataset,
)

from examples.invoice_extraction.models import InvoiceExtraction

COMMITTED = DEFAULT_OUT_DIR


def test_thirty_pdfs_and_thirty_json_committed() -> None:
    assert len(sorted(COMMITTED.glob("*.pdf"))) == 30
    assert len(sorted(COMMITTED.glob("*.json"))) == 30


def test_regeneration_is_byte_identical(tmp_path: Path) -> None:
    generate_dataset(tmp_path)
    committed_files = sorted(COMMITTED.glob("*"))
    assert committed_files, "no committed dataset found"
    for committed in committed_files:
        fresh = tmp_path / committed.name
        assert fresh.exists(), f"missing regenerated file: {committed.name}"
        assert fresh.read_bytes() == committed.read_bytes(), f"drift in {committed.name}"


def test_all_json_valid_arithmetic_and_tier_split() -> None:
    tier_by_id = {case.case_id: case.tier for case in build_cases()}
    tier_counts: Counter[int] = Counter()
    for json_file in sorted(COMMITTED.glob("*.json")):
        model = InvoiceExtraction.model_validate_json(json_file.read_text(encoding="utf-8"))
        tier_counts[tier_by_id[json_file.stem]] += 1
        line_sum = sum((item.qty * item.unit_price for item in model.line_items), Decimal(0))
        assert abs(line_sum - model.subtotal) <= Decimal("0.01"), json_file.stem
        assert abs(model.subtotal + model.tax - model.total) <= Decimal("0.01"), json_file.stem
    assert tier_counts == Counter({1: 10, 2: 10, 3: 10})


def test_case_14_demo_headline_totals() -> None:
    model = InvoiceExtraction.model_validate_json(
        (COMMITTED / "case_14.json").read_text(encoding="utf-8")
    )
    assert model.subtotal == Decimal("1150.00")
    assert model.tax == Decimal("97.50")
    assert model.total == Decimal("1247.50")


def test_case_21_preserves_leading_zero_invoice_number() -> None:
    model = InvoiceExtraction.model_validate_json(
        (COMMITTED / "case_21.json").read_text(encoding="utf-8")
    )
    assert model.invoice_number == "007341"
