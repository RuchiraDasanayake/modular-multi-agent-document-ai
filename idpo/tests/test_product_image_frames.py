"""A multi-frame upload must not be presented as a complete one-page extraction."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from idpo.product_auto.brief_draft import _sample_text
from idpo.product_auto.image_frames import require_single_frame_image
from idpo.product_auto.workflow import process_auto


def _two_frames(tmp_path: Path, extension: str) -> Path:
    source = tmp_path / f"two-pages.{extension}"
    first = Image.new("RGB", (32, 32), "white")
    second = Image.new("RGB", (32, 32), "black")
    first.save(source, save_all=True, append_images=[second])
    first.close()
    second.close()
    return source


@pytest.mark.parametrize("extension", ["tiff", "png", "jpg", "bmp"])
def test_single_frame_images_remain_supported(tmp_path: Path, extension: str) -> None:
    source = tmp_path / f"one-page.{extension}"
    with Image.new("RGB", (32, 32), "white") as image:
        image.save(source)
    with Image.open(source) as image:
        require_single_frame_image(image)


@pytest.mark.parametrize("extension", ["tiff", "png"])
def test_multiframe_extraction_abstains_before_ocr(tmp_path: Path, monkeypatch, extension: str) -> None:
    source = _two_frames(tmp_path, extension)
    monkeypatch.setattr("idpo.agents.preprocess.OcrAgent.run",
                        lambda *args, **kwargs: pytest.fail("partial-image OCR was started"))
    result = process_auto(source, output_root=tmp_path / "runs")
    assert result["status_counts"]["unsupported"] == 1
    candidate = json.loads((Path(result["run_dir"]) / "candidates.jsonl").read_text())
    sidecar = json.loads((Path(result["run_dir"]) / "docs" / candidate["doc_id"] / "result.json").read_text())
    assert sidecar["reason"] == "multi_frame_image_unsupported"
    assert candidate["extracted_values"] == []


@pytest.mark.parametrize("extension", ["tiff", "png"])
def test_multiframe_schema_sample_abstains_before_ocr(tmp_path: Path, monkeypatch, extension: str) -> None:
    source = _two_frames(tmp_path, extension)
    monkeypatch.setattr("idpo.agents.preprocess.OcrAgent.run",
                        lambda *args, **kwargs: pytest.fail("partial-image sample OCR was started"))
    with pytest.raises(ValueError, match="single-frame"):
        _sample_text(source, "a" * 64)
