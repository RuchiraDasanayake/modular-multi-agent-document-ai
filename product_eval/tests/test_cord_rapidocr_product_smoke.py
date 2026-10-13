"""Development smoke must preserve source identity and exact OCR evidence."""
from __future__ import annotations

import hashlib
from copy import deepcopy

import pytest
from PIL import Image

from product_eval import cord_rapidocr_product_smoke as smoke


def test_source_verification_rejects_changed_original_and_preserves_rgb_identity(tmp_path, monkeypatch):
    sources = []
    for index, color in enumerate(("white", "black")):
        source = tmp_path / f"{index}.png"
        Image.new("RGB", (200, 100), color).save(source)
        sources.append({"doc_id": str(index), "source_path": str(source),
                        "source_sha256": smoke.sha(source), "source_size_bytes": source.stat().st_size})
    monkeypatch.setattr(smoke, "SOURCE_HASHES", {row["source_sha256"] for row in sources})
    identities = smoke.verify_sources(sources)
    assert len(identities) == 2
    assert identities["0"]["image_size"] == [200, 100]
    source.write_bytes(b"changed original")
    with pytest.raises(ValueError, match="Frozen source bytes differ"):
        smoke.verify_sources(sources)


def test_output_verification_rejects_different_raster_and_shifted_offsets():
    source = {"source_sha256": "a" * 64}
    raster = {"rgb_png_sha256": "b" * 64, "image_size": [200, 100]}
    provenance = {"revision": smoke.REVISION, "model_sha256": smoke.MODEL_SHA256,
                  "input_png_sha256": "b" * 64, "image_size_px": [200, 100],
                  "text_sha256": hashlib.sha256(b"invoice").hexdigest(),
                  "worker_elapsed_ms": 12, "peak_tree_rss_bytes_sampled": 100}
    result = {"source_sha256": "a" * 64, "pages": [{"page": 1, "text": "invoice"}],
              "ocr_pages": [{"engine": "rapidocr", "rerun_attempted": False, "failure_reason": None,
                             "ocr_provenance": provenance,
                             "ocr_lines": [{"start": 0, "end": 7, "text": "invoice"}]}]}
    assert smoke.verify_ocr_result(result, source, raster)["line_count"] == 1
    for mutate in (lambda row: row["ocr_pages"][0]["ocr_provenance"].update(input_png_sha256="c" * 64),
                   lambda row: row["ocr_pages"][0]["ocr_lines"][0].update(start=1)):
        changed = deepcopy(result)
        mutate(changed)
        with pytest.raises(ValueError, match="source binding or exact line offsets differ"):
            smoke.verify_ocr_result(changed, source, raster)
