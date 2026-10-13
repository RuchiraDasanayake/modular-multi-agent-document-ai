from __future__ import annotations

import sys
import threading
import time
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from PIL import Image, ImageFilter, ImageOps

from idpo.agents import preprocess
from idpo.agents.base import AgentContext
from idpo.agents.preprocess import DenoiseAgent, OcrAgent, rasterize_pdf_page
from idpo.core.artifacts import ArtifactStore
from idpo.core.config import PipelineConfig
from idpo.core.provenance import ProvenanceRecorder
from idpo.core.types import Document, Page


def _ctx(tmp_path: Path, config: PipelineConfig | None = None) -> AgentContext:
    cfg = config or PipelineConfig()
    artifacts = ArtifactStore(str(tmp_path / "artifacts"))
    provenance = ProvenanceRecorder(str(tmp_path / "provenance.jsonl"))
    return AgentContext(config=cfg, artifact_store=artifacts, provenance=provenance, run_id="test-run")


def test_score_ocr_candidate_prefers_higher_confidence() -> None:
    agent = OcrAgent()
    weak = agent._score_ocr_candidate("Invoice Number: INV-1001", 15.0)  # noqa: SLF001
    strong = agent._score_ocr_candidate("Invoice Number: INV-1001", 90.0)  # noqa: SLF001
    assert strong > weak


def test_detect_rotation_degrees_parses_osd() -> None:
    agent = OcrAgent()

    class StubTesseract:
        def image_to_osd(self, img, config):  # noqa: ANN001, ARG002
            return "Orientation in degrees: 90\nRotate: 270\nOrientation confidence: 11.23"

    rotation = agent._detect_rotation_degrees(object(), StubTesseract(), "eng")  # noqa: SLF001
    assert rotation == 270


def test_extract_with_confidence_uses_tesseract_word_confidence() -> None:
    agent = OcrAgent()

    class StubTesseract:
        class Output:
            DICT = "DICT"

        def image_to_string(self, img, lang, config):  # noqa: ANN001, ARG002
            return "Total Amount: 100.00"

        def image_to_data(self, img, lang, config, output_type):  # noqa: ANN001, ARG002
            return {"conf": ["96", "80", "-1", "bad"]}

    text, conf = agent._extract_with_confidence(  # noqa: SLF001
        StubTesseract(),
        image=object(),
        lang="eng",
        config="--oem 3 --psm 6",
    )
    assert text == "Total Amount: 100.00"
    assert conf == 88.0


def test_product_tesseract_budget_is_shared_across_osd_text_and_confidence(monkeypatch) -> None:
    clock = [0.0]
    monkeypatch.setattr(preprocess.time, "monotonic", lambda: clock[0])
    observed: list[tuple[str, float]] = []

    class StubTesseract:
        class Output:
            DICT = "DICT"

        def image_to_osd(self, image, config, timeout):  # noqa: ANN001, ARG002
            observed.append(("osd", timeout))
            clock[0] += 2.0
            return "Rotate: 0"

        def image_to_string(self, image, lang, config, timeout):  # noqa: ANN001, ARG002
            observed.append(("text", timeout))
            clock[0] += 4.0
            return "Invoice Number INV-42"

        def image_to_data(self, image, lang, config, output_type, timeout):  # noqa: ANN001, ARG002
            observed.append(("data", timeout))
            return {"conf": ["90"]}

    agent = OcrAgent()
    budget = preprocess._TesseractBudget(call_timeout_s=5.0, deadline=10.0)  # noqa: SLF001
    assert agent._detect_rotation_degrees(object(), StubTesseract(), "eng", budget) == 0  # noqa: SLF001
    text, confidence = agent._extract_with_confidence(  # noqa: SLF001
        StubTesseract(), object(), "eng", "--psm 6", budget=budget,
    )
    assert (text, confidence) == ("Invoice Number INV-42", 90.0)
    assert observed == [("osd", 5.0), ("text", 5.0), ("data", 4.0)]


def test_product_page_budget_exhaustion_preserves_text_from_completed_call(monkeypatch) -> None:
    clock = [0.0]
    monkeypatch.setattr(preprocess.time, "monotonic", lambda: clock[0])

    class StubTesseract:
        class Output:
            DICT = "DICT"

        def image_to_string(self, image, lang, config, timeout):  # noqa: ANN001, ARG002
            assert timeout == 3.0
            clock[0] = 4.0
            return "Invoice Number INV-42"

        def image_to_data(self, image, lang, config, output_type, timeout):  # noqa: ANN001, ARG002
            raise AssertionError("The page budget must stop further Tesseract calls")

    with pytest.raises(preprocess._TesseractTimeout) as raised:  # noqa: SLF001
        OcrAgent()._extract_with_confidence(  # noqa: SLF001
            StubTesseract(), object(), "eng", "--psm 6",
            budget=preprocess._TesseractBudget(call_timeout_s=30.0, deadline=3.0),  # noqa: SLF001
        )
    assert raised.value.partial_text == "Invoice Number INV-42"


def test_product_engine_start_failure_is_not_silently_treated_as_empty_scan() -> None:
    class MissingTesseract:
        def image_to_string(self, image, lang, config, timeout):  # noqa: ANN001, ARG002
            raise FileNotFoundError("Tesseract binary is absent")

    agent = OcrAgent()
    with pytest.raises(FileNotFoundError, match="Tesseract binary is absent"):
        agent._extract_with_confidence(  # noqa: SLF001
            MissingTesseract(), object(), "eng", "--psm 6",
            budget=preprocess._TesseractBudget(30.0, time.monotonic() + 120.0),  # noqa: SLF001
        )
    assert agent._extract_with_confidence(  # noqa: SLF001
        MissingTesseract(), object(), "eng", "--psm 6",
    ) == ("", 0.0)


def test_product_tesseract_subprocess_timeout_is_classified(monkeypatch) -> None:
    class SlowTesseract:
        def image_to_string(self, image, lang, config, timeout):  # noqa: ANN001, ARG002
            raise RuntimeError("Tesseract process timeout")

    with pytest.raises(preprocess._TesseractTimeout):  # noqa: SLF001
        OcrAgent()._extract_with_confidence(  # noqa: SLF001
            SlowTesseract(), object(), "eng", "--psm 6",
            budget=preprocess._TesseractBudget(30.0, time.monotonic() + 120.0),  # noqa: SLF001
        )
    assert PipelineConfig().preprocessing.ocr_tesseract_call_timeout_s is None
    assert PipelineConfig().preprocessing.ocr_tesseract_page_budget_s is None


def test_tesseract_timeout_preserves_earlier_candidate_and_stops_search(monkeypatch) -> None:
    agent = OcrAgent()
    calls = 0

    def extract(pytesseract, image, lang, config, *, budget):  # noqa: ANN001, ARG001
        nonlocal calls
        calls += 1
        if calls == 1:
            return "Invoice Number INV-42", 80.0
        raise preprocess._TesseractTimeout()  # noqa: SLF001

    monkeypatch.setattr(agent, "_extract_with_confidence", extract)
    text, meta = agent._run_ocr_variants(  # noqa: SLF001
        Image.new("RGB", (20, 20), "white"), object(), None, "eng", 6, 3, [3],
        ImageOps, ImageFilter,
        budget=preprocess._TesseractBudget(call_timeout_s=30.0, deadline=time.monotonic() + 120.0),  # noqa: SLF001
    )
    assert text == "Invoice Number INV-42"
    assert meta["ocr_timeout"] is True
    assert meta["ocr_candidate_count"] == 2
    assert calls == 2


def test_product_retry_timeout_keeps_initial_text_for_review(tmp_path: Path, monkeypatch) -> None:
    config = PipelineConfig()
    config.preprocessing.ocr_initial_single_pass = True
    config.preprocessing.ocr_tesseract_call_timeout_s = 30.0
    config.preprocessing.ocr_tesseract_page_budget_s = 120.0
    agent = OcrAgent()
    calls = 0

    def ocr_image(page, settings, engine_name):  # noqa: ANN001, ARG001
        nonlocal calls
        calls += 1
        assert isinstance(settings["tesseract_budget"], preprocess._TesseractBudget)  # noqa: SLF001
        if calls == 1:
            return "Invoice Number INV-42 !!!! @@", True, None, {
                "ocr_confidence": 75.0, "ocr_engine_used": "tesseract", "ocr_candidate_count": 1,
            }
        return "", True, "ocr_timeout", {"ocr_engine_used": "tesseract", "ocr_candidate_count": 1}

    monkeypatch.setattr(agent, "_ocr_image", ocr_image)
    document = Document(
        doc_id="scan", source="scanned", path="scan.png",
        pages=[Page(number=1, text="", image_path="scan.png")],
    )
    result = agent.run({"document": document}, _ctx(tmp_path, config))
    page = result.artifacts["document"].pages[0]
    assert calls == 2
    assert result.artifacts["signal"].failure_reason == "ocr_timeout"
    assert page.text == "Invoice Number INV-42 !!!! @@"
    assert page.metadata["ocr_failure_reason"] == "ocr_timeout"
    assert page.metadata["ocr_retry_path"] == "quick_psm11_timeout"


def test_single_initial_ocr_uses_one_variant_while_default_keeps_search(monkeypatch) -> None:
    agent = OcrAgent()
    image = Image.new("RGB", (20, 20), "white")
    calls: list[str] = []

    def extract(pytesseract, candidate_image, lang, config):  # noqa: ANN001, ARG001
        calls.append(config)
        return "readable text", 35.0

    monkeypatch.setattr(agent, "_extract_with_confidence", extract)
    agent._run_ocr_variants(  # noqa: SLF001
        image, object(), None, "eng", 6, 3, [], ImageOps, ImageFilter, single_pass=True
    )
    assert len(calls) == 1
    assert "--psm 6" in calls[0]

    calls.clear()
    agent._run_ocr_variants(image, object(), None, "eng", 6, 3, [], ImageOps, ImageFilter)  # noqa: SLF001
    assert len(calls) > 1
    assert PipelineConfig().preprocessing.ocr_initial_single_pass is False


def test_bounded_full_retry_checks_eight_prioritized_candidates(monkeypatch) -> None:
    agent = OcrAgent()
    image = Image.new("RGB", (20, 20), "white")
    calls: list[str] = []

    def extract(pytesseract, candidate_image, lang, config):  # noqa: ANN001, ARG001
        calls.append(config)
        return "readable text", 35.0

    monkeypatch.setattr(agent, "_extract_with_confidence", extract)
    _, meta = agent._run_ocr_variants(  # noqa: SLF001
        image, object(), None, "eng", 6, 3, [3, 4, 11, 12], ImageOps, ImageFilter, max_candidates=8
    )

    assert len(calls) == 8
    assert [int(config.split("--psm ")[1].split()[0]) for config in calls] == [6, 11, 3, 12, 4, 6, 11, 6]
    assert meta["ocr_candidate_count"] == 8

    calls.clear()
    agent._run_ocr_variants(  # noqa: SLF001
        image, object(), None, "eng", 6, 3, [3, 4, 11, 12], ImageOps, ImageFilter
    )
    assert len(calls) == 20


def test_empty_product_initial_ocr_escalates_to_existing_retry(tmp_path: Path, monkeypatch) -> None:
    cfg = PipelineConfig()
    cfg.preprocessing.ocr_initial_single_pass = True
    cfg.preprocessing.ocr_passes = 1
    cfg.preprocessing.ocr_alt_psm = []
    ctx = _ctx(tmp_path, cfg)
    agent = OcrAgent()
    settings_seen: list[dict] = []

    def ocr_image(page, settings, engine_name):  # noqa: ANN001, ARG001
        settings_seen.append(dict(settings))
        if len(settings_seen) == 1:
            return "", True, None, {"ocr_confidence": 0.0, "ocr_variant": "base", "ocr_candidate_count": 1}
        return "Recovered invoice number INV-17", True, None, {
            "ocr_confidence": 86.0, "ocr_variant": "base", "ocr_candidate_count": 8
        }

    monkeypatch.setattr(agent, "_ocr_image", ocr_image)
    doc = Document(
        doc_id="scan", source="scanned", path="scan.png",
        pages=[Page(number=1, text="", image_path="scan.png")],
    )
    result = agent.run({"document": doc}, ctx)

    assert len(settings_seen) == 2
    assert settings_seen[0]["single_pass"] is True
    assert settings_seen[0]["alt_psm"] == []
    assert settings_seen[1]["single_pass"] is False
    assert 11 in settings_seen[1]["alt_psm"]
    assert result.artifacts["document"].pages[0].text == "Recovered invoice number INV-17"
    assert result.artifacts["document"].pages[0].metadata["ocr_rerun_used"] is True
    assert result.artifacts["document"].pages[0].metadata["ocr_retry_path"] == "full_bounded"
    assert result.artifacts["document"].pages[0].metadata["ocr_candidate_count"] == 9


def test_high_confidence_noisy_product_ocr_uses_quick_psm11_retry(tmp_path: Path, monkeypatch) -> None:
    cfg = PipelineConfig()
    cfg.preprocessing.ocr_initial_single_pass = True
    cfg.preprocessing.ocr_passes = 1
    cfg.preprocessing.ocr_alt_psm = []
    cfg.preprocessing.ocr_retry_max_candidates = 8
    agent = OcrAgent()
    settings_seen: list[dict] = []

    def ocr_image(page, settings, engine_name):  # noqa: ANN001, ARG001
        settings_seen.append(dict(settings))
        if len(settings_seen) == 1:
            return "Invoice Number INV-17 !!!! @@", True, None, {
                "ocr_confidence": 75.0, "ocr_engine_used": "tesseract", "ocr_candidate_count": 1
            }
        return "Invoice Number INV-17 Total 100", True, None, {
            "ocr_confidence": 78.0, "ocr_engine_used": "tesseract", "ocr_candidate_count": 1
        }

    monkeypatch.setattr(agent, "_ocr_image", ocr_image)
    doc = Document(
        doc_id="scan", source="scanned", path="scan.png",
        pages=[Page(number=1, text="", image_path="scan.png")],
    )
    page = agent.run({"document": doc}, _ctx(tmp_path, cfg)).artifacts["document"].pages[0]

    assert len(settings_seen) == 2
    assert settings_seen[1]["psm"] == 11
    assert settings_seen[1]["single_pass"] is True
    assert settings_seen[1]["alt_psm"] == []
    assert page.text == "Invoice Number INV-17 Total 100"
    assert page.metadata["ocr_retry_path"] == "quick_psm11"
    assert page.metadata["ocr_candidate_count"] == 2
    assert page.metadata["ocr_rerun_used"] is True


def test_noisy_quick_retry_escalates_when_still_noisy(tmp_path: Path, monkeypatch) -> None:
    cfg = PipelineConfig()
    cfg.preprocessing.ocr_initial_single_pass = True
    cfg.preprocessing.ocr_passes = 1
    cfg.preprocessing.ocr_alt_psm = []
    cfg.preprocessing.ocr_retry_max_candidates = 8
    agent = OcrAgent()
    settings_seen: list[dict] = []

    def ocr_image(page, settings, engine_name):  # noqa: ANN001, ARG001
        settings_seen.append(dict(settings))
        if len(settings_seen) < 3:
            return "Invoice Number INV-17 !!!! @@", True, None, {
                "ocr_confidence": 75.0, "ocr_engine_used": "tesseract", "ocr_candidate_count": 1
            }
        return "Invoice Number INV-17 Total 100", True, None, {
            "ocr_confidence": 90.0, "ocr_engine_used": "tesseract", "ocr_candidate_count": 8
        }

    monkeypatch.setattr(agent, "_ocr_image", ocr_image)
    doc = Document(
        doc_id="scan", source="scanned", path="scan.png",
        pages=[Page(number=1, text="", image_path="scan.png")],
    )
    page = agent.run({"document": doc}, _ctx(tmp_path, cfg)).artifacts["document"].pages[0]

    assert len(settings_seen) == 3
    assert settings_seen[2]["single_pass"] is False
    assert settings_seen[2]["max_candidates"] == 8
    assert page.metadata["ocr_retry_path"] == "quick_then_full_bounded"
    assert page.metadata["ocr_candidate_count"] == 10


def test_stale_tessdata_environment_falls_back_to_tesseract_directory(tmp_path: Path, monkeypatch) -> None:
    valid_tessdata = tmp_path / "tessdata"
    valid_tessdata.mkdir()
    monkeypatch.setenv("TESSDATA_PREFIX", str(tmp_path / "missing"))

    agent = OcrAgent()
    config = agent._tessdata_config(valid_tessdata, psm=6, oem=3)

    assert f"--tessdata-dir {agent._short_path(str(valid_tessdata))}" in config
    assert str(tmp_path / "missing") not in config


def test_native_text_detector_accepts_clean_text() -> None:
    agent = OcrAgent()
    assert agent._looks_like_native_text("Invoice Number INV-100 Total Amount 120.00 Due Date 2026-03-25")  # noqa: SLF001


def test_ocr_rerun_reason_triggers_on_noisy_text_even_above_confidence_floor(tmp_path: Path) -> None:
    agent = OcrAgent()
    ctx = _ctx(tmp_path)
    noisy_text = (
        "~~ MAGAZINE Scones\n"
        "AVOTEKCE STUDIES\n"
        "/ Brand SALE (ROR) __ Project ¢ 74-80\n"
        "Title \"MEAD IN WATER\" Total Sanple 724\n"
        "Location _QHICAGO, DALLIAS/TORT_WORTH, INDIANAPOLIS, 105 ANGELES\n"
        "MEMPHIS, PHILADELPHIA, PITTSBURG es\n"
        "Sample Description MAIN AMD PENAL MErMOL SMOXTERS\n"
        "Exe ROVEO PECALL __Covnamrrs\n"
        "Kale Sard $51) 32 (63) averaged acrozr several\n"
        "Date Sent 4/19/74\n"
        "TWiI-Tes3T\n"
        "7710205964\n"
    )

    reason = agent._ocr_rerun_reason(noisy_text, 55.65, ctx)  # noqa: SLF001

    assert reason == "noisy_text"
    assert agent._ocr_noise_ratio(noisy_text) >= 0.12  # noqa: SLF001


def test_ocr_rerun_reason_does_not_trigger_on_clean_text_above_confidence_floor(tmp_path: Path) -> None:
    agent = OcrAgent()
    ctx = _ctx(tmp_path)
    clean_text = "Invoice Number: INV-1001\nCustomer: Globex Corporation\nTotal Amount: 1200.00\n"

    reason = agent._ocr_rerun_reason(clean_text, 72.0, ctx)  # noqa: SLF001

    assert reason is None


def test_ocr_image_prefers_paddle_when_requested(monkeypatch) -> None:
    agent = OcrAgent()
    monkeypatch.setattr(
        agent,
        "_ocr_image_paddle",
        lambda path, lang: ("Total Amount: 42.00", True, None, {"ocr_confidence": 93.0, "ocr_variant": "paddle"}),
    )

    text, used, failure, meta = agent._ocr_image(  # noqa: SLF001
        Page(number=1, text="", image_path="receipt.png"),
        {"lang": "eng", "psm": 6, "oem": 3, "alt_psm": [], "dpi": 300},
        engine_name="paddle",
    )

    assert used is True
    assert failure is None
    assert text == "Total Amount: 42.00"
    assert meta["ocr_engine_used"] == "paddleocr"


def test_ocr_image_falls_back_to_tesseract_when_paddle_returns_no_text(tmp_path: Path, monkeypatch) -> None:
    agent = OcrAgent()
    image_path = tmp_path / "receipt.png"
    Image.new("RGB", (8, 8), color="white").save(image_path)

    class StubTesseract:
        class Output:
            DICT = "DICT"

    monkeypatch.setattr(
        agent,
        "_ocr_image_paddle",
        lambda path, lang: ("", True, "paddleocr_empty", {"ocr_confidence": 0.0, "ocr_variant": "paddle"}),
    )
    monkeypatch.setitem(sys.modules, "pytesseract", StubTesseract())
    monkeypatch.setattr(agent, "_configure_tesseract", lambda pytesseract: None)
    monkeypatch.setattr(agent, "_apply_orientation_correction", lambda img, pytesseract, lang: (img, 0))
    monkeypatch.setattr(
        agent,
        "_run_ocr_variants",
            lambda cleaned, pytesseract, tessdata_dir, lang, psm, oem, alt_psm, ImageOps, ImageFilter, single_pass=False, max_candidates=None: (
            "Total Amount: 42.00",
            {"ocr_psm": psm, "ocr_oem": oem, "ocr_variant": "base", "ocr_confidence": 88.0},
        ),
    )

    text, used, failure, meta = agent._ocr_image(  # noqa: SLF001
        Page(number=1, text="", image_path=str(image_path)),
        {"lang": "eng", "psm": 6, "oem": 3, "alt_psm": [], "dpi": 300},
        engine_name="paddle",
    )

    assert used is True
    assert failure is None
    assert text == "Total Amount: 42.00"
    assert meta["ocr_engine_used"] == "tesseract"


def test_rasterize_pdf_page_renders_the_requested_page_of_an_image_only_pdf(tmp_path: Path) -> None:
    import pypdfium2

    pdf_path = tmp_path / "scan.pdf"
    first = Image.new("RGB", (400, 300), "red")
    second = Image.new("RGB", (300, 500), "blue")
    second.paste("green", (25, 30, 100, 80))
    first.save(pdf_path, "PDF", resolution=100, save_all=True, append_images=[second])

    # An independent invocation of the pre-instrumentation PDFium pixel path.
    pdf = pypdfium2.PdfDocument(str(pdf_path))
    try:
        pdf_page = pdf[1]
        try:
            bitmap = pdf_page.render(scale=100 / 72)
            try:
                expected_pixels = bitmap.to_pil().convert("RGB").copy().tobytes()
            finally:
                bitmap.close()
        finally:
            pdf_page.close()
    finally:
        pdf.close()

    page = Page(number=2, text="", image_path=str(pdf_path), metadata={"file_type": ".pdf", "pdf_page_index": 1})
    rendered = rasterize_pdf_page(page, "scan", _ctx(tmp_path), dpi=100)

    assert rendered.image_path is not None and rendered.image_path.endswith(".png")
    assert rendered.metadata["pdf_source_path"] == str(pdf_path)
    assert rendered.metadata["pdf_renderer"] == "pdfium"
    assert rendered.metadata["pdf_renderer_fallback_reason"] is None
    assert rendered.metadata["pdf_page_index"] == 1
    assert rendered.metadata["pdf_rendered_dpi"] == 100
    assert rendered.metadata["pdf_render_size_px"] == [300, 500]
    with Image.open(rendered.image_path) as img:
        assert img.size == (300, 500)
        assert img.convert("RGB").tobytes() == expected_pixels


def test_rasterize_pdf_page_honors_pdf_page_rotation(tmp_path: Path) -> None:
    pypdf = pytest.importorskip("pypdf")
    source = tmp_path / "source.pdf"
    rotated = tmp_path / "rotated.pdf"
    Image.new("RGB", (400, 300), "white").save(source, "PDF", resolution=100)
    writer = pypdf.PdfWriter()
    writer.add_page(pypdf.PdfReader(source).pages[0]).rotate(90)
    with rotated.open("wb") as file:
        writer.write(file)

    page = Page(number=1, text="", image_path=str(rotated), metadata={"pdf_page_index": 0})
    rendered = rasterize_pdf_page(page, "rotated", _ctx(tmp_path), dpi=100)

    assert rendered.image_path is not None
    assert rendered.metadata["pdf_page_rotation_deg"] == 90
    with Image.open(rendered.image_path) as img:
        assert img.size == (300, 400)


def test_pdfium_failure_falls_back_to_one_based_poppler_page(tmp_path: Path, monkeypatch) -> None:
    import pypdfium2

    expected = Image.new("RGB", (30, 50), "white")
    calls = []

    def unavailable(pdf_path):  # noqa: ANN001, ARG001
        raise RuntimeError("PDFium unavailable")

    def poppler(pdf_path, **kwargs):  # noqa: ANN001
        calls.append((pdf_path, kwargs))
        return [expected]

    monkeypatch.setattr(pypdfium2, "PdfDocument", unavailable)
    monkeypatch.setattr(OcrAgent, "_find_poppler_path", lambda self: str(tmp_path))
    monkeypatch.setattr("pdf2image.convert_from_path", poppler)

    actual = preprocess._render_pdf_page("scan.pdf", page_index=1, dpi=150)  # noqa: SLF001

    assert actual.image is expected
    assert actual.renderer == "poppler"
    assert actual.fallback_reason == "pdfium_open_failed"
    assert calls == [("scan.pdf", {"first_page": 2, "last_page": 2, "poppler_path": str(tmp_path), "dpi": 150,
                                  "size": 3464})]


def test_both_pdf_renderers_fail_with_bounded_provenance(tmp_path: Path, monkeypatch) -> None:
    import pypdfium2

    def fail(*args, **kwargs):  # noqa: ANN002, ANN003, ARG001
        raise RuntimeError("private/customer.pdf: sensitive document text")

    monkeypatch.setattr(pypdfium2, "PdfDocument", fail)
    monkeypatch.setattr("pdf2image.convert_from_path", fail)
    page = Page(number=1, text="", image_path=str(tmp_path / "private.pdf"), metadata={"pdf_page_index": 0})

    rendered = rasterize_pdf_page(page, "private", _ctx(tmp_path), dpi=150)

    assert rendered.image_path == page.image_path
    assert rendered.metadata["pdf_renderer"] == "none"
    assert rendered.metadata["pdf_renderer_fallback_reason"] == "poppler_failed"
    assert rendered.metadata["pdf_render_size_px"] is None
    assert "private" not in str(rendered.metadata["pdf_renderer_fallback_reason"])


def test_direct_pdf_poppler_provenance_only_after_a_page_is_rendered(monkeypatch) -> None:
    from PIL import ImageSequence

    image = Image.new("RGB", (40, 70), "white")
    agent = OcrAgent()
    monkeypatch.setattr("pdf2image.convert_from_path", lambda *args, **kwargs: [image])
    monkeypatch.setattr(agent, "_find_poppler_path", lambda: None)
    monkeypatch.setattr(agent, "_normalize_image", lambda frame, *args: frame)
    monkeypatch.setattr(agent, "_apply_orientation_correction", lambda frame, *args: (frame, 0))
    monkeypatch.setattr(agent, "_run_ocr_variants", lambda *args, **kwargs: ("Invoice 42", {}))
    page = Page(number=2, text="", image_path="private.pdf", metadata={
        "pdf_page_index": 1,
        "pdf_page_rotation_deg": 90,
        "pdf_renderer": "none",
        "pdf_renderer_fallback_reason": "poppler_failed",
    })

    text, failure, meta = agent._ocr_pdf_page(  # noqa: SLF001
        "private.pdf", page, object(), Image, ImageSequence, None, "eng", 6, 3, [], 150
    )

    assert (text, failure) == ("Invoice 42", None)
    assert meta["pdf_renderer"] == "poppler_direct"
    assert meta["pdf_page_index"] == 1
    assert meta["pdf_page_rotation_deg"] == 90
    assert meta["pdf_rendered_dpi"] is None  # A nonexistent fixture cannot establish a page-to-pixel scale.
    assert meta["pdf_render_plan"]["requested_dpi"] == 150
    assert meta["pdf_render_size_px"] == [40, 70]

    monkeypatch.setattr("pdf2image.convert_from_path", lambda *args, **kwargs: [])
    monkeypatch.setattr(Image, "open", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("failed")))
    _, failure, meta = agent._ocr_pdf_page(  # noqa: SLF001
        "private.pdf", page, object(), Image, ImageSequence, None, "eng", 6, 3, [], 150
    )
    assert failure == "pdf_render_failed"
    assert "pdf_renderer" not in meta


def test_ocr_run_preserves_direct_pdf_renderer_metadata(tmp_path: Path, monkeypatch) -> None:
    agent = OcrAgent()
    page = Page(number=1, text="", image_path="scan.pdf", metadata={
        "pdf_page_index": 0,
        "pdf_renderer": "none",
        "pdf_renderer_fallback_reason": "poppler_failed",
    })
    monkeypatch.setattr(preprocess, "rasterize_pdf_page", lambda page, doc_id, ctx, dpi: page)
    monkeypatch.setattr(agent, "_ocr_image", lambda page, settings, engine_name: (
        "Invoice Number INV-42", True, None, {
            "ocr_engine_used": "tesseract",
            "ocr_confidence": 90.0,
            "pdf_renderer": "poppler_direct",
            "pdf_renderer_fallback_reason": "poppler_failed",
            "pdf_page_index": 0,
            "pdf_page_rotation_deg": 90,
            "pdf_rendered_dpi": 300,
            "pdf_render_size_px": [500, 700],
        }
    ))
    document = Document(doc_id="scan", source="scanned", path="scan.pdf", pages=[page])

    result = agent.run({"document": document}, _ctx(tmp_path))
    metadata = result.artifacts["document"].pages[0].metadata

    assert metadata["pdf_renderer"] == "poppler_direct"
    assert metadata["pdf_page_rotation_deg"] == 90
    assert metadata["pdf_render_size_px"] == [500, 700]


def test_pdfium_render_is_serialized_and_image_does_not_share_bitmap_buffer(monkeypatch) -> None:
    import pypdfium2

    state = {"active": 0, "peak": 0}
    guard = threading.Lock()

    class Bitmap:
        def __init__(self) -> None:
            self.image = Image.new("RGB", (10, 10), "white")

        def to_pil(self):
            return self.image

        def close(self) -> None:
            self.image.paste("black", (0, 0, 10, 10))

    class PdfPage:
        def get_size(self):
            return 7.2, 7.2

        def get_bbox(self):
            return 0, 0, 7.2, 7.2

        def get_objects(self, max_depth):
            return iter(())

        def render(self, scale):  # noqa: ANN001
            assert scale == 100 / 72
            time.sleep(0.01)
            return Bitmap()

        def close(self) -> None:
            pass

    class PdfDocument:
        def __init__(self, path):  # noqa: ANN001, ARG002
            with guard:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])

        def __len__(self) -> int:
            return 1

        def __getitem__(self, index):  # noqa: ANN001
            assert index == 0
            return PdfPage()

        def close(self) -> None:
            with guard:
                state["active"] -= 1

    monkeypatch.setattr(pypdfium2, "PdfDocument", PdfDocument)
    with ThreadPoolExecutor(max_workers=4) as pool:
        images = list(pool.map(lambda _: preprocess._render_pdf_page("scan.pdf", 0, 100), range(4)))

    assert state == {"active": 0, "peak": 1}
    assert all(result.renderer == "pdfium" and result.image.getpixel((0, 0)) == (255, 255, 255) for result in images)


def test_rasterize_pdf_page_leaves_image_pages_untouched(tmp_path: Path) -> None:
    page = Page(number=1, text="", image_path=str(tmp_path / "receipt.png"))
    assert rasterize_pdf_page(page, "receipt", _ctx(tmp_path)) is page


def test_denoise_keeps_thin_strokes_on_low_resolution_scans(tmp_path: Path) -> None:
    source = tmp_path / "fax.png"
    img = Image.new("L", (754, 1000), 255)
    for x in range(100, 600):
        img.putpixel((x, 500), 0)
    img.save(source)

    denoised = DenoiseAgent()._denoise_image(str(source), 1, "fax", _ctx(tmp_path))

    assert denoised is not None
    with Image.open(denoised) as out:
        assert out.size == (1508, 2000)
        assert min(out.getpixel((700, y)) for y in range(996, 1006)) < 128


def test_denoise_keeps_size_of_high_resolution_scans(tmp_path: Path) -> None:
    source = tmp_path / "scan.png"
    Image.new("L", (1700, 2200), 255).save(source)

    denoised = DenoiseAgent()._denoise_image(str(source), 1, "scan", _ctx(tmp_path))

    assert denoised is not None
    with Image.open(denoised) as out:
        assert out.size == (1700, 2200)


def _paddle_item(left: float, top: float, right: float, bottom: float, text: str) -> list[object]:
    return [[[left, top], [right, top], [right, bottom], [left, bottom]], (text, 0.98)]


def test_paddle_text_keeps_labels_and_values_on_the_same_row() -> None:
    # Right-column amounts sit a few pixels above their labels, as on photographed receipts.
    result = [[
        _paddle_item(300, 98, 380, 118, "23.000"),
        _paddle_item(20, 100, 90, 120, "Total"),
        _paddle_item(300, 137, 380, 157, "50.000"),
        _paddle_item(20, 140, 90, 160, "Tunai"),
        _paddle_item(300, 158, 380, 178, "27.000"),
        _paddle_item(20, 162, 100, 182, "Kembali"),
    ]]

    text, confidence = OcrAgent()._extract_paddle_text(result)  # noqa: SLF001

    assert text.splitlines() == ["Total  23.000", "Tunai  50.000", "Kembali  27.000"]
    assert round(confidence) == 98


def test_paddle_text_keeps_detector_order_when_boxes_have_no_geometry() -> None:
    result = [[[None, ("first", 0.9)], [None, ("second", 0.9)]]]

    text, _ = OcrAgent()._extract_paddle_text(result)  # noqa: SLF001

    assert text.splitlines() == ["first", "second"]


def test_recognition_widths_are_padded_up_to_fixed_buckets() -> None:
    widths: list[int] = []

    class StubRecognizer:
        rec_image_shape = [3, 48, 320]

        def resize_norm_img(self, img, max_wh_ratio):  # noqa: ANN001, ARG002
            widths.append(int(48 * max_wh_ratio))
            return img

    engine = types.SimpleNamespace(text_recognizer=StubRecognizer())
    preprocess._bucket_recognition_widths(engine)  # noqa: SLF001

    for raw_width in (320, 330, 640, 641, 2399):
        engine.text_recognizer.resize_norm_img("crop", raw_width / 48)

    assert widths == [320, 640, 640, 960, 2560]


def test_paddle_engine_is_shared_across_threads_and_never_runs_concurrently(tmp_path: Path, monkeypatch) -> None:
    created: list[dict[str, object]] = []
    state = {"active": 0, "peak": 0}
    guard = threading.Lock()

    class StubPaddleOCR:
        def __init__(self, **kwargs) -> None:  # noqa: ANN003
            created.append(kwargs)

        def ocr(self, path, cls):  # noqa: ANN001, ARG002
            with guard:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
            time.sleep(0.02)
            with guard:
                state["active"] -= 1
            return [[_paddle_item(20, 100, 90, 120, "Total"), _paddle_item(300, 100, 380, 120, "23.000")]]

    monkeypatch.setitem(sys.modules, "paddleocr", types.SimpleNamespace(PaddleOCR=StubPaddleOCR))
    monkeypatch.setattr(preprocess, "_PADDLE_ENGINES", {})
    images = []
    for index in range(4):
        image_path = tmp_path / f"receipt_{index}.png"
        Image.new("RGB", (40, 40), color="white").save(image_path)
        images.append(str(image_path))
    agent = OcrAgent()

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda path: agent._ocr_image_paddle(path, "eng"), images))  # noqa: SLF001

    assert [text for text, _, _, _ in results] == ["Total  23.000"] * 4
    assert len(created) == 1
    assert created[0]["rec_batch_num"] == 1
    assert state["peak"] == 1


def test_paddle_text_does_not_merge_tightly_spaced_lines() -> None:
    result = [[
        _paddle_item(20, 100, 200, 114, "Dear Dr. Smith,"),
        _paddle_item(20, 116, 260, 130, "Thank you for the report."),
    ]]

    text, _ = OcrAgent()._extract_paddle_text(result)  # noqa: SLF001

    assert text.splitlines() == ["Dear Dr. Smith,", "Thank you for the report."]
