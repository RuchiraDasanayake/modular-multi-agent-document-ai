"""Bounded second-arm GLiNER weight acquisition; never loads the model.

The read-only ``check`` command is safe before release. ``acquire`` performs
one official Hub/Xet download into a fresh C: staging tree outside Git.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "product_eval" / "fixtures" / "gliner25_small_oracle_six.json"
MANIFEST_SHA256 = "1871cf55460944e748257c4e5de8832870250a581158126aba8b90f51ca5e77b"
MODEL_ID = "fastino/gliner2.5-small-v1"
REVISION = "df5910e44bc4ffdb0d95399a83b0ca4516349aa5"
WEIGHT = "model.safetensors"
WEIGHT_BYTES = 295_567_700
WEIGHT_SHA256 = "4ee982787ace270d4bf15dbcb28ced38e0aa201372347114ceedd6336055de2b"
SMALL_FILES = ("config.json", "encoder_config/config.json", "tokenizer.json", "tokenizer_config.json")
DEFAULT_SMALL_SOURCE = Path("E:/DocAI-Benchmarks/models/gliner25-small-v1-df5910e")
HUB_VERSION = "2.2.0"
XET_VERSION = "1.7.0"
PSUTIL_VERSION = "7.2.2"
MAX_WALL_SECONDS = 900
MIN_START_C_BYTES = 6 * 1024**3
MIN_CONTINUE_C_BYTES = 4 * 1024**3
MIN_START_RAM_BYTES = 4 * 1024**3
MIN_CONTINUE_RAM_BYTES = 3 * 1024**3
MAX_TREE_RSS_BYTES = 3 * 1024**3
MAX_STAGE_BYTES = 2 * 1024**3
SAMPLE_SECONDS = 0.5
XET_SETTINGS = {
    "HF_XET_FIXED_DOWNLOAD_CONCURRENCY": "2",
    "HF_XET_CLIENT_RETRY_MAX_ATTEMPTS": "2",
    "HF_XET_CLIENT_RETRY_BASE_DELAY": "1000ms",
    "HF_XET_CLIENT_RETRY_MAX_DURATION": "60s",
    "HF_XET_CLIENT_CONNECT_TIMEOUT": "15s",
    "HF_XET_CLIENT_READ_TIMEOUT": "30s",
    "HF_XET_HIGH_PERFORMANCE": "0",
}
_SAFE_CLASSES = frozenset({
    "FileNotFoundError", "FileExistsError", "PermissionError", "ValueError",
    "RuntimeError", "TimeoutError", "OSError", "ConnectionError",
    "ConnectError", "ReadTimeout", "ConnectTimeout", "RemoteProtocolError",
    "HfHubHTTPError", "HTTPStatusError", "XetDownloadError", "XetOnlyError",
    "LocalEntryNotFoundError", "EntryNotFoundError", "GatedRepoError",
    "RepositoryNotFoundError", "RevisionNotFoundError", "HashMismatchError",
    "ResourceGuardError", "VersionMismatchError", "StagePathError",
})


class HashMismatchError(ValueError):
    pass


class ResourceGuardError(RuntimeError):
    pass


class VersionMismatchError(RuntimeError):
    pass


class StagePathError(ValueError):
    pass


class XetOnlyError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def model_lock() -> dict[str, Any]:
    if sha256_file(MANIFEST) != MANIFEST_SHA256:
        raise HashMismatchError("model manifest changed")
    model = json.loads(MANIFEST.read_text(encoding="utf-8"))["model"]
    if (model["id"] != MODEL_ID or model["revision"] != REVISION
            or set(model["files"]) != {*SMALL_FILES, WEIGHT}
            or model["files"][WEIGHT] != {"bytes": WEIGHT_BYTES, "sha256": WEIGHT_SHA256}):
        raise HashMismatchError("model specification differs from frozen arm")
    return model


def verify_file(path: Path, spec: dict[str, Any]) -> str:
    if not path.is_file() or path.stat().st_size != spec["bytes"]:
        raise HashMismatchError("file missing or byte count differs")
    digest = sha256_file(path)
    if digest != spec["sha256"]:
        raise HashMismatchError("file digest differs")
    return digest


def _safe_class(exc: BaseException) -> str:
    name = type(exc).__name__
    return name if name in _SAFE_CLASSES else "OtherError"


def safe_error(exc: BaseException) -> dict[str, Any]:
    seen: set[int] = {id(exc)}
    causes: list[str] = []
    current = exc.__cause__ or exc.__context__
    for _ in range(4):
        if current is None or id(current) in seen:
            break
        seen.add(id(current))
        causes.append(_safe_class(current))
        current = current.__cause__ or current.__context__
    return {"error_class": _safe_class(exc), "cause_classes": causes}


def validate_stage(stage: Path) -> None:
    resolved = stage.resolve()
    if (not stage.is_absolute() or resolved.drive.upper() != "C:"
            or resolved.is_relative_to(REPO_ROOT) or stage.exists()
            or not stage.parent.is_dir()):
        raise StagePathError("stage must be a fresh C: directory outside Git")


def _versions() -> dict[str, str]:
    versions = {
        "huggingface_hub": importlib.metadata.version("huggingface-hub"),
        "hf_xet": importlib.metadata.version("hf-xet"),
        "psutil": importlib.metadata.version("psutil"),
    }
    if (sys.version_info[:2] != (3, 11) or versions != {
            "huggingface_hub": HUB_VERSION, "hf_xet": XET_VERSION,
            "psutil": PSUTIL_VERSION}):
        raise VersionMismatchError("acquisition runtime differs from lock")
    return versions


def preflight(stage: Path, small_source: Path) -> dict[str, Any]:
    import psutil

    validate_stage(stage)
    versions = _versions()
    model = model_lock()
    verified = {name: verify_file(small_source / name, model["files"][name]) for name in SMALL_FILES}
    free_c = shutil.disk_usage("C:\\").free
    free_ram = psutil.virtual_memory().available
    if free_c < MIN_START_C_BYTES or free_ram < MIN_START_RAM_BYTES:
        raise ResourceGuardError("host start floor not met")
    return {"ready": True, "verified_small_files": len(verified),
            "manifest_sha256": MANIFEST_SHA256, "free_c_bytes": free_c,
            "available_ram_bytes": free_ram, "versions": versions}


def copy_small_files(stage: Path, small_source: Path, model: dict[str, Any]) -> dict[str, str]:
    copied: dict[str, str] = {}
    for name in SMALL_FILES:
        source = small_source / name
        expected = model["files"][name]
        verify_file(source, expected)  # Rehash immediately before copying.
        target = stage / "model" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as reader, target.open("xb") as writer:
            shutil.copyfileobj(reader, writer, 1024 * 1024)
        copied[name] = verify_file(target, expected)
    return copied


def worker_environment(stage: Path) -> dict[str, str]:
    environment = os.environ.copy()
    for name in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HF_HUB_DISABLE_XET", "HF_DEBUG"):
        environment.pop(name, None)
    home = stage / "hf-home"
    environment.update(XET_SETTINGS)
    environment.update({
        "GLINER_HUB_WORKER_ARM": MANIFEST_SHA256,
        "HF_HOME": str(home), "HF_HUB_CACHE": str(home / "hub"),
        "HF_XET_CACHE": str(home / "xet"), "HF_TOKEN_PATH": str(home / "token"),
        "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1", "HF_HUB_DISABLE_TELEMETRY": "1",
        "HF_HUB_DISABLE_PROGRESS_BARS": "1", "HF_HUB_VERBOSITY": "error",
        "HF_HUB_DOWNLOAD_TIMEOUT": "30", "HF_HUB_ETAG_TIMEOUT": "15",
        "HF_ENDPOINT": "https://huggingface.co", "HF_XET_LOG_DEST": os.devnull,
    })
    return environment


def download_once(stage: Path, model: dict[str, Any],
                  hub_download: Callable[..., str], xet_calls: list[int]) -> dict[str, Any]:
    """One pinned Hub call; reject a cache hit or HTTP fallback without Xet."""
    cached = Path(hub_download(
        repo_id=MODEL_ID, filename=WEIGHT, revision=REVISION, repo_type="model",
        endpoint="https://huggingface.co", cache_dir=stage / "hf-home" / "hub",
        token=False, force_download=True, etag_timeout=15,
    ))
    if xet_calls[0] < 1:
        raise XetOnlyError("Xet was not used")
    if not cached.resolve().is_relative_to(stage.resolve()):
        raise StagePathError("Hub returned a path outside isolated stage")
    expected = model["files"][WEIGHT]
    verify_file(cached, expected)
    target = stage / "model" / WEIGHT
    with cached.open("rb") as reader, target.open("xb") as writer:
        shutil.copyfileobj(reader, writer, 1024 * 1024)
    verify_file(target, expected)
    return {"xet_calls": xet_calls[0], "weight_bytes": expected["bytes"],
            "weight_sha256": expected["sha256"]}


def worker(stage: Path) -> int:
    """Child process: no stdout/stderr is retained by the parent."""
    result: dict[str, Any] = {"status": "failure", "xet_calls": 0}
    xet_calls = [0]
    timer = threading.Timer(MAX_WALL_SECONDS, lambda: os._exit(124))
    timer.daemon = True
    timer.start()
    try:
        if (stage.resolve().drive.upper() != "C:"
                or stage.resolve().is_relative_to(REPO_ROOT)
                or os.environ.get("GLINER_HUB_WORKER_ARM") != MANIFEST_SHA256
                or Path(os.environ.get("HF_HOME", "")).resolve() != (stage / "hf-home").resolve()
                or any(os.environ.get(name) != value for name, value in XET_SETTINGS.items())
                or any(os.environ.get(name) for name in ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"))):
            raise StagePathError("worker isolation differs from frozen arm")
        _versions()
        model = model_lock()
        for name in SMALL_FILES:
            verify_file(stage / "model" / name, model["files"][name])
        from huggingface_hub import file_download, hf_hub_download

        original_xet_get = file_download.xet_get
        original_http_get = file_download.http_get

        def counted_xet_get(*args: Any, **kwargs: Any) -> None:
            xet_calls[0] += 1
            original_xet_get(*args, **kwargs)

        def reject_raw_http(*args: Any, **kwargs: Any) -> None:
            raise XetOnlyError("raw HTTP body fallback forbidden in this arm")

        file_download.xet_get = counted_xet_get
        file_download.http_get = reject_raw_http
        try:
            result.update(download_once(stage, model, hf_hub_download, xet_calls))
            result["status"] = "complete"
        finally:
            file_download.xet_get = original_xet_get
            file_download.http_get = original_http_get
    except Exception as exc:  # noqa: BLE001 - do not persist signed URLs or exception messages
        result.update(safe_error(exc))
        result["xet_calls"] = xet_calls[0]
    finally:
        timer.cancel()
    (stage / "worker.json").write_text(json.dumps(result, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if result["status"] == "complete" else 1


def _tree_rss(process: subprocess.Popen[bytes]) -> int:
    import psutil

    try:
        root = psutil.Process(process.pid)
        return sum(item.memory_info().rss for item in [root, *root.children(recursive=True)]
                   if item.is_running())
    except psutil.Error:
        return 0


def _stop_tree(process: subprocess.Popen[bytes]) -> None:
    import psutil

    try:
        root = psutil.Process(process.pid)
        for child in root.children(recursive=True):
            try:
                child.kill()
            except psutil.Error:
                pass
        root.kill()
    except psutil.Error:
        pass
    process.wait(timeout=10)


def guard_reason(*, now: float, deadline: float, free_c: int,
                 available_ram: int, tree_rss: int, stage_bytes: int) -> str | None:
    if now >= deadline:
        return "wall_deadline"
    if free_c < MIN_CONTINUE_C_BYTES:
        return "disk_floor"
    if available_ram < MIN_CONTINUE_RAM_BYTES or tree_rss > MAX_TREE_RSS_BYTES:
        return "memory_floor"
    if stage_bytes > MAX_STAGE_BYTES:
        return "stage_size_cap"
    return None


def _stage_bytes(stage: Path) -> int:
    total = 0
    for path in stage.rglob("*"):
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:  # A cache temporary can disappear between enumeration and stat.
            continue
    return total


def acquire(stage: Path, small_source: Path) -> dict[str, Any]:
    import psutil

    started = time.monotonic()
    deadline = started + MAX_WALL_SECONDS
    start = preflight(stage, small_source)
    model = model_lock()
    stage.mkdir()  # No overwrite of prior arm or partial attempts.
    copied = copy_small_files(stage, small_source, model)
    process = subprocess.Popen(
        [sys.executable, "-m", "product_eval.gliner25_hub_acquisition",
         "worker", "--stage-root", str(stage)],
        cwd=REPO_ROOT, env=worker_environment(stage),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    peak_rss = 0
    min_free_c = start["free_c_bytes"]
    min_available_ram = start["available_ram_bytes"]
    status, stop_reason = "failure", None
    stage_bytes = 0
    last_size_sample = 0.0
    try:
        while process.poll() is None:
            now = time.monotonic()
            free_c = shutil.disk_usage("C:\\").free
            available_ram = psutil.virtual_memory().available
            rss = _tree_rss(process)
            peak_rss = max(peak_rss, rss)
            min_free_c = min(min_free_c, free_c)
            min_available_ram = min(min_available_ram, available_ram)
            if now - last_size_sample >= 5:
                stage_bytes = _stage_bytes(stage)
                last_size_sample = now
            stop_reason = guard_reason(now=now, deadline=deadline, free_c=free_c,
                                       available_ram=available_ram, tree_rss=rss,
                                       stage_bytes=stage_bytes)
            if stop_reason:
                _stop_tree(process)
                status = "resource_stop"
                break
            time.sleep(SAMPLE_SECONDS)
    finally:
        if process.poll() is None:
            _stop_tree(process)
    process.wait(timeout=10)
    worker_path = stage / "worker.json"
    try:
        worker_result = json.loads(worker_path.read_text(encoding="utf-8")) if worker_path.is_file() else {}
    except (OSError, ValueError):
        worker_result = {}
    verified = copied
    if time.monotonic() >= deadline and status != "resource_stop":
        status, stop_reason = "resource_stop", "wall_deadline"
    if status != "resource_stop" and process.returncode == 0 and worker_result.get("status") == "complete":
        try:
            verified = {name: verify_file(stage / "model" / name, spec)
                        for name, spec in model["files"].items()}
            status = "verified" if len(verified) == 5 else "failure"
        except Exception as exc:  # noqa: BLE001 - hash failure must still seal a receipt
            status = "hash_failure"
            worker_result.update(safe_error(exc))
    receipt = {
        "status": status, "stop_reason": stop_reason,
        "manifest_sha256": MANIFEST_SHA256,
        "verified_files": verified,
        "weight_bytes": worker_result.get("weight_bytes") if status == "verified" else None,
        "weight_sha256": worker_result.get("weight_sha256") if status == "verified" else None,
        "xet_calls": worker_result.get("xet_calls", 0),
        "worker_exit_code": process.returncode,
        "error_class": worker_result.get("error_class"),
        "cause_classes": worker_result.get("cause_classes", []),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "peak_tree_rss_bytes_sampled": peak_rss,
        "min_free_c_bytes_sampled": min_free_c,
        "min_available_ram_bytes_sampled": min_available_ram,
        "start": start,
    }
    with (stage / "acquisition_receipt.json").open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, sort_keys=True, indent=2)
        handle.write("\n")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "acquire", "worker"):
        command = commands.add_parser(name)
        command.add_argument("--stage-root", required=True, type=Path)
        if name != "worker":
            command.add_argument("--small-source", type=Path, default=DEFAULT_SMALL_SOURCE)
    args = parser.parse_args()
    if args.command == "worker":
        return worker(args.stage_root)
    try:
        result = (preflight(args.stage_root, args.small_source) if args.command == "check"
                  else acquire(args.stage_root, args.small_source))
        print(json.dumps(result, sort_keys=True))
        return 0 if result.get("status", "ready") in {"ready", "verified"} else 1
    except Exception as exc:  # noqa: BLE001 - output only classes; paths/URLs may be in messages
        print(json.dumps(safe_error(exc), sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
