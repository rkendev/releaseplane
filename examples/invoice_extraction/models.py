"""Pydantic v2 models for AP invoice extraction.

These models are the single source of truth for the prompt's variable schema and
output schema. JSON Schema is auto-generated via `Model.model_json_schema()`.

ADR: docs/ADR/0002-pydantic-v2-as-schema-source.md
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

Currency = Literal["EUR", "USD", "GBP", "JPY", "CHF", "SEK", "NOK", "DKK"]


class LineItem(BaseModel):
    """One row from the invoice line-items table."""

    description: str = Field(..., min_length=1, max_length=500)
    qty: Decimal = Field(..., gt=0)
    unit_price: Decimal = Field(..., ge=0)


class InvoiceVariables(BaseModel):
    """Variables passed in at prompt-render time."""

    invoice_pdf_text: str = Field(
        ..., description="The OCR'd or text-extracted body of the invoice PDF."
    )


class InvoiceExtraction(BaseModel):
    """The structured response the model must produce.

    The arithmetic-consistency policy asserts:
      sum(line_items[i].qty * line_items[i].unit_price for all i) == subtotal
      subtotal + tax == total
    within +/- 0.01 currency-unit tolerance.

    The checksum-exact-match policy asserts that invoice_number, invoice_date,
    currency, and total match the ground truth exactly.
    """

    vendor_name: str = Field(..., min_length=1, max_length=200)
    invoice_number: str = Field(..., min_length=1, max_length=64)
    invoice_date: date
    line_items: list[LineItem] = Field(..., min_length=1)
    subtotal: Decimal = Field(..., ge=0)
    tax: Decimal = Field(..., ge=0)
    total: Decimal = Field(..., ge=0)
    currency: Currency
    payment_terms: str = Field("", max_length=500)
