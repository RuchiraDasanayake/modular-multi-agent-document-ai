from __future__ import annotations

from pathlib import Path

from idpo.agents.base import AgentContext
from idpo.agents.preprocess import OcrAgent
from idpo.core.artifacts import ArtifactStore
from idpo.core.config import PipelineConfig
from idpo.core.provenance import ProvenanceRecorder


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
