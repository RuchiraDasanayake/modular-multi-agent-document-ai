"""Standalone image-only RapidOCR child; no product or provider imports."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import sys
from pathlib import Path

# -I omits the application and user site directories. Import only the adjacent
# standard-library protocol, avoiding product_auto.__init__ and its workflow.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from rapid_ocr_protocol import (  # noqa: E402
    LINE_SCORE_THRESHOLD, MAX_PNG_BYTES, MAX_RESULT_BYTES, MODEL_SHA256,
    PROVIDERS, REVISION, WORKER_FAILURES, RapidOcrError, sha256_file, validate_image_size, validate_lines,
)


def prohibit_network_and_children(event: str, _args: tuple) -> None:
    if event in {"socket.connect", "socket.connect_ex", "socket.getaddrinfo", "socket.bind",
                 "subprocess.Popen", "os.system", "os.posix_spawn", "os.spawn"}:
        raise RapidOcrError("rapidocr_offline_policy")


def verify_models(model_root: Path) -> None:
    for name, expected in MODEL_SHA256.items():
        path = model_root / name
        if not path.is_file() or path.is_symlink() or sha256_file(path) != expected:
            raise RapidOcrError("rapidocr_model_mismatch")


def verify_runtime() -> Path:
    for name, version in (("rapidocr", "3.10.0"), ("onnxruntime", "1.31.0"),
                          ("opencv-python-headless", "5.0.0.93")):
        try:
            if importlib.metadata.version(name) != version:
                raise RapidOcrError("rapidocr_runtime_mismatch")
        except importlib.metadata.PackageNotFoundError:
            raise RapidOcrError("rapidocr_runtime_mismatch") from None
    try:
        importlib.metadata.version("opencv-python")
    except importlib.metadata.PackageNotFoundError:
        pass
    else:
        raise RapidOcrError("rapidocr_runtime_mismatch")
    distribution = importlib.metadata.distribution("rapidocr")
    model_root = Path(distribution.locate_file("rapidocr/models")).resolve(strict=True)
    if not model_root.is_relative_to(Path(sys.prefix).resolve()):
        raise RapidOcrError("rapidocr_runtime_mismatch")
    verify_models(model_root)
    return model_root


def recognize_png(input_png: Path, input_hash: str, size: tuple[int, int]) -> dict:
    size = validate_image_size(size)
    if (not input_png.is_file() or input_png.is_symlink()
            or not 0 < input_png.stat().st_size <= MAX_PNG_BYTES
            or sha256_file(input_png) != input_hash):
        raise RapidOcrError("rapidocr_input_mismatch")
    model_root = verify_runtime()
    import numpy as np
    from PIL import Image
    from rapidocr import RapidOCR
    from rapidocr.utils.download_file import DownloadFile

    # Explicit model paths bypass downloading. Disable the downloader as well,
    # so a library routing change cannot silently acquire another model.
    def no_download(*_args, **_kwargs):
        raise RapidOcrError("rapidocr_offline_policy")
    DownloadFile.run = no_download
    with Image.open(input_png) as image:
        if image.format != "PNG" or image.mode != "RGB" or image.size != size:
            raise RapidOcrError("rapidocr_input_mismatch")
        image.load()
        raster = np.asarray(image)
    engine = RapidOCR(params={
        "Global.text_score": LINE_SCORE_THRESHOLD,
        "Global.log_level": "error",
        "Det.lang_type": "en", "Rec.lang_type": "en",
        "Det.model_path": str(model_root / "PP-OCRv6_det_small.onnx"),
        "Rec.model_path": str(model_root / "PP-OCRv6_rec_small.onnx"),
        "Cls.model_path": str(model_root / "ch_ppocr_mobile_v2.0_cls_mobile.onnx"),
        "EngineConfig.onnxruntime.intra_op_num_threads": 4,
        "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        "EngineConfig.onnxruntime.use_cuda": False,
        "EngineConfig.onnxruntime.use_dml": False,
        "EngineConfig.onnxruntime.use_cann": False,
        "EngineConfig.onnxruntime.use_coreml": False,
    })
    output = engine(raster)
    if output.txts is None or not len(output.txts):
        raise RapidOcrError("rapidocr_no_text")
    providers = {part: getattr(engine, part).session.session.get_providers() for part in PROVIDERS}
    if providers != PROVIDERS:
        raise RapidOcrError("rapidocr_provider_mismatch")
    texts = list(output.txts) if output.txts is not None else []
    scores = list(output.scores) if output.scores is not None else []
    boxes = output.boxes.tolist() if output.boxes is not None else []
    if not len(texts) == len(scores) == len(boxes):
        raise RapidOcrError("rapidocr_result_invalid")
    lines = [{"text": text, "score": float(score), "polygon": polygon}
             for text, score, polygon in zip(texts, scores, boxes, strict=True)]
    validate_lines(lines, size)
    return {"schema_version": 1, "status": "ready", "revision": REVISION,
            "input_png_sha256": input_hash, "image_size": list(size),
            "model_sha256": MODEL_SHA256, "providers": providers,
            "line_score_threshold": LINE_SCORE_THRESHOLD, "lines": lines}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-png", type=Path, required=True)
    parser.add_argument("--input-sha256", required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--result-json", type=Path, required=True)
    args = parser.parse_args()
    # Python 3.11 on Windows can invoke `ver` for its own platform discovery.
    # Prime that stdlib cache before blocking child processes; third-party
    # imports and inference then run under the offline audit policy.
    platform.system()
    sys.addaudithook(prohibit_network_and_children)
    try:
        payload = recognize_png(args.input_png, args.input_sha256, (args.width, args.height))
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        if len(encoded) > MAX_RESULT_BYTES:
            raise RapidOcrError("rapidocr_result_invalid")
        with args.result_json.open("xb") as stream:
            stream.write(encoded)
        return 0
    except Exception as exc:
        # Raw engine exceptions can contain document content or filesystem
        # details. Only enumerated failure codes cross the process boundary.
        reason = exc.reason if isinstance(exc, RapidOcrError) and exc.reason in WORKER_FAILURES else "rapidocr_worker_failed"
        try:
            with args.result_json.open("xb") as stream:
                stream.write(json.dumps({"status": "failed", "reason": reason}).encode("utf-8"))
        except OSError:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
