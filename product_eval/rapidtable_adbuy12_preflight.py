"""Source-free contract smoke for RapidTable 3.0.2 on a synthetic table.

This module deliberately cannot open any VRDU PDF or gold annotation. A separate
sealed runner would be needed before the 12-document parser comparison.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import platform
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

MODEL_SHA256 = "d57a942af6a2f57d6a4a0372573c696a2379bf5857c45e2ac69993f3b334514b"
SELECTION_SHA256 = "b843d48146a60f02bb206900ee06d446eb82ba484a3781c291235864b5230d2d"
EXPECTED_PACKAGES = {
    "rapid-table": "3.0.2",
    "rapidocr": "3.10.0",
    "onnxruntime": "1.31.0",
}
RUNTIME_LOCK_SHA256 = "1264a56da9c666676deb1a442eae8811aff296001340c105d07acd90e3042f4a"
INSTALLED_CV2_SHA256 = (
    "f1e76ab01cf4d33af780adf8ada1a26c5eaeecc55d2cbe8a5e288195e8f9b0dd"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class _Cells(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_cell = False
        self.current = ""
        self.cells: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"td", "th"}:
            if self.in_cell:
                raise ValueError("nested HTML table cell")
            self.in_cell = True
            self.current = ""

    def handle_data(self, data: str) -> None:
        if self.in_cell:
            self.current += data

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self.in_cell:
            self.cells.append(" ".join(self.current.split()))
            self.in_cell = False


def validate_ocr_tuple(value: Any) -> None:
    """Fail before vendor code if batch OCR input is not boxes/texts/scores."""
    import numpy as np

    if not isinstance(value, tuple) or len(value) != 3:
        raise ValueError("OCR result must be a 3-tuple of boxes, texts and scores")
    boxes, texts, scores = value
    if (
        not isinstance(boxes, np.ndarray)
        or boxes.ndim != 3
        or boxes.shape[1:] != (4, 2)
        or not isinstance(texts, tuple)
        or not isinstance(scores, tuple)
        or not (len(boxes) == len(texts) == len(scores))
    ):
        raise ValueError("OCR tuple has mismatched boxes, texts or scores")
    if not np.isfinite(boxes).all() or any(not isinstance(text, str) for text in texts):
        raise ValueError("OCR tuple has nonfinite geometry or non-text value")
    if any(type(score) not in (float, int) or not 0 <= score <= 1 for score in scores):
        raise ValueError("OCR tuple has invalid score")


def verify_runtime_lock(
    lock_file: Path, wheel_dir: Path, model: Path
) -> dict[str, Any]:
    """Check cached wheel bytes, installed versions, model bytes and one cv2 binary."""
    if sha256_file(lock_file) != RUNTIME_LOCK_SHA256:
        raise ValueError("RapidTable wheel lock changed")
    lock = json.loads(lock_file.read_text(encoding="utf-8"))
    wheels = lock.get("wheels")
    if (
        lock.get("schema_version") != 1
        or not isinstance(wheels, list)
        or len(wheels) != 23
    ):
        raise ValueError("RapidTable wheel lock incomplete")
    if len({row.get("filename") for row in wheels}) != len(wheels):
        raise ValueError("RapidTable wheel lock repeats filenames")
    for row in wheels:
        name = row.get("filename")
        if (
            not isinstance(name, str)
            or Path(name).name != name
            or not name.endswith(".whl")
        ):
            raise ValueError("RapidTable wheel lock has unsafe filename")
        wheel = wheel_dir / name
        if wheel.stat().st_size != row.get("size_bytes") or sha256_file(
            wheel
        ) != row.get("sha256"):
            raise ValueError(f"RapidTable wheel differs from lock: {name}")
        if importlib.metadata.version(row["package"]) != row["version"]:
            raise ValueError(
                f"installed version differs from wheel lock: {row['package']}"
            )
        with zipfile.ZipFile(wheel) as archive:
            for notice in row.get("notices", []):
                if (
                    hashlib.sha256(archive.read(notice["path"])).hexdigest()
                    != notice["sha256"]
                ):
                    raise ValueError(f"wheel notice changed: {name}")
    model_lock = lock.get("model")
    if (
        not isinstance(model_lock, dict)
        or model_lock.get("sha256") != MODEL_SHA256
        or model_lock.get("size_bytes") != model.stat().st_size
        or sha256_file(model) != MODEL_SHA256
    ):
        raise ValueError("SLANet-plus model differs from official registry hash")
    import cv2
    import onnxruntime as ort

    cv2_binary = Path(cv2.__file__).parent / "cv2.pyd"
    if cv2.__version__ != "5.0.0" or sha256_file(cv2_binary) != INSTALLED_CV2_SHA256:
        raise ValueError(
            "installed OpenCV binary differs from source-free smoke runtime"
        )
    if "CPUExecutionProvider" not in ort.get_available_providers():
        raise ValueError("ONNX Runtime CPU provider is unavailable")
    return {
        "wheel_count": len(wheels),
        "wheel_lock_sha256": RUNTIME_LOCK_SHA256,
        "model_sha256": MODEL_SHA256,
        "installed_distribution_versions_verified": len(wheels),
        "installed_distribution_contents_verified": False,
        "installed_cv2_binary_sha256": INSTALLED_CV2_SHA256,
        "onnxruntime_available_providers": ort.get_available_providers(),
        "unresolved_wheel_notices": [
            row["package"] for row in wheels if not row.get("notices")
        ],
    }


def validate_result(
    result: Any,
    width: int,
    height: int,
    supplied_texts: tuple[str, ...],
    expected_grid: dict[tuple[int, int, int, int], str] | None = None,
) -> dict[str, Any]:
    """Check the vendor output contract; do not infer source evidence from it."""
    import numpy as np

    items = (result.imgs, result.pred_htmls, result.cell_bboxes, result.logic_points)
    if any(not isinstance(item, list) or len(item) != 1 for item in items):
        raise ValueError("RapidTable batch output is not one image/HTML/box/logic item")
    markup = result.pred_htmls[0]
    if not isinstance(markup, str) or "<table" not in markup.lower():
        raise ValueError("RapidTable returned no table HTML")
    parsed = _Cells()
    parsed.feed(markup)
    boxes = result.cell_bboxes[0]
    logic = result.logic_points[0]
    if len(boxes) == 0 or len(boxes) != len(logic):
        raise ValueError(
            "RapidTable cell boxes and logic points are missing or misaligned"
        )
    if len(boxes) != len(parsed.cells):
        raise ValueError("RapidTable physical HTML cell count differs from box count")
    for box, point in zip(boxes, logic, strict=True):
        raw_point = np.asarray(point)
        if raw_point.shape != (4,) or not np.issubdtype(raw_point.dtype, np.number):
            raise ValueError(
                "RapidTable logic point must contain four numeric coordinates"
            )
        coordinates = [float(number) for number in raw_point]
        if (
            not all(math.isfinite(number) for number in coordinates)
            or any(int(number) != number or number < 0 for number in coordinates)
            or coordinates[0] > coordinates[1]
            or coordinates[2] > coordinates[3]
        ):
            raise ValueError(
                "RapidTable logic point is not [row_start,row_end,col_start,col_end]"
            )
        coords = [float(number) for number in box]
        if len(coords) not in (4, 8) or not all(
            math.isfinite(number) for number in coords
        ):
            raise ValueError(
                "RapidTable cell box lacks finite four or eight coordinates"
            )
        xs, ys = coords[::2], coords[1::2]
        if min(xs) < -1 or max(xs) > width + 1 or min(ys) < -1 or max(ys) > height + 1:
            raise ValueError("RapidTable cell box lies outside input raster")
        if min(xs) == max(xs) or min(ys) == max(ys):
            raise ValueError("RapidTable cell box has zero area")
    if not any(text in " ".join(parsed.cells) for text in supplied_texts):
        raise ValueError("HTML has no supplied OCR text")
    if expected_grid is not None:
        observed_grid: dict[tuple[int, int, int, int], str] = {}
        for point, cell in zip(logic, parsed.cells, strict=True):
            coordinate = tuple(int(number) for number in point)
            if coordinate in observed_grid:
                raise ValueError("synthetic logical grid has duplicate cell position")
            observed_grid[coordinate] = cell
        if observed_grid != expected_grid:
            raise ValueError(
                "synthetic logical grid has incorrect cell text or position"
            )
    stats = {
        "physical_html_cells": len(parsed.cells),
        "cell_boxes": len(boxes),
        "logic_points": len(logic),
        "nonempty_cells": sum(bool(cell) for cell in parsed.cells),
        "supplied_texts_present": [
            text for text in supplied_texts if text in " ".join(parsed.cells)
        ],
        "elapsed_seconds_per_image": float(result.elapse),
    }
    if expected_grid is not None:
        stats["exact_synthetic_grid_cells"] = len(expected_grid)
    return stats


def write_receipt_exclusive(output: Path, receipt: dict[str, Any]) -> None:
    """Prevent a competing run from replacing an existing receipt."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")


def make_synthetic_table() -> tuple[
    Any, tuple[Any, tuple[str, ...], tuple[float, ...]]
]:
    """Build a 2x3 table with explicit OCR polygons and no external content."""
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (900, 300), "white")
    draw = ImageDraw.Draw(image)
    for x in (0, 300, 600, 899):
        draw.line((x, 10, x, 270), fill="black", width=3)
    for y in (10, 140, 270):
        draw.line((0, y, 899, y), fill="black", width=3)
    try:
        font = ImageFont.truetype("arial.ttf", 32)
    except OSError:
        font = ImageFont.load_default()
    texts = ("Item", "Qty", "Price", "Widget", "2", "10.00")
    boxes = []
    for row, y in enumerate((45, 175)):
        for col, x in enumerate((25, 325, 625)):
            text = texts[row * 3 + col]
            draw.text((x, y), text, fill="black", font=font)
            left, top, right, bottom = draw.textbbox((x, y), text, font=font)
            boxes.append(((left, top), (right, top), (right, bottom), (left, bottom)))
    return np.asarray(image), (
        np.asarray(boxes, dtype=np.float32),
        texts,
        (0.99,) * len(texts),
    )


def preflight(
    model: Path,
    selection: Path,
    wheel_lock: Path,
    wheel_dir: Path,
    output: Path,
    smoke: bool,
) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError("refusing to overwrite source-free preflight receipt")
    if sha256_file(selection) != SELECTION_SHA256:
        raise ValueError("VRDU selection manifest changed")
    if sys.version_info[:2] != (3, 11) or platform.system() != "Windows":
        raise ValueError(
            "RapidTable research runtime requires pinned Windows Python 3.11"
        )
    runtime = verify_runtime_lock(wheel_lock, wheel_dir, model)
    versions = {name: importlib.metadata.version(name) for name in EXPECTED_PACKAGES}
    if versions != EXPECTED_PACKAGES:
        raise ValueError(f"unlocked runtime packages: {versions}")
    receipt: dict[str, Any] = {
        "status": "model_and_selection_hashes_pass",
        "source_pdf_count_opened": 0,
        "gold_count_opened": 0,
        "preflight_source_sha256": sha256_file(Path(__file__).resolve()),
        "model_sha256": MODEL_SHA256,
        "selection_sha256": SELECTION_SHA256,
        "package_versions": versions,
        "runtime": runtime,
        "model_rights": "research_only_hold_mirror_agpl_metadata",
    }
    if smoke:
        from rapid_table import ModelType, RapidTable, RapidTableInput

        image, ocr_tuple = make_synthetic_table()
        validate_ocr_tuple(ocr_tuple)
        engine = RapidTable(
            RapidTableInput(
                model_type=ModelType.SLANETPLUS,
                model_dir_or_path=str(model),
                use_ocr=True,
            )
        )
        providers = engine.table_structure.session.session.get_providers()
        if providers != ["CPUExecutionProvider"]:
            raise ValueError(
                f"unexpected RapidTable model session providers: {providers}"
            )
        result = engine(image, ocr_results=[ocr_tuple])
        expected_grid = {
            (row, row, col, col): ocr_tuple[1][row * 3 + col]
            for row in range(2)
            for col in range(3)
        }
        contract = validate_result(
            result, image.shape[1], image.shape[0], ocr_tuple[1], expected_grid
        )
        receipt["synthetic_model_session_providers"] = providers
        receipt["synthetic_contract"] = contract
        receipt["status"] = "synthetic_contract_pass"
    write_receipt_exclusive(output, receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--wheel-lock", type=Path, required=True)
    parser.add_argument("--wheel-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            preflight(
                args.model,
                args.selection,
                args.wheel_lock,
                args.wheel_dir,
                args.output,
                args.smoke,
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
