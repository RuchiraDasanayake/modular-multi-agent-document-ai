"""Real PDF regressions for native text that does not represent painted content."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, FloatObject, NameObject

from idpo.agents.intake import IntakeAgent
from idpo.agents.preprocess import OcrAgent
from idpo.core import pdf_native
from idpo.product_auto import process_auto
from product_eval.execution import verify_run

METADATA = "Document Metadata REGISTRANT NAME=Wrong Company FOREIGN PRINCIPAL=N/A " * 3
VISIBLE = "Invoice Number: INV-42 Total Amount: 120.00 Customer: Example Company"


def _pdf(tmp_path: Path, *, scan=False, mode=0, alpha=1.0, x=20) -> Path:
    writer = PdfWriter()
    if scan:
        image = Image.new("RGB", (600, 800), "white")
        ImageDraw.Draw(image).text((30, 100), VISIBLE, fill="black", font_size=20)
        image_path = tmp_path / "source-image.pdf"
        image.save(image_path, "PDF", resolution=72)
        writer.append(image_path)
        page = writer.pages[0]
    else:
        page = writer.add_blank_page(width=600, height=800)
    resources = page.setdefault(NameObject("/Resources"), DictionaryObject())
    resources[NameObject("/Font")] = DictionaryObject({NameObject("/F1"): DictionaryObject({
        NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })})
    resources[NameObject("/ExtGState")] = DictionaryObject({NameObject("/GS1"): DictionaryObject({
        NameObject("/Type"): NameObject("/ExtGState"), NameObject("/ca"): FloatObject(alpha),
        NameObject("/CA"): FloatObject(alpha),
    })})
    contents = page.get_contents()
    original = contents.get_data() if contents is not None else b""
    text = METADATA if scan else VISIBLE
    stream = DecodedStreamObject()
    stream.set_data(original + f"\nq /GS1 gs BT /F1 10 Tf {mode} Tr 1 0 0 1 {x} 750 Tm ({text}) Tj ET Q".encode())
    page[NameObject("/Contents")] = writer._add_object(stream)
    target = tmp_path / "fixture.pdf"
    writer.write(target)
    writer.close()
    return target


@pytest.mark.parametrize(("mode", "alpha"), [(3, 1.0), (7, 1.0), (0, 0.0)])
def test_hidden_metadata_over_real_raster_is_rejected(tmp_path: Path, mode, alpha) -> None:
    source = _pdf(tmp_path, scan=True, mode=mode, alpha=alpha)
    original = PdfReader(source).pages[0].extract_text()
    assert "Wrong Company" in original

    doc = IntakeAgent().ingest(str(source))[0]
    page = doc.pages[0]

    assert doc.source == "scanned"
    assert page.text == page.raw_text == ""
    assert page.metadata["pdf_native_text_sha256"] == hashlib.sha256(original.encode()).hexdigest()
    assert page.metadata["pdf_native_text_rejected"] is True
    inspection = page.metadata["pdf_native_layer"]
    assert inspection["reason"] == "raster_without_painting_text"
    assert inspection["painting_text_chars"] == 0
    assert inspection["nonpainting_text_chars"] > 100
    assert inspection["image_coverage"] == 1.0


def test_normal_digital_pdf_keeps_native_text_and_never_calls_ocr(tmp_path: Path, monkeypatch) -> None:
    source = _pdf(tmp_path)
    monkeypatch.setattr(OcrAgent, "_ocr_image", lambda *args, **kwargs: pytest.fail("Unexpected OCR"))

    run = process_auto(source, run_id="digital", output_root=tmp_path / "runs")
    sidecar = next((Path(run["run_dir"]) / "docs").glob("*/result.json"))
    result = json.loads(sidecar.read_text())

    assert result["pages"] == [{"page": 1, "text": VISIBLE}]
    assert result["ocr_pages"][0]["engine"] == "native_text"
    assert result["ocr_pages"][0]["pdf_native_layer"]["requires_ocr"] is False


@pytest.mark.parametrize("failure", [False, True])
def test_product_uses_fresh_ocr_and_never_falls_back_to_rejected_metadata(tmp_path: Path, monkeypatch, failure) -> None:
    source = _pdf(tmp_path, scan=True, mode=3)
    calls = []

    def ocr(self, page, settings, engine_name="paddle"):
        calls.append(page)
        assert page.image_path.endswith(".png")
        assert page.raw_text == ""
        return ("" if failure else VISIBLE, True, "ocr_failed" if failure else None,
                {"ocr_engine_used": "fixture", "ocr_confidence": 99.0})

    monkeypatch.setattr(OcrAgent, "_ocr_image", ocr)
    run = process_auto(source, run_id="hidden", output_root=tmp_path / "runs")
    sidecar = next((Path(run["run_dir"]) / "docs").glob("*/result.json"))
    result = json.loads(sidecar.read_text())

    assert len(calls) == 1
    assert result["pages"][0]["text"] == ("" if failure else VISIBLE)
    assert "Wrong Company" not in sidecar.read_text()
    assert result["ocr_pages"][0]["pdf_native_text_rejected"] is True
    assert len(result["ocr_pages"][0]["pdf_native_text_sha256"]) == 64
    assert verify_run(run["run_dir"])["distinct_sources"] == 1


def test_off_page_text_does_not_count_as_painting_on_the_page(tmp_path: Path) -> None:
    result = pdf_native.inspect_native_layer(_pdf(tmp_path, x=900), 0)
    assert result["requires_ocr"] is True
    assert result["painting_text_chars"] == 0
    assert result["nonpainting_text_chars"] > 0


def test_inspection_limits_and_missing_pdfium_fail_closed(tmp_path: Path, monkeypatch) -> None:
    source = _pdf(tmp_path, scan=True, mode=3)
    monkeypatch.setattr(pdf_native, "MAX_OBJECTS", 1)
    assert pdf_native.inspect_native_layer(source, 0)["reason"] == "inspection_limit"
    monkeypatch.setitem(sys.modules, "pypdfium2", None)
    result = pdf_native.inspect_native_layer(source, 0)
    assert result["requires_ocr"] is True
    assert result["reason"] == "inspection_unavailable"


def test_raster_coverage_does_not_double_count_overlaps() -> None:
    assert pdf_native._union_area([(0, 0, 10, 10), (0, 0, 10, 10), (5, 0, 15, 10)]) == 150
