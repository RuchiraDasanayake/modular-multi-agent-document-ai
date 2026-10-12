"""Fresh, bounded Hub/Xet acquisition of frozen PP-TableMagic v2 model files.

Preparation only until the parent task releases CPU/network resources. This
module never runs the parser. It keeps the prior raw-HTTP failure untouched.
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
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from product_eval.contracts import ContractError, load_jsonl
from product_eval.docling_table_diagnostic import (
    GOLD_SHA256,
    gold_linked_rows,
    sha256_file,
    verify_selection,
)
from product_eval.tablemagic_v2_pilot import (
    MODEL_MANIFEST,
    MODEL_MANIFEST_SHA256,
    _manifest_digest,
    verify_models,
    verify_runtime,
)

EXPECTED_PYTHON = Path(r"C:\Users\USER\Documents\DocAI-PaddleVL\venv\Scripts\python.exe")
ROOT = Path(r"C:\DocAI-TableMagic-Xet2")
OLD_ROOT = Path(r"C:\DocAI-TableMagic")
OLD_SEAL_SHA256 = "2ea0655eb496b2cb6c4158448131acdab8a5f307fcdacca3b404083ac3eb2364"
OLD_ROOT_DIGEST_SHA256 = "25f6509e400158ea8260385eda442a7d09c5c219d2caf65bf1f4e69b967360ac"
MAX_ASSET_SECONDS = 900
MAX_TOTAL_SECONDS = 5400
MAX_PROCESS_TREE_RSS_BYTES = 3 * 1024**3
MAX_NEW_ROOT_BYTES = 3_500_000_000
MIN_INITIAL_RAM_BYTES = 6 * 1024**3
MIN_RAM_BYTES = 3 * 1024**3
MIN_C_FREE_BYTES = 4 * 1024**3
MIN_E_FREE_BYTES = 2 * 1024**3
EXPECTED_ACTIVE_FILES = 54
EXPECTED_ACTIVE_BYTES = 1_344_345_025
XET_ENV = {
    "HF_ENDPOINT": "https://huggingface.co",
    "HF_HUB_DISABLE_XET": "0",
    "HF_HUB_OFFLINE": "0",
    "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "HF_HUB_DISABLE_PROGRESS_BARS": "1",
    "HF_HUB_DISABLE_UPDATE_CHECK": "1",
    "HF_HUB_VERBOSITY": "error",
    "HF_DEBUG": "0",
    "RUST_LOG": "off",
    "RUST_BACKTRACE": "0",
    "HF_XET_HIGH_PERFORMANCE": "0",
    "HF_XET_FIXED_DOWNLOAD_CONCURRENCY": "2",
    "HF_XET_DATA_MAX_CONCURRENT_FILE_DOWNLOADS": "1",
    "HF_XET_CLIENT_RETRY_MAX_ATTEMPTS": "3",
    "HF_XET_CLIENT_RETRY_BASE_DELAY": "1000ms",
    "HF_XET_CLIENT_RETRY_MAX_DURATION": "90s",
    "HF_XET_CLIENT_CONNECT_TIMEOUT": "20s",
    "HF_XET_CLIENT_READ_TIMEOUT": "60s",
    "HF_XET_RECONSTRUCTION_DOWNLOAD_BUFFER_SIZE": "128mb",
    "HF_XET_RECONSTRUCTION_DOWNLOAD_BUFFER_PERFILE_SIZE": "32mb",
    "HF_XET_RECONSTRUCTION_DOWNLOAD_BUFFER_LIMIT": "512mb",
    "HF_HUB_ETAG_TIMEOUT": "20",
    "HF_HUB_DOWNLOAD_TIMEOUT": "60",
}


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
                         encoding="utf-8")
    os.replace(temporary, path)


def _append_jsonl(path: Path, value: Any) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _asset_digest(path: Path, entry: dict[str, Any]) -> str:
    size = path.stat().st_size
    if size != entry["size_bytes"]:
        raise ContractError(f"asset size differs: {path.name}: {size} != {entry['size_bytes']}")
    if "sha256" in entry:
        return sha256_file(path)
    if "git_blob_sha1" in entry:
        digest = hashlib.sha1(b"blob " + str(size).encode("ascii") + b"\0")
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    raise ContractError("asset has no frozen content digest")


def verify_asset(path: Path, entry: dict[str, Any], *, require_plain: bool = True) -> dict[str, Any]:
    if not path.is_file() or (require_plain and path.is_symlink()):
        raise ContractError("verified asset must be a plain file")
    actual = _asset_digest(path, entry)
    kind = "sha256" if "sha256" in entry else "git_blob_sha1"
    if actual != entry[kind]:
        raise ContractError(f"asset {kind} differs: {path.name}")
    return {"size_bytes": path.stat().st_size, "digest_kind": kind, "digest": actual,
            "file_sha256": sha256_file(path)}


def _root_bytes(root: Path) -> int:
    if not root.exists():
        return 0
    return sum((Path(folder) / filename).lstat().st_size
               for folder, _, files in os.walk(root) for filename in files)


def _sample(process: subprocess.Popen[Any] | None, root: Path) -> dict[str, int]:
    import psutil

    rss = 0
    if process is not None and process.poll() is None:
        try:
            parent = psutil.Process(process.pid)
            for member in [parent, *parent.children(recursive=True)]:
                try:
                    rss += member.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return {"process_tree_rss_bytes": rss,
            "host_available_bytes": psutil.virtual_memory().available,
            "c_free_bytes": shutil.disk_usage("C:\\").free,
            "e_free_bytes": shutil.disk_usage("E:\\").free,
            "new_root_bytes": _root_bytes(root)}


def _resource_error(sample: dict[str, int]) -> str | None:
    if sample["process_tree_rss_bytes"] > MAX_PROCESS_TREE_RSS_BYTES:
        return "process_tree_rss_limit"
    if sample["host_available_bytes"] < MIN_RAM_BYTES:
        return "host_ram_floor"
    if sample["c_free_bytes"] < MIN_C_FREE_BYTES or sample["e_free_bytes"] < MIN_E_FREE_BYTES:
        return "disk_floor"
    if sample["new_root_bytes"] > MAX_NEW_ROOT_BYTES:
        return "new_root_byte_limit"
    return None


def _kill_tree(process: subprocess.Popen[Any]) -> None:
    import psutil

    try:
        parent = psutil.Process(process.pid)
        for child in reversed(parent.children(recursive=True)):
            try:
                child.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        parent.kill()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=15)


def _verified_prior_assets(manifest: dict[str, Any]) -> dict[tuple[str, str], Path]:
    seal_path = OLD_ROOT / "acquisition-seal.json"
    if sha256_file(seal_path) != OLD_SEAL_SHA256:
        raise ContractError("prior failed-arm seal bytes changed")
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    if seal.get("root_digest_sha256") != OLD_ROOT_DIGEST_SHA256:
        raise ContractError("prior failed-arm root digest changed")
    files = seal.get("files")
    if not isinstance(files, list) or len(files) != 20:
        raise ContractError("prior failed-arm inventory changed")
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != OLD_ROOT_DIGEST_SHA256:
        raise ContractError("prior failed-arm inventory digest differs")
    sealed: dict[str, str] = {}
    for file in files:
        relative = Path(file["path"])
        if relative.is_absolute() or ".." in relative.parts or relative.as_posix() in sealed:
            raise ContractError("unsafe or duplicate prior sealed path")
        original = OLD_ROOT / relative
        if (not original.is_file() or original.is_symlink()
                or original.stat().st_size != file["size_bytes"]
                or sha256_file(original) != file["sha256"]):
            raise ContractError(f"prior sealed file changed: {relative}")
        sealed[relative.as_posix()] = file["sha256"]
    receipts = [json.loads(line) for line in (OLD_ROOT / "acquisition.jsonl").read_text(
        encoding="utf-8").splitlines()]
    if (len(receipts) != 17 or sum(item["status"] == "verified" for item in receipts) != 16
            or receipts[-1]["status"] != "failed"):
        raise ContractError("prior failed-arm receipt sequence changed")
    expected = {(model["name"], entry["path"]): entry
                for model in manifest["models"]
                if model["name"] in manifest["profile"]["active_model_names"]
                for entry in model["files"]}
    reused = {}
    for item in receipts:
        if item["status"] != "verified":
            continue
        key = item["model"], item["filename"]
        if key in reused or key not in expected:
            raise ContractError("prior receipt repeats or changes a frozen asset")
        relative = Path("models-v2-pinned") / key[0] / key[1]
        if relative.as_posix() not in sealed:
            raise ContractError("prior verified asset is absent from sealed inventory")
        path = OLD_ROOT / relative
        verified = verify_asset(path, expected[key])
        if (item.get("expected_size_bytes") != verified["size_bytes"]
                or item.get("expected_digest") != verified["digest"]):
            raise ContractError("prior receipt and frozen asset disagree")
        reused[key] = path
    return reused


def _manifest() -> dict[str, Any]:
    manifest = json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))
    active = manifest["profile"]["active_model_names"]
    entries = [entry for model in manifest["models"] if model["name"] in active
               for entry in model["files"]]
    if (_manifest_digest(manifest) != MODEL_MANIFEST_SHA256 or len(active) != 9
            or len(entries) != EXPECTED_ACTIVE_FILES
            or sum(entry["size_bytes"] for entry in entries) != EXPECTED_ACTIVE_BYTES):
        raise ContractError("frozen TableMagic active model inventory changed")
    return manifest


def _worker_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    for key in ("HF_TOKEN", "HF_TOKEN_PATH", "HUGGING_FACE_HUB_TOKEN",
                "HUGGINGFACE_HUB_TOKEN"):
        env.pop(key, None)
    env.update(XET_ENV)
    env.update({"HF_HOME": str(root / "hf-home"),
                "HF_HUB_CACHE": str(root / "hub-cache"),
                "HF_XET_CACHE": str(root / "xet-cache")})
    return env


def _copy_with_guard(source: Path, target: Path, root: Path) -> None:
    with source.open("rb") as original, target.open("xb") as copied:
        for chunk in iter(lambda: original.read(4 * 1024 * 1024), b""):
            sample = _sample(None, root)
            if reason := _resource_error(sample):
                raise ContractError(f"acquisition copy guard: {reason}")
            if (sample["new_root_bytes"] + len(chunk) > MAX_NEW_ROOT_BYTES
                    or sample["c_free_bytes"] - len(chunk) < MIN_C_FREE_BYTES):
                raise ContractError("acquisition copy would exceed byte or disk floor")
            copied.write(chunk)
        copied.flush()
        os.fsync(copied.fileno())


def _asset_worker(args: argparse.Namespace) -> None:
    from huggingface_hub import file_download as hub_download
    from huggingface_hub import hf_hub_download

    if (importlib.metadata.version("huggingface_hub") != "2.2.0"
            or importlib.metadata.version("hf_xet") != "1.7.0"
            or hub_download.constants.HF_HUB_DISABLE_XET):
        raise ContractError("Hub/Xet runtime differs from frozen acquisition arm")
    marker = args.result.with_suffix(".xet-called")
    original_xet_get = hub_download.xet_get
    original_http_get = hub_download.http_get

    def marked_xet_get(*call_args: Any, **call_kwargs: Any) -> Any:
        marker.write_text("xet_get entered\n", encoding="utf-8")
        return original_xet_get(*call_args, **call_kwargs)

    def no_weight_http(*call_args: Any, **call_kwargs: Any) -> Any:
        if args.require_xet:
            raise ContractError("weight lacks Xet route; raw HTTP fallback forbidden")
        return original_http_get(*call_args, **call_kwargs)

    hub_download.xet_get = marked_xet_get
    hub_download.http_get = no_weight_http
    try:
        downloaded = hf_hub_download(
            repo_id=args.repo, filename=args.filename, revision=args.revision,
            cache_dir=str(args.root / "hub-cache"), token=False, etag_timeout=20,
            local_files_only=False, force_download=False,
            endpoint="https://huggingface.co",
        )
    finally:
        hub_download.xet_get = original_xet_get
        hub_download.http_get = original_http_get
    _write_json(args.result, {"path": downloaded, "xet_called": marker.exists(),
                              "hub_version": importlib.metadata.version("huggingface_hub"),
                              "xet_version": importlib.metadata.version("hf_xet")})


def _download_asset(root: Path, model: dict[str, Any], entry: dict[str, Any],
                    started_all: float) -> tuple[Path, dict[str, Any]]:
    index_name = model["name"] + "__" + entry["path"]
    child_result = root / "child-results" / (index_name + ".json")
    log_path = root / "logs" / (index_name + ".log")
    child_result.parent.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, str(Path(__file__).resolve()), "--asset-worker",
               "--root", str(root), "--repo", model["repo"], "--revision",
               model["revision"], "--filename", entry["path"],
               "--result", str(child_result)]
    if "sha256" in entry:
        command.append("--require-xet")
    started = time.monotonic()
    peak_rss = peak_root = 0
    min_ram = sys.maxsize
    reason = "finished"
    with log_path.open("wb") as log:
        process = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1],
                                   env=_worker_env(root), stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            while process.poll() is None:
                sample = _sample(process, root)
                peak_rss = max(peak_rss, sample["process_tree_rss_bytes"])
                peak_root = max(peak_root, sample["new_root_bytes"])
                min_ram = min(min_ram, sample["host_available_bytes"])
                _append_jsonl(root / "resource-samples.jsonl",
                              {"model": model["name"], "filename": entry["path"],
                               "elapsed_seconds": round(time.monotonic() - started, 3),
                               **sample})
                if time.monotonic() - started > MAX_ASSET_SECONDS:
                    reason = "asset_timeout"
                elif time.monotonic() - started_all > MAX_TOTAL_SECONDS:
                    reason = "total_timeout"
                else:
                    reason = _resource_error(sample) or "finished"
                if reason != "finished":
                    _kill_tree(process)
                    break
                time.sleep(2)
            exit_code = process.wait(timeout=15)
        finally:
            if process.poll() is None:
                _kill_tree(process)
    if reason == "finished" and exit_code != 0:
        reason = "child_exit_nonzero"
    result = {"stop_reason": reason, "exit_code": exit_code,
              "duration_seconds": round(time.monotonic() - started, 3),
              "peak_process_tree_rss_bytes": peak_rss, "peak_new_root_bytes": peak_root,
              "min_host_available_bytes": min_ram if min_ram != sys.maxsize else None,
              "log_sha256": sha256_file(log_path),
              "xet_called": child_result.with_suffix(".xet-called").is_file()}
    if child_result.is_file():
        child_status = json.loads(child_result.read_text(encoding="utf-8"))
        if child_status.get("status") == "failed":
            result["child_error_type"] = child_status.get("error_type")
    if reason != "finished" or exit_code != 0 or not child_result.is_file():
        raise AcquisitionFailure(result)
    child = child_status
    if child.get("hub_version") != "2.2.0" or child.get("xet_version") != "1.7.0":
        raise AcquisitionFailure({**result, "stop_reason": "child_runtime_mismatch"})
    downloaded = Path(child["path"])
    if (not downloaded.is_file() or not downloaded.resolve().is_relative_to(root.resolve())
            or child.get("xet_called") is not result["xet_called"]
            or ("sha256" in entry and not result["xet_called"])):
        raise AcquisitionFailure({**result, "stop_reason": "Xet_route_or_cache_path_invalid"})
    return downloaded, result


class AcquisitionFailure(RuntimeError):
    def __init__(self, result: dict[str, Any]):
        super().__init__(result["stop_reason"])
        self.result = result


def _seal(root: Path) -> dict[str, Any]:
    files = []
    for path in sorted(root.rglob("*")):
        if path.name == "acquisition-seal.json" or path.is_dir():
            continue
        if path.is_symlink():
            files.append({"path": path.relative_to(root).as_posix(),
                          "symlink_target": os.readlink(path)})
        elif path.is_file():
            files.append({"path": path.relative_to(root).as_posix(),
                          "size_bytes": path.stat().st_size, "sha256": sha256_file(path)})
    digest = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":"))
                            .encode("utf-8")).hexdigest()
    seal = {"files": files, "root_digest_sha256": digest}
    _write_json(root / "acquisition-seal.json", seal)
    return {"file_count": len(files), "root_digest_sha256": digest,
            "seal_file_sha256": sha256_file(root / "acquisition-seal.json")}


def run(root: Path, selection: Path, cohort: Path, corpus_root: Path,
        gold_path: Path) -> dict[str, Any]:
    if (root != ROOT or root.exists() or root.resolve().drive.upper() != "C:"
            or Path(sys.executable).resolve() != EXPECTED_PYTHON.resolve()):
        raise ContractError("fresh frozen C: acquisition root and pinned Paddle Python required")
    selected = verify_selection(selection, cohort, corpus_root)
    if sha256_file(gold_path) != GOLD_SHA256 or len(selected) != 12:
        raise ContractError("frozen TableMagic source/gold lock differs")
    gold = load_jsonl(gold_path, kind="gold")
    linked = [gold_linked_rows(gold[item["doc_id"]]) for item in selected]
    if sum(len(rows) for rows in linked) != 219 or sum(
        len(cell) for rows in linked for cell in rows.values()
    ) != 808:
        raise ContractError("frozen linked table denominator differs")
    runtime = verify_runtime(Path(sys.executable))
    if (runtime["core_versions"]["paddlex"] != "3.7.2"
            or importlib.metadata.version("huggingface_hub") != "2.2.0"
            or importlib.metadata.version("hf_xet") != "1.7.0"):
        raise ContractError("pinned Hub/Xet acquisition runtime differs")
    manifest = _manifest()
    reused = _verified_prior_assets(manifest)
    initial = _sample(None, root)
    if initial["host_available_bytes"] < MIN_INITIAL_RAM_BYTES or _resource_error(initial):
        raise ContractError("initial RAM, disk or byte-budget guard failed")
    root.mkdir(parents=True)
    started = time.monotonic()
    _write_json(root / "acquisition-lock.json", {
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "manifest_canonical_sha256": MODEL_MANIFEST_SHA256,
        "selection_sha256": sha256_file(selection), "cohort_sha256": sha256_file(cohort),
        "gold_sha256": GOLD_SHA256, "source_sha256": {item["doc_id"]: item["source_sha256"]
                                                for item in selected},
        "runtime": runtime, "hub_version": "2.2.0", "xet_version": "1.7.0",
        "prior_seal_sha256": OLD_SEAL_SHA256,
        "downloader_sha256": sha256_file(Path(__file__)),
        "xet_env": XET_ENV, "initial_resources": initial,
        "limits": {"max_asset_seconds": MAX_ASSET_SECONDS,
                   "max_total_seconds": MAX_TOTAL_SECONDS,
                   "max_process_tree_rss_bytes": MAX_PROCESS_TREE_RSS_BYTES,
                   "max_new_root_bytes": MAX_NEW_ROOT_BYTES,
                   "min_initial_ram_bytes": MIN_INITIAL_RAM_BYTES,
                   "min_ram_bytes": MIN_RAM_BYTES,
                   "min_c_free_bytes": MIN_C_FREE_BYTES,
                   "min_e_free_bytes": MIN_E_FREE_BYTES},
    })
    receipts = root / "acquisition.jsonl"
    summary: dict[str, Any] = {"status": "failed", "reason": None,
                               "verified_reused": 0, "verified_downloaded": 0,
                               "attempted_downloads": 0}
    try:
        for model in manifest["models"]:
            if model["name"] not in manifest["profile"]["active_model_names"]:
                continue
            folder = root / "models-v2-pinned" / model["name"]
            folder.mkdir(parents=True, exist_ok=True)
            for entry in model["files"]:
                key = model["name"], entry["path"]
                target = folder / entry["path"]
                if Path(entry["path"]).name != entry["path"] or target.exists():
                    raise ContractError("unsafe or duplicate model asset path")
                item: dict[str, Any] = {"model": model["name"], "repo": model["repo"],
                                        "revision": model["revision"],
                                        "filename": entry["path"],
                                        "expected_size_bytes": entry["size_bytes"],
                                        "status": "failed"}
                try:
                    if key in reused:
                        _copy_with_guard(reused[key], target, root)
                        item["route"] = "prior_verified_reuse"
                    else:
                        item["route"] = "pinned_hub_xet"
                        summary["attempted_downloads"] += 1
                        downloaded, transfer = _download_asset(root, model, entry, started)
                        item["transfer"] = transfer
                        verify_asset(downloaded, entry, require_plain=False)
                        _copy_with_guard(downloaded, target, root)
                    item["verified"] = verify_asset(target, entry)
                    item["status"] = "verified"
                    if key in reused:
                        summary["verified_reused"] += 1
                    else:
                        summary["verified_downloaded"] += 1
                    item["source_sha256"] = sha256_file(reused[key]) if key in reused else None
                except AcquisitionFailure as exc:
                    item["transfer"] = exc.result
                    item["error"] = str(exc)
                    raise
                except Exception as exc:
                    item["error"] = f"{type(exc).__name__}: {exc}"
                    raise
                finally:
                    item["resources_after"] = _sample(None, root)
                    _append_jsonl(receipts, item)
                if time.monotonic() - started > MAX_TOTAL_SECONDS:
                    raise ContractError("total acquisition time cap exceeded")
                if reason := _resource_error(_sample(None, root)):
                    raise ContractError(f"acquisition resource guard: {reason}")
        summary["verified_model_inventory"] = verify_models(root / "models-v2-pinned")
        summary["status"] = "verified"
    except Exception as exc:  # noqa: BLE001 - seal all transfer failures, including library errors
        summary["reason"] = f"{type(exc).__name__}: {exc}"
    summary["elapsed_seconds"] = round(time.monotonic() - started, 3)
    summary["final_resources"] = _sample(None, root)
    _write_json(root / "acquisition-summary.json", summary)
    summary["seal"] = _seal(root)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquire", action="store_true", help="explicitly enable model transfer")
    parser.add_argument("--asset-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--root", type=Path, default=ROOT)
    for name in ("selection", "cohort", "corpus-root", "gold"):
        parser.add_argument("--" + name, type=Path)
    for name in ("repo", "revision", "filename"):
        parser.add_argument("--" + name)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--require-xet", action="store_true")
    args = parser.parse_args()
    if args.asset_worker:
        if not all((args.repo, args.revision, args.filename, args.result)):
            parser.error("asset worker requires repo/revision/filename/result")
        try:
            _asset_worker(args)
        except Exception as exc:  # noqa: BLE001 - keep signed provider URLs out of logs
            _write_json(args.result, {"status": "failed", "error_type": type(exc).__name__,
                                      "xet_called": args.result.with_suffix(".xet-called").exists()})
            print(f"asset worker failed: {type(exc).__name__}", file=sys.stderr)
            sys.exit(1)
        return
    if not args.acquire:
        parser.error("frozen second arm is inactive; explicit --acquire required after resource release")
    if not all((args.selection, args.cohort, args.corpus_root, args.gold)):
        parser.error("source and gold lock paths are required")
    result = run(args.root, args.selection, args.cohort, args.corpus_root, args.gold)
    if result["status"] != "verified":
        sys.exit(1)


if __name__ == "__main__":
    main()
