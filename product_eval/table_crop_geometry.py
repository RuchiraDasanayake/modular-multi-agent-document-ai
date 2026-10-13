"""Source-free raster crop transforms shared by local table-parser trials.

Detector proposals and word boxes use the rendered page's pixel frame. This
module records the exact integer crop and rejects boxes that cross its edge;
PDFium's converter handles the separate PDF crop/rotation transform.
"""

from __future__ import annotations

import math
import numbers
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


def _valid_box(box: Any) -> bool:
    if (isinstance(box, (str, bytes))
            or not hasattr(box, "__len__") or not hasattr(box, "__getitem__")):
        return False
    try:
        values = tuple(box)
    except TypeError:
        return False
    return (len(values) == 4
            and all(isinstance(value, numbers.Real) and not isinstance(value, bool)
                    and math.isfinite(value) for value in values)
            and values[0] < values[2] and values[1] < values[3])


def table_crop_from_proposal(
    proposal_box: tuple[float, float, float, float],
    page_size: tuple[int, int],
    *,
    padding: int = 5,
) -> TableCrop:
    """Freeze a detected box as an integer page-raster crop, with at most 5 px pad."""
    if isinstance(page_size, (str, bytes)):
        raise GeometryError("invalid rendered page size")
    try:
        dimensions = tuple(page_size)
    except TypeError as exc:
        raise GeometryError("invalid rendered page size") from exc
    if len(dimensions) != 2 or any(
        not isinstance(value, numbers.Integral)
        or isinstance(value, bool) or value <= 0 for value in dimensions
    ):
        raise GeometryError("invalid rendered page size")
    width, height = (int(value) for value in dimensions)
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
    crop: TableCrop,
    box: tuple[float, float, float, float],
    *,
    rotated_clockwise: bool = False,
) -> tuple[float, float, float, float]:
    """Map an upright local cell box to the rendered page pixel frame."""
    if not _valid_box(box):
        raise GeometryError("invalid local cell box")
    if rotated_clockwise:
        box = _upright_box_to_crop(box, crop.size)
    width, height = crop.size
    if box[0] < 0 or box[1] < 0 or box[2] > width or box[3] > height:
        raise GeometryError("local cell box lies outside table crop")
    left, top = crop.raster_box[:2]
    return box[0] + left, box[1] + top, box[2] + left, box[3] + top


def page_word_to_crop(
    crop: TableCrop,
    page_box: tuple[float, float, float, float],
    *,
    rotated_clockwise: bool = False,
) -> tuple[float, float, float, float] | None:
    """Map a fully contained word into the upright table crop pixel frame."""
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
    local = (
        page_box[0] - left, page_box[1] - top,
        page_box[2] - left, page_box[3] - top,
    )
    return _crop_box_to_upright(local, crop.size) if rotated_clockwise else local


def _crop_box_to_upright(
    box: tuple[float, float, float, float], crop_size: tuple[int, int]
) -> tuple[float, float, float, float]:
    """Rotate continuous box edges 90 degrees clockwise, as PIL 270 does."""
    width, height = crop_size
    if not _valid_box(box) or box[0] < 0 or box[1] < 0 or box[2] > width or box[3] > height:
        raise GeometryError("invalid box in unrotated table crop")
    return height - box[3], box[0], height - box[1], box[2]


def _upright_box_to_crop(
    box: tuple[float, float, float, float], crop_size: tuple[int, int]
) -> tuple[float, float, float, float]:
    width, height = crop_size
    if not _valid_box(box) or box[0] < 0 or box[1] < 0 or box[2] > height or box[3] > width:
        raise GeometryError("invalid box in upright table crop")
    return box[1], height - box[2], box[3], height - box[0]


def crop_box_to_pdf_page(
    crop: TableCrop,
    box: tuple[float, float, float, float],
    converter: Any,
    *,
    rotated_clockwise: bool = False,
) -> tuple[float, float, float, float]:
    """Reproject a local cell box through the exact crop and PDFium converter."""
    page_box = crop_box_to_page_pixels(
        crop, box, rotated_clockwise=rotated_clockwise
    )
    return pixel_box_to_page(page_box, converter, crop.page_width, crop.page_height)
