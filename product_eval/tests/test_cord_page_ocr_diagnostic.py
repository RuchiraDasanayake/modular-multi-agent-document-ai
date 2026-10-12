"""Focused contract tests for the CORD full-page OCR diagnostic."""

from __future__ import annotations

import pytest

from product_eval import cord_page_ocr_diagnostic as diagnostic


def test_tesseract_tsv_keeps_word_order_line_geometry_and_offsets() -> None:
    tsv = (
        "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        "5\t1\t1\t1\t1\t1\t10\t20\t30\t8\t89\tGrand\n"
        "5\t1\t1\t1\t1\t2\t44\t20\t20\t8\t87\tTotal\n"
        "5\t1\t1\t1\t2\t1\t10\t40\t15\t8\t91\t42\n"
    )
    text, lines, words = diagnostic.parse_tesseract_tsv(tsv)

    assert text == "Grand Total\n42"
    assert [word["text"] for word in words] == ["Grand", "Total", "42"]
    assert lines[0]["polygon"] == [[10, 20], [64, 20], [64, 28], [10, 28]]
    assert [text[line["start"]:line["end"]] for line in lines] == ["Grand Total", "42"]
    assert [line["position_order"] for line in lines] == [0, 1]


def test_tesseract_tsv_rejects_unknown_header() -> None:
    with pytest.raises(ValueError, match="TSV header"):
        diagnostic.parse_tesseract_tsv("text\tconfidence\nabc\t90\n")


def test_annotation_availability_separates_page_and_local_geometry() -> None:
    gold = {
        "gold_text": "Rp. 12,000",
        "quad": {"x1": 10, "y1": 20, "x2": 80, "y2": 20,
                 "x3": 80, "y3": 30, "x4": 10, "y4": 30},
    }
    engine = {"text": "Rp 12 000", "lines": [{"text": "Rp 12 000", "polygon":
              [[11, 20], [79, 20], [79, 30], [11, 30]]}]}
    assert diagnostic.annotation_availability(gold, engine) == {
        "page_text_present": True, "local_box_detected": True, "local_text_present": True,
    }
    engine["lines"][0]["polygon"] = [[200, 20], [270, 20], [270, 30], [200, 30]]
    assert diagnostic.annotation_availability(gold, engine) == {
        "page_text_present": True, "local_box_detected": False, "local_text_present": False,
    }


def test_downstream_no_model_stage_retains_pending_review() -> None:
    candidate = diagnostic._extract_without_model("doc-1", "receipt.png", "Total: 42\n")
    assert candidate["document_status"] == "needs_review"
    assert candidate["proposed_schema"][0]["field_id"] == "total"
    assert candidate["extracted_values"][0]["review_state"] == "pending"
    assert candidate["extracted_values"][0]["value"] == 42


def test_paired_metric_keeps_all_failures_in_denominator() -> None:
    assert diagnostic._paired_metric([(True, True), (True, False), (False, True), (False, False)]) == {
        "both": 1, "tesseract_only": 1, "rapidocr_only": 1, "neither": 1,
    }
