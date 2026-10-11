from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from product_eval import cord_word_ocr_diagnostic as diagnostic


def test_quad_crop_preserves_left_to_right_orientation_and_rejects_distant_coordinates() -> None:
    image = Image.new("RGB", (100, 50), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, 49, 39), fill="red")
    draw.rectangle((50, 10, 89, 39), fill="blue")
    quad = {"x1": 10, "y1": 10, "x2": 90, "y2": 10,
            "x3": 90, "y3": 40, "x4": 10, "y4": 40}

    crop = diagnostic.crop_quad(image, quad)

    assert crop.size == (252, 102)
    left, right = crop.getpixel((35, 50)), crop.getpixel((215, 50))
    assert left[0] > 200 and left[2] < 50
    assert right[2] > 200 and right[0] < 50
    quad["x4"] = -10
    with pytest.raises(ValueError, match="annotation tolerance"):
        diagnostic.crop_quad(image, quad)


def test_exact_and_cer_are_paired_on_annotated_boxes_and_clustered_by_document() -> None:
    references = [("doc-a", "ABC"), ("doc-a", "4 5"), ("doc-b", "X")]
    texts = [("ABC", "ADC"), ("45", "4 5"), ("", "X")]
    manifest = [
        {"crop_id": f"crop-{i}", "doc_id": doc, "source_sha256": f"source-{i}",
         "crop_sha256": f"image-{i}", "gold_text": gold}
        for i, (doc, gold) in enumerate(references)
    ]
    predictions = [
        {"crop_id": row["crop_id"], "doc_id": row["doc_id"],
         "source_sha256": row["source_sha256"], "crop_sha256": row["crop_sha256"],
         "tesseract_text": tess, "rapid_text": rapid,
         "tesseract_ms": i + 1, "rapid_ms": i + 3}
        for i, (row, (tess, rapid)) in enumerate(zip(manifest, texts, strict=True))
    ]

    summary = diagnostic.score_predictions(manifest, predictions, bootstrap_replicates=100)

    assert diagnostic.canonical_text("  ＡＢＣ\n 4  ") == "ABC 4"
    assert diagnostic.character_edits("4 5", "45") == 1
    assert summary["documents"] == 2
    assert summary["annotated_boxes"] == 3
    assert summary["paired_exact_boxes"] == {"both": 0, "tesseract_only": 1, "rapidocr_only": 2, "neither": 0}
    assert summary["tesseract"]["exact_micro"] == pytest.approx(1 / 3)
    assert summary["rapidocr"]["exact_micro"] == pytest.approx(2 / 3)
    assert summary["tesseract"]["exact_macro_document"] == pytest.approx(0.25)
    assert summary["rapidocr"]["exact_macro_document"] == pytest.approx(0.75)
    assert summary["tesseract"]["cer_micro"] == pytest.approx(2 / 7)
    assert summary["rapidocr"]["cer_micro"] == pytest.approx(1 / 7)
    assert summary["paired_document_bootstrap_95pct"]["exact_micro_delta"] == [0.0, 1.0]
    assert summary["latency_ms"]["tesseract"]["p50"] == 2
    assert summary["latency_ms"]["rapidocr"]["p95"] == pytest.approx(4.9)

    predictions[0]["source_sha256"] = "wrong"
    with pytest.raises(ValueError, match="identity"):
        diagnostic.score_predictions(manifest, predictions, bootstrap_replicates=10)


def test_development_source_selection_rejects_reserved_path(tmp_path: Path, monkeypatch) -> None:
    reserved = tmp_path / "input_reserved" / "cord_test_0000.png"
    reserved.parent.mkdir()
    Image.new("RGB", (10, 10), "white").save(reserved)
    row = {
        "source_id": "cord-v2/test/0000", "source_path": str(reserved),
        "source_sha256": diagnostic.sha256_file(reserved),
        "evaluation_split": "development", "doc_id": "doc-a",
    }
    cohort = tmp_path / "cohort_development.jsonl"
    cohort.write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(diagnostic, "DEVELOPMENT_COHORT_SHA256", diagnostic.sha256_file(cohort))
    monkeypatch.setattr(diagnostic, "EXPECTED_DEVELOPMENT_SOURCES", 1)

    with pytest.raises(ValueError, match="not a unique frozen development image"):
        diagnostic._development_sources(cohort, tmp_path)


def test_recognition_only_stage_uses_one_result_and_keeps_failed_crop() -> None:
    class FakeEngine:
        def __call__(self, path: Path, **kwargs):
            assert path == Path("crop.png")
            assert kwargs == {"use_det": False, "use_cls": False, "use_rec": True}
            return SimpleNamespace(txts=("TOTAL",), scores=(0.9,))

    text, elapsed, score, failure = diagnostic._rapid_crop(FakeEngine(), Path("crop.png"))
    assert (text, score, failure) == ("TOTAL", 0.9, None)
    assert elapsed >= 0

    class EmptyEngine(FakeEngine):
        def __call__(self, path: Path, **kwargs):
            return SimpleNamespace(txts=(), scores=())

    text, _, score, failure = diagnostic._rapid_crop(EmptyEngine(), Path("crop.png"))
    assert text == "" and score is None
    assert failure is not None
