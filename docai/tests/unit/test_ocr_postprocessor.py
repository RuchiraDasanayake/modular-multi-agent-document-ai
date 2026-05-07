from __future__ import annotations

from docai_core.contracts.domain import OCROutput, OCRPage
from docai_core.extraction.ocr_postprocessor import OCRPostProcessor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ocr(pages: list[tuple[int, str]], doc_id: str = "doc-1") -> OCROutput:
    return OCROutput(
        document_id=doc_id,
        engine_id="test_ocr",
        text="\n\n".join(text for _, text in pages),
        pages=[OCRPage(page_number=n, text=text) for n, text in pages],
        blocks=[{"type": "text"}],
        tables_detected=["table-1"],
        confidence=0.85,
    )


# Garbled string: 9 Latin Extended chars out of 20 total → ratio 0.45 > 0.15 threshold.
_GARBLED = "abĨĞŝŽũŬŵƉƌcdefghijk"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_clean_text_passes_through_unchanged() -> None:
    proc = OCRPostProcessor()
    src = _ocr([(1, "Invoice Number: INV-001")])
    result = proc.process(src)
    assert result.pages[0].text == "Invoice Number: INV-001"


def test_garbled_page_text_is_degarbled_when_ratio_exceeds_threshold() -> None:
    proc = OCRPostProcessor(garble_threshold=0.15)
    src = _ocr([(1, _GARBLED)])
    result = proc.process(src)
    # degarble should have converted some garbled chars to ASCII
    assert result.pages[0].text != _GARBLED


def test_garbled_page_text_not_degarbled_below_threshold() -> None:
    # Threshold set above the garbled ratio — degarble should NOT be applied.
    proc = OCRPostProcessor(garble_threshold=0.99)
    src = _ocr([(1, _GARBLED)])
    result = proc.process(src)
    # Only cleanup (control chars, whitespace) applied — no degarble substitution.
    # The garbled chars should still be present.
    garbled_chars_in = sum(1 for c in _GARBLED if "Ā" <= c <= "ɏ")
    garbled_chars_out = sum(1 for c in result.pages[0].text if "Ā" <= c <= "ɏ")
    assert garbled_chars_out == garbled_chars_in


def test_hyphenated_line_break_is_joined() -> None:
    proc = OCRPostProcessor()
    src = _ocr([(1, "in-\nvoice")])
    result = proc.process(src)
    assert "invoice" in result.pages[0].text
    assert "-\n" not in result.pages[0].text


def test_control_characters_are_stripped() -> None:
    proc = OCRPostProcessor()
    src = _ocr([(1, "Invoice\x00Number\x1fINV-001")])
    result = proc.process(src)
    assert "\x00" not in result.pages[0].text
    assert "\x1f" not in result.pages[0].text
    assert "INV-001" in result.pages[0].text


def test_multiple_blank_lines_collapsed_to_single_blank_line() -> None:
    proc = OCRPostProcessor()
    src = _ocr([(1, "line1\n\n\n\n\nline2")])
    result = proc.process(src)
    assert "\n\n\n" not in result.pages[0].text
    assert "line1" in result.pages[0].text
    assert "line2" in result.pages[0].text


def test_ocr_output_text_rebuilt_from_cleaned_pages() -> None:
    proc = OCRPostProcessor()
    src = _ocr([(1, "Invoice Number: INV-001"), (2, "Total: $100.00")])
    result = proc.process(src)
    assert result.text == "Invoice Number: INV-001\n\nTotal: $100.00"


def test_document_id_engine_id_blocks_tables_and_confidence_preserved() -> None:
    proc = OCRPostProcessor()
    src = _ocr([(1, "text")])
    result = proc.process(src)
    assert result.document_id == src.document_id
    assert result.engine_id == src.engine_id
    assert result.blocks == src.blocks
    assert result.tables_detected == src.tables_detected
    assert result.confidence == src.confidence


def test_original_ocr_output_is_not_mutated() -> None:
    proc = OCRPostProcessor()
    original_text = "Invoice\x00Number: INV-001"
    src = _ocr([(1, original_text)])
    proc.process(src)
    assert src.pages[0].text == original_text


def test_public_export_available() -> None:
    from docai_core.extraction import OCRPostProcessor as ExportedProcessor

    assert ExportedProcessor is not None
    proc = ExportedProcessor()
    assert callable(proc.process)
    # Smoke round-trip
    src = _ocr([(1, "Total Amount: $50.00")])
    result = proc.process(src)
    assert "Total Amount" in result.text
