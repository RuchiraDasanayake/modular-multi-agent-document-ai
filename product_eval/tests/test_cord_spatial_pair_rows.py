"""Synthetic source-only tests for CORD v2 geometry hypotheses."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from product_eval import cord_ocr_line_graph as line_graph
from product_eval import cord_spatial_pair_rows as pairs
from product_eval import cord_spatial_rows as v1

RULES_SHA = "e" * 64
Box = tuple[int, int, int, int]


def _graph(tmp_path: Path, boxes: list[Box]) -> line_graph.OcrLineGraph:
    source_path = tmp_path / "synthetic.png"
    Image.new("RGB", (900, 600), "white").save(source_path)
    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    position_order = {index: rank for rank, index in enumerate(sorted(
        range(len(boxes)), key=lambda index: (boxes[index][1], boxes[index][0], index),
    ))}
    offset = 0
    lines = []
    for index, (left, top, right, bottom) in enumerate(boxes):
        value = f"raw{index}"
        lines.append({
            "text": value, "confidence": 0.9,
            "polygon": [[left, top], [right, top], [right, bottom], [left, bottom]],
            "raw_order": index, "position_order": position_order[index],
            "start": offset, "end": offset + len(value),
        })
        offset += len(value) + 1
    row = {
        "source_id": "cord-v2/test/0000", "doc_id": "synthetic",
        "source_sha256": source_sha256, "image_size": [900, 600],
        "rapidocr": {"text": "\n".join(line["text"] for line in lines),
                     "lines": lines, "lines_in_bounds": len(lines), "failure": None},
    }
    return line_graph.build_line_graph(
        row, source_path, "rapidocr", raw_sidecar_sha256=v1.INPUT_RAW_SHA256,
        producer_code_sha256="c" * 64, graph_rules_sha256=pairs.INPUT_LINE_RULES_SHA256,
    )


def _page(tmp_path: Path, boxes: list[Box]) -> pairs.SpatialPairPage:
    return pairs.build_spatial_pair_page(_graph(tmp_path, boxes), pair_rules_sha256=RULES_SHA)


def test_two_column_pair_keeps_exact_line_ids_without_semantic_fields(tmp_path: Path) -> None:
    graph = _graph(tmp_path, [(30, 100, 200, 130), (700, 100, 800, 130)])
    page = pairs.build_spatial_pair_page(graph, pair_rules_sha256=RULES_SHA)
    assert page == pairs.build_spatial_pair_page(graph, pair_rules_sha256=RULES_SHA)
    assert page.status == "candidate" and page.reason is None
    assert len(page.pairs) == 1 and page.conflicts == ()
    pair = page.pairs[0]
    assert pair.left_node_id == graph.nodes[0].node_id
    assert pair.right_node_id == graph.nodes[1].node_id
    assert pair.witness_kind == "spatial_line_pair"
    assert pair.rank == 1 and pair.vertical_overlap_fraction == 1
    assert pair.prefix_status == "none" and pair.prefix_node_id is None
    assert pair.prefix_alternatives == () and pair.ambiguity_status == "uncontested"
    payload = page.source_only_payload()
    assert b'"text"' not in payload and b'"item_name"' not in payload


def test_overlapping_prefix_line_is_preserved_and_conflicts_are_explicit(tmp_path: Path) -> None:
    graph = _graph(tmp_path, [(160, 100, 200, 130), (184, 100, 333, 130),
                              (644, 100, 757, 130)])
    page = pairs.build_spatial_pair_page(graph, pair_rules_sha256=RULES_SHA)
    by_endpoints = {(pair.left_node_id, pair.right_node_id): pair for pair in page.pairs}
    assert len(page.pairs) == 2
    main = by_endpoints[(graph.nodes[1].node_id, graph.nodes[2].node_id)]
    assert main.prefix_node_id == graph.nodes[0].node_id
    assert main.prefix_alternatives == (graph.nodes[0].node_id,)
    assert main.prefix_status == "unique"
    assert all(pair.ambiguity_status == "conflicted" for pair in page.pairs)
    assert page.conflicts == (pairs.PairConflict(page.pairs[0].pair_id,
                                                 page.pairs[1].pair_id, "shared_line"),)


def test_multiple_prefix_alternatives_are_not_silently_selected(tmp_path: Path) -> None:
    graph = _graph(tmp_path, [(20, 100, 60, 130), (80, 100, 120, 130),
                              (200, 100, 400, 130), (700, 100, 800, 130)])
    page = pairs.build_spatial_pair_page(graph, pair_rules_sha256=RULES_SHA)
    main = next(pair for pair in page.pairs if pair.left_node_id == graph.nodes[2].node_id
                and pair.right_node_id == graph.nodes[3].node_id)
    assert main.prefix_status == "ambiguous" and main.prefix_node_id is None
    assert main.prefix_alternatives == (graph.nodes[1].node_id, graph.nodes[0].node_id)
    assert len({pair.rank for pair in page.pairs}) == len(page.pairs)


def test_crossing_order_conflict_is_recorded(tmp_path: Path) -> None:
    graph = _graph(tmp_path, [(30, 100, 150, 140), (30, 120, 150, 160),
                              (700, 120, 800, 160), (700, 100, 800, 140)])
    page = pairs.build_spatial_pair_page(graph, pair_rules_sha256=RULES_SHA)
    assert len(page.pairs) == 4
    assert any(conflict.reason == "crossing_order" for conflict in page.conflicts)
    valid_pair_ids = {pair.pair_id for pair in page.pairs}
    assert all(conflict.first_pair_id in valid_pair_ids
               and conflict.second_pair_id in valid_pair_ids for conflict in page.conflicts)
    assert len({(conflict.first_pair_id, conflict.second_pair_id)
                for conflict in page.conflicts}) == len(page.conflicts)


def test_single_joined_ocr_line_abstains(tmp_path: Path) -> None:
    page = _page(tmp_path, [(30, 100, 800, 130)])
    assert page.status == "abstained" and page.reason == "no_spatial_pair"
    assert page.pairs == () and page.conflicts == ()


def test_profile_hash_and_line_pointer_fail_closed(tmp_path: Path) -> None:
    graph = _graph(tmp_path, [(30, 100, 150, 130), (700, 100, 800, 130)])
    with pytest.raises(pairs.SpatialPairError, match="^input_graph_profile_mismatch$"):
        pairs.build_spatial_pair_page(replace(graph, engine="tesseract"),
                                      pair_rules_sha256=RULES_SHA)
    with pytest.raises(pairs.SpatialPairError, match="^pair_rules_hash_invalid$"):
        pairs.build_spatial_pair_page(graph, pair_rules_sha256="unlocked")
    tampered = replace(graph.nodes[0], node_id="ol_" + "0" * 24)
    with pytest.raises(line_graph.LineGraphError, match="^line_pointer_invalid$"):
        pairs.build_spatial_pair_page(replace(graph, nodes=(tampered, graph.nodes[1])),
                                      pair_rules_sha256=RULES_SHA)
