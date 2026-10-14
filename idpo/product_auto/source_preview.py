"""Bounded local source-page rendering for the authenticated review workspace."""

from __future__ import annotations

import argparse
import base64
import io
import json
import math
import sys
import warnings

MAX_SOURCE_BYTES = 20 * 1024 * 1024
MAX_PAGES = 50
MAX_EDGE = 1600
MAX_IMAGE_PIXELS = 12_000_000
MAX_PNG_BYTES = 8 * 1024 * 1024


class PreviewError(ValueError):
    pass


def render_preview(source: bytes, kind: str, page_number: int) -> tuple[bytes, int]:
    """Decode only supplied bytes; the helper cannot select paths or remote URLs."""
    from PIL import Image

    if not source or len(source) > MAX_SOURCE_BYTES:
        raise PreviewError("source_size")
    if type(page_number) is not int or not 1 <= page_number <= MAX_PAGES:
        raise PreviewError("page_out_of_range")
    if kind == "pdf":
        if not source.startswith(b"%PDF-"):
            raise PreviewError("invalid_source")
        import pypdfium2 as pdfium
        from idpo.core.pdf_raster import pdfium_raster_plan

        try:
            with pdfium.PdfDocument(source) as document:
                total = len(document)
                if not 1 <= total <= MAX_PAGES:
                    raise PreviewError("page_limit")
                if page_number > total:
                    raise PreviewError("page_out_of_range")
                page = document[page_number - 1]
                try:
                    width, height = page.get_size()
                    if not all(math.isfinite(n) and n > 0 for n in (width, height)):
                        raise PreviewError("invalid_geometry")
                    # Plan before allocating a bitmap, using the existing PDF geometry guard.
                    dpi = min(144.0, 72.0 * (MAX_EDGE - 1) / max(width, height))
                    plan = pdfium_raster_plan(page, dpi)
                    bitmap = page.render(scale=plan["scale"])
                    try:
                        image = bitmap.to_pil().convert("RGB").copy()
                    finally:
                        bitmap.close()
                finally:
                    page.close()
        except PreviewError:
            raise
        except Exception:
            raise PreviewError("invalid_source") from None
    elif kind == "image":
        if page_number != 1:
            raise PreviewError("page_out_of_range")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(source)) as original:
                    if original.format not in {"PNG", "JPEG", "TIFF", "BMP"}:
                        raise PreviewError("unsupported_format")
                    if getattr(original, "n_frames", 1) != 1:
                        raise PreviewError("multiple_frames")
                    if max(original.size) > 4096 or original.width * original.height > MAX_IMAGE_PIXELS:
                        raise PreviewError("image_limit")
                    # Match the source grid used by OCR; do not apply an EXIF rotation here.
                    image = original.convert("RGB")
            total = 1
        except PreviewError:
            raise
        except Exception:
            raise PreviewError("invalid_source") from None
    else:
        raise PreviewError("unsupported_format")
    try:
        image.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
        # Copy pixels into a fresh image to strip source metadata and embedded profiles.
        with Image.frombytes("RGB", image.size, image.tobytes()) as clean:
            output = io.BytesIO()
            clean.save(output, format="PNG")
        png = output.getvalue()
        if len(png) > MAX_PNG_BYTES:
            raise PreviewError("output_limit")
        return png, total
    finally:
        image.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kind", choices=("pdf", "image"), required=True)
    parser.add_argument("--page", type=int, required=True)
    args = parser.parse_args()
    try:
        png, count = render_preview(sys.stdin.buffer.read(MAX_SOURCE_BYTES + 1), args.kind, args.page)
        print(json.dumps({"page": args.page, "page_count": count,
                          "png": base64.b64encode(png).decode("ascii")}, separators=(",", ":")))
        return 0
    except PreviewError as exc:
        print(json.dumps({"error": str(exc)}))
        return 2
    except Exception:
        print('{"error":"renderer_unavailable"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
