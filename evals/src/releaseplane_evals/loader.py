"""Build the dataset-load payload from the generator and post it to the control plane.

The generator is the single source of truth for the golden dataset: it yields the
tier, the ground-truth extraction, and the perfect-OCR input text for each case,
none of which the committed PDF/JSON pair carries inline. build_dataset_payload
turns those cases into the control-plane load shape; load_dataset posts it. The
httpx client is injected so the CLI points it at CONTROL_PLANE_URL and tests
point it at an in-process app.
"""

from __future__ import annotations

from typing import Any

import httpx

from .generator.invoices import SEED, build_cases

DATASET_NAME = "invoice_v1"
DOMAIN = "ap_invoice_extraction"
SOURCE = "releaseplane_evals.generator.invoices:build_cases"


def build_dataset_payload(name: str = DATASET_NAME) -> dict[str, Any]:
    """Render the 30 generator cases into a control-plane dataset-load payload."""
    cases = build_cases()
    return {
        "name": name,
        "domain": DOMAIN,
        "source": SOURCE,
        "generator_seed": SEED,
        "cases": [
            {
                "input_path": f"{case.case_id}.pdf",
                "input_text": case.pdf_text,
                "expected_json": case.extraction.model_dump(mode="json"),
                "tier": case.tier,
                "metadata_json": {"case_id": case.case_id},
            }
            for case in cases
        ],
    }


async def load_dataset(client: httpx.AsyncClient, payload: dict[str, Any]) -> dict[str, Any]:
    """Post the load payload and return the parsed EvalDatasetLoadResult body."""
    response = await client.post("/eval-datasets", json=payload)
    response.raise_for_status()
    result: dict[str, Any] = response.json()
    return result
