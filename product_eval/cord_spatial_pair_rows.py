"""Research-only CORD spatial pair hypotheses from sealed RapidOCR line nodes.

This code proposes geometry-only left/right pairs with optional third prefix
lines. It does not assign item, quantity, price, table, or cell semantics.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from product_eval import cord_ocr_line_graph as line_graph
from product_eval import cord_spatial_rows as v1

INPUT_GRAPH_SHA256 = v1.INPUT_GRAPH_SHA256
INPUT_LINE_RULES_SHA256 = v1.INPUT_RULES_SHA256
INPUT_V1_RULES_SHA256 = "48de68d33a7845f7f17c65e895bae00cb07aa869dec6bfa2c153702210935482"
OVERLAP_FRACTION = 0.5
PREFIX_CENTER_GAP_FRACTION = 0.02
MAX_PAIRS_PER_PAGE = 1024
MAX_PAGE_BYTES = 2 * 1024 * 1024


class SpatialPairError(ValueError):
    """Fixed, source-free candidate failure."""


@dataclass(frozen=True)
class PairHypothesis:
    pair_id: str
    witness_kind: Literal["spatial_line_pair"]
    left_node_id: str
    right_node_id: str
    prefix_node_id: str | None
    prefix_alternatives: tuple[str, ...]
    prefix_status: Literal["none", "unique", "ambiguous"]
    rank: int
    vertical_overlap_fraction: float
    normalized_center_delta: float
    normalized_horizontal_gap: float
    ambiguity_status: Literal["uncontested", "conflicted"]


@dataclass(frozen=True)
class PairConflict:
    first_pair_id: str
    second_pair_id: str
    reason: Literal["shared_line", "crossing_order"]


@dataclass(frozen=True)
class SpatialPairPage:
    source_id: str
    doc_id: str
    source_sha256: str
    image_size_px: tuple[int, int]
    input_graph_sha256: str
    input_line_rules_sha256: str
    pair_rules_sha256: str
    pairs: tuple[PairHypothesis, ...]
    conflicts: tuple[PairConflict, ...]
    status: Literal["candidate", "abstained"]
    reason: str | None

    def source_only_payload(self) -> bytes:
        payload = (line_graph._canonical(asdict(self)) + "\n").encode("utf-8")
        if len(payload) > MAX_PAGE_BYTES:
            raise SpatialPairError("page_output_limit")
        return payload


def _digest(value: object) -> str:
    return hashlib.sha256(line_graph._canonical(value).encode("utf-8")).hexdigest()


def _bounds(node: line_graph.OcrLineNode) -> tuple[float, float, float, float]:
    xs = [point[0] for point in node.polygon_px]
    ys = [point[1] for point in node.polygon_px]
    return min(xs), min(ys), max(xs), max(ys)


def _height(box: tuple[float, float, float, float]) -> float:
    return box[3] - box[1]


def _center_y(box: tuple[float, float, float, float]) -> float:
    return (box[1] + box[3]) / 2


def _center_x(box: tuple[float, float, float, float]) -> float:
    return (box[0] + box[2]) / 2


def _overlap_fraction(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    overlap = max(0.0, min(first[3], second[3]) - max(first[1], second[1]))
    return overlap / min(_height(first), _height(second))


def _prefix_alternatives(
    left_index: int, right_index: int,
    boxes: list[tuple[float, float, float, float]],
    node_ids: tuple[str, ...], image_width: int,
) -> tuple[str, ...]:
    left, right = boxes[left_index], boxes[right_index]
    alternatives = [
        index for index, box in enumerate(boxes)
        if (index not in (left_index, right_index)
            and _center_x(box) <= _center_x(left) - PREFIX_CENTER_GAP_FRACTION * image_width
            and box[2] - box[0] <= left[2] - left[0]
            and _overlap_fraction(box, left) >= OVERLAP_FRACTION
            and _overlap_fraction(box, right) >= OVERLAP_FRACTION)
    ]
    alternatives.sort(key=lambda index: (
        abs(_center_y(boxes[index]) - _center_y(left)),
        _center_x(left) - _center_x(boxes[index]), index,
    ))
    return tuple(node_ids[index] for index in alternatives)


def build_spatial_pair_page(
    graph: line_graph.OcrLineGraph, *, pair_rules_sha256: str,
) -> SpatialPairPage:
    """Keep every qualifying pair and disclose shared/crossing alternatives."""
    if (graph.engine != "rapidocr" or graph.raw_sidecar_sha256 != v1.INPUT_RAW_SHA256
            or graph.graph_rules_sha256 != INPUT_LINE_RULES_SHA256
            or graph.parser_config_sha256 != v1.RAPID_CONFIG_SHA256):
        raise SpatialPairError("input_graph_profile_mismatch")
    if not isinstance(pair_rules_sha256, str) or re.fullmatch(
            r"[0-9a-f]{64}", pair_rules_sha256) is None:
        raise SpatialPairError("pair_rules_hash_invalid")
    graph.research_payload()
    if graph.status == "abstained":
        return SpatialPairPage(
            graph.source_id, graph.doc_id, graph.source_sha256, graph.image_size_px,
            INPUT_GRAPH_SHA256, INPUT_LINE_RULES_SHA256, pair_rules_sha256,
            (), (), "abstained", "input_ocr_abstained",
        )
    nodes = graph.nodes
    node_ids = tuple(node.node_id for node in nodes)
    if len(set(node_ids)) != len(node_ids):
        raise SpatialPairError("duplicate_input_node")
    boxes = [_bounds(node) for node in nodes]
    width = graph.image_size_px[0]
    candidates: list[tuple[tuple[float, float, float, int, int], int, int, float,
                           float, float, tuple[str, ...]]] = []
    for left_index, left in enumerate(boxes):
        for right_index, right in enumerate(boxes):
            if left_index == right_index or left[2] > right[0]:
                continue
            overlap = _overlap_fraction(left, right)
            if overlap < OVERLAP_FRACTION:
                continue
            center_delta = abs(_center_y(left) - _center_y(right)) / max(
                _height(left), _height(right))
            horizontal_gap = (right[0] - left[2]) / width
            prefixes = _prefix_alternatives(
                left_index, right_index, boxes, node_ids, width)
            rank_key = (center_delta, -overlap, horizontal_gap, left_index, right_index)
            candidates.append((rank_key, left_index, right_index, overlap,
                               center_delta, horizontal_gap, prefixes))
            if len(candidates) > MAX_PAIRS_PER_PAGE:
                raise SpatialPairError("pair_candidate_limit")
    candidates.sort(key=lambda item: item[0])
    ids = tuple("sp_" + _digest([
        graph.source_sha256, INPUT_GRAPH_SHA256, pair_rules_sha256,
        node_ids[left_index], node_ids[right_index],
    ])[:24] for _, left_index, right_index, *_ in candidates)
    if len(set(ids)) != len(ids):
        raise SpatialPairError("duplicate_pair_id")
    conflicts: list[PairConflict] = []
    by_pair: dict[str, set[str]] = defaultdict(set)
    for first in range(len(candidates)):
        _, left_a, right_a, *_ = candidates[first]
        for second in range(first + 1, len(candidates)):
            _, left_b, right_b, *_ = candidates[second]
            if {left_a, right_a} & {left_b, right_b}:
                reason: Literal["shared_line", "crossing_order"] | None = "shared_line"
            else:
                left_order = _center_y(boxes[left_a]) - _center_y(boxes[left_b])
                right_order = _center_y(boxes[right_a]) - _center_y(boxes[right_b])
                reason = "crossing_order" if left_order * right_order < 0 else None
            if reason is not None:
                conflicts.append(PairConflict(ids[first], ids[second], reason))
                by_pair[ids[first]].add(ids[second])
                by_pair[ids[second]].add(ids[first])
    pairs: list[PairHypothesis] = []
    for rank, (candidate, pair_id) in enumerate(zip(candidates, ids, strict=True), start=1):
        _, left_index, right_index, overlap, center_delta, horizontal_gap, prefixes = candidate
        prefix_status: Literal["none", "unique", "ambiguous"] = (
            "none" if not prefixes else "unique" if len(prefixes) == 1 else "ambiguous")
        pairs.append(PairHypothesis(
            pair_id, "spatial_line_pair", node_ids[left_index], node_ids[right_index],
            prefixes[0] if len(prefixes) == 1 else None, prefixes,
            prefix_status, rank, overlap, center_delta, horizontal_gap,
            "conflicted" if by_pair[pair_id] else "uncontested",
        ))
    page = SpatialPairPage(
        graph.source_id, graph.doc_id, graph.source_sha256, graph.image_size_px,
        INPUT_GRAPH_SHA256, INPUT_LINE_RULES_SHA256, pair_rules_sha256,
        tuple(pairs), tuple(conflicts), "candidate" if pairs else "abstained",
        None if pairs else "no_spatial_pair",
    )
    page.source_only_payload()
    return page


def run_source_only(stage_root: Path, graph_path: Path, output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise SpatialPairError("output_exists")
    if line_graph._code_hash(Path(line_graph.__file__)) != INPUT_LINE_RULES_SHA256:
        raise SpatialPairError("input_line_rules_lock_mismatch")
    if line_graph._code_hash(Path(v1.__file__)) != INPUT_V1_RULES_SHA256:
        raise SpatialPairError("input_v1_rules_lock_mismatch")
    graphs = v1._verified_rapid_graphs(stage_root, graph_path)
    rules_sha256 = line_graph._code_hash(Path(__file__))
    pages = [build_spatial_pair_page(graph, pair_rules_sha256=rules_sha256)
             for graph in graphs]
    output_dir.mkdir(parents=True, exist_ok=False)
    result_path = output_dir / "spatial_pairs.jsonl"
    with result_path.open("wb") as handle:
        for page in pages:
            handle.write(page.source_only_payload())
    pair_count = sum(len(page.pairs) for page in pages)
    receipt: dict[str, object] = {
        "protocol": "cord_s1_spatial_pairs_v2_source_only",
        "scope": "60 CORD development PNGs, RapidOCR line geometry only",
        "source_cohort_sha256": line_graph.COHORT_SHA256,
        "input_line_graphs_sha256": INPUT_GRAPH_SHA256,
        "input_line_rules_sha256": INPUT_LINE_RULES_SHA256,
        "input_v1_rules_sha256": INPUT_V1_RULES_SHA256,
        "pair_rules_lf_sha256": rules_sha256,
        "sources_verified": len(graphs),
        "source_records": len(pages),
        "pages_with_pairs": sum(bool(page.pairs) for page in pages),
        "pages_without_pairs": sum(not page.pairs for page in pages),
        "pair_hypotheses": pair_count,
        "pair_statuses": dict(sorted(Counter(
            pair.ambiguity_status for page in pages for pair in page.pairs).items())),
        "prefix_statuses": dict(sorted(Counter(
            pair.prefix_status for page in pages for pair in page.pairs).items())),
        "conflict_reasons": dict(sorted(Counter(
            conflict.reason for page in pages for conflict in page.conflicts).items())),
        "spatial_pairs_sha256": line_graph._sha256(result_path, 64 * 1024 * 1024),
        "model_calls": 0, "gold_access": False, "creator_quad_access": False,
        "reserved_source_access": False, "product_extraction_calls": 0,
        "limitations": [
            "Pairs and prefixes are geometry hypotheses, not typed cells or item rows.",
            "Conflicting hypotheses are preserved; no row is semantically selected.",
            "A missed OCR column cannot be recovered from line geometry.",
            "Candidate support does not establish recall, precision, or cost improvement.",
        ],
    }
    (output_dir / "receipt.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-root", type=Path, required=True)
    parser.add_argument("--line-graphs", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_source_only(args.stage_root, args.line_graphs, args.output_dir),
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
