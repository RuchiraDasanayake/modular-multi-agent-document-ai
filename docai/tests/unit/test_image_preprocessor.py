"""Unit tests for ImagePreprocessor."""

from __future__ import annotations

from PIL import Image

from docai_core.text_acquisition.image_preprocessor import ImagePreprocessor


def _rgb(w: int = 200, h: int = 150, color: tuple[int, int, int] = (128, 64, 32)) -> Image.Image:
    return Image.new("RGB", (w, h), color=color)


def _gradient(w: int = 200, h: int = 150) -> Image.Image:
    img = Image.new("L", (w, h))
    pixels = img.load()
    for x in range(w):
        for y in range(h):
            pixels[x, y] = int((x / w) * 255)
    return img.convert("RGB")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_normalize_rgb_image_returns_grayscale() -> None:
    result = ImagePreprocessor().normalize(_rgb())
    assert result.mode == "L"


def test_small_image_is_upscaled() -> None:
    result = ImagePreprocessor().normalize(_rgb(100, 80))
    assert max(result.size) >= 200


def test_large_image_is_not_upscaled() -> None:
    result = ImagePreprocessor().normalize(_rgb(2000, 1500))
    assert result.size == (2000, 1500)


def test_normalize_does_not_mutate_input_image() -> None:
    original = _rgb(200, 150, color=(10, 20, 30))
    original_mode = original.mode
    original_size = original.size
    ImagePreprocessor().normalize(original)
    assert original.mode == original_mode
    assert original.size == original_size


def test_binarize_outputs_only_black_or_white_pixels() -> None:
    proc = ImagePreprocessor(binarize=True)
    result = proc.normalize(_rgb(50, 50))
    assert result.mode == "L"
    unique_values = set(result.get_flattened_data())
    assert unique_values.issubset({0, 255}), f"Unexpected pixel values: {unique_values}"


def test_median_filter_preserves_size() -> None:
    # Use an image above the upscale threshold so size is unchanged.
    proc = ImagePreprocessor(median_filter=True)
    result = proc.normalize(_rgb(1500, 1000))
    assert result.size == (1500, 1000)


def test_autocontrast_or_processing_changes_gradient_image() -> None:
    # Use an image above the upscale threshold so size assertions are stable.
    src = _gradient(1500, 1000)
    result = ImagePreprocessor().normalize(src)
    assert result is not None
    assert result.mode == "L"
    assert result.size == (1500, 1000)
    # Output must contain more than one distinct value (i.e. not a blank image)
    unique_values = set(result.get_flattened_data())
    assert len(unique_values) > 1


def test_public_export_available() -> None:
    from docai_core.text_acquisition import ImagePreprocessor as ExportedPreprocessor

    assert ExportedPreprocessor is not None
    proc = ExportedPreprocessor()
    result = proc.normalize(_rgb(100, 80))
    assert result.mode == "L"
