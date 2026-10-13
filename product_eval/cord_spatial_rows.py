"""Research-only geometry triplets from sealed CORD RapidOCR line graphs.

This deliberately conservative rule does not read OCR words, field labels,
creator annotations, gold, model replies, or reserved sources. Left, middle,
and right are spatial slots, not item-name, quantity, or price predictions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from product_eval.cord_ocr_line_graph import (
    COHORT_SHA256,
    LineGraphError,
    OcrLineGraph,
    OcrLineNode,
    _canonical,
    _code_hash,
    _image_size,
    _sha256,
)

INPUT_GRAPH_SHA256 = "4eb59422fddeb51778150f3cb79ed8f4ff9a34572e4f74b5974d680aaecd4b0d"
INPUT_RULES_SHA256 = "21b30b1b0b70918fc7d87bdf3a672d3796d3a2835e97ae62e4b5f283bd901d90"
RAPID_CONFIG_SHA256 = "4095d047339523203f72cc6eee2c2424340504680d79b875cf30ed04159f02d0"
INPUT_RAW_SHA256 = "3c1322181b893cc948b0dbde6414dcf7ed9669a1609ec007b09a12e52e40a92f"
MAX_GRAPH_FILE_BYTES = 8 * 1024 * 1024
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
OVERLAP_FRACTION = 0.5
MAX_LINE_WIDTH_FRACTION = 0.4


class SpatialRowsError(ValueError):
    """Fixed, source-free validation failure."""


@dataclass(frozen=True)
class SpatialRowCandidate:
    row_id: str
    witness_kind: Literal["spatial_line_triplet"]
    left_node_id: str
    middle_node_id: str
    right_node_id: str
    top_px: float
    bottom_px: float


@dataclass(frozen=True)
class LaneAbstention:
    lane_id: str
    node_ids: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class SpatialPageRows:
    source_id: str
    doc_id: str
    source_sha256: str
    input_graph_sha256: str
    input_rules_sha256: str
    spatial_rules_sha256: str
    image_size_px: tuple[int, int]
    rows: tuple[SpatialRowCandidate, ...]
    abstentions: tuple[LaneAbstention, ...]
    status: Literal["candidate", "abstained"]
    reason: str | None

    def source_only_payload(self) -> bytes:
        payload = (_canonical(asdict(self)) + "\n").encode("utf-8")
        if len(payload) > MAX_OUTPUT_BYTES:
            raise SpatialRowsError("page_output_limit")
        return payload


@dataclass(frozen=True)
class SlotTexts:
    """A source-backed candidate for later scoring, with no semantic labels."""

    left: str
    middle: str
    right: str


@dataclass(frozen=True)
class PositiveGoldRow:
    """A later positive-only scoring input; no gold files are read here."""

    item_name: str
    item_price: str
    item_quantity: str | None = None


@dataclass(frozen=True)
class PositiveRowScore:
    source_count: int
    positive_rows: int
    candidate_rows: int
    matched_rows: int
    positive_row_recall: float | None


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _bounds(node: OcrLineNode) -> tuple[float, float, float, float]:
    xs = [point[0] for point in node.polygon_px]
    ys = [point[1] for point in node.polygon_px]
    return min(xs), min(ys), max(xs), max(ys)


def _aligned(a: tuple[float, float, float, float],
             b: tuple[float, float, float, float]) -> bool:
    overlap = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return overlap >= OVERLAP_FRACTION * min(a[3] - a[1], b[3] - b[1])


def _spatial_band(box: tuple[float, float, float, float], image_width: int) -> int:
    center = (box[0] + box[2]) / 2
    if center < image_width / 3:
        return 0
    if center < 2 * image_width / 3:
        return 1
    return 2


def build_spatial_rows(graph: OcrLineGraph, *, spatial_rules_sha256: str) -> SpatialPageRows:
    """Group line-box overlap components; only isolated three-band lanes pass."""
    if (graph.engine != "rapidocr" or graph.raw_sidecar_sha256 != INPUT_RAW_SHA256
            or graph.graph_rules_sha256 != INPUT_RULES_SHA256
            or graph.parser_config_sha256 != RAPID_CONFIG_SHA256):
        raise SpatialRowsError("input_graph_profile_mismatch")
    if not re.fullmatch(r"[0-9a-f]{64}", spatial_rules_sha256):
        raise SpatialRowsError("spatial_rules_hash_invalid")
    graph.research_payload()
    if graph.status == "abstained":
        return SpatialPageRows(
            graph.source_id, graph.doc_id, graph.source_sha256,
            INPUT_GRAPH_SHA256, INPUT_RULES_SHA256, spatial_rules_sha256,
            graph.image_size_px, (), (), "abstained", "input_ocr_abstained",
        )
    nodes = graph.nodes
    if len({node.node_id for node in nodes}) != len(nodes):
        raise SpatialRowsError("duplicate_input_node")
    boxes = [_bounds(node) for node in nodes]
    parents = list(range(len(nodes)))

    def root(index: int) -> int:
        while parents[index] != index:
            index = parents[index]
        return index

    for first in range(len(nodes)):
        for second in range(first + 1, len(nodes)):
            if _aligned(boxes[first], boxes[second]):
                parents[root(second)] = root(first)
    components: dict[int, list[int]] = defaultdict(list)
    for index in range(len(nodes)):
        components[root(index)].append(index)
    ordered = sorted(components.values(), key=lambda indices: (
        min(boxes[index][1] for index in indices),
        min(boxes[index][0] for index in indices), min(indices),
    ))
    rows: list[SpatialRowCandidate] = []
    abstentions: list[LaneAbstention] = []
    width = graph.image_size_px[0]
    for members in ordered:
        node_ids = tuple(nodes[index].node_id for index in members)
        lane_id = "sl_" + _digest([graph.source_sha256, INPUT_GRAPH_SHA256,
                                   spatial_rules_sha256, node_ids])[:24]
        reason: str | None = None
        if len(members) < 3:
            reason = "incomplete_lane"
        elif len(members) > 3:
            reason = "crowded_lane"
        elif not all(_aligned(boxes[members[first]], boxes[members[second]])
                     for first, second in ((0, 1), (0, 2), (1, 2))):
            reason = "transitive_overlap_ambiguous"
        else:
            band_to_index = {_spatial_band(boxes[index], width): index for index in members}
            if len(band_to_index) != 3:
                reason = "duplicate_or_missing_band"
            else:
                left, middle, right = (band_to_index[band] for band in range(3))
                if any((boxes[index][2] - boxes[index][0]) > MAX_LINE_WIDTH_FRACTION * width
                       for index in (left, middle, right)):
                    reason = "wide_line"
                elif boxes[left][2] > boxes[middle][0] or boxes[middle][2] > boxes[right][0]:
                    reason = "horizontal_overlap"
                else:
                    row_id = "sr_" + _digest([
                        graph.source_sha256, INPUT_GRAPH_SHA256,
                        spatial_rules_sha256,
                        nodes[left].node_id, nodes[middle].node_id,
                        nodes[right].node_id,
                    ])[:24]
                    rows.append(SpatialRowCandidate(
                        row_id, "spatial_line_triplet", nodes[left].node_id,
                        nodes[middle].node_id, nodes[right].node_id,
                        min(boxes[index][1] for index in members),
                        max(boxes[index][3] for index in members),
                    ))
        if reason is not None:
            abstentions.append(LaneAbstention(lane_id, node_ids, reason))
    if len({node_id for row in rows for node_id in (
            row.left_node_id, row.middle_node_id, row.right_node_id)}) != len(rows) * 3:
        raise SpatialRowsError("reused_row_node")
    status: Literal["candidate", "abstained"] = "candidate" if rows else "abstained"
    result = SpatialPageRows(
        graph.source_id, graph.doc_id, graph.source_sha256,
        INPUT_GRAPH_SHA256, INPUT_RULES_SHA256, spatial_rules_sha256,
        graph.image_size_px, tuple(rows), tuple(abstentions), status,
        None if rows else "no_unambiguous_triplet",
    )
    result.source_only_payload()
    return result


def candidate_slot_texts(page: SpatialPageRows, graph: OcrLineGraph) -> tuple[SlotTexts, ...]:
    """Dereference only exact verified OCR line IDs from the same page."""
    graph.research_payload()
    if (page.source_sha256 != graph.source_sha256 or page.source_id != graph.source_id
            or page.doc_id != graph.doc_id or page.image_size_px != graph.image_size_px
            or page.input_graph_sha256 != INPUT_GRAPH_SHA256
            or page.input_rules_sha256 != INPUT_RULES_SHA256):
        raise SpatialRowsError("candidate_graph_mismatch")
    if build_spatial_rows(graph, spatial_rules_sha256=page.spatial_rules_sha256) != page:
        raise SpatialRowsError("candidate_page_invalid")
    by_id = {node.node_id: node for node in graph.nodes}
    if len(by_id) != len(graph.nodes):
        raise SpatialRowsError("duplicate_input_node")
    result: list[SlotTexts] = []
    used: set[str] = set()
    for row in page.rows:
        ids = (row.left_node_id, row.middle_node_id, row.right_node_id)
        if (row.witness_kind != "spatial_line_triplet" or len(set(ids)) != 3
                or any(node_id not in by_id or node_id in used for node_id in ids)):
            raise SpatialRowsError("candidate_pointer_invalid")
        used.update(ids)
        result.append(SlotTexts(*(by_id[node_id].text for node_id in ids)))
    return tuple(result)


def score_positive_rows(
    source_sha256s: tuple[str, ...],
    candidates: dict[str, tuple[SlotTexts, ...]],
    gold: dict[str, tuple[PositiveGoldRow, ...]],
) -> PositiveRowScore:
    """Frozen exact-text, one-to-one, positive-only row-recall convention.

    This pure function cannot read gold or source files. All source IDs must be
    supplied, including pages with no candidates and pages with no gold rows.
    """
    if (not source_sha256s or len(set(source_sha256s)) != len(source_sha256s)
            or any(not isinstance(sha, str)
                   or re.fullmatch(r"[0-9a-f]{64}", sha) is None for sha in source_sha256s)
            or set(candidates) != set(source_sha256s) or set(gold) != set(source_sha256s)):
        raise SpatialRowsError("score_source_set_mismatch")
    positive_rows = candidate_rows = matched_rows = 0
    for source_sha256 in source_sha256s:
        source_candidates = candidates[source_sha256]
        source_gold = gold[source_sha256]
        if (any(not isinstance(row, SlotTexts)
                or any(not isinstance(value, str) for value in asdict(row).values())
                for row in source_candidates)
                or any(not isinstance(row, PositiveGoldRow) or not row.item_name
                       or not row.item_price or not isinstance(row.item_name, str)
                       or not isinstance(row.item_price, str)
                       or (row.item_quantity is not None
                           and not isinstance(row.item_quantity, str))
                       for row in source_gold)):
            raise SpatialRowsError("score_row_invalid")
        positive_rows += len(source_gold)
        candidate_rows += len(source_candidates)
        matched_rows += _maximum_positive_matches(source_gold, source_candidates)
    return PositiveRowScore(
        len(source_sha256s), positive_rows, candidate_rows, matched_rows,
        matched_rows / positive_rows if positive_rows else None,
    )


def _maximum_positive_matches(
    gold_rows: Sequence[PositiveGoldRow], candidates: Sequence[SlotTexts],
) -> int:
    """Maximum-cardinality one-to-one match within one source."""
    matched_candidate_for_gold: dict[int, int] = {}

    def augment(gold_index: int, seen: set[int]) -> bool:
        actual = gold_rows[gold_index]
        for candidate_index, proposed in enumerate(candidates):
            if (candidate_index in seen or proposed.left != actual.item_name
                    or proposed.right != actual.item_price
                    or (actual.item_quantity is not None
                        and proposed.middle != actual.item_quantity)):
                continue
            seen.add(candidate_index)
            previous = matched_candidate_for_gold.get(candidate_index)
            if previous is None or augment(previous, seen):
                matched_candidate_for_gold[candidate_index] = gold_index
                return True
        return False

    return sum(augment(index, set()) for index in range(len(gold_rows)))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()]
    except (OSError, UnicodeError, ValueError) as exc:
        raise SpatialRowsError("input_jsonl_invalid") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise SpatialRowsError("input_jsonl_invalid")
    return rows


def _verified_rapid_graphs(stage_root: Path, graph_path: Path) -> list[OcrLineGraph]:
    if _sha256(graph_path, MAX_GRAPH_FILE_BYTES) != INPUT_GRAPH_SHA256:
        raise SpatialRowsError("input_graph_lock_mismatch")
    cohort_path = stage_root / "cohort_development.jsonl"
    if _sha256(cohort_path, MAX_GRAPH_FILE_BYTES) != COHORT_SHA256:
        raise SpatialRowsError("cohort_lock_mismatch")
    sources = _read_jsonl(cohort_path)
    if len(sources) != 60:
        raise SpatialRowsError("cohort_count_mismatch")
    by_source = {}
    for source in sources:
        source_sha256 = source.get("source_sha256")
        path_value = source.get("source_path")
        if (not isinstance(source_sha256, str)
                or not re.fullmatch(r"[0-9a-f]{64}", source_sha256)
                or source_sha256 in by_source or not isinstance(path_value, str)
                or source.get("evaluation_split") != "development"):
            raise SpatialRowsError("cohort_identity_invalid")
        path = Path(path_value).resolve()
        if path.parent != (stage_root / "input_development").resolve():
            raise SpatialRowsError("source_path_outside_development")
        size = _image_size(path, source_sha256)
        by_source[source_sha256] = (source, size)
    graph_records = _read_jsonl(graph_path)
    if len(graph_records) != 120:
        raise SpatialRowsError("input_graph_count_mismatch")
    seen: set[tuple[str, str]] = set()
    rapid_graphs: list[OcrLineGraph] = []
    for record in graph_records:
        source_sha256 = record.get("source_sha256")
        engine = record.get("engine")
        if (source_sha256 not in by_source or engine not in ("rapidocr", "tesseract")
                or (source_sha256, engine) in seen):
            raise SpatialRowsError("input_graph_source_set_mismatch")
        source, image_size = by_source[source_sha256]
        if (record.get("source_id") != source["source_id"]
                or record.get("doc_id") != source["doc_id"]
                or record.get("image_size_px") != list(image_size)
                or record.get("input_graph_sha256") is not None):
            raise SpatialRowsError("input_graph_source_set_mismatch")
        seen.add((source_sha256, engine))
        if engine == "rapidocr":
            try:
                nodes = tuple(OcrLineNode(**{
                    **node,
                    "image_size_px": tuple(node["image_size_px"]),
                    "text_span": tuple(node["text_span"]),
                    "polygon_px": tuple(tuple(point) for point in node["polygon_px"]),
                }) for node in record["nodes"])
                graph = OcrLineGraph(**{
                    **record, "image_size_px": tuple(record["image_size_px"]),
                    "nodes": nodes,
                })
                graph.research_payload()
            except (KeyError, TypeError, ValueError, LineGraphError) as exc:
                raise SpatialRowsError("input_graph_validation_failed") from exc
            rapid_graphs.append(graph)
    if (seen != {(source_sha256, engine) for source_sha256 in by_source
                 for engine in ("rapidocr", "tesseract")}
            or len(rapid_graphs) != 60):
        raise SpatialRowsError("input_graph_source_set_mismatch")
    return sorted(rapid_graphs, key=lambda graph: graph.source_sha256)


def run_source_only(stage_root: Path, graph_path: Path, output_dir: Path) -> dict[str, object]:
    if output_dir.exists():
        raise SpatialRowsError("output_exists")
    rapid_graphs = _verified_rapid_graphs(stage_root, graph_path)
    rules_sha256 = _code_hash(Path(__file__))
    pages = [build_spatial_rows(graph, spatial_rules_sha256=rules_sha256)
             for graph in rapid_graphs]
    output_dir.mkdir(parents=True, exist_ok=False)
    candidate_path = output_dir / "spatial_rows.jsonl"
    with candidate_path.open("wb") as handle:
        for page in pages:
            handle.write(page.source_only_payload())
    receipt: dict[str, object] = {
        "protocol": "cord_s1_spatial_rows_v1",
        "scope": "60 CORD development PNGs, RapidOCR line geometry only",
        "source_cohort_sha256": COHORT_SHA256,
        "input_line_graphs_sha256": INPUT_GRAPH_SHA256,
        "input_line_rules_sha256": INPUT_RULES_SHA256,
        "spatial_rules_lf_sha256": rules_sha256,
        "sources_verified": len(rapid_graphs),
        "source_records": len(pages),
        "pages_with_triplets": sum(bool(page.rows) for page in pages),
        "pages_without_triplets": sum(not page.rows for page in pages),
        "candidate_triplets": sum(len(page.rows) for page in pages),
        "lane_abstentions": dict(sorted(Counter(
            lane.reason for page in pages for lane in page.abstentions).items())),
        "spatial_rows_sha256": _sha256(candidate_path, MAX_OUTPUT_BYTES * 4),
        "model_calls": 0, "gold_access": False, "creator_quad_access": False,
        "reserved_source_access": False, "product_extraction_calls": 0,
        "limitations": [
            "Slots are spatial left/middle/right, not item, quantity, or price labels.",
            "Only isolated three-line overlap components can qualify; two-column and merged-line layouts abstain.",
            "No transcription, semantic, row-link, precision, reviewer-cost, or product quality score is reported.",
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
