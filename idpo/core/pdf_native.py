"""Bounded PDF paint inspection before trusting an embedded text layer."""

from __future__ import annotations

import ctypes
import math
import threading
from itertools import pairwise
from pathlib import Path

# All PDFium use in this process, including rendering, must share this lock.
PDFIUM_LOCK = threading.Lock()
MAX_OBJECTS = 10_000
MAX_TEXT_CHARS = 1_000_000
MAX_IMAGES = 256
MAX_FORM_DEPTH = 8


def _clip(box, bounds):
    if not all(math.isfinite(float(value)) for value in (*box, *bounds)):
        raise ValueError("Non-finite PDF geometry")
    left, bottom = max(box[0], bounds[0]), max(box[1], bounds[1])
    right, top = min(box[2], bounds[2]), min(box[3], bounds[3])
    return (left, bottom, right, top) if right > left and top > bottom else None


def _union_area(rectangles):
    """Bounded exact union of axis-aligned boxes; overlapping images count once."""
    xs = sorted({edge for rectangle in rectangles for edge in (rectangle[0], rectangle[2])})
    area = 0.0
    for left, right in pairwise(xs):
        intervals = sorted((b, t) for l, b, r, t in rectangles if l < right and r > left)
        height, end = 0.0, -math.inf
        for bottom, top in intervals:
            height += max(0.0, top - max(bottom, end))
            end = max(end, top)
        area += (right - left) * height
    return area


def _alpha(raw, obj, stroke=False):
    channels = [ctypes.c_uint() for _ in range(4)]
    get_color = raw.FPDFPageObj_GetStrokeColor if stroke else raw.FPDFPageObj_GetFillColor
    if not get_color(obj, *(ctypes.byref(channel) for channel in channels)):
        raise ValueError("PDF text color unavailable")
    return channels[3].value


def _painted(raw, obj):
    mode = raw.FPDFTextObj_GetTextRenderMode(obj)
    if mode not in range(8):
        raise ValueError("PDF text render mode unavailable")
    if mode in (3, 7):  # Neither invisible text nor clip-only text paints glyphs.
        return False
    return ((mode in (0, 2, 4, 6) and _alpha(raw, obj) > 0)
            or (mode in (1, 2, 5, 6) and _alpha(raw, obj, stroke=True) > 0))


def inspect_native_layer(path: Path, page_index: int) -> dict[str, object]:
    """Inspect painting, not semantic correctness. Unknown geometry requires OCR.

    Invisible searchable OCR can be perfectly valid. We conservatively re-OCR it
    because text-only evidence cannot establish correspondence with visible pixels.
    Nested forms are bounded and reported as unknown: their inherited transforms,
    clips and transparency need a fuller paint interpreter than this guard.
    """
    result: dict[str, object] = {
        "version": 1, "inspector": "pdfium_paint_v1", "requires_ocr": True,
        "reason": "inspection_unavailable", "painting_text_chars": 0,
        "nonpainting_text_chars": 0, "image_coverage": None, "objects": 0,
    }
    try:
        import pypdfium2 as pdfium

        with PDFIUM_LOCK, pdfium.PdfDocument(str(path)) as pdf:
            page = pdf[page_index]
            try:
                bounds = page.get_bbox()
                area = (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])
                if not math.isfinite(area) or area <= 0:
                    raise ValueError("Invalid PDF page bounds")
                textpage = page.get_textpage()
                try:
                    if textpage.count_chars() > MAX_TEXT_CHARS:
                        result["reason"] = "inspection_limit"
                        return result
                    images = []
                    nested = False
                    for index, obj in enumerate(page.get_objects(max_depth=MAX_FORM_DEPTH, textpage=textpage), 1):
                        result["objects"] = index
                        if index > MAX_OBJECTS:
                            result["reason"] = "inspection_limit"
                            return result
                        if obj.type == pdfium.raw.FPDF_PAGEOBJ_FORM:
                            nested = True
                        # A child's box is in its container's coordinates. Do not
                        # pretend it is in page space when transforms are unknown.
                        if obj.level:
                            continue
                        box = _clip(obj.get_bounds(), bounds)
                        if obj.type == pdfium.raw.FPDF_PAGEOBJ_IMAGE and box:
                            images.append(box)
                            if len(images) > MAX_IMAGES:
                                result["reason"] = "inspection_limit"
                                return result
                        elif obj.type == pdfium.raw.FPDF_PAGEOBJ_TEXT:
                            count = len(obj.extract().strip())
                            key = "painting_text_chars" if box and _painted(pdfium.raw, obj) else "nonpainting_text_chars"
                            result[key] += count
                    result["image_coverage"] = round(min(1.0, _union_area(images) / area), 6)
                    if nested:
                        result["reason"] = "nested_paint_state_unassessed"
                    elif result["image_coverage"] >= 0.5 and result["painting_text_chars"] < 40:
                        result["reason"] = "raster_without_painting_text"
                    elif result["nonpainting_text_chars"]:
                        result["reason"] = "nonpainting_text_layer"
                    else:
                        result.update(requires_ocr=False, reason="painting_native_text")
                finally:
                    textpage.close()
            finally:
                page.close()
    except Exception as exc:  # noqa: BLE001 - an uninspectable layer cannot authorize native grounding
        result["error_type"] = type(exc).__name__
    return result
