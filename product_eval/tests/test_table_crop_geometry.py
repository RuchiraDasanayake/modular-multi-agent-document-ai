"""Synthetic raster, PDF crop and rotation checks; no selected PDFs or models."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from product_eval.table_crop_geometry import (
    crop_box_to_page_pixels,
    crop_box_to_pdf_page,
    page_word_to_crop,
    table_crop_from_proposal,
)
from product_eval.tatr_native_geometry import GeometryError, native_word_tokens


def _synthetic_pdf(path: Path, rotation: int) -> None:
    pypdf = pytest.importorskip("pypdf")
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = pypdf.PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    font = DictionaryObject({
        NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"),
        NameObject("/BaseFont"): NameObject("/Helvetica"),
    })
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)}),
    })
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 14 Tf 40 120 Td (Alpha Beta) Tj ET")
    page[NameObject("/Contents")] = writer._add_object(stream)
    page.cropbox.lower_left = (20, 15)
    page.cropbox.upper_right = (280, 180)
    page.rotate(rotation)
    with path.open("wb") as destination:
        writer.write(destination)


def test_crop_freezes_integer_bounds_and_rejects_partial_word() -> None:
    crop = table_crop_from_proposal((10.1, 20.1, 50.9, 60.9), (100, 100))
    assert crop.raster_box == (5, 15, 56, 66)
    assert crop.size == (51, 51)
    assert not crop.padding_clipped_at_page_edge
    assert page_word_to_crop(crop, (10, 20, 20, 30)) == (5, 5, 15, 15)
    assert crop_box_to_page_pixels(crop, (5, 5, 15, 15)) == (10, 20, 20, 30)
    assert page_word_to_crop(crop, (70, 70, 80, 80)) is None
    with pytest.raises(GeometryError, match="crosses"):
        page_word_to_crop(crop, (0, 20, 10, 30))


def test_page_edge_padding_is_recorded_and_bad_boxes_fail() -> None:
    crop = table_crop_from_proposal((0, 0, 10, 10), (100, 100))
    assert crop.raster_box == (0, 0, 15, 15)
    assert crop.padding_clipped_at_page_edge
    with pytest.raises(GeometryError, match="outside page"):
        table_crop_from_proposal((-1, 0, 10, 10), (100, 100))
    with pytest.raises(GeometryError, match="padding"):
        table_crop_from_proposal((1, 1, 10, 10), (100, 100), padding=6)
    with pytest.raises(GeometryError, match="outside table crop"):
        crop_box_to_page_pixels(crop, (0, 0, 16, 10))
    with pytest.raises(GeometryError, match="invalid"):
        crop_box_to_page_pixels(crop, (0, 0, float("nan"), 10))


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_crop_word_and_pdf_roundtrip_on_rotated_cropped_pdf(
    tmp_path: Path, rotation: int
) -> None:
    pdfium = pytest.importorskip("pypdfium2")
    path = tmp_path / "synthetic.pdf"
    _synthetic_pdf(path, rotation)
    document = pdfium.PdfDocument(path)
    try:
        page = document[0]
        bitmap = page.render(scale=300 / 72, rotation=0)
        try:
            words = native_word_tokens(page, bitmap)
            assert [word.text for word in words] == ["Alpha", "Beta"]
            proposal = (
                min(word.bbox[0] for word in words),
                min(word.bbox[1] for word in words),
                max(word.bbox[2] for word in words),
                max(word.bbox[3] for word in words),
            )
            crop = table_crop_from_proposal(proposal, (bitmap.width, bitmap.height))
            converter = bitmap.get_posconv(page)
            image = bitmap.to_pil().convert("L").crop(crop.raster_box)
            for word in words:
                local = page_word_to_crop(crop, word.bbox)
                assert local is not None
                assert crop_box_to_page_pixels(crop, local) == word.bbox
                page_box = crop_box_to_pdf_page(crop, local, converter)
                assert all(math.isclose(a, b, abs_tol=1.0)
                           for a, b in zip(page_box, word.pdf_bbox))
                pixels = image.crop(tuple(round(value) for value in local))
                assert pixels.getextrema()[0] < 100
        finally:
            bitmap.close()
            page.close()
    finally:
        document.close()
