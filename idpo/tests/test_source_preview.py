from __future__ import annotations

import io

import pytest
from PIL import Image, PngImagePlugin
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject

from idpo.product_auto.source_preview import MAX_SOURCE_BYTES, PreviewError, render_preview


def pdf_bytes(pages: int = 2, width: int = 300, height: int = 400) -> bytes:
    writer = PdfWriter()
    for index in range(pages):
        page = writer.add_blank_page(width=width, height=height)
        content = DecodedStreamObject()
        content.set_data(f"{index % 2} 0 {1 - index % 2} rg 0 0 {width} {height} re f".encode())
        page[NameObject("/Contents")] = writer._add_object(content)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def image_bytes(size=(40, 20), format="PNG") -> bytes:
    output = io.BytesIO()
    with Image.new("RGB", size, "red") as image:
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("private", "do-not-copy")
        image.save(output, format=format, pnginfo=metadata)
    return output.getvalue()


def test_real_pdf_page_selection_and_dimensions_are_bounded() -> None:
    source = pdf_bytes(width=3000, height=4000)
    for page, color in [(1, (0, 0, 255)), (2, (255, 0, 0))]:
        png, count = render_preview(source, "pdf", page)
        assert count == 2
        with Image.open(io.BytesIO(png)) as result:
            assert result.format == "PNG"
            assert max(result.size) <= 1600
            assert result.getpixel((10, 10)) == color


@pytest.mark.parametrize("format", ["PNG", "JPEG", "TIFF", "BMP"])
def test_images_are_rasterized_without_metadata(format: str) -> None:
    png, count = render_preview(image_bytes(format=format), "image", 1)
    assert count == 1
    with Image.open(io.BytesIO(png)) as result:
        assert result.size == (40, 20)
        assert result.info == {}


@pytest.mark.parametrize("page", [0, -1, 51, True, 1.5])
def test_bad_page_numbers_are_rejected(page) -> None:
    with pytest.raises(PreviewError, match="page_out_of_range"):
        render_preview(b"test", "pdf", page)


def test_source_page_count_and_size_limits() -> None:
    with pytest.raises(PreviewError, match="page_limit"):
        render_preview(pdf_bytes(pages=51), "pdf", 1)
    with pytest.raises(PreviewError, match="page_out_of_range"):
        render_preview(pdf_bytes(), "pdf", 3)
    with pytest.raises(PreviewError, match="page_out_of_range"):
        render_preview(image_bytes(), "image", 2)
    for source in [b"", b"x" * (MAX_SOURCE_BYTES + 1)]:
        with pytest.raises(PreviewError, match="source_size"):
            render_preview(source, "pdf", 1)
    with pytest.raises(PreviewError, match="image_limit"):
        render_preview(image_bytes(size=(4097, 1)), "image", 1)


@pytest.mark.parametrize("kind,source", [("pdf", b"%PDF-malformed"), ("pdf", b"not-pdf"),
    ("image", b"not-image"), ("url", b"https://example.invalid/file.png")])
def test_malformed_and_unsupported_sources_fail_without_paths(kind: str, source: bytes) -> None:
    with pytest.raises(PreviewError):
        render_preview(source, kind, 1)


def test_multiframe_image_does_not_silently_preview_one_frame() -> None:
    output = io.BytesIO()
    with Image.new("RGB", (10, 10), "red") as one, Image.new("RGB", (10, 10), "blue") as two:
        one.save(output, format="TIFF", save_all=True, append_images=[two])
    with pytest.raises(PreviewError, match="multiple_frames"):
        render_preview(output.getvalue(), "image", 1)
