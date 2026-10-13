"""Choose bounded PDF raster dimensions before the renderer allocates a bitmap."""

from __future__ import annotations

import math

MAX_RENDER_EDGE = 4096
MAX_RENDER_PIXELS = 12_000_000
MAX_INSPECT_OBJECTS = 10_000


def raster_plan(width: float, height: float, dpi: float, *, source_dpi: float | None = None) -> dict:
    if not all(math.isfinite(value) and value > 0 for value in (width, height, dpi)):
        raise ValueError("Invalid PDF raster geometry")
    scale = dpi / 72
    reasons = []
    if source_dpi is not None and math.isfinite(source_dpi) and 0 < source_dpi < dpi * 0.99:
        scale = source_dpi / 72
        reasons.append("dominant_scan_native_resolution")
    if max(width, height) * scale > MAX_RENDER_EDGE:
        scale = min(scale, MAX_RENDER_EDGE / max(width, height))
        reasons.append("edge_limit")
    if width * height * scale * scale > MAX_RENDER_PIXELS:
        scale = min(scale, math.sqrt(MAX_RENDER_PIXELS / (width * height)))
        reasons.append("pixel_limit")
    # PDFium rounds each dimension up. Account for that before allocation.
    for _ in range(3):
        pixel_width, pixel_height = max(1, math.ceil(width * scale)), max(1, math.ceil(height * scale))
        if max(pixel_width, pixel_height) <= MAX_RENDER_EDGE and pixel_width * pixel_height <= MAX_RENDER_PIXELS:
            break
        scale *= min(MAX_RENDER_EDGE / max(pixel_width, pixel_height),
                     math.sqrt(MAX_RENDER_PIXELS / (pixel_width * pixel_height))) * (1 - 1e-9)
    else:
        raise ValueError("Cannot bound PDF raster")
    return {
        "version": 1, "requested_dpi": dpi, "effective_dpi": scale * 72, "scale": scale,
        "page_size_points": [width, height], "target_size_px": [pixel_width, pixel_height],
        "source_image_dpi": source_dpi, "limit_reasons": reasons,
        "max_edge_px": MAX_RENDER_EDGE, "max_pixels": MAX_RENDER_PIXELS,
    }


def pdfium_raster_plan(page, dpi: float) -> dict:
    """Use image dimensions only for one dominant, unskewed page-level scan.

    Multiple images, forms or failed inspection keep the requested DPI subject
    to hard geometry limits. Image object dimensions do not decode image pixels.
    """
    import pypdfium2 as pdfium

    source_dpi = None
    status = "no_single_dominant_scan"
    bounds = page.get_bbox()
    page_area = (bounds[2] - bounds[0]) * (bounds[3] - bounds[1])
    try:
        images, forms = [], False
        for index, obj in enumerate(page.get_objects(max_depth=1), 1):
            if index > MAX_INSPECT_OBJECTS:
                raise ValueError("PDF object inspection limit")
            forms = forms or obj.type == pdfium.raw.FPDF_PAGEOBJ_FORM
            if obj.type == pdfium.raw.FPDF_PAGEOBJ_IMAGE:
                images.append(obj)
                if len(images) > 1:
                    break
        if len(images) == 1 and not forms and page_area > 0:
            image = images[0]
            left, bottom, right, top = image.get_bounds()
            overlap = max(0, min(right, bounds[2]) - max(left, bounds[0])) * max(0, min(top, bounds[3]) - max(bottom, bounds[1]))
            matrix = image.get_matrix()
            # PDF image coordinates use a unit square; vector lengths also
            # handle quarter-turn image rotations without swapping pixel axes.
            x_length, y_length = math.hypot(matrix.a, matrix.b), math.hypot(matrix.c, matrix.d)
            dot = matrix.a * matrix.c + matrix.b * matrix.d
            if overlap / page_area >= 0.95 and x_length > 0 and y_length > 0 and abs(dot) <= 1e-6 * x_length * y_length:
                width_px, height_px = image.get_px_size()
                source_dpi = 72 * min(width_px / x_length, height_px / y_length)
                status = "single_dominant_scan"
    except Exception as exc:  # noqa: BLE001 - geometry caps still apply when native image inspection fails
        status = "inspection_unavailable:" + type(exc).__name__
    result = raster_plan(*page.get_size(), dpi, source_dpi=source_dpi)
    result.update(source_resolution_status=status, page_box_points=list(bounds), geometry_source="pdfium")
    return result


def poppler_raster_plan(path: str, page_index: int, dpi: float) -> tuple[dict, tuple[int, int] | int]:
    """Bound Poppler allocation too, even if the preferred renderer is unavailable."""
    try:
        from pypdf import PdfReader

        page = PdfReader(path).pages[page_index]
        box = page.mediabox  # pdf2image defaults to the media box, not the crop box.
        width, height = float(box.width), float(box.height)
        if int(page.rotation) % 180:
            width, height = height, width
        result = raster_plan(width, height, dpi)
        result.update(page_box_points=list(map(float, box)), geometry_source="pypdf_media_box",
                      source_resolution_status="unassessed", page_rotation_deg=int(page.rotation))
        return result, tuple(result["target_size_px"])
    except Exception:  # noqa: BLE001 - unknown page geometry still needs a pre-allocation limit
        edge = min(MAX_RENDER_EDGE, math.isqrt(MAX_RENDER_PIXELS))
        return {
            "version": 1, "requested_dpi": dpi, "effective_dpi": None, "scale": None,
            "page_size_points": None, "target_size_px": None, "source_image_dpi": None,
            "limit_reasons": ["unknown_geometry_long_edge_limit"], "geometry_source": "unavailable",
            "max_edge_px": edge, "max_pixels": MAX_RENDER_PIXELS,
        }, edge
