"""Synthetic raster IPC and strict cross-process OCR payload checks."""

from __future__ import annotations

import json
import os
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from product_eval import tatr_ocr_page_worker
from product_eval.tatr_asset_preflight import sha256_file
from product_eval.tatr_cell_compat import load_official_cell_functions
from product_eval.tatr_first_pdf_worker import run_document
from product_eval.tatr_native_geometry import native_word_tokens
from product_eval.tatr_ocr_handoff import OcrPageHandoff, validate_ocr_payload
from product_eval.tatr_ocr_word_source_free import LOCK_PATH, OCR_REVISION


def _payload() -> dict:
    polygon = [[1.0, 1.0], [20.0, 1.0], [20.0, 10.0], [1.0, 10.0]]
    return {
        "status": "ocr_page_words_ready", "source": "ocr_word",
        "ocr_revision": OCR_REVISION, "input_png_sha256": "0" * 64,
        "image_size": [100, 40], "line_score_threshold": 0.0,
        "source_pdf_opened": False, "gold_opened": False,
        "line_count": 1, "word_count": 1,
        "line_orientations": [{"label": "0", "score": 0.95}],
        "providers_selected": {part: ["CPUExecutionProvider"]
                               for part in ("text_det", "text_cls", "text_rec")},
        "runtime_inventory": {"ocr_lock_sha256": sha256_file(LOCK_PATH),
                              "opencv_package": "opencv-python-headless==5.0.0.93"},
        "raw_lines": [{"line_index": 0, "text": "ALPHA", "polygon": polygon,
                       "score": 0.9, "words": [{"text": "ALPHA", "reported_score": 0.8,
                                                  "polygon": polygon}]}],
        "word_tokens": [{
            "text": "ALPHA", "bbox": [1.0, 1.0, 20.0, 10.0],
            "ocr_polygon": polygon, "source": "ocr_word", "reading_order": 0,
            "source_token_id": "rapidocr:l0:w0", "ocr_engine": "RapidOCR/ONNXRuntime-CPU",
            "ocr_revision": OCR_REVISION, "ocr_confidence": 0.8,
            "ocr_line_score": 0.9,
        }],
    }


def test_cross_process_payload_accepts_only_consistent_upright_words() -> None:
    tokens, provenance = validate_ocr_payload(_payload(), image_size=(100, 40),
                                               input_hash="0" * 64)
    assert [token["text"] for token in tokens] == ["ALPHA"]
    assert provenance["line_count"] == 1
    for mutate in (
        lambda value: value["line_orientations"][0].update(label="180"),
        lambda value: value["word_tokens"][0].update(source="pdfium_native"),
        lambda value: value["word_tokens"][0].update(bbox=[1, 1, 19, 10]),
        lambda value: value["word_tokens"][0].update(ocr_engine="other"),
        lambda value: value["word_tokens"][0].update(ocr_revision="other"),
        lambda value: value["raw_lines"][0]["words"][0].update(text="BETA"),
        lambda value: value.update(input_png_sha256="1" * 64),
    ):
        mutant = deepcopy(_payload())
        mutate(mutant)
        with pytest.raises(ValueError):
            validate_ocr_payload(mutant, image_size=(100, 40), input_hash="0" * 64)


def test_ocr_failure_receipt_omits_exception_text_and_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_marker = "PRIVATE_SOURCE_TEXT_AND_KEY"

    def fail(**_kwargs):
        raise ValueError(private_marker)

    result = tmp_path / "ocr_result.json"
    monkeypatch.setattr(tatr_ocr_page_worker, "run_ocr_png", fail)
    monkeypatch.setattr(sys, "argv", [
        "tatr_ocr_page_worker", "--input-png", str(tmp_path / "raster.png"),
        "--input-sha256", "0" * 64, "--width", "10", "--height", "10",
        "--runtime-root", str(tmp_path), "--wheelhouse", str(tmp_path),
        "--notices-root", str(tmp_path), "--result-json", str(result),
    ])
    with pytest.raises(SystemExit) as stopped:
        tatr_ocr_page_worker.main()
    assert stopped.value.code == 1
    failure_text = (tmp_path / "ocr_failure.json").read_text(encoding="utf-8")
    assert private_marker not in failure_text
    assert "traceback" not in failure_text
    assert json.loads(failure_text)["reason"] == "ValueError"


@pytest.fixture(scope="module")
def ocr_runtime() -> tuple[Path, Path, Path, Path]:
    python = os.environ.get("TATR_OCR_RUNTIME_PYTHON")
    wheelhouse = os.environ.get("TATR_OCR_WHEELHOUSE")
    notices = os.environ.get("TATR_OCR_NOTICES_ROOT")
    font = os.environ.get("TATR_OCR_TEST_FONT")
    if not all((python, wheelhouse, notices, font)):
        pytest.skip("pinned OCR runtime and synthetic font not configured")
    python_path = Path(python).resolve(strict=True)
    return python_path, Path(wheelhouse).resolve(strict=True), Path(notices).resolve(strict=True), Path(font).resolve(strict=True)


def _synthetic_raster(font: Path):
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (1100, 340), "white")
    draw = ImageDraw.Draw(image)
    selected_font = ImageFont.truetype(str(font), 58)
    draw.text((50, 60), "NORTH SOUTH", font=selected_font, fill="black")
    draw.text((50, 190), "ALPHA BETA", font=selected_font, fill="black")
    return image


def test_pinned_ocr_subprocess_preserves_words_and_rejects_180_degrees(
    tmp_path: Path, ocr_runtime: tuple[Path, Path, Path, Path],
) -> None:
    python, wheelhouse, notices, font = ocr_runtime
    image = _synthetic_raster(font)
    handoff = OcrPageHandoff(python, python.parent.parent, wheelhouse, notices, tmp_path)
    words, provenance = handoff(image, 1)
    assert [word["text"] for word in words] == ["NORTH", "SOUTH", "ALPHA", "BETA"]
    assert provenance["line_count"] == 2
    assert provenance["word_count"] == 4
    assert provenance["raw_lines"][0]["text"] == "NORTH SOUTH"
    assert provenance["providers_selected"]["text_rec"] == ["CPUExecutionProvider"]
    rotated = image.rotate(180)
    with pytest.raises(RuntimeError, match="subprocess failed"):
        handoff(rotated, 2)
    failure = json.loads((tmp_path / "ocr-page-002" / "ocr_failure.json").read_text(encoding="utf-8"))
    assert failure["reason"] == "orientation_not_confidently_upright"
    assert "NORTH" not in json.dumps(failure)


def test_synthetic_image_only_pdf_uses_one_page_ocr_route(
    tmp_path: Path, ocr_runtime: tuple[Path, Path, Path, Path],
) -> None:
    pdfium = pytest.importorskip("pypdfium2")
    stage = Path(os.environ.get("TATR_ASSET_STAGE", r"I:\DocAI-Benchmarks\tatr-adbuy12-runtime-v1-stage"))
    if not stage.exists():
        pytest.skip("pinned TATR cell adapter stage absent")
    python, wheelhouse, notices, font = ocr_runtime
    source = tmp_path / "synthetic-raster.pdf"
    output = tmp_path / "result"
    output.mkdir()
    _synthetic_raster(font).save(source, format="PDF", resolution=300.0)
    pdf = pdfium.PdfDocument(source)
    try:
        page = pdf[0]
        bitmap = page.render(scale=300 / 72)
        try:
            assert native_word_tokens(page, bitmap) == []
        finally:
            bitmap.close()
            page.close()
    finally:
        pdf.close()

    def infer(image, kind):
        box = (0, 0, image.width, image.height)
        if kind == "detection":
            return [{"label": "table", "score": 0.9, "bbox": box,
                     "query_index": 0, "above_frozen_threshold": True}]
        return [{"label": label, "score": 0.9, "bbox": box}
                for label in ("table", "table row", "table column")]

    handoff = OcrPageHandoff(python, python.parent.parent, wheelhouse, notices, output)
    receipt = run_document(source, sha256_file(source), output, infer,
                           load_official_cell_functions(stage), handoff)
    assert receipt["status"] == "first_pdf_needs_visual_review"
    raw = json.loads((output / "raw_pages.json").read_text(encoding="utf-8"))
    assert len(raw) == 1
    assert raw[0]["word_route"] == "ocr_word"
    assert [word["text"] for word in raw[0]["page_words"]] == [
        "NORTH", "SOUTH", "ALPHA", "BETA",
    ]
    assert raw[0]["ocr_provenance"]["line_count"] == 2
    assert len(list(output.glob("ocr-page-*/ocr_result.json"))) == 1
    parsed = json.loads((output / "parsed_document.json").read_text(encoding="utf-8"))
    assert parsed["tables"][0]["cells"][0]["text"]
    assert (output / "first_nonempty_source_overlay.png").is_file()
