from __future__ import annotations

from idpo.agents.preprocess import OcrAgent


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
