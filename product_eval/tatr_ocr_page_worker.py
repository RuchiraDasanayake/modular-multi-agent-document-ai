"""One full-page raster through the pinned, isolated RapidOCR CPU runtime.

The input is a bounded lossless PNG, never a PDF or gold record. The parent
TATR worker hashes the transport file and validates this result again before
using its word boxes. The source-free orientation guard rejects 180-degree
or uncertain lines before RapidOCR constructs word geometry.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from product_eval.tatr_ocr_word_source_free import (
    OCR_REVISION,
    guarded_rapidocr_class,
    rapidocr_words_to_tatr_tokens,
    sha256_file,
    verify_runtime,
)

MAX_PNG_BYTES = 64 * 1024 * 1024
MAX_PIXELS = 35_000_000
MAX_LINES = 10_000
MAX_WORDS = 50_000
MAX_RESULT_BYTES = 16 * 1024 * 1024


def _write_new_json(path: Path, value: dict[str, Any]) -> None:
    encoded = (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
               + "\n").encode("utf-8")
    if len(encoded) > MAX_RESULT_BYTES:
        raise ValueError("OCR JSON transport exceeds frozen byte limit")
    with path.open("xb") as stream:
        stream.write(encoded)


def _raw_lines(result: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, (text, box, score, words) in enumerate(zip(
        result.txts, result.boxes, result.scores, result.word_results, strict=True,
    )):
        rows.append({
            "line_index": index,
            "text": text,
            "polygon": box.tolist() if hasattr(box, "tolist") else box,
            "score": float(score),
            "words": [{
                "text": item[0], "reported_score": float(item[1]),
                "polygon": item[2].tolist() if hasattr(item[2], "tolist") else item[2],
            } for item in words],
        })
    return rows


def run_ocr_png(
    *, input_png: Path, expected_sha256: str, expected_size: tuple[int, int],
    runtime_root: Path, wheelhouse: Path, notices_root: Path, result_json: Path,
) -> dict[str, Any]:
    if not input_png.is_file() or not 0 < input_png.stat().st_size <= MAX_PNG_BYTES:
        raise ValueError("OCR PNG transport file is absent or too large")
    if sha256_file(input_png) != expected_sha256:
        raise ValueError("OCR PNG transport hash changed")
    if (len(expected_size) != 2 or any(type(value) is not int or value <= 0 for value in expected_size)
            or expected_size[0] * expected_size[1] > MAX_PIXELS):
        raise ValueError("OCR expected raster size exceeds frozen bound")
    runtime = verify_runtime(runtime_root, wheelhouse, notices_root)
    import numpy as np
    from PIL import Image
    from rapidocr import RapidOCR

    with Image.open(input_png) as image:
        if image.format != "PNG" or image.mode != "RGB" or image.size != expected_size:
            raise ValueError("OCR raster transport format, mode or dimensions changed")
        image.load()
        raster = np.asarray(image)
    model_dir = runtime_root / "Lib" / "site-packages" / "rapidocr" / "models"
    engine = guarded_rapidocr_class(RapidOCR)(params={
        "Global.text_score": 0.0,
        "Det.lang_type": "en", "Rec.lang_type": "en",
        "Det.model_path": str(model_dir / "PP-OCRv6_det_small.onnx"),
        "Cls.model_path": str(model_dir / "ch_ppocr_mobile_v2.0_cls_mobile.onnx"),
        "Rec.model_path": str(model_dir / "PP-OCRv6_rec_small.onnx"),
        "EngineConfig.onnxruntime.intra_op_num_threads": 4,
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        "EngineConfig.onnxruntime.use_cuda": False,
        "EngineConfig.onnxruntime.use_dml": False,
    })
    result = engine(raster, return_word_box=True, return_single_char_box=False)
    providers = {
        part: getattr(engine, part).session.session.get_providers()
        for part in ("text_det", "text_cls", "text_rec")
    }
    if any(selected != ["CPUExecutionProvider"] for selected in providers.values()):
        raise ValueError("OCR model session selected a non-CPU provider")
    tokens = rapidocr_words_to_tatr_tokens(result, expected_size)
    orientations = engine.last_line_orientations
    if (orientations is None or len(orientations) != len(result.txts)
            or not 0 < len(result.txts) <= MAX_LINES or not 0 < len(tokens) <= MAX_WORDS):
        raise ValueError("OCR line or word count is absent, misaligned or above bound")
    lines = _raw_lines(result)
    payload = {
        "status": "ocr_page_words_ready",
        "source": "ocr_word", "ocr_revision": OCR_REVISION,
        "input_png_sha256": expected_sha256,
        "input_png_size_bytes": input_png.stat().st_size,
        "image_size": list(expected_size),
        "line_score_threshold": engine.text_score,
        "line_orientations": [{"label": label, "score": score}
                              for label, score in orientations],
        "line_count": len(lines), "word_count": len(tokens),
        "raw_lines": lines, "word_tokens": tokens,
        "providers_selected": providers,
        "runtime_inventory": runtime,
        "word_score_caveat": "RapidOCR grouped-word reported score is uncalibrated; no word-score filter or rank applied.",
        "source_pdf_opened": False, "gold_opened": False,
    }
    _write_new_json(result_json, payload)
    return {"result_sha256": sha256_file(result_json),
            "line_count": len(lines), "word_count": len(tokens)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-png", type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--notices-root", type=Path, required=True)
    parser.add_argument("--result-json", type=Path, required=True)
    args = parser.parse_args()
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    try:
        print(json.dumps(run_ocr_png(
            input_png=args.input_png, expected_sha256=args.input_sha256,
            expected_size=(args.width, args.height), runtime_root=args.runtime_root,
            wheelhouse=args.wheelhouse, notices_root=args.notices_root,
            result_json=args.result_json,
        )))
    except Exception as exc:  # noqa: BLE001 - bounded failure receipt at the process boundary
        reason = ("orientation_not_confidently_upright"
                  if str(exc) == "RapidOCR word geometry requires confidently upright lines"
                  else type(exc).__name__)
        _write_new_json(args.result_json.with_name("ocr_failure.json"), {
            "status": "failed", "reason": reason,
            "source_pdf_opened": False, "gold_opened": False,
        })
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
