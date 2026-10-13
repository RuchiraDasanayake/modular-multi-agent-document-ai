"""Source-only tests for the research OCR line graph; no gold or model calls."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from PIL import Image

from product_eval import cord_ocr_line_graph as graph

RAW_SHA = "a" * 64
PRODUCER_SHA = "b" * 64
RULES_SHA = "c" * 64


def _source(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    path = tmp_path / "page.png"
    Image.new("RGB", (100, 80), "white").save(path)
    source_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    lines = [
        {"text": "same", "confidence": 0.9,
         "polygon": [[10, 40], [40, 40], [40, 50], [10, 50]],
         "raw_order": 0, "position_order": 1, "start": 0, "end": 4},
        {"text": "same", "confidence": 0.8,
         "polygon": [[10, 10], [40, 10], [40, 20], [10, 20]],
         "raw_order": 1, "position_order": 0, "start": 5, "end": 9},
    ]
    row: dict[str, object] = {
        "doc_id": "test-doc", "source_id": "cord-v2/test/0000",
        "source_sha256": source_sha, "image_size": [100, 80],
        "rapidocr": {"text": "same\nsame", "lines": lines,
                     "lines_in_bounds": 2, "failure": None},
        "tesseract": {"text": "", "lines": [], "words": [],
                      "lines_in_bounds": 0, "failure": None},
    }
    return path, row


def _build(path: Path, row: dict[str, object], engine: str = "rapidocr") -> graph.OcrLineGraph:
    return graph.build_line_graph(
        row, path, engine, raw_sidecar_sha256=RAW_SHA,
        producer_code_sha256=PRODUCER_SHA, graph_rules_sha256=RULES_SHA,
    )


def test_repeated_ocr_lines_keep_distinct_exact_source_pointers(tmp_path: Path) -> None:
    path, row = _source(tmp_path)
    first, second = _build(path, row), _build(path, row)
    assert first == second
    assert first.status == "candidate" and first.reason is None
    assert len(first.nodes) == 2
    assert [node.text_span for node in first.nodes] == [(0, 4), (5, 9)]
    assert [node.position_order for node in first.nodes] == [1, 0]
    assert len({node.node_id for node in first.nodes}) == 2
    assert [first.page_text[slice(*node.text_span)] for node in first.nodes] == ["same", "same"]
    for node in first.nodes:
        assert node.kind == "ocr_line"
        assert node.unit_id == "image-1" and node.page_number == 1
        assert node.source_sha256 == row["source_sha256"]
        assert node.image_size_px == (100, 80)
        locator = json.loads(node.source_locator)
        assert locator["kind"] == "ocr_line" and locator["raw_order"] == node.raw_order
        assert locator["raw_line_sha256"] == node.raw_line_sha256
        assert "table_id" not in asdict(node) and "word_box" not in asdict(node)
    assert first.research_payload() == second.research_payload()


@pytest.mark.parametrize("change,reason", [
    ("source_hash", "source_hash_mismatch"),
    ("image_size", "sidecar_source_mismatch"),
    ("out_of_bounds", "line_polygon_out_of_bounds"),
    ("bow_tie", "line_polygon_degenerate"),
    ("wrong_span", "line_offset_invalid"),
    ("wrong_order", "position_order_invalid"),
    ("wrong_confidence", "line_confidence_invalid"),
    ("long_line", "line_length_limit"),
])
def test_malformed_source_or_line_abstains_before_candidate(
    tmp_path: Path, change: str, reason: str,
) -> None:
    path, source = _source(tmp_path)
    row = copy.deepcopy(source)
    if change == "source_hash":
        row["source_sha256"] = "0" * 64
    elif change == "image_size":
        row["image_size"] = [100, 81]
    elif change == "out_of_bounds":
        row["rapidocr"]["lines"][0]["polygon"][0][0] = -1
    elif change == "bow_tie":
        row["rapidocr"]["lines"][0]["polygon"] = [[10, 40], [40, 50], [40, 40], [10, 50]]
    elif change == "wrong_span":
        row["rapidocr"]["lines"][1]["start"] = 4
    elif change == "wrong_order":
        row["rapidocr"]["lines"][0]["position_order"] = 0
    elif change == "long_line":
        long_text = "x" * (graph.MAX_LINE_CHARS + 1)
        row["rapidocr"]["lines"][0]["text"] = long_text
        row["rapidocr"]["lines"][0]["end"] = len(long_text)
        row["rapidocr"]["lines"][1]["start"] = len(long_text) + 1
        row["rapidocr"]["lines"][1]["end"] = len(long_text) + 5
        row["rapidocr"]["text"] = long_text + "\nsame"
    else:
        row["rapidocr"]["lines"][0]["confidence"] = 1.5
    with pytest.raises(graph.LineGraphError, match=f"^{reason}$"):
        _build(path, row)


def test_empty_tesseract_page_is_explicit_abstention(tmp_path: Path) -> None:
    path, row = _source(tmp_path)
    result = _build(path, row, "tesseract")
    assert result.status == "abstained"
    assert result.reason == "empty_ocr_page"
    assert result.nodes == () and result.page_text == ""
    result.research_payload()


def test_tesseract_line_hierarchy_is_kept_at_line_scope(tmp_path: Path) -> None:
    path, row = _source(tmp_path)
    lines = copy.deepcopy(row["rapidocr"]["lines"])
    for line in lines:
        line["confidence"] = 88.5
        line["hierarchy"] = [1, 1, 1, line["raw_order"] + 1]
    row["tesseract"] = {"text": "same\nsame", "lines": lines, "words": [],
                        "lines_in_bounds": 2, "failure": None}
    result = _build(path, row, "tesseract")
    assert result.status == "candidate" and len(result.nodes) == 2
    assert all(node.kind == "ocr_line" for node in result.nodes)
    assert all("word" not in node.source_locator for node in result.nodes)


def test_failed_ocr_page_cannot_contain_hidden_lines(tmp_path: Path) -> None:
    path, row = _source(tmp_path)
    row["rapidocr"]["failure"] = "timeout_30s"
    with pytest.raises(graph.LineGraphError, match="^engine_failure_invalid$"):
        _build(path, row)


def test_serialization_rechecks_line_text_and_source_metadata(tmp_path: Path) -> None:
    path, row = _source(tmp_path)
    original = _build(path, row)
    with pytest.raises(graph.LineGraphError, match="^page_text_hash_mismatch$"):
        replace(original, page_text="invented").research_payload()
    forged_node = replace(original.nodes[0], source_sha256="0" * 64)
    with pytest.raises(graph.LineGraphError, match="^line_pointer_invalid$"):
        replace(original, nodes=(forged_node, original.nodes[1])).research_payload()
    forged_locator = replace(original.nodes[0], source_locator="{}")
    with pytest.raises(graph.LineGraphError, match="^line_locator_invalid$"):
        replace(original, nodes=(forged_locator, original.nodes[1])).research_payload()
