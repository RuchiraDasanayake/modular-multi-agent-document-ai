from __future__ import annotations

import sys
import threading
import time
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from idpo.agents import preprocess
from idpo.agents.base import AgentContext
from idpo.agents.preprocess import DenoiseAgent, OcrAgent, rasterize_pdf_page
from idpo.core.artifacts import ArtifactStore
from idpo.core.config import PipelineConfig
from idpo.core.provenance import ProvenanceRecorder
from idpo.core.types import Page


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
        lambda cleaned, pytesseract, tessdata_dir, lang, psm, oem, alt_psm, ImageOps, ImageFilter: (
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
    pdf_path = tmp_path / "scan.pdf"
    first = Image.new("RGB", (400, 300), "white")
    second = Image.new("RGB", (300, 500), "white")
    first.save(pdf_path, "PDF", resolution=100, save_all=True, append_images=[second])

    page = Page(number=2, text="", image_path=str(pdf_path), metadata={"file_type": ".pdf", "pdf_page_index": 1})
    rendered = rasterize_pdf_page(page, "scan", _ctx(tmp_path), dpi=100)

    assert rendered.image_path is not None and rendered.image_path.endswith(".png")
    assert rendered.metadata["pdf_source_path"] == str(pdf_path)
    with Image.open(rendered.image_path) as img:
        assert img.size == (300, 500)


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
