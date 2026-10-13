"""Source-only synthetic geometry and pure scorer tests; no gold file access."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from product_eval import cord_ocr_line_graph as line_graph
from product_eval import cord_spatial_rows as spatial

RULES_SHA = "e" * 64
SHA_A = "a" * 64
SHA_B = "b" * 64
Box = tuple[int, int, int, int]


def _graph(tmp_path: Path, boxes: list[Box], *, text: str = "same") -> line_graph.OcrLineGraph:
    path = tmp_path / "synthetic.png"
    Image.new("RGB", (900, 600), "white").save(path)
    source_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    order = sorted(range(len(boxes)), key=lambda index: (boxes[index][1], boxes[index][0], index))
    position = {index: rank for rank, index in enumerate(order)}
    lines = []
    offset = 0
    for index, (left, top, right, bottom) in enumerate(boxes):
        lines.append({
            "text": text, "confidence": 0.9,
            "polygon": [[left, top], [right, top], [right, bottom], [left, bottom]],
            "raw_order": index, "position_order": position[index],
            "start": offset, "end": offset + len(text),
        })
        offset += len(text) + 1
    row = {
        "doc_id": "synthetic", "source_id": "cord-v2/test/0000",
        "source_sha256": source_sha256, "image_size": [900, 600],
        "rapidocr": {"text": "\n".join([text] * len(lines)), "lines": lines,
                     "lines_in_bounds": len(lines), "failure": None},
    }
    return line_graph.build_line_graph(
        row, path, "rapidocr", raw_sidecar_sha256=spatial.INPUT_RAW_SHA256,
        producer_code_sha256="c" * 64,
        graph_rules_sha256=spatial.INPUT_RULES_SHA256,
    )


def _result(tmp_path: Path, boxes: list[Box]) -> spatial.SpatialPageRows:
    return spatial.build_spatial_rows(_graph(tmp_path, boxes), spatial_rules_sha256=RULES_SHA)


def test_isolated_three_band_line_triplet_keeps_exact_distinct_ids(tmp_path: Path) -> None:
    graph = _graph(tmp_path, [(30, 100, 90, 120), (390, 100, 450, 120),
                              (750, 100, 810, 120), (35, 200, 85, 220)])
    page = spatial.build_spatial_rows(graph, spatial_rules_sha256=RULES_SHA)
    assert page == spatial.build_spatial_rows(graph, spatial_rules_sha256=RULES_SHA)
    assert page.status == "candidate" and page.reason is None
    assert len(page.rows) == 1
    assert page.rows[0].witness_kind == "spatial_line_triplet"
    assert page.rows[0].row_id.startswith("sr_")
    assert (page.rows[0].left_node_id, page.rows[0].middle_node_id,
            page.rows[0].right_node_id) == tuple(node.node_id for node in graph.nodes[:3])
    assert page.rows[0].top_px == 100 and page.rows[0].bottom_px == 120
    assert [lane.reason for lane in page.abstentions] == ["incomplete_lane"]
    assert spatial.candidate_slot_texts(page, graph) == (spatial.SlotTexts("same", "same", "same"),)
    assert len({node.node_id for node in graph.nodes[:3]}) == 3


@pytest.mark.parametrize("boxes,reason", [
    ([(30, 100, 90, 120), (390, 100, 450, 120)], "incomplete_lane"),
    ([(30, 100, 90, 120), (390, 100, 450, 120),
      (750, 100, 810, 120), (840, 100, 880, 120)], "crowded_lane"),
    ([(30, 100, 90, 120), (130, 100, 190, 120),
      (750, 100, 810, 120)], "duplicate_or_missing_band"),
    ([(30, 100, 90, 120), (390, 110, 450, 130),
      (750, 120, 810, 140)], "transitive_overlap_ambiguous"),
    ([(30, 100, 440, 120), (500, 100, 550, 120),
      (750, 100, 810, 120)], "wide_line"),
    ([(150, 100, 440, 120), (430, 100, 470, 120),
      (750, 100, 810, 120)], "horizontal_overlap"),
])
def test_ambiguous_lanes_abstain_with_fixed_reason(
    tmp_path: Path, boxes: list[Box], reason: str,
) -> None:
    page = _result(tmp_path, boxes)
    assert page.status == "abstained" and page.reason == "no_unambiguous_triplet"
    assert page.rows == ()
    assert len(page.abstentions) == 1 and page.abstentions[0].reason == reason
    assert len(page.abstentions[0].node_ids) == len(boxes)


def test_geometry_uses_pixel_boxes_not_text_or_confidence(tmp_path: Path) -> None:
    boxes = [(30, 100, 90, 120), (390, 100, 450, 120), (750, 100, 810, 120)]
    graph = _graph(tmp_path, boxes, text="gibberish")
    page = spatial.build_spatial_rows(graph, spatial_rules_sha256=RULES_SHA)
    assert len(page.rows) == 1
    assert spatial.candidate_slot_texts(page, graph) == (
        spatial.SlotTexts("gibberish", "gibberish", "gibberish"),
    )
    altered_page = replace(page, rows=(replace(page.rows[0], left_node_id=graph.nodes[1].node_id),))
    with pytest.raises(spatial.SpatialRowsError, match="^candidate_page_invalid$"):
        spatial.candidate_slot_texts(altered_page, graph)
    tampered_node = replace(graph.nodes[0], text="invented")
    with pytest.raises(line_graph.LineGraphError, match="^graph_text_mismatch$"):
        spatial.build_spatial_rows(replace(graph, nodes=(tampered_node, *graph.nodes[1:])),
                                   spatial_rules_sha256=RULES_SHA)


def test_non_rapid_and_invalid_rule_hash_fail_closed(tmp_path: Path) -> None:
    graph = _graph(tmp_path, [(30, 100, 90, 120), (390, 100, 450, 120),
                              (750, 100, 810, 120)])
    with pytest.raises(spatial.SpatialRowsError, match="^input_graph_profile_mismatch$"):
        spatial.build_spatial_rows(replace(graph, engine="tesseract"),
                                   spatial_rules_sha256=RULES_SHA)
    with pytest.raises(spatial.SpatialRowsError, match="^spatial_rules_hash_invalid$"):
        spatial.build_spatial_rows(graph, spatial_rules_sha256="not-a-hash")


def test_pure_scorer_is_exact_positive_only_and_one_to_one() -> None:
    candidates = {
        SHA_A: (spatial.SlotTexts("Tea", "2", "4.00"),),
        SHA_B: (),
    }
    gold = {
        SHA_A: (spatial.PositiveGoldRow("Tea", "4.00", "2"),
                spatial.PositiveGoldRow("Tea", "4.00", "2"),
                spatial.PositiveGoldRow("tea", "4.00")),
        SHA_B: (spatial.PositiveGoldRow("Coffee", "3.00"),),
    }
    score = spatial.score_positive_rows((SHA_A, SHA_B), candidates, gold)
    assert score == spatial.PositiveRowScore(2, 4, 1, 1, 0.25)
    assert spatial.score_positive_rows((SHA_A,), {SHA_A: ()}, {SHA_A: ()}).positive_row_recall is None


def test_scorer_rejects_missing_source_and_requires_annotated_quantity() -> None:
    with pytest.raises(spatial.SpatialRowsError, match="^score_source_set_mismatch$"):
        spatial.score_positive_rows((SHA_A, SHA_B), {SHA_A: ()}, {SHA_A: (), SHA_B: ()})
    score = spatial.score_positive_rows(
        (SHA_A,), {SHA_A: (spatial.SlotTexts("Tea", "3", "4.00"),)},
        {SHA_A: (spatial.PositiveGoldRow("Tea", "4.00", "2"),)},
    )
    assert score.matched_rows == 0 and score.positive_row_recall == 0
