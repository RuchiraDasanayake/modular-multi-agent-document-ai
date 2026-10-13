"""Source-only PDFium word boxes and page/raster transforms for the TATR trial.

This module does not run Table Transformer or assign words to cells. Its output
is a proposed native-text feed that must pass the protocol's separate visual
and scan-OCR checks before document inference can start.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


class GeometryError(ValueError):
    """A source box cannot be represented on the rendered PDF page."""


@dataclass(frozen=True)
class WordToken:
    text: str
    bbox: tuple[float, float, float, float]
    pdf_bbox: tuple[float, float, float, float]
    char_start: int
    char_end: int
    source: str = "pdfium_native"


def _rect(box: tuple[float, float, float, float]) -> None:
    if len(box) != 4 or not all(math.isfinite(value) for value in box):
        raise GeometryError("rectangle coordinates must be finite")
    if box[2] <= box[0] or box[3] <= box[1]:
        raise GeometryError("rectangle must have positive area")


def _corners(box: tuple[float, float, float, float]) -> tuple[tuple[float, float], ...]:
    left, bottom, right, top = box
    return ((left, bottom), (left, top), (right, bottom), (right, top))


def _bounds(points: tuple[tuple[float, float], ...]) -> tuple[float, float, float, float]:
    return (
        min(point[0] for point in points), min(point[1] for point in points),
        max(point[0] for point in points), max(point[1] for point in points),
    )


def page_box_to_pixels(
    pdf_box: tuple[float, float, float, float],
    converter: Any,
    image_width: int,
    image_height: int,
) -> tuple[float, float, float, float]:
    """Project a PDF-unit box with PDFium's actual render transform."""
    _rect(pdf_box)
    if image_width <= 0 or image_height <= 0:
        raise GeometryError("invalid rendered image dimensions")
    pixel_box = _bounds(tuple(converter.to_bitmap(x, y) for x, y in _corners(pdf_box)))
    _rect(pixel_box)
    left, top, right, bottom = pixel_box
    if left < -1 or top < -1 or right > image_width + 1 or bottom > image_height + 1:
        raise GeometryError("PDF box lies outside the rendered image")
    clipped = (max(left, 0), max(top, 0), min(right, image_width), min(bottom, image_height))
    _rect(clipped)
    return clipped


def pixel_box_to_page(
    pixel_box: tuple[float, float, float, float],
    converter: Any,
    image_width: int,
    image_height: int,
) -> tuple[float, float, float, float]:
    """Reproject an image-pixel box to the original PDF page coordinates."""
    _rect(pixel_box)
    if image_width <= 0 or image_height <= 0:
        raise GeometryError("invalid rendered image dimensions")
    left, top, right, bottom = pixel_box
    if left < 0 or top < 0 or right > image_width or bottom > image_height:
        raise GeometryError("pixel box lies outside the rendered image")
    # PDFium's FPDF_DeviceToPage takes integer raster coordinates. Model boxes
    # have fractional edges, so expand to enclosing pixels before conversion.
    # The page-point anchor is conservative by at most one source pixel/edge.
    integer_box = (
        math.floor(left), math.floor(top), math.ceil(right), math.ceil(bottom)
    )
    page_box = _bounds(tuple(converter.to_page(x, y) for x, y in _corners(integer_box)))
    _rect(page_box)
    return page_box


def native_word_tokens(page: Any, bitmap: Any) -> list[WordToken]:
    """Split PDFium character order on whitespace or a large spatial break.

    PDFium's internal character array is the only ordering used. A missing
    Unicode map or invalid source geometry fails the page, rather than silently
    moving text between cells.
    """
    import pypdfium2.raw as pdfium

    converter = bitmap.get_posconv(page)
    text_page = page.get_textpage()
    result: list[WordToken] = []
    chars: list[str] = []
    boxes: list[tuple[float, float, float, float]] = []
    page_boxes: list[tuple[float, float, float, float]] = []
    first = 0

    def flush(last: int) -> None:
        nonlocal chars, boxes, page_boxes
        if not chars:
            return
        result.append(WordToken(
            text="".join(chars),
            bbox=_bounds(tuple((x, y) for box in boxes for x, y in _corners(box))),
            pdf_bbox=_bounds(tuple((x, y) for box in page_boxes for x, y in _corners(box))),
            char_start=first,
            char_end=last,
        ))
        chars, boxes, page_boxes = [], [], []

    try:
        for index in range(text_page.count_chars()):
            codepoint = pdfium.FPDFText_GetUnicode(text_page.raw, index)
            if codepoint == 0 or 0xD800 <= codepoint <= 0xDFFF or codepoint > 0x10FFFF:
                raise GeometryError(f"invalid PDF Unicode mapping at char {index}")
            char = chr(codepoint)
            if char.isspace():
                flush(index)
                continue
            page_box = tuple(float(value) for value in text_page.get_charbox(index))
            pixel_box = page_box_to_pixels(page_box, converter, bitmap.width, bitmap.height)
            if page_boxes:
                prev = page_boxes[-1]
                height = max(prev[3] - prev[1], page_box[3] - page_box[1])
                line_break = abs((prev[1] + prev[3] - page_box[1] - page_box[3]) / 2) > 0.7 * height
                gap = page_box[0] - prev[2] > 1.5 * height
                backwards = page_box[0] < prev[0] - 0.4 * height
                if line_break or gap or backwards:
                    flush(index)
            if not chars:
                first = index
            chars.append(char)
            boxes.append(pixel_box)
            page_boxes.append(page_box)
        flush(text_page.count_chars())
        return result
    finally:
        text_page.close()
