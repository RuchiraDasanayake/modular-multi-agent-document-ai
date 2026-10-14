"""Explicit RapidOCR through preprocessing and durable product artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from idpo.agents import preprocess
from idpo.agents.base import AgentContext
from idpo.agents.preprocess import OcrAgent
from idpo.core.artifacts import ArtifactStore
from idpo.core.config import PipelineConfig
from idpo.core.provenance import ProvenanceRecorder
from idpo.core.types import Document, Page
from idpo.product_auto import process_auto, rapid_ocr
from idpo.tests.test_pdf_native_layer import _pdf
from product_eval.execution import verify_run


def _sidecar(run):
    path = next((Path(run["run_dir"]) / "docs").glob("*/result.json"))
    return json.loads(path.read_text(encoding="utf-8"))


def _forbid_legacy(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("RapidOCR must not invoke Tesseract, retry OCR, or repair source text")
    monkeypatch.setattr(OcrAgent, "_configure_tesseract", forbidden)
    monkeypatch.setattr(OcrAgent, "_build_retry_settings", forbidden)
    monkeypatch.setattr(preprocess, "degarble", forbidden)


def test_rapidocr_preserves_exact_text_once_even_when_legacy_rules_want_repairs(tmp_path, monkeypatch):
    source = tmp_path / "source.png"
    Image.new("RGB", (200, 100)).save(source)
    monkeypatch.setenv("IDPO_RAPIDOCR_PYTHON", sys.executable)
    _forbid_legacy(monkeypatch)
    monkeypatch.setattr(preprocess, "is_garbled", lambda text: True)
    monkeypatch.setattr(OcrAgent, "_ocr_rerun_reason", lambda *_: "noisy_text")
    text = "  Amount:  10.00 \nkept \u00a3\U0001f642 "
    line = {"text": text, "start": 0, "end": len(text)}
    provenance = {"text_sha256": hashlib.sha256(text.encode()).hexdigest()}
    calls = []

    def recognize(image, *, config):
        calls.append((image.size, config.timeout_s))
        return rapid_ocr.RapidOcrResult(text, {"ocr_engine_used": "rapidocr", "ocr_confidence": 30,
                                             "ocr_lines": [line], "ocr_provenance": provenance})
    monkeypatch.setattr(rapid_ocr, "recognize_image", recognize)
    config = PipelineConfig()
    config.preprocessing.ocr_engine = "rapidocr"
    config.preprocessing.ocr_max_reruns_per_page = 3
    config.preprocessing.ocr_tesseract_page_budget_s = 7
    ctx = AgentContext(config, ArtifactStore(str(tmp_path / "artifacts")),
                       ProvenanceRecorder(str(tmp_path / "events.jsonl")), run_id="one-pass")
    document = Document("one", "scanned", str(source), [Page(1, "", image_path=str(source))])
    result = OcrAgent().run({"document": document}, ctx)
    page = result.artifacts["document"].pages[0]
    assert calls == [((200, 100), 7)]
    assert page.text == text
    assert page.metadata["ocr_lines"] == [line]
    assert page.metadata["ocr_provenance"] == provenance
    assert page.metadata["ocr_rerun_attempted"] is False


@pytest.mark.parametrize("reason", ["rapidocr_not_configured", "rapidocr_timeout", "rapidocr_model_mismatch"])
def test_product_failure_never_uses_hidden_pdf_text_or_accepts_values(tmp_path, monkeypatch, reason):
    source = _pdf(tmp_path, scan=True, mode=3)
    _forbid_legacy(monkeypatch)
    monkeypatch.setenv("IDPO_RAPIDOCR_PYTHON", sys.executable)
    calls = []
    def fail(image, *, config):
        calls.append(image.size)
        raise rapid_ocr.RapidOcrError(reason)
    monkeypatch.setattr(rapid_ocr, "recognize_image", fail)
    run = process_auto(source, run_id="failure", ocr_engine="rapidocr", output_root=tmp_path / "runs")
    result = _sidecar(run)
    assert len(calls) == 1
    assert result["candidate"]["document_status"] == "failed"
    assert result["candidate"]["extracted_values"] == []
    assert result["pages"] == [{"page": 1, "text": ""}]
    assert result["reason"] == reason
    page = result["ocr_pages"][0]
    assert page["engine"] == "rapidocr" and page["failure_reason"] == reason
    assert page["pdf_native_text_rejected"] is True
    assert page["pdf_render_plan"]["max_edge_px"] == 4096
    assert page["rerun_attempted"] is False
    assert verify_run(run["run_dir"])["distinct_sources"] == 1


def test_multi_frame_container_and_unknown_engine_fail_explicitly(tmp_path, monkeypatch):
    monkeypatch.setenv("IDPO_RAPIDOCR_PYTHON", sys.executable)
    source = tmp_path / "two.tiff"
    image = Image.new("RGB", (80, 80), "white")
    image.save(source, save_all=True, append_images=[image])
    monkeypatch.setattr(OcrAgent, "run", lambda *_a, **_k: pytest.fail("Reject multiple frames before OCR"))
    monkeypatch.setattr(rapid_ocr, "recognize_image", lambda *_a, **_k: pytest.fail("Cannot drop another frame"))
    run = process_auto(source, ocr_engine="rapidocr", output_root=tmp_path / "runs")
    result = _sidecar(run)
    assert result["reason"] == "multi_frame_image_unsupported"
    assert result["candidate"]["document_status"] == "unsupported"
    assert result["pages"] == [] and result["model_calls"] == []
    assert verify_run(run["run_dir"])["distinct_sources"] == 1
    with pytest.raises(ValueError, match="Unsupported product OCR engine"):
        process_auto(source, ocr_engine="typo", output_root=tmp_path / "runs")


def test_live_cli_and_scanned_pdf_store_source_bound_rapidocr_lines(tmp_path, monkeypatch):
    python, font = os.environ.get("TEST_RAPIDOCR_PYTHON"), os.environ.get("TEST_RAPIDOCR_FONT")
    if not python or not font:
        pytest.skip("explicit isolated runtime and local font are required")
    monkeypatch.setenv("IDPO_RAPIDOCR_PYTHON", python)
    monkeypatch.setenv("IDPO_RAPIDOCR_WORK_DIR", str(tmp_path))
    monkeypatch.setenv("IDPO_DATA_DIR", str(tmp_path / "data"))
    _forbid_legacy(monkeypatch)
    image = Image.new("RGB", (1100, 340), "white")
    draw = ImageDraw.Draw(image)
    chosen = ImageFont.truetype(font, 54)
    draw.text((40, 60), "Invoice Number: INV-42", font=chosen, fill="black")
    draw.text((40, 190), "Total Amount: 120.00", font=chosen, fill="black")
    png, pdf = tmp_path / "source.png", tmp_path / "source.pdf"
    image.save(png)
    image.save(pdf, "PDF", resolution=100)
    completed = subprocess.run([sys.executable, "-m", "idpo.cli", "process-auto", "--input", str(png),
                                "--ocr-engine", "rapidocr", "--run-id", "real-cli"],
                               capture_output=True, text=True, timeout=45, check=True)
    cli_run = json.loads(completed.stdout)
    pdf_run = process_auto(pdf, run_id="real-pdf", ocr_engine="rapidocr", output_root=tmp_path / "runs")
    for source, run in ((png, cli_run), (pdf, pdf_run)):
        result = _sidecar(run)
        assert result["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
        assert result["candidate"]["document_status"] == "needs_review"
        assert all(value["status"] != "accepted" for value in result["candidate"]["extracted_values"])
        page_text = result["pages"][0]["text"]
        assert "INV-42" in page_text and "120.00" in page_text
        ocr = result["ocr_pages"][0]
        assert ocr["engine"] == "rapidocr" and not ocr["rerun_attempted"]
        assert ocr["ocr_provenance"]["text_sha256"] == hashlib.sha256(page_text.encode()).hexdigest()
        for line in ocr["ocr_lines"]:
            assert page_text[line["start"]:line["end"]] == line["text"]
        if source == pdf:
            assert ocr["ocr_provenance"]["image_size_px"] == ocr["pdf_render_size_px"]
            assert ocr["pdf_render_plan"]["effective_dpi"] == pytest.approx(100)
        run_record = json.loads((Path(run["run_dir"]) / "run.json").read_text())
        assert run_record["ocr_profile"] == "rapidocr_single_bounded_page"
        assert run_record["ocr_retry_max_candidates"] == 0
        assert run_record["model_call_count"] == 0
        assert verify_run(run["run_dir"])["distinct_sources"] == 1
