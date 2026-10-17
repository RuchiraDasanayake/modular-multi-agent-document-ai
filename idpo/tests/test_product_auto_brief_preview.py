"""Schema samples reuse product intake/OCR; fixtures contain no benchmark data."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from idpo.agents import intake, preprocess
from idpo.agents.intake import IntakeAgent
from idpo.agents.preprocess import OcrAgent
from idpo.product_auto import brief_draft, rapid_ocr
from idpo.product_auto.brief_draft import (
    SAMPLE_OCR_TIMEOUT_S,
    SAMPLE_TOTAL_TIMEOUT_S,
    SampleBudgetExceeded,
    suggest_fields,
)
from idpo.tests.test_pdf_native_layer import METADATA, VISIBLE, _pdf
from idpo.tests.test_product_auto_brief_draft import FakeModel, _reply, _request


def _preview_reply() -> str:
    # These tests exercise sample intake, not model-proposed example values.
    payload = json.loads(_reply())
    payload["fields"][0]["example_values"] = []
    return json.dumps(payload)


@pytest.fixture(autouse=True)
def preview_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("IDPO_DATA_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("IDPO_AUTO_OCR_ENGINE", "rapidocr")


def _mixed_pdf(tmp_path: Path, *, scanned_first: bool = False) -> Path:
    digital_dir, scanned_dir = tmp_path / "digital", tmp_path / "scanned"
    digital_dir.mkdir()
    scanned_dir.mkdir()
    digital = _pdf(digital_dir)
    scanned = _pdf(scanned_dir, scan=True, mode=3)
    with PdfWriter() as writer:
        for path in ([scanned, digital] if scanned_first else [digital, scanned]):
            writer.append(path)
        writer.append(scanned)  # This third page must not be inspected or rendered by preview.
        target = tmp_path / "mixed.pdf"
        writer.write(target)
    return target


def test_hidden_metadata_is_rejected_before_draft_model(tmp_path, monkeypatch):
    source = _pdf(tmp_path, scan=True, mode=3)
    assert METADATA in PdfReader(source).pages[0].extract_text()
    calls = []

    def ocr(self, page, settings, engine_name="paddle"):
        calls.append(page)
        assert engine_name == "rapidocr"
        assert settings["single_pass"] is True
        assert settings["rapidocr_page_budget_s"] == SAMPLE_OCR_TIMEOUT_S
        assert page.raw_text == ""
        assert page.metadata["pdf_native_text_rejected"] is True
        assert page.metadata["pdf_native_layer"]["reason"] == "raster_without_painting_text"
        assert Path(page.image_path).suffix == ".png"
        assert Path(page.image_path).is_file()
        return VISIBLE, True, None, {"ocr_confidence": 99, "ocr_engine_used": "rapidocr"}

    monkeypatch.setattr(OcrAgent, "_ocr_image", ocr)
    model = FakeModel(_preview_reply())
    result = suggest_fields(_request(source), model)
    assert len(calls) == len(model.calls) == 1
    prompt = json.loads(model.calls[0][1])
    assert prompt["sample_excerpts_untrusted"][0]["excerpt"] == VISIBLE
    assert "Wrong Company" not in model.calls[0][1]
    assert result["provenance"]["samples"][0]["parser_id"] == "intake-pdf-preview-rapidocr-v1"
    assert not Path(calls[0].image_path).exists()
    assert list((tmp_path / "runtime" / "brief_previews").iterdir()) == []


@pytest.mark.parametrize("scanned_first", [False, True])
def test_mixed_pages_are_handled_individually_and_third_is_not_inspected(tmp_path, monkeypatch, scanned_first):
    source = _mixed_pdf(tmp_path, scanned_first=scanned_first)
    inspections, ocr_pages = [], []
    real_inspect = intake.inspect_native_layer

    def inspect(path, index):
        inspections.append(index)
        return real_inspect(path, index)

    def ocr(self, page, settings, engine_name="paddle"):
        ocr_pages.append(page.number)
        return "Visible scanned page invoice total 42.00", True, None, {"ocr_confidence": 99}

    monkeypatch.setattr(intake, "inspect_native_layer", inspect)
    monkeypatch.setattr(OcrAgent, "_ocr_image", ocr)
    model = FakeModel(_preview_reply())
    suggest_fields(_request(source), model)
    assert inspections == [0, 1]
    assert ocr_pages == ([1] if scanned_first else [2])
    text = json.loads(model.calls[0][1])["sample_excerpts_untrusted"][0]["excerpt"]
    expected = ["Visible scanned page invoice total 42.00", VISIBLE]
    assert text.splitlines() == (expected if scanned_first else expected[::-1])


def test_normal_digital_pdf_never_calls_ocr(tmp_path, monkeypatch):
    source = _pdf(tmp_path)
    monkeypatch.setattr(OcrAgent, "_ocr_image", lambda *a, **kw: pytest.fail("Unexpected OCR"))
    model = FakeModel(_preview_reply())
    suggest_fields(_request(source), model)
    assert json.loads(model.calls[0][1])["sample_excerpts_untrusted"][0]["excerpt"] == VISIBLE


def test_full_intake_still_reads_all_pages_with_same_prefix_metadata(tmp_path):
    source = _mixed_pdf(tmp_path)
    agent = IntakeAgent()
    full = agent.ingest(str(source))[0]
    preview = agent.preview_pdf(source)
    assert len(full.pages) == 3
    assert len(preview.pages) == 2
    assert full.pages[:2] == preview.pages
    assert full.doc_id == preview.doc_id
    assert full.source == preview.source == "digital"
    assert full.path == preview.path == str(source)
    assert full.pages[2].metadata["pdf_native_text_rejected"] is True


def test_51_page_pdf_rejected_before_text_extraction_render_or_model(tmp_path, monkeypatch):
    source = tmp_path / "too-many.pdf"
    with PdfWriter() as writer:
        for _ in range(51):
            writer.add_blank_page(width=100, height=100)
        writer.write(source)
    from pypdf._page import PageObject

    def unexpected(*args, **kwargs):
        pytest.fail("Oversized preview reached page work")

    monkeypatch.setattr(PageObject, "extract_text", unexpected)
    monkeypatch.setattr(intake, "inspect_native_layer", unexpected)
    monkeypatch.setattr(preprocess, "rasterize_pdf_page", unexpected)
    model = FakeModel(_preview_reply())
    with pytest.raises(ValueError, match="50-page"):
        suggest_fields(_request(source), model)
    assert model.calls == []


@pytest.mark.parametrize("reason", ["rapidocr_memory_limit", "rapidocr_timeout"])
def test_actual_adapter_resource_failure_prevents_model_and_cleans_raster(tmp_path, monkeypatch, reason):
    source = _pdf(tmp_path, scan=True, mode=3)
    monkeypatch.setenv("IDPO_RAPIDOCR_PYTHON", sys.executable)
    monkeypatch.setenv("IDPO_RAPIDOCR_WORK_DIR", str(tmp_path))
    called = []

    def recognize(image, *, config):
        called.append(image.size)
        assert SAMPLE_OCR_TIMEOUT_S == 30.0
        assert config.timeout_s == SAMPLE_OCR_TIMEOUT_S
        raise rapid_ocr.RapidOcrError(reason)

    monkeypatch.setattr(rapid_ocr, "recognize_image", recognize)
    model = FakeModel(_preview_reply())
    with pytest.raises(ValueError, match="Sample OCR failed"):
        suggest_fields(_request(source), model)
    assert len(called) == 1
    assert model.calls == []
    assert list((tmp_path / "runtime" / "brief_previews").iterdir()) == []


def test_total_sample_budget_stops_before_next_sample_and_model(tmp_path, monkeypatch):
    first, second = tmp_path / "first.txt", tmp_path / "second.txt"
    first.write_text("First total 123.45", encoding="utf-8")
    second.write_text("Second total 123.45", encoding="utf-8")
    request = _request(first)
    request["samples"].append({"file_id": "c" * 32,
                               "source_sha256": brief_draft._sha256_file(second), "path": str(second)})
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(brief_draft, "time", SimpleNamespace(monotonic=lambda: clock.now))
    parsed = []

    def parse(path, _digest, *, deadline=None):
        parsed.append(path.name)
        assert deadline == SAMPLE_TOTAL_TIMEOUT_S
        clock.now = SAMPLE_TOTAL_TIMEOUT_S + 0.1
        return "First total 123.45", "utf8-text"

    monkeypatch.setattr(brief_draft, "_sample_text", parse)
    model = FakeModel(_preview_reply())
    with pytest.raises(SampleBudgetExceeded):
        suggest_fields(request, model)
    assert parsed == ["first.txt"]
    assert model.calls == []


def test_budget_exhaustion_has_safe_cli_diagnostic(tmp_path, monkeypatch, capsys):
    sample = tmp_path / "sample.txt"
    sample.write_text("Total 123.45", encoding="utf-8")
    request = _request(sample)
    request_file = tmp_path / "request.json"
    raw = json.dumps(request).encode()
    request_file.write_bytes(raw)
    model = FakeModel(_preview_reply())
    monkeypatch.setattr(brief_draft, "OpenAICompatibleChat", lambda **_: model)
    def exhausted(*_, **__):
        raise SampleBudgetExceeded()

    monkeypatch.setattr(brief_draft, "_sample_text", exhausted)
    assert brief_draft.main(["--request-file", str(request_file), "--request-sha256",
                             brief_draft._sha256_file(request_file)]) == 1
    assert json.loads(capsys.readouterr().err) == {"stage": "sample", "code": "budget_exhausted"}
    assert model.calls == []


def test_ocr_page_budget_uses_remaining_shared_deadline(tmp_path, monkeypatch):
    scanned_dir = tmp_path / "scanned"
    scanned_dir.mkdir()
    scanned = _pdf(scanned_dir, scan=True, mode=3)
    source = tmp_path / "two-scans.pdf"
    with PdfWriter() as writer:
        writer.append(scanned)
        writer.append(scanned)
        writer.write(source)
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(brief_draft, "time", SimpleNamespace(monotonic=lambda: clock.now))
    observed = []

    def ocr(self, page, settings, engine_name="paddle"):
        observed.append((page.number, settings["rapidocr_page_budget_s"]))
        if len(observed) == 1:
            clock.now = 35.0
        return "Visible scanned total 123.45", True, None, {"ocr_confidence": 99}

    monkeypatch.setattr(OcrAgent, "_ocr_image", ocr)
    model = FakeModel(_preview_reply())
    suggest_fields(_request(source), model)
    assert observed == [(1, 30.0), (2, 25.0)]
    assert len(model.calls) == 1


def test_exhausted_budget_does_not_skip_a_selected_scan_page(tmp_path, monkeypatch):
    scanned_dir = tmp_path / "scanned"
    scanned_dir.mkdir()
    scanned = _pdf(scanned_dir, scan=True, mode=3)
    source = tmp_path / "two-scans.pdf"
    with PdfWriter() as writer:
        writer.append(scanned)
        writer.append(scanned)
        writer.write(source)
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(brief_draft, "time", SimpleNamespace(monotonic=lambda: clock.now))
    observed = []

    def ocr(self, page, settings, engine_name="paddle"):
        observed.append(page.number)
        clock.now = SAMPLE_TOTAL_TIMEOUT_S
        return "Visible scanned total 123.45", True, None, {"ocr_confidence": 99}

    monkeypatch.setattr(OcrAgent, "_ocr_image", ocr)
    model = FakeModel(_preview_reply())
    with pytest.raises(SampleBudgetExceeded):
        suggest_fields(_request(source), model)
    assert observed == [1]
    assert model.calls == []


def test_unreadable_preview_prevents_model(tmp_path, monkeypatch):
    source = _pdf(tmp_path, scan=True, mode=3)
    monkeypatch.setattr(OcrAgent, "_ocr_image", lambda *a, **kw: ("", True, None, {}))
    model = FakeModel(_preview_reply())
    with pytest.raises(ValueError, match="no readable text"):
        suggest_fields(_request(source), model)
    assert model.calls == []


@pytest.mark.parametrize("engine", ["rapidocr", "tesseract", ""])
def test_image_uses_configured_engine_and_default(tmp_path, monkeypatch, engine):
    source = tmp_path / "image.png"
    Image.new("RGB", (100, 100), "white").save(source)
    monkeypatch.setenv("IDPO_AUTO_OCR_ENGINE", engine)
    observed = []

    def ocr(self, page, settings, engine_name="paddle"):
        observed.append(engine_name)
        return VISIBLE, True, None, {"ocr_confidence": 99}

    monkeypatch.setattr(OcrAgent, "_ocr_image", ocr)
    result = suggest_fields(_request(source), FakeModel(_preview_reply()))
    expected = engine or "tesseract"
    assert observed == [expected]
    assert result["provenance"]["samples"][0]["parser_id"] == f"intake-image-preview-{expected}-v1"


def test_invalid_engine_prevents_model(tmp_path, monkeypatch):
    source = _pdf(tmp_path)
    monkeypatch.setenv("IDPO_AUTO_OCR_ENGINE", "misspelled-engine")
    model = FakeModel(_preview_reply())
    with pytest.raises(ValueError, match="Unsupported sample OCR engine"):
        suggest_fields(_request(source), model)
    assert model.calls == []


@pytest.mark.parametrize("page_limit,max_pages", [(0, 50), (3, 2), (True, 50), (2, 0)])
def test_pdf_preview_bounds_are_validated_before_file_access(page_limit, max_pages):
    with pytest.raises(ValueError, match="Invalid PDF preview"):
        IntakeAgent().preview_pdf(Path("unused.pdf"), page_limit=page_limit, max_document_pages=max_pages)


def test_missing_page_count_parser_fails_closed_for_preview_only(tmp_path, monkeypatch):
    source = _pdf(tmp_path)
    monkeypatch.setitem(sys.modules, "pypdf", None)
    with pytest.raises(ValueError, match="page-count parser"):
        IntakeAgent().preview_pdf(source)
    # The existing full-intake fallback remains unchanged.
    full = IntakeAgent().ingest(str(source))[0]
    assert len(full.pages) == 1
    assert full.source == "scanned"
    assert full.pages[0].image_path == str(source)
