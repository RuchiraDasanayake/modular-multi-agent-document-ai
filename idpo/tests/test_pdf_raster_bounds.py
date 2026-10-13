"""Regression coverage for oversized page canvases and source pixel preservation."""

from __future__ import annotations

from pathlib import Path

import pypdfium2
import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from idpo.agents.preprocess import _render_pdf_page
from idpo.core.pdf_raster import (
    MAX_RENDER_EDGE,
    MAX_RENDER_PIXELS,
    pdfium_raster_plan,
    raster_plan,
)


@pytest.mark.parametrize("rotation", [0, 90])
def test_large_canvas_scan_preserves_source_resolution(tmp_path: Path, rotation: int) -> None:
    source = tmp_path / "low-dpi.pdf"
    Image.new("RGB", (2200, 1700), "white").save(source, "PDF", resolution=70)
    if rotation:
        writer = PdfWriter()
        writer.add_page(PdfReader(source).pages[0]).rotate(rotation)
        rotated = tmp_path / "rotated.pdf"
        writer.write(rotated)
        source = rotated

    result = _render_pdf_page(str(source), 0, 300)

    assert result.renderer == "pdfium"
    assert result.image is not None
    expected = (2200, 1700) if rotation == 0 else (1700, 2200)
    assert all(abs(actual - desired) <= 1 for actual, desired in zip(result.image.size, expected))
    assert result.image.width * result.image.height < 3_750_000
    assert result.rotation_deg == rotation
    assert result.sizing["effective_dpi"] == pytest.approx(70, rel=0.001)
    assert result.sizing["requested_dpi"] == 300
    assert result.sizing["limit_reasons"] == ["dominant_scan_native_resolution"]
    assert len(result.sizing["page_box_points"]) == 4


def test_normal_letter_pdf_preserves_requested_dpi(tmp_path: Path) -> None:
    path = tmp_path / "digital.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(path)
    with pypdfium2.PdfDocument(path) as pdf:
        page = pdf[0]
        try:
            plan = pdfium_raster_plan(page, 300)
        finally:
            page.close()
    assert plan["scale"] == 300 / 72
    assert plan["target_size_px"] == [2550, 3301] or plan["target_size_px"] == [2550, 3300]
    assert plan["limit_reasons"] == []


@pytest.mark.parametrize(("width", "height", "dpi"), [(12000, 12000, 300), (500000, 1, 600), (612, 792, 2400)])
def test_plan_caps_dimensions_before_any_bitmap_allocation(width, height, dpi) -> None:
    plan = raster_plan(width, height, dpi)
    x, y = plan["target_size_px"]
    assert x * y <= MAX_RENDER_PIXELS
    assert max(x, y) <= MAX_RENDER_EDGE
    assert plan["effective_dpi"] < dpi
    assert plan["limit_reasons"]


@pytest.mark.parametrize("dimension", [0, -1, float("nan"), float("inf")])
def test_invalid_geometry_cannot_produce_a_render_plan(dimension) -> None:
    with pytest.raises(ValueError, match="Invalid PDF raster geometry"):
        raster_plan(dimension, 792, 300)
