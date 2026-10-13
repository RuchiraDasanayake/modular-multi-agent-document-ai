"""Source-free raster crop transforms shared by local table-parser trials.

Detector proposals and word boxes use the rendered page's pixel frame. This
module records the exact integer crop and rejects boxes that cross its edge;
PDFium's converter handles the separate PDF crop/rotation transform.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from product_eval.tatr_native_geometry import GeometryError, pixel_box_to_page


@dataclass(frozen=True)
class TableCrop:
    proposal_box: tuple[float, float, float, float]
    raster_box: tuple[int, int, int, int]
    page_width: int
    page_height: int
    requested_padding: int
    padding_clipped_at_page_edge: bool

    @property
    def size(self) -> tuple[int, int]:
        left, top, right, bottom = self.raster_box
        return right - left, bottom - top


def _valid_box(box: tuple[float, float, float, float]) -> bool:
    return (len(box) == 4
            and all(isinstance(value, (int, float)) and not isinstance(value, bool)
                    and math.isfinite(value) for value in box)
            and box[0] < box[2] and box[1] < box[3])


def table_crop_from_proposal(
    proposal_box: tuple[float, float, float, float],
    page_size: tuple[int, int],
    *,
    padding: int = 5,
) -> TableCrop:
    """Freeze a detected box as an integer page-raster crop, with at most 5 px pad."""
    if len(page_size) != 2 or any(
        not isinstance(value, int) or isinstance(value, bool) or value <= 0
        for value in page_size
    ):
        raise GeometryError("invalid rendered page size")
    width, height = page_size
    if not isinstance(padding, int) or isinstance(padding, bool) or not 0 <= padding <= 5:
        raise GeometryError("table crop padding must be an integer from 0 to 5")
    if not _valid_box(proposal_box):
        raise GeometryError("invalid table proposal box")
    left, top, right, bottom = proposal_box
    if left < 0 or top < 0 or right > width or bottom > height:
        raise GeometryError("table proposal lies outside page raster")
    raster_box = (
        max(0, math.floor(left - padding)),
        max(0, math.floor(top - padding)),
        min(width, math.ceil(right + padding)),
        min(height, math.ceil(bottom + padding)),
    )
    if raster_box[0] >= raster_box[2] or raster_box[1] >= raster_box[3]:
        raise GeometryError("table crop has no area")
    return TableCrop(
        tuple(float(value) for value in proposal_box), raster_box,
        width, height, padding,
        left - padding < 0 or top - padding < 0
        or right + padding > width or bottom + padding > height,
    )


def crop_box_to_page_pixels(
    crop: TableCrop, box: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    """Map one fully contained local cell box to the rendered page pixel frame."""
    if not _valid_box(box):
        raise GeometryError("invalid local cell box")
    width, height = crop.size
    if box[0] < 0 or box[1] < 0 or box[2] > width or box[3] > height:
        raise GeometryError("local cell box lies outside table crop")
    left, top = crop.raster_box[:2]
    return box[0] + left, box[1] + top, box[2] + left, box[3] + top


def page_word_to_crop(
    crop: TableCrop, page_box: tuple[float, float, float, float]
) -> tuple[float, float, float, float] | None:
    """Map a word only when it is wholly inside; partial words are ambiguous."""
    if not _valid_box(page_box):
        raise GeometryError("invalid source word box")
    if (page_box[0] < 0 or page_box[1] < 0
            or page_box[2] > crop.page_width or page_box[3] > crop.page_height):
        raise GeometryError("source word box lies outside page raster")
    left, top, right, bottom = crop.raster_box
    if (page_box[2] <= left or page_box[0] >= right
            or page_box[3] <= top or page_box[1] >= bottom):
        return None
    if (page_box[0] < left or page_box[1] < top
            or page_box[2] > right or page_box[3] > bottom):
        raise GeometryError("source word crosses table crop edge")
    return (
        page_box[0] - left, page_box[1] - top,
        page_box[2] - left, page_box[3] - top,
    )


def crop_box_to_pdf_page(
    crop: TableCrop,
    box: tuple[float, float, float, float],
    converter: Any,
) -> tuple[float, float, float, float]:
    """Reproject a local cell box through the exact crop and PDFium converter."""
    page_box = crop_box_to_page_pixels(crop, box)
    return pixel_box_to_page(page_box, converter, crop.page_width, crop.page_height)
