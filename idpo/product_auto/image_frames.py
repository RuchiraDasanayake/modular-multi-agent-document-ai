"""Shared boundary for image routes that currently process exactly one frame."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image


class UnsupportedImageFrames(ValueError):
    def __init__(self) -> None:
        super().__init__("Only single-frame images are supported; split extra pages into separate files.")


def require_single_frame_image(image: Image.Image) -> None:
    if getattr(image, "n_frames", 1) != 1:
        raise UnsupportedImageFrames()
