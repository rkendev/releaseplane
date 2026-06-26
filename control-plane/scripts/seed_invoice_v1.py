"""Host op: seed the invoice_v1 bundle and the two prompts into a running control plane.

Idempotent. Resolves the prompt schemas from the reference `examples` package
(repo root on the path), so it runs from the dev environment, not the container.

Usage (from the repo root, against the running dev stack):

    CONTROL_PLANE_URL=http://localhost:8001 uv run python control-plane/scripts/seed_invoice_v1.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
# Put the repo root on the path so bootstrap can import the reference `examples`
# package when it resolves the prompt schemas.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from releaseplane_control.services.bootstrap import seed_invoice_v1  # noqa: E402

PROMPTS = REPO_ROOT / "examples" / "invoice_extraction"


def main() -> None:
    base_url = os.environ.get("CONTROL_PLANE_URL", "http://localhost:8001")
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        summary = seed_invoice_v1(
            client,
            prompt_v1_path=PROMPTS / "prompt_v1.yaml",
            prompt_v2_path=PROMPTS / "prompt_v2.yaml",
        )
    print(f"control plane: {base_url}")
    print(f"policy bundle invoice_v1 created: {summary.bundle_created}")
    print(f"prompt invoice-extraction id: {summary.prompt_id}")
    for version, created in summary.versions_created.items():
        print(f"prompt version {version} created: {created}")


if __name__ == "__main__":
    main()
