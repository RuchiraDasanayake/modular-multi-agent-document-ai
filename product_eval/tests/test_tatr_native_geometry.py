"""Source-free geometry tests for the inactive TATR research arm."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from product_eval.tatr_native_geometry import (
    GeometryError,
    native_word_tokens,
    page_box_to_pixels,
    pixel_box_to_page,
)


def _synthetic_pdf(path: Path, *, rotation: int = 0, crop: bool = False) -> None:
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
    if crop:
        page.cropbox.lower_left = (20, 15)
        page.cropbox.upper_right = (280, 180)
    if rotation:
        page.rotate(rotation)
    with path.open("wb") as destination:
        writer.write(destination)


@pytest.mark.parametrize("rotation,crop", [(0, False), (90, True), (180, True), (270, True)])
def test_pdfium_words_and_roundtrip_on_synthetic_page(tmp_path: Path, rotation: int, crop: bool) -> None:
    pdfium = pytest.importorskip("pypdfium2")
    path = tmp_path / "synthetic.pdf"
    _synthetic_pdf(path, rotation=rotation, crop=crop)
    document = pdfium.PdfDocument(path)
    try:
        page = document[0]
        bitmap = page.render(scale=300 / 72, rotation=0)
        try:
            tokens = native_word_tokens(page, bitmap)
            assert [token.text for token in tokens] == ["Alpha", "Beta"]
            assert all(token.source == "pdfium_native" for token in tokens)
            assert all(0 <= token.bbox[0] < token.bbox[2] <= bitmap.width for token in tokens)
            assert all(0 <= token.bbox[1] < token.bbox[3] <= bitmap.height for token in tokens)
            rendered = bitmap.to_pil().convert("L")
            for token in tokens:
                patch = rendered.crop(tuple(round(value) for value in token.bbox))
                assert patch.getextrema()[0] < 100
            converter = bitmap.get_posconv(page)
            for token in tokens:
                roundtrip = pixel_box_to_page(token.bbox, converter, bitmap.width, bitmap.height)
                assert all(math.isclose(left, right, abs_tol=1.0) for left, right in zip(roundtrip, token.pdf_bbox))
                projected = page_box_to_pixels(roundtrip, converter, bitmap.width, bitmap.height)
                assert all(math.isclose(left, right, abs_tol=5) for left, right in zip(projected, token.bbox))
        finally:
            bitmap.close()
            page.close()
    finally:
        document.close()


@pytest.mark.parametrize("box", [
    (0, 0, 0, 2),
    (0, 0, float("nan"), 2),
    (-20, 0, -10, 2),
    (-0.8, 10, -0.2, 20),
    (10, -0.8, 20, -0.2),
])
def test_invalid_pdf_box_is_rejected(box: tuple[float, float, float, float]) -> None:
    class Identity:
        def to_bitmap(self, x: float, y: float) -> tuple[float, float]:
            return x, y

    with pytest.raises(GeometryError):
        page_box_to_pixels(box, Identity(), 100, 100)


def test_outside_pixel_box_is_rejected() -> None:
    class Identity:
        def to_page(self, x: float, y: float) -> tuple[float, float]:
            return x, y

    with pytest.raises(GeometryError):
        pixel_box_to_page((10, 10, 101, 20), Identity(), 100, 100)
