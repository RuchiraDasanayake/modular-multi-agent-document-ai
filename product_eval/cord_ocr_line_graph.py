"""Research-only, source-locked OCR line graph for CORD development images.

The input is the existing full-page OCR raw sidecar. This code neither performs
OCR nor reads creator annotations, positive gold, model replies, or reserved
sources. A line polygon is not a word box, table cell, or verified field.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from PIL import Image

COHORT_SHA256 = "48f9af8c04a5ee874c68ccb4c70a5fb81bcfddc508064747779678949103414a"
RAW_SIDECAR_SHA256 = "3c1322181b893cc948b0dbde6414dcf7ed9669a1609ec007b09a12e52e40a92f"
PRODUCER_CODE_LF_SHA256 = "8097af878f63c834757b65edbc8172473284c46da6f2a8a86597f00b2f2d5cf9"
RAPID_ASSETS = {
    "det": "090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f",
    "rec": "6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884",
    "cls": "e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c",
}
TESSERACT_EXE_SHA256 = "c66f0f12ed76f6aa455dac97684bbc86756d6a732380bee09122454cfda3f420"
TESSERACT_ENG_SHA256 = "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2"
ENGINES = ("rapidocr", "tesseract")
SOURCE_LOCK_REASONS = {
    "input_size_limit", "input_unavailable", "source_hash_mismatch",
    "source_changed_during_validation", "source_image_invalid",
    "unsupported_image_format", "unsupported_image_orientation", "image_size_limit",
}
MAX_SOURCE_BYTES = 20 * 1024 * 1024
MAX_RAW_BYTES = 2 * 1024 * 1024
MAX_LINES = 256
MAX_PAGE_CHARS = 24_000
MAX_LINE_CHARS = 500
MAX_GRAPH_BYTES = 512 * 1024
MAX_IMAGE_SIDE = 10_000


class LineGraphError(ValueError):
    """A fixed, source-free validation reason."""


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _sha256(path: Path, maximum: int) -> str:
    try:
        if path.stat().st_size > maximum:
            raise LineGraphError("input_size_limit")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as exc:
        raise LineGraphError("input_unavailable") from exc


def _code_hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    except OSError as exc:
        raise LineGraphError("producer_code_unavailable") from exc


def _config(engine: str) -> dict[str, object]:
    if engine == "rapidocr":
        return {
            "engine": "rapidocr", "rapidocr_version": "3.10.0",
            "onnxruntime_version": "1.23.2", "assets_sha256": RAPID_ASSETS,
            "language": "en", "provider": "CPUExecutionProvider",
            "intra_op_num_threads": 4, "inter_op_num_threads": 1,
            "use_cuda": False, "use_dml": False,
            "source": "cord_page_ocr_diagnostic.py:_rapid_page",
        }
    if engine == "tesseract":
        return {
            "engine": "tesseract", "executable_sha256": TESSERACT_EXE_SHA256,
            "eng_sha256": TESSERACT_ENG_SHA256,
            "language": "eng", "oem": 3, "psm": 6,
            "omp_thread_limit": 4, "source": "cord_page_ocr_diagnostic.py:_tesseract_page",
        }
    raise LineGraphError("unsupported_engine")


def _integer(value: object, *, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def _number(value: object) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _image_size(path: Path, expected_sha256: str) -> tuple[int, int]:
    if _sha256(path, MAX_SOURCE_BYTES) != expected_sha256:
        raise LineGraphError("source_hash_mismatch")
    try:
        with Image.open(path) as image:
            if image.format != "PNG":
                raise LineGraphError("unsupported_image_format")
            size = image.size
            image.verify()
        with Image.open(path) as image:
            if image.getexif().get(274, 1) != 1:
                raise LineGraphError("unsupported_image_orientation")
    except (OSError, ValueError, RuntimeError, SyntaxError) as exc:
        if isinstance(exc, LineGraphError):
            raise
        raise LineGraphError("source_image_invalid") from exc
    if not all(_integer(side, minimum=1) and side <= MAX_IMAGE_SIDE for side in size):
        raise LineGraphError("image_size_limit")
    if _sha256(path, MAX_SOURCE_BYTES) != expected_sha256:
        raise LineGraphError("source_changed_during_validation")
    return size


def _polygon(value: object, image_size: tuple[int, int]) -> tuple[tuple[float, float], ...]:
    if not isinstance(value, list) or len(value) != 4:
        raise LineGraphError("line_polygon_invalid")
    points: list[tuple[float, float]] = []
    for item in value:
        if (not isinstance(item, list) or len(item) != 2
                or not all(_number(coordinate) for coordinate in item)):
            raise LineGraphError("line_polygon_invalid")
        x, y = float(item[0]), float(item[1])
        if not (0 <= x <= image_size[0] and 0 <= y <= image_size[1]):
            raise LineGraphError("line_polygon_out_of_bounds")
        points.append((x, y))
    if len(set(points)) != 4:
        raise LineGraphError("line_polygon_degenerate")
    crosses = []
    for index in range(4):
        a, b, c = points[index], points[(index + 1) % 4], points[(index + 2) % 4]
        crosses.append((b[0] - a[0]) * (c[1] - b[1])
                       - (b[1] - a[1]) * (c[0] - b[0]))
    if not (all(cross > 0 for cross in crosses) or all(cross < 0 for cross in crosses)):
        raise LineGraphError("line_polygon_degenerate")
    return tuple(points)


@dataclass(frozen=True)
class OcrLineNode:
    node_id: str
    kind: Literal["ocr_line"]
    source_sha256: str
    raw_sidecar_sha256: str
    engine: str
    parser_config_sha256: str
    producer_code_sha256: str
    graph_rules_sha256: str
    unit_id: Literal["image-1"]
    page_number: Literal[1]
    image_size_px: tuple[int, int]
    raw_order: int
    position_order: int
    text: str
    text_span: tuple[int, int]
    polygon_px: tuple[tuple[float, float], ...]
    confidence: float
    raw_line_sha256: str
    source_locator: str


@dataclass(frozen=True)
class OcrLineGraph:
    source_id: str
    doc_id: str
    source_sha256: str
    raw_sidecar_sha256: str
    engine: str
    parser_config_sha256: str
    producer_code_sha256: str
    graph_rules_sha256: str
    image_size_px: tuple[int, int]
    page_text: str
    page_text_sha256: str
    nodes: tuple[OcrLineNode, ...]
    status: Literal["candidate", "abstained"]
    reason: str | None

    def research_payload(self) -> bytes:
        if self.page_text_sha256 != hashlib.sha256(self.page_text.encode("utf-8")).hexdigest():
            raise LineGraphError("page_text_hash_mismatch")
        if self.status == "candidate":
            if self.reason is not None or not self.nodes or self.page_text != "\n".join(
                    node.text for node in self.nodes):
                raise LineGraphError("graph_text_mismatch")
            if len({node.node_id for node in self.nodes}) != len(self.nodes):
                raise LineGraphError("duplicate_line_id")
            if {node.position_order for node in self.nodes} != set(range(len(self.nodes))):
                raise LineGraphError("position_order_invalid")
            for index, node in enumerate(self.nodes):
                if (node.kind != "ocr_line" or node.source_sha256 != self.source_sha256
                        or node.raw_sidecar_sha256 != self.raw_sidecar_sha256
                        or node.engine != self.engine
                        or node.parser_config_sha256 != self.parser_config_sha256
                        or node.producer_code_sha256 != self.producer_code_sha256
                        or node.graph_rules_sha256 != self.graph_rules_sha256
                        or node.image_size_px != self.image_size_px
                        or node.unit_id != "image-1" or node.page_number != 1
                        or node.raw_order != index
                        or self.page_text[slice(*node.text_span)] != node.text):
                    raise LineGraphError("line_pointer_invalid")
                expected_start = 0 if index == 0 else self.nodes[index - 1].text_span[1] + 1
                if node.text_span != (expected_start, expected_start + len(node.text)):
                    raise LineGraphError("line_offset_invalid")
                _polygon([list(point) for point in node.polygon_px], self.image_size_px)
                try:
                    locator = json.loads(node.source_locator)
                except ValueError as exc:
                    raise LineGraphError("line_locator_invalid") from exc
                if locator != {
                    "kind": "ocr_line", "source_sha256": self.source_sha256,
                    "raw_sidecar_sha256": self.raw_sidecar_sha256,
                    "page": 1, "engine": self.engine, "raw_order": index,
                    "polygon_px": [list(point) for point in node.polygon_px],
                    "raw_line_sha256": node.raw_line_sha256,
                } or node.source_locator != _canonical(locator):
                    raise LineGraphError("line_locator_invalid")
                expected_id = "ol_" + _digest([
                    self.source_sha256, self.raw_sidecar_sha256, self.engine,
                    self.parser_config_sha256, self.producer_code_sha256,
                    self.graph_rules_sha256, index, *node.text_span,
                    node.polygon_px, node.raw_line_sha256,
                ])[:24]
                if node.node_id != expected_id:
                    raise LineGraphError("line_pointer_invalid")
        elif (self.status != "abstained" or self.reason is None
              or re.fullmatch(r"[a-z0-9_]{1,64}", self.reason) is None
              or self.nodes or self.page_text):
            raise LineGraphError("graph_status_invalid")
        payload = (_canonical(asdict(self)) + "\n").encode("utf-8")
        if len(payload) > MAX_GRAPH_BYTES:
            raise LineGraphError("graph_size_limit")
        return payload


def _abstention(row: dict[str, Any], engine: str, raw_sha256: str,
                producer_sha256: str, rules_sha256: str, image_size: tuple[int, int],
                reason: str) -> OcrLineGraph:
    return OcrLineGraph(
        row["source_id"], row["doc_id"], row["source_sha256"], raw_sha256,
        engine, _digest(_config(engine)), producer_sha256, rules_sha256,
        image_size, "", hashlib.sha256(b"").hexdigest(), (), "abstained", reason,
    )


def build_line_graph(row: dict[str, Any], source_path: Path, engine: str, *,
                     raw_sidecar_sha256: str, producer_code_sha256: str,
                     graph_rules_sha256: str) -> OcrLineGraph:
    """Verify one saved engine page against the original PNG and raw text offsets."""
    config_sha256 = _digest(_config(engine))
    source_sha256 = row.get("source_sha256")
    if not isinstance(source_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise LineGraphError("source_identity_invalid")
    image_size = _image_size(source_path, source_sha256)
    if (row.get("image_size") != list(image_size)
            or not isinstance(row.get("source_id"), str)
            or not isinstance(row.get("doc_id"), str)):
        raise LineGraphError("sidecar_source_mismatch")
    result = row.get(engine)
    if not isinstance(result, dict) or not isinstance(result.get("lines"), list):
        raise LineGraphError("engine_sidecar_invalid")
    text, lines, failure = result.get("text"), result["lines"], result.get("failure")
    if not isinstance(text, str) or len(text) > MAX_PAGE_CHARS or len(lines) > MAX_LINES:
        raise LineGraphError("line_limit")
    if failure is not None:
        if not isinstance(failure, str) or text or lines:
            raise LineGraphError("engine_failure_invalid")
        return _abstention(row, engine, raw_sidecar_sha256,
                           producer_code_sha256, graph_rules_sha256, image_size,
                           "ocr_page_failed")
    if not text and not lines:
        return _abstention(row, engine, raw_sidecar_sha256,
                           producer_code_sha256, graph_rules_sha256, image_size,
                           "empty_ocr_page")
    if (not text or not lines or not _integer(result.get("lines_in_bounds"))
            or result["lines_in_bounds"] != len(lines)):
        raise LineGraphError("line_count_or_bounds_invalid")
    if text != "\n".join(line.get("text", "") for line in lines if isinstance(line, dict)):
        raise LineGraphError("page_text_line_mismatch")
    nodes: list[OcrLineNode] = []
    for index, line in enumerate(lines):
        if not isinstance(line, dict):
            raise LineGraphError("line_record_invalid")
        expected_keys = {"text", "confidence", "polygon", "raw_order",
                         "position_order", "start", "end"}
        if engine == "tesseract":
            expected_keys.add("hierarchy")
        if set(line) != expected_keys:
            raise LineGraphError("line_record_invalid")
        line_text, start, end = line.get("text"), line.get("start"), line.get("end")
        if not isinstance(line_text, str) or len(line_text) > MAX_LINE_CHARS:
            raise LineGraphError("line_length_limit")
        if (not line_text.strip() or "\n" in line_text or "\r" in line_text
                or not _integer(start) or not _integer(end, minimum=1)
                or end != start + len(line_text)
                or text[start:end] != line_text
                or not _integer(line.get("raw_order")) or line["raw_order"] != index
                or not _integer(line.get("position_order"))):
            raise LineGraphError("line_offset_invalid")
        expected_start = 0 if index == 0 else nodes[-1].text_span[1] + 1
        if start != expected_start:
            raise LineGraphError("line_offset_invalid")
        confidence = line.get("confidence")
        maximum = 1 if engine == "rapidocr" else 100
        if not _number(confidence) or not 0 <= confidence <= maximum:
            raise LineGraphError("line_confidence_invalid")
        polygon = _polygon(line.get("polygon"), image_size)
        if engine == "tesseract":
            hierarchy = line.get("hierarchy")
            if (not isinstance(hierarchy, list) or len(hierarchy) != 4
                    or not all(_integer(value, minimum=1) for value in hierarchy)
                    or hierarchy[0] != 1):
                raise LineGraphError("tesseract_hierarchy_invalid")
        elif "hierarchy" in line:
            raise LineGraphError("rapidocr_line_metadata_invalid")
        raw_line_sha256 = _digest(line)
        locator = _canonical({
            "kind": "ocr_line", "source_sha256": source_sha256,
            "raw_sidecar_sha256": raw_sidecar_sha256, "page": 1,
            "engine": engine, "raw_order": index, "polygon_px": polygon,
            "raw_line_sha256": raw_line_sha256,
        })
        node_id = "ol_" + _digest([source_sha256, raw_sidecar_sha256, engine,
                                  config_sha256, producer_code_sha256,
                                  graph_rules_sha256, index, start, end,
                                  polygon, raw_line_sha256])[:24]
        nodes.append(OcrLineNode(
            node_id, "ocr_line", source_sha256, raw_sidecar_sha256, engine,
            config_sha256, producer_code_sha256, graph_rules_sha256,
            "image-1", 1, image_size, index, line["position_order"],
            line_text, (start, end), polygon, float(confidence),
            raw_line_sha256, locator,
        ))
    expected_position = sorted(range(len(nodes)), key=lambda index: (
        min(point[1] for point in nodes[index].polygon_px),
        min(point[0] for point in nodes[index].polygon_px), index,
    ))
    if any(nodes[index].position_order != position
           for position, index in enumerate(expected_position)):
        raise LineGraphError("position_order_invalid")
    graph = OcrLineGraph(
        row["source_id"], row["doc_id"], source_sha256, raw_sidecar_sha256,
        engine, config_sha256, producer_code_sha256, graph_rules_sha256,
        image_size, text, hashlib.sha256(text.encode("utf-8")).hexdigest(),
        tuple(nodes), "candidate", None,
    )
    graph.research_payload()
    return graph


def _read_jsonl(path: Path, maximum: int) -> list[dict[str, Any]]:
    _sha256(path, maximum)
    try:
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                   if line.strip()]
    except (OSError, UnicodeError, ValueError) as exc:
        raise LineGraphError("jsonl_invalid") from exc
    if any(not isinstance(item, dict) for item in records):
        raise LineGraphError("jsonl_invalid")
    return records


def run_locked_corpus(stage_root: Path, raw_sidecar_path: Path, output_dir: Path) -> dict[str, object]:
    """Verify 60 source PNGs and the prior raw OCR bytes; write no gold or model data."""
    if output_dir.exists():
        raise LineGraphError("output_exists")
    cohort_path = stage_root / "cohort_development.jsonl"
    if _sha256(cohort_path, MAX_RAW_BYTES) != COHORT_SHA256:
        raise LineGraphError("cohort_lock_mismatch")
    if _sha256(raw_sidecar_path, MAX_RAW_BYTES) != RAW_SIDECAR_SHA256:
        raise LineGraphError("raw_sidecar_lock_mismatch")
    producer_path = Path(__file__).with_name("cord_page_ocr_diagnostic.py")
    if _code_hash(producer_path) != PRODUCER_CODE_LF_SHA256:
        raise LineGraphError("producer_code_lock_mismatch")
    rules_sha256 = _code_hash(Path(__file__))
    cohort = _read_jsonl(cohort_path, MAX_RAW_BYTES)
    raw_rows = _read_jsonl(raw_sidecar_path, MAX_RAW_BYTES)
    if len(cohort) != 60 or len(raw_rows) != 60:
        raise LineGraphError("development_count_mismatch")
    sources: dict[str, tuple[dict[str, Any], Path, tuple[int, int]]] = {}
    for source in cohort:
        source_sha256 = source.get("source_sha256")
        source_id = source.get("source_id")
        source_path_value = source.get("source_path")
        if (not isinstance(source_sha256, str)
                or not re.fullmatch(r"[0-9a-f]{64}", source_sha256)
                or not isinstance(source_id, str)
                or re.fullmatch(r"cord-v2/test/\d{4}", source_id) is None
                or not isinstance(source_path_value, str)
                or source.get("evaluation_split") != "development"
                or not isinstance(source.get("doc_id"), str)
                or source_sha256 in sources):
            raise LineGraphError("cohort_identity_invalid")
        source_path = Path(source_path_value).resolve()
        if source_path.parent != (stage_root / "input_development").resolve():
            raise LineGraphError("source_path_outside_development")
        image_size = _image_size(source_path, source_sha256)
        if source_path.stat().st_size != source.get("source_size_bytes"):
            raise LineGraphError("source_size_mismatch")
        sources[source_sha256] = (source, source_path, image_size)
    by_source: dict[str, dict[str, Any]] = {}
    for row in raw_rows:
        source_sha256 = row.get("source_sha256")
        if (source_sha256 not in sources or source_sha256 in by_source
                or set(row) != {"doc_id", "source_id", "source_sha256", "image_size",
                                "tesseract", "rapidocr"}):
            raise LineGraphError("raw_source_set_mismatch")
        source, _, image_size = sources[source_sha256]
        if (row["doc_id"] != source["doc_id"] or row["source_id"] != source["source_id"]
                or row["image_size"] != list(image_size)):
            raise LineGraphError("raw_source_set_mismatch")
        by_source[source_sha256] = row
    if set(by_source) != set(sources):
        raise LineGraphError("raw_source_set_mismatch")
    graphs: list[OcrLineGraph] = []
    for source_sha256 in sorted(sources):
        _, source_path, image_size = sources[source_sha256]
        row = by_source[source_sha256]
        for engine in ENGINES:
            try:
                graph = build_line_graph(
                    row, source_path, engine,
                    raw_sidecar_sha256=RAW_SIDECAR_SHA256,
                    producer_code_sha256=PRODUCER_CODE_LF_SHA256,
                    graph_rules_sha256=rules_sha256,
                )
            except LineGraphError as exc:
                if str(exc) in SOURCE_LOCK_REASONS:
                    raise
                graph = _abstention(row, engine, RAW_SIDECAR_SHA256,
                                    PRODUCER_CODE_LF_SHA256, rules_sha256,
                                    image_size, str(exc))
            graphs.append(graph)
    output_dir.mkdir(parents=True, exist_ok=False)
    graph_path = output_dir / "line_graphs.jsonl"
    with graph_path.open("wb") as handle:
        for graph in graphs:
            handle.write(graph.research_payload())
    engines = {}
    for engine in ENGINES:
        selected = [graph for graph in graphs if graph.engine == engine]
        engines[engine] = {
            "parser_config_sha256": _digest(_config(engine)),
            "raw_sidecar_lines": sum(len(row[engine]["lines"]) for row in raw_rows),
            "candidate_pages": sum(graph.status == "candidate" for graph in selected),
            "abstained_pages": sum(graph.status == "abstained" for graph in selected),
            "ocr_line_nodes": sum(len(graph.nodes) for graph in selected),
            "abstention_reasons": dict(sorted(Counter(
                graph.reason for graph in selected if graph.reason is not None).items())),
        }
    receipt: dict[str, object] = {
        "protocol": "cord_s1_ocr_line_graph_v1", "scope": "CORD development PNGs only",
        "cohort_sha256": COHORT_SHA256, "raw_sidecar_sha256": RAW_SIDECAR_SHA256,
        "producer_code_lf_sha256": PRODUCER_CODE_LF_SHA256,
        "graph_rules_lf_sha256": rules_sha256,
        "original_sources_verified": len(sources), "distinct_source_hashes": len(sources),
        "graph_records": len(graphs), "engines": engines,
        "line_graphs_sha256": _sha256(graph_path, MAX_RAW_BYTES * 8),
        "model_calls": 0, "gold_access": False, "reserved_source_access": False,
        "product_extraction_calls": 0,
        "limitations": [
            "OCR quadrilaterals are line regions, not word boxes or table cells.",
            "Pixel bounds and text offsets do not verify transcription or field meaning.",
            "No schema, row links, accepted values, model calls, or cost improvement were tested.",
        ],
    }
    (output_dir / "receipt.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage-root", type=Path, required=True)
    parser.add_argument("--raw-sidecar", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_locked_corpus(args.stage_root, args.raw_sidecar, args.output_dir),
                     indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
