"""Pillow-based image normalization for document images before OCR."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageFilter, ImageOps


@dataclass(slots=True)
class ImagePreprocessor:
    """Normalize a PIL image for OCR without performing OCR.

    All operations are non-mutating: the input image is never modified.
    No file I/O occurs; the caller is responsible for reading/writing images.

    Default pipeline:
      RGB→convert → autocontrast → grayscale → conditional upscale → sharpen

    Optional extensions (controlled by flags):
      binarize     — threshold grayscale to black/white after autocontrast
      median_filter — smooth after sharpen to reduce salt-and-pepper noise
    """

    binarize: bool = False
    median_filter: bool = False
    upscale_threshold: int = 1400
    upscale_factor: int = 2
    binarize_threshold: int = 170

    def normalize(self, image: Image.Image) -> Image.Image:
        """Return a cleaned copy of *image* ready for an OCR engine.

        Steps:
        1. Convert to RGB (handles CMYK, RGBA, palette, TIFF modes).
        2. Autocontrast with cutoff=2 (normalises brightness range).
        3. Convert to grayscale (L mode).
        4. Upscale 2× with BICUBIC if max dimension < upscale_threshold.
        5. Binarize at binarize_threshold if binarize=True.
        6. Sharpen.
        7. Apply 3×3 median filter if median_filter=True.
        """
        img = image.copy()

        if img.mode not in {"RGB", "L"}:
            img = img.convert("RGB")

        img = ImageOps.autocontrast(img, cutoff=2)
        img = ImageOps.grayscale(img)

        w, h = img.size
        if max(w, h) < self.upscale_threshold:
            img = img.resize(
                (w * self.upscale_factor, h * self.upscale_factor),
                Image.BICUBIC,
            )

        if self.binarize:
            threshold = self.binarize_threshold
            img = img.point(lambda px: 255 if px > threshold else 0)

        img = img.filter(ImageFilter.SHARPEN)

        if self.median_filter:
            img = img.filter(ImageFilter.MedianFilter(size=3))

        return img
