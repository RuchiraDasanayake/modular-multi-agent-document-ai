"""Regenerate a source-free fixture through the complete Python visual workflow.

Run from the repository root with a Python environment containing the product
dependencies and pytest. The TypeScript test consumes only the sealed, small
candidate/page/source bundle; it never calls a model or OCR service.
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
import tempfile
from pathlib import Path

from pytest import MonkeyPatch

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from idpo.tests.test_product_visual_workflow import Model, fake_ocr, reply, run_product, source_image


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="docai-visual-review-") as directory:
        root = Path(directory)
        variants = {}
        source_bytes = None
        for variant_name, text in [("image_only", ""), ("ocr_text_match", "Widget 100")]:
            variant_dir = root / variant_name
            variant_dir.mkdir()
            source = source_image(variant_dir)
            current_bytes = source.read_bytes()
            if source_bytes is None:
                source_bytes = current_bytes
            else:
                assert source_bytes == current_bytes
            patcher = MonkeyPatch()
            try:
                fake_ocr(patcher, texts=[text], failure="rapidocr_no_text" if not text else None)
                model = Model(lambda request, _: reply(page=request.receipt()["covered_pages"][0], quote="Widget"))
                candidate, sidecar, manifest, _ = run_product(variant_dir, source, model)
            finally:
                patcher.undo()
            assert candidate["document_status"] == "needs_review"
            assert sidecar["visual_document"]["full_source_covered"] is True
            assert manifest["source_container_sha256"] == hashlib.sha256(current_bytes).hexdigest()
            variants[variant_name] = {
                "candidate": candidate,
                "pages": sidecar["pages"],
                "visual_receipt": {
                    "profile": sidecar["visual_document"]["profile"],
                    "route": sidecar["visual_document"]["route"],
                    "source_sha256": sidecar["visual_document"]["source_sha256"],
                    "full_source_covered": sidecar["visual_document"]["full_source_covered"],
                },
            }
        assert source_bytes is not None
        source_sha = hashlib.sha256(source_bytes).hexdigest()
        fixture = {
            "generator": "idpo.tests.test_product_visual_workflow.run_product",
            "source_name": "source.png",
            "source_base64": base64.b64encode(source_bytes).decode("ascii"),
            "source_sha256": source_sha,
            "variants": variants,
        }
        target = Path(__file__).with_name("visual-review-workflow.json")
        target.write_text(json.dumps(fixture, sort_keys=True, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
