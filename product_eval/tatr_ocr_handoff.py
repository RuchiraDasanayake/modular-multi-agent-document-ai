"""Bounded full-page IPC from the TATR CPU worker to pinned RapidOCR CPU."""

from __future__ import annotations

import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from product_eval.tatr_asset_preflight import sha256_file
from product_eval.tatr_cell_compat import prepare_word_tokens
from product_eval.tatr_ocr_page_worker import (
    MAX_LINES,
    MAX_PIXELS,
    MAX_PNG_BYTES,
    MAX_RESULT_BYTES,
    MAX_WORDS,
)
from product_eval.tatr_ocr_word_source_free import (
    LOCK_PATH,
    OCR_REVISION,
    _polygon,
)
from product_eval.tatr_process_env import environment_sha256, isolated_worker_env

OCR_PAGE_SECONDS = 120


def _stop_process_tree(process: subprocess.Popen[bytes]) -> None:
    import psutil

    try:
        parent = psutil.Process(process.pid)
        members = [*parent.children(recursive=True), parent]
        for member in reversed(members):
            try:
                member.kill()
            except psutil.Error:
                pass
    except psutil.Error:
        pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def validate_ocr_payload(
    payload: Any, *, image_size: tuple[int, int], input_hash: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Revalidate cross-process OCR evidence before any cell assignment."""
    if not isinstance(payload, dict) or any(payload.get(key) != value for key, value in {
        "status": "ocr_page_words_ready", "source": "ocr_word",
        "ocr_revision": OCR_REVISION, "input_png_sha256": input_hash,
        "image_size": list(image_size), "line_score_threshold": 0.0,
        "source_pdf_opened": False, "gold_opened": False,
    }.items()):
        raise ValueError("OCR payload identity, policy or page size differs")
    lines = payload.get("raw_lines")
    tokens = payload.get("word_tokens")
    orientations = payload.get("line_orientations")
    if (not isinstance(lines, list) or not 0 < len(lines) <= MAX_LINES
            or not isinstance(tokens, list) or not 0 < len(tokens) <= MAX_WORDS
            or not isinstance(orientations, list) or len(orientations) != len(lines)
            or payload.get("line_count") != len(lines)
            or payload.get("word_count") != len(tokens)):
        raise ValueError("OCR lines, orientations or words are missing or above bound")
    providers = payload.get("providers_selected")
    if (not isinstance(providers, dict)
            or set(providers) != {"text_det", "text_cls", "text_rec"}
            or any(value != ["CPUExecutionProvider"] for value in providers.values())):
        raise ValueError("OCR provider provenance differs from CPU-only lock")
    runtime = payload.get("runtime_inventory")
    if (not isinstance(runtime, dict)
            or runtime.get("ocr_lock_sha256") != sha256_file(LOCK_PATH)
            or runtime.get("opencv_package") != "opencv-python-headless==5.0.0.93"):
        raise ValueError("OCR runtime provenance differs from pinned lock")
    prepared = prepare_word_tokens(tokens, image_size)
    if len(prepared) != len(tokens):
        raise ValueError("OCR token preparation lost words")
    flat_index = 0
    for index, (line, orientation) in enumerate(zip(lines, orientations, strict=True)):
        if (not isinstance(line, dict) or line.get("line_index") != index
                or not isinstance(line.get("text"), str) or not line["text"].strip()
                or not isinstance(line.get("words"), list) or not line["words"]
                or not isinstance(orientation, dict)
                or orientation.get("label") != "0"
                or not isinstance(orientation.get("score"), (int, float))
                or isinstance(orientation["score"], bool)
                or not math.isfinite(orientation["score"])
                or not 0.9 < orientation["score"] <= 1):
            raise ValueError("OCR line metadata or orientation is invalid")
        line_polygon = _polygon(line["polygon"], image_size)
        line_bounds = (
            min(point[0] for point in line_polygon),
            min(point[1] for point in line_polygon),
            max(point[0] for point in line_polygon),
            max(point[1] for point in line_polygon),
        )
        score = line.get("score")
        if (not isinstance(score, (int, float)) or isinstance(score, bool)
                or not math.isfinite(score) or not 0 <= score <= 1):
            raise ValueError("OCR line score is invalid")
        concatenated = ""
        for word_index, word in enumerate(line["words"]):
            if flat_index >= len(tokens) or not isinstance(word, dict):
                raise ValueError("OCR line words exceed flattened token count")
            token = tokens[flat_index]
            if (token["source_token_id"] != f"rapidocr:l{index}:w{word_index}"
                    or token["text"] != word.get("text")
                    or token["ocr_engine"] != "RapidOCR/ONNXRuntime-CPU"
                    or token["ocr_revision"] != OCR_REVISION
                    or token["ocr_confidence"] != word.get("reported_score")
                    or token["ocr_line_score"] != score
                    or token["ocr_polygon"] != word.get("polygon")):
                raise ValueError("OCR raw line word differs from flattened token")
            polygon = _polygon(word["polygon"], image_size)
            box = token["bbox"]
            center_x = (box[0] + box[2]) / 2
            center_y = (box[1] + box[3]) / 2
            if (not line_bounds[0] - 2 <= center_x <= line_bounds[2] + 2
                    or not line_bounds[1] - 2 <= center_y <= line_bounds[3] + 2):
                raise ValueError("OCR word lies outside its parent line")
            if box != [min(point[0] for point in polygon),
                       min(point[1] for point in polygon),
                       max(point[0] for point in polygon),
                       max(point[1] for point in polygon)]:
                raise ValueError("OCR token box differs from word quadrilateral")
            concatenated += token["text"]
            flat_index += 1
        if "".join(line["text"].split()) != concatenated:
            raise ValueError("OCR line text differs from its words")
    if flat_index != len(tokens):
        raise ValueError("OCR flattened tokens have no source line")
    return tokens, {
        "raw_lines": lines, "line_orientations": orientations,
        "providers_selected": providers, "runtime_inventory": runtime,
        "line_count": len(lines), "word_count": len(tokens),
    }


@dataclass(frozen=True)
class OcrPageHandoff:
    python: Path
    runtime_root: Path
    wheelhouse: Path
    notices_root: Path
    output_root: Path

    def __call__(self, image: Any, page_number: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        if (image.mode != "RGB" or image.width <= 0 or image.height <= 0
                or image.width * image.height > MAX_PIXELS):
            raise ValueError("OCR input raster differs from frozen RGB pixel bound")
        if self.python.resolve(strict=True).parent.parent != self.runtime_root.resolve(strict=True):
            raise ValueError("OCR Python executable is outside pinned runtime")
        page_dir = self.output_root / f"ocr-page-{page_number:03d}"
        page_dir.mkdir(exist_ok=False)
        input_png = page_dir / "page.png"
        with input_png.open("xb") as destination:
            image.save(destination, format="PNG")
        if not 0 < input_png.stat().st_size <= MAX_PNG_BYTES:
            raise ValueError("OCR PNG transport exceeds frozen byte bound")
        input_hash = sha256_file(input_png)
        result_json = page_dir / "ocr_result.json"
        repo_root = Path(__file__).resolve().parents[1]
        command = [
            str(self.python), "-B", "-m", "product_eval.tatr_ocr_page_worker",
            "--input-png", str(input_png), "--input-sha256", input_hash,
            "--width", str(image.width), "--height", str(image.height),
            "--runtime-root", str(self.runtime_root),
            "--wheelhouse", str(self.wheelhouse),
            "--notices-root", str(self.notices_root),
            "--result-json", str(result_json),
        ]
        environment = isolated_worker_env(self.python, repo_root)
        with (page_dir / "ocr.log").open("xb") as log:
            process = subprocess.Popen(command, cwd=repo_root, env=environment,
                                       stdout=log, stderr=subprocess.STDOUT)
            try:
                exit_code = process.wait(timeout=OCR_PAGE_SECONDS)
            except subprocess.TimeoutExpired as exc:
                _stop_process_tree(process)
                raise TimeoutError("OCR page subprocess exceeded frozen time limit") from exc
            finally:
                if process.poll() is None:
                    _stop_process_tree(process)
        if exit_code != 0 or (page_dir / "ocr_failure.json").exists():
            raise RuntimeError("OCR page subprocess failed; no partial words accepted")
        if not result_json.is_file() or not 0 < result_json.stat().st_size <= MAX_RESULT_BYTES:
            raise ValueError("OCR JSON transport is missing or above frozen byte bound")
        result_hash = sha256_file(result_json)
        payload = json.loads(result_json.read_text(encoding="utf-8"))
        tokens, provenance = validate_ocr_payload(
            payload, image_size=image.size, input_hash=input_hash,
        )
        provenance.update({
            "input_png_relative": str(input_png.relative_to(self.output_root)),
            "input_png_sha256": input_hash,
            "ocr_result_relative": str(result_json.relative_to(self.output_root)),
            "ocr_result_sha256": result_hash,
            "ocr_log_relative": str((page_dir / "ocr.log").relative_to(self.output_root)),
            "ocr_log_sha256": sha256_file(page_dir / "ocr.log"),
            "ocr_timeout_seconds": OCR_PAGE_SECONDS,
            "ocr_child_env_keys": sorted(environment),
            "ocr_child_env_sha256": environment_sha256(environment),
        })
        return tokens, provenance
