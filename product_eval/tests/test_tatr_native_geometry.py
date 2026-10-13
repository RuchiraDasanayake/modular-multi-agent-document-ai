"""Source-free geometry tests for the inactive TATR research arm."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from product_eval.tatr_native_geometry import (
    GeometryError,
    OutsideRenderedPageError,
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
            rejected: list[dict[str, object]] = []
            tokens = native_word_tokens(page, bitmap, rejected_words=rejected)
            assert rejected == []
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


def test_fractional_model_box_uses_enclosing_integer_pdfium_pixels() -> None:
    class IntegerOnly:
        def to_page(self, x: int, y: int) -> tuple[float, float]:
            assert type(x) is int and type(y) is int
            return float(x), float(y)

    assert pixel_box_to_page((10.25, 20.75, 30.1, 40.2), IntegerOnly(), 100, 100) == (
        10.0, 20.0, 31.0, 41.0,
    )


class _FakeTextPage:
    def __init__(self, chars: str, boxes: dict[int, tuple[float, float, float, float]]) -> None:
        self.chars = chars
        self.boxes = boxes
        self.raw = self
        self.closed = False

    def count_chars(self) -> int:
        return len(self.chars)

    def get_charbox(self, index: int) -> tuple[float, float, float, float]:
        return self.boxes[index]

    def close(self) -> None:
        self.closed = True


class _FakePage:
    def __init__(self, text_page: _FakeTextPage) -> None:
        self.text_page = text_page

    def get_textpage(self) -> _FakeTextPage:
        return self.text_page


class _FakeBitmap:
    width = 100
    height = 100

    def get_posconv(self, page: _FakePage) -> _FakeBitmap:
        return self

    def to_bitmap(self, x: float, y: float) -> tuple[float, float]:
        return x, y


def _fake_pdfium_page(
    monkeypatch: pytest.MonkeyPatch,
    chars: str,
    boxes: dict[int, tuple[float, float, float, float]],
) -> tuple[_FakePage, _FakeBitmap, _FakeTextPage]:
    pdfium_raw = pytest.importorskip("pypdfium2.raw")
    text_page = _FakeTextPage(chars, boxes)
    monkeypatch.setattr(pdfium_raw, "FPDFText_GetUnicode", lambda raw, index: ord(raw.chars[index]))
    return _FakePage(text_page), _FakeBitmap(), text_page


def test_outside_glyph_rejects_whole_word_and_preserves_neighbors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chars = "OK EDGE END"
    boxes = {
        0: (10, 10, 12, 20), 1: (12, 10, 14, 20),
        3: (94, 10, 96, 20), 4: (96, 10, 98, 20),
        5: (98, 10, 100, 20), 6: (100, 10, 102, 20),
        8: (20, 10, 22, 20), 9: (22, 10, 24, 20), 10: (24, 10, 26, 20),
    }
    page, bitmap, text_page = _fake_pdfium_page(monkeypatch, chars, boxes)
    rejected: list[dict[str, object]] = []

    tokens = native_word_tokens(page, bitmap, rejected_words=rejected)

    assert [token.text for token in tokens] == ["OK", "END"]
    assert [(token.char_start, token.char_end) for token in tokens] == [(0, 2), (8, 11)]
    assert rejected == [{
        "text": "EDGE",
        "char_start": 3,
        "char_end": 7,
        "pdf_glyph_boxes": [boxes[index] for index in range(3, 7)],
        "pixel_glyph_boxes": [boxes[index] for index in range(3, 7)],
        "reason": "outside_rendered_viewport",
    }]
    assert text_page.closed


def test_outside_glyph_raises_in_strict_default(monkeypatch: pytest.MonkeyPatch) -> None:
    page, bitmap, text_page = _fake_pdfium_page(monkeypatch, "A", {0: (100, 10, 102, 20)})
    with pytest.raises(OutsideRenderedPageError):
        native_word_tokens(page, bitmap)
    assert text_page.closed


@pytest.mark.parametrize("invalid_box", [
    (10, 10, 10, 20),
    (10, 10, float("nan"), 20),
])
def test_malformed_glyph_still_fails_with_salvage_enabled(
    monkeypatch: pytest.MonkeyPatch,
    invalid_box: tuple[float, float, float, float],
) -> None:
    page, bitmap, text_page = _fake_pdfium_page(
        monkeypatch,
        "AB",
        {0: (100, 10, 102, 20), 1: invalid_box},
    )
    with pytest.raises(GeometryError, match="rectangle") as exc:
        native_word_tokens(page, bitmap, rejected_words=[])
    assert not isinstance(exc.value, OutsideRenderedPageError)
    assert text_page.closed


def test_spatial_break_precedes_outside_projection(monkeypatch: pytest.MonkeyPatch) -> None:
    page, bitmap, _ = _fake_pdfium_page(
        monkeypatch,
        "AB",
        {0: (10, 10, 12, 20), 1: (110, 10, 112, 20)},
    )
    rejected: list[dict[str, object]] = []
    tokens = native_word_tokens(page, bitmap, rejected_words=rejected)
    assert [token.text for token in tokens] == ["A"]
    assert [word["text"] for word in rejected] == ["B"]


def test_invalid_unicode_still_fails_with_salvage_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    page, bitmap, text_page = _fake_pdfium_page(
        monkeypatch,
        "AB",
        {0: (100, 10, 102, 20), 1: (10, 10, 12, 20)},
    )
    pdfium_raw = pytest.importorskip("pypdfium2.raw")
    monkeypatch.setattr(
        pdfium_raw,
        "FPDFText_GetUnicode",
        lambda raw, index: ord(raw.chars[index]) if index == 0 else 0,
    )
    with pytest.raises(GeometryError, match="Unicode mapping") as exc:
        native_word_tokens(page, bitmap, rejected_words=[])
    assert not isinstance(exc.value, OutsideRenderedPageError)
    assert text_page.closed


def test_invalid_render_dimensions_still_fail_with_salvage_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page, bitmap, _ = _fake_pdfium_page(monkeypatch, "A", {0: (10, 10, 12, 20)})
    bitmap.width = 0
    with pytest.raises(GeometryError, match="rendered image dimensions") as exc:
        native_word_tokens(page, bitmap, rejected_words=[])
    assert not isinstance(exc.value, OutsideRenderedPageError)
