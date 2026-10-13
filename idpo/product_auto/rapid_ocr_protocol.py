"""Versioned, source-bound IPC for the optional local RapidOCR worker.

This module uses only the standard library so the isolated OCR interpreter can
load it without importing the product application or its provider clients.
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

REVISION = "rapidocr==3.10.0;onnxruntime==1.31.0;PP-OCRv6-small;lines-v1"
MODEL_SHA256 = {
    "PP-OCRv6_det_small.onnx": "090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f",
    "PP-OCRv6_rec_small.onnx": "6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884",
    "ch_ppocr_mobile_v2.0_cls_mobile.onnx": "e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c",
}
MAX_EDGE = 4096
MAX_PIXELS = 12_000_000
MAX_PNG_BYTES = 64 * 1024 * 1024
MAX_RESULT_BYTES = 16 * 1024 * 1024
MAX_TEXT_CHARS = 2_000_000
MAX_LINES = 10_000
LINE_SCORE_THRESHOLD = 0.5
PROVIDERS = {part: ["CPUExecutionProvider"] for part in ("text_det", "text_cls", "text_rec")}
WORKER_FAILURES = frozenset({
    "rapidocr_input_mismatch", "rapidocr_image_size", "rapidocr_runtime_mismatch",
    "rapidocr_model_mismatch", "rapidocr_provider_mismatch", "rapidocr_offline_policy",
    "rapidocr_result_invalid", "rapidocr_no_text", "rapidocr_worker_failed",
})


class RapidOcrError(RuntimeError):
    """A stable, content-free failure code suitable for product metadata."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_image_size(size: Any) -> tuple[int, int]:
    if not isinstance(size, (list, tuple)) or len(size) != 2:
        raise RapidOcrError("rapidocr_image_size")
    if any(type(value) is not int or value < 1 or value > MAX_EDGE for value in size):
        raise RapidOcrError("rapidocr_image_size")
    width, height = size
    if width * height > MAX_PIXELS:
        raise RapidOcrError("rapidocr_image_size")
    return width, height


def _number(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def validate_lines(raw_lines: Any, image_size: tuple[int, int]) -> tuple[str, list[dict]]:
    """Keep OCR text verbatim; offsets are Python Unicode character offsets."""
    width, height = validate_image_size(image_size)
    if not isinstance(raw_lines, list) or len(raw_lines) > MAX_LINES:
        raise RapidOcrError("rapidocr_result_invalid")
    lines, texts, cursor = [], [], 0
    for index, raw in enumerate(raw_lines):
        if not isinstance(raw, dict):
            raise RapidOcrError("rapidocr_result_invalid")
        text, score, polygon = raw.get("text"), raw.get("score"), raw.get("polygon")
        if (not isinstance(text, str) or not text.strip() or "\x00" in text
                or not _number(score) or not LINE_SCORE_THRESHOLD <= score <= 1
                or not isinstance(polygon, list) or len(polygon) != 4):
            raise RapidOcrError("rapidocr_result_invalid")
        for point in polygon:
            if (not isinstance(point, list) or len(point) != 2
                    or not all(_number(value) for value in point)
                    or not 0 <= point[0] <= width or not 0 <= point[1] <= height):
                raise RapidOcrError("rapidocr_result_invalid")
        # A quadrilateral must have nonzero area and consistently turn, so a
        # malformed or self-crossing polygon cannot become a visual citation.
        turns = []
        for corner in range(4):
            a, b, c = (polygon[(corner + step) % 4] for step in range(3))
            turns.append((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))
        if not (all(value > 0 for value in turns) or all(value < 0 for value in turns)):
            raise RapidOcrError("rapidocr_result_invalid")
        end = cursor + len(text)
        if end > MAX_TEXT_CHARS:
            raise RapidOcrError("rapidocr_result_invalid")
        lines.append({"line_index": index, "text": text, "start": cursor, "end": end,
                      "score": float(score), "polygon": polygon})
        texts.append(text)
        cursor = end + 1
    return "\n".join(texts), lines


def validate_payload(payload: Any, *, image_size: tuple[int, int], input_hash: str) -> tuple[str, list[dict]]:
    if (not isinstance(payload, dict) or type(payload.get("schema_version")) is not int
            or payload.get("schema_version") != 1
            or payload.get("status") != "ready" or payload.get("revision") != REVISION
            or payload.get("input_png_sha256") != input_hash
            or payload.get("image_size") != list(image_size)
            or payload.get("model_sha256") != MODEL_SHA256
            or payload.get("providers") != PROVIDERS
            or payload.get("line_score_threshold") != LINE_SCORE_THRESHOLD):
        raise RapidOcrError("rapidocr_result_invalid")
    validate_image_size(payload.get("image_size"))
    return validate_lines(payload.get("lines"), image_size)
