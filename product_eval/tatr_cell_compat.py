"""Source-free research harness for the pinned Microsoft TATR cell functions.

This loads only checksum-verified, staged MIT source. It does not load models,
open selected documents, or run in the product extraction path. The official
functions remain unedited; their PyMuPDF rectangle dependency is replaced in
memory by :mod:`product_eval.tatr_rect` after source verification.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from product_eval.tatr_asset_preflight import EXPECTED, verify_assets
from product_eval.tatr_native_geometry import WordToken
from product_eval.tatr_output_adapter import CLASS_LABELS
from product_eval.tatr_rect import Rect

INFERENCE_FUNCTIONS = (
    "iob", "align_headers", "refine_table_structure",
    "objects_to_structures", "structure_to_cells",
)
STRUCTURE_THRESHOLDS = {label: 0.5 for label in CLASS_LABELS["structure"]}


@dataclass(frozen=True)
class CellResult:
    cells: list[dict[str, Any]]
    confidence_score: float
    unassigned_token_ids: tuple[str, ...]


def _verified_source(root: Path, name: str) -> str:
    expected_size, expected_hash = EXPECTED[name]
    path = (root / name).resolve(strict=True)
    if not path.is_relative_to(root.resolve(strict=True)):
        raise ValueError("TATR source escapes asset root")
    contents = path.read_bytes()
    if len(contents) != expected_size or hashlib.sha256(contents).hexdigest() != expected_hash:
        raise ValueError(f"TATR source differs from pinned bytes: {name}")
    return contents.decode("utf-8")


def load_official_cell_functions(asset_root: Path) -> ModuleType:
    """Verify all pinned assets, then expose the official pure cell functions.

    The staged model files are only hashed; no model weights are deserialized.
    The exact Microsoft source files and MIT notice are covered by the same
    asset lock. Fail closed if either source file changes.
    """
    verify_assets(asset_root)
    for card in ("detection/README.md", "structure/README.md", "author-notice/README.md"):
        if "license: mit" not in _verified_source(asset_root, card).lower():
            raise ValueError(f"pinned TATR model card lacks MIT declaration: {card}")
    post_source = _verified_source(asset_root, "microsoft-source/src/postprocess.py")
    old_import = "from fitz import Rect\n"
    if post_source.count(old_import) != 1:
        raise ValueError("pinned postprocessor has unexpected rectangle import")
    post_source = post_source.replace(old_import, "from product_eval.tatr_rect import Rect\n")
    postprocess = ModuleType("tatr_pinned_postprocess")
    # The full asset manifest pins this executable source by SHA-256 before execution.
    exec(compile(post_source, "pinned_microsoft_postprocess.py", "exec"), postprocess.__dict__)  # noqa: S102

    inference_source = _verified_source(asset_root, "microsoft-source/src/inference.py")
    tree = ast.parse(inference_source)
    nodes = [node for node in tree.body
             if isinstance(node, ast.FunctionDef) and node.name in INFERENCE_FUNCTIONS]
    if len(nodes) != len(INFERENCE_FUNCTIONS) or {node.name for node in nodes} != set(INFERENCE_FUNCTIONS):
        raise ValueError("pinned inference cell functions changed")
    cell_module = ModuleType("tatr_pinned_inference_cells")
    cell_module.__dict__.update({"Rect": Rect, "postprocess": postprocess, "defaultdict": defaultdict})
    subset = ast.Module(body=nodes, type_ignores=[])
    exec(compile(subset, "pinned_microsoft_inference.py", "exec"), cell_module.__dict__)  # noqa: S102
    return cell_module


def _box(values: Sequence[float], image_size: tuple[int, int]) -> list[float]:
    width, height = image_size
    if width <= 0 or height <= 0:
        raise ValueError("invalid crop dimensions")
    if len(values) != 4 or not all(
        isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)
        for value in values
    ):
        raise ValueError("box requires four finite coordinates")
    left, top, right, bottom = (float(value) for value in values)
    if not 0 <= left < right <= width or not 0 <= top < bottom <= height:
        raise ValueError("box falls outside the image or has no area")
    return [left, top, right, bottom]


def prepare_word_tokens(
    tokens: Sequence[WordToken | Mapping[str, Any]],
    image_size: tuple[int, int],
) -> list[dict[str, Any]]:
    """Validate word-level native/OCR tokens and supply official order fields.

    Existing PDFium ``WordToken`` order is preserved. OCR mappings must supply
    explicit contiguous ``reading_order`` and engine provenance; this function
    never guesses reading order from box coordinates or silently deduplicates.
    """
    prepared: list[dict[str, Any]] = []
    seen: set[tuple[str, str, tuple[float, ...]]] = set()
    source_mode: str | None = None
    for index, token in enumerate(tokens):
        if isinstance(token, WordToken):
            data: dict[str, Any] = {
                "text": token.text, "bbox": token.bbox,
                "source": token.source, "reading_order": index,
                "source_token_id": f"pdfium:{token.char_start}:{token.char_end}",
                "pdf_bbox": token.pdf_bbox,
            }
        else:
            data = dict(token)
        text = data.get("text")
        if not isinstance(text, str) or not text or any(char.isspace() for char in text):
            raise ValueError("TATR requires one nonempty word per token")
        source = data.get("source")
        if source not in ("pdfium_native", "ocr_word"):
            raise ValueError("unknown TATR token source")
        if source_mode is None:
            source_mode = source
        elif source != source_mode:
            raise ValueError("mixed native and OCR words require an explicit page-level route")
        if data.get("reading_order") != index or isinstance(data["reading_order"], bool):
            raise ValueError("tokens must have explicit contiguous reading order")
        if source == "ocr_word":
            if not isinstance(data.get("ocr_engine"), str) or not data["ocr_engine"]:
                raise ValueError("OCR word lacks engine provenance")
            if not isinstance(data.get("ocr_revision"), str) or not data["ocr_revision"]:
                raise ValueError("OCR word lacks revision provenance")
            confidence = data.get("ocr_confidence")
            if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
                raise ValueError("OCR word lacks finite 0-1 confidence")
        elif "pdf_bbox" not in data:
            raise ValueError("native word lacks original PDF box")
        box = _box(data["bbox"], image_size)
        if source == "pdfium_native":
            pdf_box = data["pdf_bbox"]
            if (len(pdf_box) != 4 or not all(math.isfinite(value) for value in pdf_box)
                    or pdf_box[2] <= pdf_box[0] or pdf_box[3] <= pdf_box[1]):
                raise ValueError("invalid original PDF box")
        duplicate_key = (source, text, tuple(box))
        if duplicate_key in seen:
            raise ValueError("duplicate TATR word token")
        seen.add(duplicate_key)
        token_id = data.get("source_token_id", f"{source}:{index}")
        if not isinstance(token_id, str) or not token_id:
            raise ValueError("invalid source token id")
        prepared.append({
            **data,
            "bbox": box,
            "source_token_id": token_id,
            "block_num": 0,
            "line_num": 0,
            "span_num": index,
        })
    if len({token["source_token_id"] for token in prepared}) != len(prepared):
        raise ValueError("duplicate TATR source token id")
    return prepared


def cells_from_synthetic_objects(
    official: ModuleType,
    objects: Sequence[Mapping[str, Any]],
    tokens: Sequence[WordToken | Mapping[str, Any]],
    image_size: tuple[int, int],
) -> CellResult:
    """Exercise the official structure/cell functions without model inference.

    Exactly one table crop is supported by this prerequisite harness. The
    eventual runner must handle multiple detected crops and page transforms.
    """
    words = prepare_word_tokens(tokens, image_size)
    active: list[dict[str, Any]] = []
    for item in objects:
        label = item.get("label")
        if label == "no object":
            continue
        if label not in CLASS_LABELS["structure"]:
            raise ValueError("unknown TATR structure class")
        score = item.get("score")
        if not isinstance(score, (int, float)) or isinstance(score, bool) or not math.isfinite(score):
            raise ValueError("nonfinite TATR structure score")
        if not 0 <= score <= 1:
            raise ValueError("TATR structure score outside 0-1")
        if score >= STRUCTURE_THRESHOLDS[label]:
            active.append({**copy.deepcopy(dict(item)), "bbox": _box(item["bbox"], image_size)})
    if sum(item["label"] == "table" for item in active) != 1:
        raise ValueError("source-free harness requires one retained table")
    structures = official.objects_to_structures(active, words, STRUCTURE_THRESHOLDS)
    if len(structures) != 1 or not structures[0]["rows"] or not structures[0]["columns"]:
        raise ValueError("TATR did not produce a row/column grid")
    cells, confidence = official.structure_to_cells(structures[0], words)
    occupied: set[tuple[int, int]] = set()
    assigned: set[str] = set()
    for cell in cells:
        _box(cell["bbox"], image_size)
        if not cell["row_nums"] or not cell["column_nums"]:
            raise ValueError("TATR cell lacks row/column indexes")
        for row in cell["row_nums"]:
            for column in cell["column_nums"]:
                slot = (row, column)
                if slot in occupied:
                    raise ValueError("overlapping TATR cell grid slots")
                occupied.add(slot)
        for span in cell["spans"]:
            token_id = span["source_token_id"]
            if token_id in assigned:
                raise ValueError("TATR assigned one token to multiple cells")
            assigned.add(token_id)
    if not math.isfinite(confidence):
        raise ValueError("nonfinite TATR cell confidence")
    return CellResult(cells, float(confidence), tuple(
        word["source_token_id"] for word in words if word["source_token_id"] not in assigned
    ))
