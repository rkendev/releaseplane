"""Generate the fixed 30-case invoice eval dataset.

The generator is deterministic: a fixed seed plus pinned PDF metadata means a
re-run produces byte-identical JSON ground truth and byte-stable PDFs. Ground
truth is produced by constructing the canonical Pydantic v2 model
(`examples.invoice_extraction.models.InvoiceExtraction`) and dumping it, so the
committed JSON cannot drift from the schema.

Tier split is 10 / 10 / 10. The split is NOT contiguous by case number: the
locked regression notes place case_21 in Tier 2 and case_27 in Tier 3, so the
tier map swaps case_20 (Tier 3) and case_21 (Tier 2).

Named cases (from examples/invoice_extraction/prompt_v1.yaml > regression_notes):
  - case_03 (Tier 1): single line item, clean baseline pass.
  - case_14 (Tier 2): multi-line with a discount row; demo headline. Ground
    truth subtotal 1150.00 / tax 97.50 / total 1247.50. A later prompt regression
    makes the model return 1257.50 and the arithmetic gate must catch it.
  - case_21 (Tier 2): vendor with leading zeros in invoice_number; checksum
    exact-match catches OCR 0/O confusion.
  - case_27 (Tier 3): handwritten annotation on the subtotal row; monitored only.

Note on the discount row: LineItem.unit_price is constrained ge=0, so a discount
cannot be a negative line item. The arithmetic policy requires
sum(qty * unit_price) == subtotal, so the ground-truth line items are the net
(post-discount) positive rows that sum to the subtotal, and the discount is
rendered as an annotation row on the PDF.

Run as a module to (re)write the committed dataset:
    uv run python -m releaseplane_evals.generator.invoices
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from fpdf import FPDF

from examples.invoice_extraction.models import Currency, InvoiceExtraction, LineItem

SEED = 20260623
# Fixed PDF creation timestamp so generated PDFs are byte-stable across runs.
FIXED_DT = datetime(2026, 1, 1, tzinfo=UTC)
DOC_META = "releaseplane-eval-generator"
CENTS = Decimal("0.01")

# Default output location for the committed dataset, resolved relative to the
# evals package root (.../evals/src/releaseplane_evals/generator/invoices.py).
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[3] / "datasets" / "invoice_v1"

CURRENCIES: tuple[Currency, ...] = ("EUR", "USD", "GBP", "JPY", "CHF", "SEK", "NOK", "DKK")
TAX_RATES = (Decimal("0"), Decimal("0.05"), Decimal("0.075"), Decimal("0.085"), Decimal("0.20"))
PAYMENT_TERMS = ("Net 30", "Net 15", "Net 45", "Due on receipt", "")
VENDORS = (
    "Northwind Trading",
    "Acme Industrial",
    "Globex Supplies",
    "Initech Services",
    "Umbrella Logistics",
    "Stark Components",
    "Wayne Hardware",
    "Cyberdyne Systems",
    "Tyrell Manufacturing",
    "Hooli Distribution",
    "Pied Piper Storage",
    "Vandelay Imports",
    "Gekko Office Group",
    "Oscorp Materials",
    "Massive Dynamic",
    "Sirius Cybernetics",
)
DESCRIPTIONS = (
    "Consulting hours",
    "Hardware components",
    "Software license",
    "Maintenance fee",
    "Shipping and handling",
    "Installation service",
    "Training session",
    "Support retainer",
    "Cloud usage",
    "Raw materials",
)

# A text line drawn on the PDF: (text, font_style) where style is "" or "I".
Line = tuple[str, str]


@dataclass(frozen=True)
class CaseSpec:
    """One eval case: its tier, ground-truth extraction, and rendered body."""

    case_id: str
    tier: int
    extraction: InvoiceExtraction
    body: tuple[Line, ...]

    @property
    def pdf_text(self) -> str:
        """The canonical text of the invoice (a perfect-OCR rendering)."""
        return "\n".join(text for text, _style in self.body)


def _tier_for(num: int) -> int:
    """Tier map: T1 = 1-10, T2 = 11-19 + 21, T3 = 20 + 22-30."""
    if num <= 10:
        return 1
    if num == 20:
        return 3
    if num == 21:
        return 2
    if num <= 19:
        return 2
    return 3


def money(value: Decimal) -> Decimal:
    return value.quantize(CENTS, rounding=ROUND_HALF_UP)


def _body(
    extraction: InvoiceExtraction,
    *,
    extra_rows: tuple[Line, ...] = (),
    subtotal_note: Line | None = None,
) -> tuple[Line, ...]:
    """Render the invoice body lines from an extraction plus optional extras.

    extra_rows are drawn between the line items and the totals (e.g. a discount
    row). subtotal_note is drawn right after the subtotal (e.g. a handwritten
    annotation).
    """
    lines: list[Line] = [
        ("INVOICE", ""),
        (f"Vendor: {extraction.vendor_name}", ""),
        (f"Invoice Number: {extraction.invoice_number}", ""),
        (f"Invoice Date: {extraction.invoice_date.isoformat()}", ""),
        (f"Currency: {extraction.currency}", ""),
        ("", ""),
        ("Line items:", ""),
    ]
    for item in extraction.line_items:
        line_total = money(item.qty * item.unit_price)
        lines.append((f"  {item.description}: {item.qty} x {item.unit_price} = {line_total}", ""))
    lines.extend(extra_rows)
    lines.append(("", ""))
    lines.append((f"Subtotal: {extraction.subtotal}", ""))
    if subtotal_note is not None:
        lines.append(subtotal_note)
    lines.append((f"Tax: {extraction.tax}", ""))
    lines.append((f"Total: {extraction.total}", ""))
    lines.append((f"Payment Terms: {extraction.payment_terms or 'n/a'}", ""))
    return tuple(lines)


def _named_case(num: int) -> CaseSpec:
    case_id = f"case_{num:02d}"
    tier = _tier_for(num)

    if num == 3:
        extraction = InvoiceExtraction(
            vendor_name="Riverside Office Supplies",
            invoice_number="INV-2026-1042",
            invoice_date=date(2026, 2, 3),
            line_items=[
                LineItem(description="Standing desk", qty=Decimal(1), unit_price=Decimal("500.00")),
            ],
            subtotal=Decimal("500.00"),
            tax=Decimal("42.50"),
            total=Decimal("542.50"),
            currency="USD",
            payment_terms="Net 30",
        )
        return CaseSpec(case_id, tier, extraction, _body(extraction))

    if num == 14:
        extraction = InvoiceExtraction(
            vendor_name="Atlas Facilities Group",
            invoice_number="INV-2026-1140",
            invoice_date=date(2026, 5, 14),
            line_items=[
                LineItem(
                    description="Professional services",
                    qty=Decimal(1),
                    unit_price=Decimal("1000.00"),
                ),
                LineItem(
                    description="On-site support",
                    qty=Decimal(3),
                    unit_price=Decimal("50.00"),
                ),
            ],
            subtotal=Decimal("1150.00"),
            tax=Decimal("97.50"),
            total=Decimal("1247.50"),
            currency="EUR",
            payment_terms="Net 30",
        )
        discount_row: Line = (
            "  Volume discount: -100.00 (already reflected in line items above)",
            "",
        )
        return CaseSpec(case_id, tier, extraction, _body(extraction, extra_rows=(discount_row,)))

    if num == 21:
        extraction = InvoiceExtraction(
            vendor_name="Zenith Precision Parts",
            invoice_number="007341",
            invoice_date=date(2026, 7, 21),
            line_items=[
                LineItem(
                    description="Bearing assembly", qty=Decimal(4), unit_price=Decimal("75.00")
                ),
                LineItem(description="Gasket set", qty=Decimal(2), unit_price=Decimal("60.00")),
            ],
            subtotal=Decimal("420.00"),
            tax=Decimal("21.00"),
            total=Decimal("441.00"),
            currency="GBP",
            payment_terms="Net 15",
        )
        return CaseSpec(case_id, tier, extraction, _body(extraction))

    if num == 27:
        extraction = InvoiceExtraction(
            vendor_name="Meadow Farm Produce",
            invoice_number="INV-2026-0277",
            invoice_date=date(2026, 9, 27),
            line_items=[
                LineItem(
                    description="Organic apples (crate)",
                    qty=Decimal(8),
                    unit_price=Decimal("24.00"),
                ),
                LineItem(description="Delivery", qty=Decimal(1), unit_price=Decimal("18.00")),
            ],
            subtotal=Decimal("210.00"),
            tax=Decimal("0.00"),
            total=Decimal("210.00"),
            currency="USD",
            payment_terms="Due on receipt",
        )
        note: Line = ("  [handwritten] subtotal checked against PO - JM", "I")
        return CaseSpec(case_id, tier, extraction, _body(extraction, subtotal_note=note))

    raise ValueError(f"no named case for {num}")


def _generic_case(num: int) -> CaseSpec:
    case_id = f"case_{num:02d}"
    tier = _tier_for(num)
    rng = random.Random(SEED + num)

    vendor = rng.choice(VENDORS)
    currency = rng.choice(CURRENCIES)
    invoice_number = f"INV-2026-{rng.randint(10000, 99999)}"
    invoice_date = date(2026, rng.randint(1, 12), rng.randint(1, 28))

    n_items = rng.randint(1, 4)
    items: list[LineItem] = []
    subtotal = Decimal("0.00")
    for _ in range(n_items):
        qty = Decimal(rng.randint(1, 12))
        unit_price = money(Decimal(rng.randint(500, 60000)) / Decimal(100))
        items.append(LineItem(description=rng.choice(DESCRIPTIONS), qty=qty, unit_price=unit_price))
        subtotal += qty * unit_price
    subtotal = money(subtotal)
    tax = money(subtotal * rng.choice(TAX_RATES))
    total = money(subtotal + tax)

    extraction = InvoiceExtraction(
        vendor_name=vendor,
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        line_items=items,
        subtotal=subtotal,
        tax=tax,
        total=total,
        currency=currency,
        payment_terms=rng.choice(PAYMENT_TERMS),
    )
    return CaseSpec(case_id, tier, extraction, _body(extraction))


NAMED = (3, 14, 21, 27)


def build_cases() -> list[CaseSpec]:
    """Build all 30 cases, ordered case_01 .. case_30."""
    return [_named_case(num) if num in NAMED else _generic_case(num) for num in range(1, 31)]


def get_case(case_id: str) -> CaseSpec:
    """Return a single case by id, e.g. "case_03"."""
    for case in build_cases():
        if case.case_id == case_id:
            return case
    raise KeyError(case_id)


def render_pdf(spec: CaseSpec, path: Path) -> None:
    pdf = FPDF()
    pdf.set_creation_date(FIXED_DT)
    pdf.set_creator(DOC_META)
    pdf.set_producer(DOC_META)
    pdf.set_title(spec.case_id)
    pdf.add_page()
    for text, style in spec.body:
        pdf.set_font("Helvetica", style=style, size=11)
        pdf.cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")
    pdf.output(str(path))


def write_json(spec: CaseSpec, path: Path) -> None:
    # Trailing newline matches the end-of-file-fixer pre-commit hook, so the
    # committed files stay byte-identical to fresh generator output.
    path.write_text(spec.extraction.model_dump_json(indent=2) + "\n", encoding="utf-8")


def generate_dataset(out_dir: Path = DEFAULT_OUT_DIR) -> list[CaseSpec]:
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = build_cases()
    for spec in cases:
        write_json(spec, out_dir / f"{spec.case_id}.json")
        render_pdf(spec, out_dir / f"{spec.case_id}.pdf")
    return cases


def main() -> None:
    cases = generate_dataset()
    by_tier = {1: 0, 2: 0, 3: 0}
    for case in cases:
        by_tier[case.tier] += 1
    print(
        f"wrote {len(cases)} cases to {DEFAULT_OUT_DIR} "
        f"(tier1={by_tier[1]} tier2={by_tier[2]} tier3={by_tier[3]})"
    )


if __name__ == "__main__":
    main()
