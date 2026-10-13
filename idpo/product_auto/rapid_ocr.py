"""Opt-in, bounded local OCR. The application never imports ONNX or RapidOCR."""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from idpo.product_auto.rapid_ocr_protocol import (
    LINE_SCORE_THRESHOLD, MAX_PNG_BYTES, MAX_RESULT_BYTES, MODEL_SHA256,
    PROVIDERS, REVISION, WORKER_FAILURES, RapidOcrError, sha256_file, validate_image_size, validate_payload,
)


@dataclass(frozen=True)
class RapidOcrConfig:
    python: Path
    timeout_s: float = 120.0
    max_rss_mib: int = 1536
    work_dir: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.python, Path) or not self.python.is_absolute() or not self.python.is_file():
            raise RapidOcrError("rapidocr_not_configured")
        if (type(self.timeout_s) not in (float, int) or not math.isfinite(self.timeout_s)
                or not 1 <= self.timeout_s <= 180
                or type(self.max_rss_mib) is not int or not 128 <= self.max_rss_mib <= 2048):
            raise RapidOcrError("rapidocr_config_invalid")
        if self.work_dir is not None and (not self.work_dir.is_absolute() or not self.work_dir.is_dir()):
            raise RapidOcrError("rapidocr_config_invalid")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> RapidOcrConfig:
        env = os.environ if environ is None else environ
        if not env.get("IDPO_RAPIDOCR_PYTHON", "").strip():
            raise RapidOcrError("rapidocr_not_configured")
        try:
            return cls(
                python=Path(env["IDPO_RAPIDOCR_PYTHON"]),
                timeout_s=float(env.get("IDPO_RAPIDOCR_TIMEOUT_S", "120")),
                max_rss_mib=int(env.get("IDPO_RAPIDOCR_MAX_RSS_MIB", "1536")),
                work_dir=Path(env["IDPO_RAPIDOCR_WORK_DIR"]) if env.get("IDPO_RAPIDOCR_WORK_DIR") else None,
            )
        except (ValueError, TypeError, OSError):
            raise RapidOcrError("rapidocr_config_invalid") from None


@dataclass(frozen=True)
class RapidOcrResult:
    text: str
    metadata: dict[str, Any]


def worker_environment(python: Path, work_dir: Path) -> dict[str, str]:
    """Allowlist runtime paths; exclude host credentials, proxies and providers."""
    environment = {
        "PATH": str(python.parent), "TEMP": str(work_dir), "TMP": str(work_dir),
        "HOME": str(work_dir), "USERPROFILE": str(work_dir),
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
        "PYTHONIOENCODING": "utf-8", "HF_HUB_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1", "TOKENIZERS_PARALLELISM": "false",
        "OMP_NUM_THREADS": "4", "OPENBLAS_NUM_THREADS": "4", "MKL_NUM_THREADS": "4",
    }
    if os.name == "nt":
        system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
        if not system_root or not Path(system_root).is_dir():
            raise RapidOcrError("rapidocr_environment_invalid")
        environment.update(SystemRoot=system_root, WINDIR=system_root)
        environment["PATH"] = os.pathsep.join((str(python.parent), str(Path(system_root) / "System32"), system_root))
    return environment


def _kill_tree(process: subprocess.Popen, monitored: Any) -> None:
    import psutil
    try:
        descendants = monitored.children(recursive=True)
    except psutil.NoSuchProcess:
        descendants = []
    for member in [*reversed(descendants), monitored]:
        try:
            member.kill()
        except psutil.NoSuchProcess:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        raise RapidOcrError("rapidocr_worker_cleanup_failed") from None
    _, alive = psutil.wait_procs(descendants, timeout=5)
    if alive:
        raise RapidOcrError("rapidocr_worker_cleanup_failed")


def _run_worker(argv: list[str], config: RapidOcrConfig, work_dir: Path) -> tuple[int, int, float]:
    try:
        import psutil
    except ImportError:
        raise RapidOcrError("rapidocr_resource_monitor_missing") from None
    started = time.monotonic()
    process = subprocess.Popen(
        argv, cwd=work_dir, env=worker_environment(config.python, work_dir),
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        monitored = psutil.Process(process.pid)
    except psutil.NoSuchProcess:
        return process.wait(timeout=5), 0, (time.monotonic() - started) * 1000
    except psutil.Error:
        process.kill()
        process.wait(timeout=5)
        raise RapidOcrError("rapidocr_resource_monitor_failed") from None
    peak = 0
    try:
        while process.poll() is None:
            if time.monotonic() - started >= config.timeout_s:
                raise RapidOcrError("rapidocr_timeout")
            try:
                members = [monitored, *monitored.children(recursive=True)]
                rss = sum(member.memory_info().rss for member in members if member.is_running())
            except psutil.NoSuchProcess:
                continue
            except psutil.Error:
                raise RapidOcrError("rapidocr_resource_monitor_failed") from None
            peak = max(peak, rss)
            if rss > config.max_rss_mib * 1024**2:
                raise RapidOcrError("rapidocr_memory_limit")
            time.sleep(0.05)
        return process.returncode, peak, (time.monotonic() - started) * 1000
    finally:
        if process.poll() is None:
            _kill_tree(process, monitored)


def recognize_image(image: Any, *, config: RapidOcrConfig | None = None) -> RapidOcrResult:
    """OCR one bounded raster; line coordinates refer to this exact input image.

    The caller owns PDF rendering, image frame/orientation selection and storage
    of returned metadata. Do not normalize the returned text without rebuilding
    offsets. No word boxes, table structure or extraction accuracy are inferred.
    """
    config = config or RapidOcrConfig.from_env()
    from PIL import Image
    if not isinstance(image, Image.Image):
        raise RapidOcrError("rapidocr_image_invalid")
    size = validate_image_size(image.size)
    worker = Path(__file__).with_name("rapid_ocr_worker.py")
    try:
        with tempfile.TemporaryDirectory(prefix="product-rapidocr-", dir=config.work_dir) as scratch:
            work_dir = Path(scratch)
            input_png, result_json = work_dir / "input.png", work_dir / "result.json"
            # RGB conversion preserves dimensions and creates no rotation or
            # resize; the parent retains original page-to-raster provenance.
            with image.convert("RGB") as rgb, input_png.open("xb") as stream:
                rgb.save(stream, format="PNG")
            if not 0 < input_png.stat().st_size <= MAX_PNG_BYTES:
                raise RapidOcrError("rapidocr_image_size")
            input_hash = sha256_file(input_png)
            code, peak, elapsed_ms = _run_worker([
                str(config.python), "-I", "-B", str(worker), "--input-png", str(input_png),
                "--input-sha256", input_hash, "--width", str(size[0]), "--height", str(size[1]),
                "--result-json", str(result_json),
            ], config, work_dir)
            if code != 0:
                if (result_json.is_file() and not result_json.is_symlink()
                        and 0 < result_json.stat().st_size < 1024):
                    try:
                        failure = json.loads(result_json.read_text(encoding="utf-8"))
                        if (isinstance(failure, dict) and failure.get("status") == "failed"
                                and failure.get("reason") in WORKER_FAILURES):
                            raise RapidOcrError(failure["reason"])
                    except (ValueError, TypeError):
                        pass
                raise RapidOcrError("rapidocr_worker_failed")
            if (not result_json.is_file() or result_json.is_symlink()
                    or not 0 < result_json.stat().st_size <= MAX_RESULT_BYTES
                    or sha256_file(input_png) != input_hash):
                raise RapidOcrError("rapidocr_result_invalid")
            try:
                payload = json.loads(result_json.read_text(encoding="utf-8"))
            except (ValueError, UnicodeError):
                raise RapidOcrError("rapidocr_result_invalid") from None
            text, lines = validate_payload(payload, image_size=size, input_hash=input_hash)
            if not lines:
                raise RapidOcrError("rapidocr_no_text")
            return RapidOcrResult(text=text, metadata={
                "ocr_engine_used": "rapidocr", "ocr_variant": "ppocrv6_small_cpu_lines",
                "ocr_confidence": 100 * sum(line["score"] for line in lines) / len(lines),
                "ocr_candidate_count": 1, "ocr_rotation_applied": 0,
                "ocr_lines": lines,
                "ocr_provenance": {
                    "revision": REVISION, "input_png_sha256": input_hash,
                    "result_sha256": sha256_file(result_json), "image_size_px": list(size),
                    "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "coordinate_space": "input_raster_pixels", "offset_unit": "unicode_code_points",
                    "engine_input_color": "RGB_PIL_converted_to_BGR_by_RapidOCR",
                    "reading_order": "engine_output", "line_score_threshold": LINE_SCORE_THRESHOLD,
                    "model_sha256": MODEL_SHA256.copy(),
                    "providers": {part: list(selected) for part, selected in PROVIDERS.items()},
                    "timeout_s": config.timeout_s, "rss_limit_mib": config.max_rss_mib,
                    "peak_tree_rss_bytes_sampled": peak, "rss_sample_interval_ms": 50,
                    "worker_elapsed_ms": round(elapsed_ms, 3),
                    "score_caveat": "OCR line scores are uncalibrated and do not establish field correctness.",
                    "isolation": "separate_interpreter_allowlisted_environment_offline_python_audit",
                },
            })
    except RapidOcrError:
        raise
    except Exception:
        raise RapidOcrError("rapidocr_failed") from None
