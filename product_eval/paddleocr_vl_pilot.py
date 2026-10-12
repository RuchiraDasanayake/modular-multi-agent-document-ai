"""Guarded, parser-only PaddleOCR-VL 1.6 pilot on the frozen ad-buy slice.

The Paddle worker sees only source PDF bytes. Gold is opened after conversion.
All model weights, logs and raw page JSON remain outside the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from product_eval.contracts import ContractError
from product_eval.docling_table_diagnostic import (
    GOLD_SHA256,
    sha256_file,
    source_path,
    verify_selection,
)
from product_eval.paddleocr_vl_table_diagnostic import score_saved, table_strings

MODEL_REVISION = "511b09642bb324401f15f97cc23bc67e8f0a291d"
LAYOUT_REVISION = "241f8bdfc77a7c7bee915a5057aaee58c235a8d3"
SERVER_SHA256 = "4fdc1a67a8c1333429ea82186087a77db202fb588c2442dcdfa442b2182d0306"
MODEL_LOCK = Path(__file__).parent / "fixtures" / "paddleocr_vl_16_models.json"
RUNTIME_LOCK = Path(__file__).parent / "fixtures" / "paddleocr_vl_16_runtime.json"
WORKER = Path(__file__).parent / "paddleocr_vl_worker.py"
SCORER = Path(__file__).parent / "paddleocr_vl_table_diagnostic.py"
MAX_FILE_BYTES = 2_000_000
MAX_PAGES = 20
MAX_DOCUMENTS = 12
DOCUMENT_TIMEOUT_SECONDS = 600
TOTAL_TIMEOUT_SECONDS = 3600
SERVER_LOAD_TIMEOUT_SECONDS = 180
MAX_PROCESS_TREE_RSS_BYTES = 8 * 1024**3
MIN_AVAILABLE_MEMORY_BYTES = 2 * 1024**3
MIN_GPU_FREE_MIB = 1024
MIN_C_FREE_BYTES = 4 * 1024**3
MIN_E_FREE_BYTES = 2 * 1024**3
SMOKE_MAX_RSS_BYTES = 6 * 1024**3
SMOKE_MIN_AVAILABLE_BYTES = 3 * 1024**3
SMOKE_MIN_GPU_FREE_MIB = 1536
SERVER_PORT = 18128
SERVER_CONTEXT_TOKENS = 8192


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                         encoding="utf-8")
    os.replace(temporary, path)


def _gpu_free_mib() -> int | None:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True, timeout=5,
        )
        return int(result.stdout.strip().splitlines()[0])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


def _resource_sample(processes: list[subprocess.Popen[Any]]) -> dict[str, int | None]:
    import psutil

    rss = 0
    for process in processes:
        if process.poll() is not None:
            continue
        try:
            parent = psutil.Process(process.pid)
            for member in [parent, *parent.children(recursive=True)]:
                try:
                    rss += member.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return {
        "process_tree_rss_bytes": rss,
        "host_available_bytes": psutil.virtual_memory().available,
        "gpu_free_mib": _gpu_free_mib(),
        "c_free_bytes": shutil.disk_usage("C:\\").free,
        "e_free_bytes": shutil.disk_usage("E:\\").free,
    }


def _resource_error(sample: dict[str, int | None]) -> str | None:
    if sample["process_tree_rss_bytes"] > MAX_PROCESS_TREE_RSS_BYTES:
        return "process_tree_rss_limit"
    if sample["host_available_bytes"] < MIN_AVAILABLE_MEMORY_BYTES:
        return "host_ram_floor"
    if sample["gpu_free_mib"] is None or sample["gpu_free_mib"] < MIN_GPU_FREE_MIB:
        return "gpu_vram_floor"
    if sample["c_free_bytes"] < MIN_C_FREE_BYTES or sample["e_free_bytes"] < MIN_E_FREE_BYTES:
        return "disk_floor"
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


def _verify_assets(model_dir: Path, layout_dir: Path, server_exe: Path,
                   worker_python: Path) -> dict[str, Any]:
    if (not MODEL_LOCK.is_file() or not RUNTIME_LOCK.is_file()
            or not server_exe.is_file() or not worker_python.is_file()):
        raise ContractError("pinned model/runtime lock, server or isolated Python is missing")
    lock = json.loads(MODEL_LOCK.read_text(encoding="utf-8"))
    if (lock.get("model_revision") != MODEL_REVISION
            or lock.get("layout_revision") != LAYOUT_REVISION):
        raise ContractError("Paddle model revision differs from frozen lock")
    for group, root in (("vlm", model_dir), ("layout", layout_dir)):
        for item in lock[group]:
            path = root / item["name"]
            if (not path.is_file() or path.stat().st_size != item["size_bytes"]
                    or sha256_file(path) != item["sha256"]):
                raise ContractError(f"pinned Paddle model bytes differ: {path}")
    if sha256_file(server_exe) != SERVER_SHA256:
        raise ContractError("pinned llama.cpp executable hash differs")
    version = subprocess.run([str(server_exe), "--version"], capture_output=True,
                             text=True, check=True, timeout=15)
    if "build 11425" not in version.stdout + version.stderr:
        raise ContractError("pinned llama.cpp build differs")
    version_script = """\
import importlib.metadata as m, json, sys
print(json.dumps({'python': sys.version.split()[0],
                  'paddlepaddle': m.version('paddlepaddle'),
                  'paddleocr': m.version('paddleocr'),
                  'paddlex': m.version('paddlex')}))
"""
    runtime = subprocess.run([str(worker_python), "-c", version_script],
                             capture_output=True, text=True, check=True, timeout=20)
    versions = json.loads(runtime.stdout)
    if ((versions["paddlepaddle"], versions["paddleocr"], versions["paddlex"])
            != ("3.3.0", "3.7.0", "3.7.2") or not versions["python"].startswith("3.11.")):
        raise ContractError("isolated Paddle runtime version differs")
    freeze = subprocess.run([str(worker_python), "-m", "pip", "freeze", "--all"],
                            capture_output=True, text=True, check=True, timeout=30).stdout
    freeze_sha256 = hashlib.sha256(freeze.encode("utf-8")).hexdigest()
    runtime_lock = json.loads(RUNTIME_LOCK.read_text(encoding="utf-8"))
    if (runtime_lock.get("pip_freeze_sha256") != freeze_sha256
            or runtime_lock.get("core_versions") != versions):
        raise ContractError("isolated Paddle package closure differs from frozen runtime lock")
    package_script = ("import importlib.metadata as m,json;"
                      "print(json.dumps({d.metadata['Name'].lower():d.version "
                      "for d in m.distributions()},sort_keys=True))")
    installed_packages = json.loads(subprocess.run(
        [str(worker_python), "-c", package_script], capture_output=True, text=True,
        check=True, timeout=30,
    ).stdout)
    if installed_packages != runtime_lock.get("package_versions"):
        raise ContractError("installed package versions differ from frozen runtime lock")
    environment_dir = worker_python.parents[2]
    pip_report = environment_dir / "pip-install-report.json"
    if (not pip_report.is_file()
            or sha256_file(pip_report) != runtime_lock.get("pip_install_report_sha256")):
        raise ContractError("isolated Paddle package receipt differs")
    for item in runtime_lock["core_wheels"]:
        path = environment_dir / item["name"] if item["name"].startswith("paddlepaddle-") else (
            environment_dir / "wheelhouse" / item["name"])
        if (not path.is_file() or path.stat().st_size != item["size_bytes"]
                or sha256_file(path) != item["sha256"]):
            raise ContractError(f"pinned Paddle package wheel differs: {item['name']}")
    package_check = subprocess.run([str(worker_python), "-m", "pip", "check"],
                                   capture_output=True, text=True, check=True, timeout=30)
    return {"model_revision": MODEL_REVISION, "layout_revision": LAYOUT_REVISION,
            "model_lock_sha256": sha256_file(MODEL_LOCK),
            "model_files": lock, "server_sha256": SERVER_SHA256,
            "server_version": (version.stdout + version.stderr).strip(),
            "versions": versions,
            "pip_freeze_sha256": freeze_sha256,
            "runtime_lock_sha256": sha256_file(RUNTIME_LOCK),
            "pip_install_report_sha256": runtime_lock["pip_install_report_sha256"],
            "package_count": len(installed_packages), "pip_check": package_check.stdout.strip(),
            "worker_sha256": sha256_file(WORKER), "scorer_sha256": sha256_file(SCORER),
            "harness_sha256": sha256_file(Path(__file__))}


def _health() -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{SERVER_PORT}/health", timeout=2) as response:
            payload = json.load(response)
        return isinstance(payload, dict) and payload.get("status") == "ok"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False


def _verify_server(model_file: Path) -> dict[str, Any]:
    with urllib.request.urlopen(f"http://127.0.0.1:{SERVER_PORT}/props", timeout=5) as response:
        props = json.load(response)
    if (not isinstance(props, dict)
            or "11425" not in str(props.get("build_info", ""))
            or props.get("total_slots") != 1
            or props.get("default_generation_settings", {}).get("n_ctx") != SERVER_CONTEXT_TOKENS
            or props.get("modalities", {}).get("vision") is not True
            or Path(str(props.get("model_path", ""))).resolve() != model_file.resolve()):
        raise ContractError("local llama.cpp model/context/vision/slot differs from frozen protocol")
    return {"build_info": props["build_info"], "context_tokens": SERVER_CONTEXT_TOKENS,
            "slots": props["total_slots"], "vision": True}


def _wait_for_server(server: subprocess.Popen[Any], started: float,
                     sample_log: Path) -> tuple[bool, str | None]:
    while time.perf_counter() - started < SERVER_LOAD_TIMEOUT_SECONDS:
        sample = _resource_sample([server])
        with sample_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"phase": "load", "elapsed_seconds": time.perf_counter()-started,
                                     **sample}) + "\n")
        reason = _resource_error(sample)
        if reason:
            return False, reason
        if server.poll() is not None:
            return False, f"server_exit_{server.returncode}"
        if _health():
            return True, None
        time.sleep(2)
    return False, "server_load_timeout"


def _run_worker(worker_python: Path, source: Path, layout_dir: Path,
                folder: Path, server: subprocess.Popen[Any],
                sample_log: Path) -> dict[str, Any]:
    raw = folder / "raw"
    folder.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                "OMP_NUM_THREADS": "4", "MKL_NUM_THREADS": "4", "OPENBLAS_NUM_THREADS": "4",
                "FLAGS_cpu_num_threads": "4"})
    command = [str(worker_python), str(WORKER), "--source", str(source),
               "--layout-dir", str(layout_dir), "--server-url",
               f"http://127.0.0.1:{SERVER_PORT}/v1", "--output-dir", str(raw)]
    peak_rss = 0
    min_ram = sys.maxsize
    min_gpu = sys.maxsize
    started = time.perf_counter()
    reason = "finished"
    with (folder / "worker.log").open("wb") as log:
        worker = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1], env=env,
                                  stdout=log, stderr=subprocess.STDOUT,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            while worker.poll() is None:
                sample = _resource_sample([server, worker])
                with sample_log.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps({"phase": "convert", "source": source.name,
                                             "elapsed_seconds": time.perf_counter()-started,
                                             **sample}) + "\n")
                peak_rss = max(peak_rss, int(sample["process_tree_rss_bytes"] or 0))
                min_ram = min(min_ram, int(sample["host_available_bytes"] or 0))
                if sample["gpu_free_mib"] is not None:
                    min_gpu = min(min_gpu, int(sample["gpu_free_mib"]))
                if server.poll() is not None:
                    reason = "server_exited"
                elif time.perf_counter() - started > DOCUMENT_TIMEOUT_SECONDS:
                    reason = "document_timeout"
                else:
                    reason = _resource_error(sample) or "finished"
                if reason != "finished":
                    _kill_tree(worker)
                    break
                time.sleep(1)
            code = worker.wait(timeout=15)
        finally:
            if worker.poll() is None:
                _kill_tree(worker)
    return {"stop_reason": reason, "exit_code": code,
            "duration_ms": round((time.perf_counter()-started)*1000, 3),
            "peak_process_tree_rss_bytes": peak_rss,
            "min_host_available_bytes": min_ram if min_ram != sys.maxsize else None,
            "min_gpu_free_mib": min_gpu if min_gpu != sys.maxsize else None}


def run(*, selection: Path, cohort: Path, corpus_root: Path, gold: Path,
        model_dir: Path, layout_dir: Path, server_exe: Path, worker_python: Path,
        output_dir: Path) -> dict[str, Any]:
    if output_dir.exists() or output_dir.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
        raise ContractError("raw output directory must be new and outside Git")
    selected = verify_selection(selection, cohort, corpus_root)
    if len(selected) != MAX_DOCUMENTS or sha256_file(gold) != GOLD_SHA256:
        raise ContractError("frozen source set or gold hash differs")
    runtime = _verify_assets(model_dir, layout_dir, server_exe, worker_python)
    import pypdfium2

    pages_by_doc = {}
    for item in selected:
        source = source_path(corpus_root, item["source_id"])
        if source.stat().st_size > MAX_FILE_BYTES:
            raise ContractError("selected PDF exceeds frozen file-size cap")
        pdf = pypdfium2.PdfDocument(source)
        try:
            count = len(pdf)
        finally:
            pdf.close()
        if not 1 <= count <= MAX_PAGES:
            raise ContractError("selected PDF exceeds frozen page cap")
        pages_by_doc[item["doc_id"]] = count
    initial = _resource_sample([])
    if reason := _resource_error(initial):
        raise ContractError(f"initial resource guard: {reason}")
    output_dir.mkdir(parents=True)
    started = time.perf_counter()
    lock = {"started_utc": datetime.now(timezone.utc).isoformat(),
            "selection_sha256": sha256_file(selection), "cohort_sha256": sha256_file(cohort),
            "gold_sha256": GOLD_SHA256, "runtime": runtime, "pages_by_doc": pages_by_doc,
            "source_sha256": {item["doc_id"]: item["source_sha256"] for item in selected},
            "initial_resources": initial,
            "limits": {"max_file_bytes": MAX_FILE_BYTES, "max_pages": MAX_PAGES,
                       "document_timeout_seconds": DOCUMENT_TIMEOUT_SECONDS,
                       "total_timeout_seconds": TOTAL_TIMEOUT_SECONDS,
                       "server_load_timeout_seconds": SERVER_LOAD_TIMEOUT_SECONDS,
                       "max_process_tree_rss_bytes": MAX_PROCESS_TREE_RSS_BYTES,
                       "min_available_memory_bytes": MIN_AVAILABLE_MEMORY_BYTES,
                       "min_gpu_free_mib": MIN_GPU_FREE_MIB,
                       "min_c_free_bytes": MIN_C_FREE_BYTES, "min_e_free_bytes": MIN_E_FREE_BYTES,
                       "smoke_max_rss_bytes": SMOKE_MAX_RSS_BYTES,
                       "smoke_min_available_bytes": SMOKE_MIN_AVAILABLE_BYTES,
                       "smoke_min_gpu_free_mib": SMOKE_MIN_GPU_FREE_MIB}}
    _write_json(output_dir / "run-lock.json", lock)
    sample_log = output_dir / "resource-samples.jsonl"
    server_command = [str(server_exe), "--model", str(model_dir / "PaddleOCR-VL-1.6-GGUF.gguf"),
                      "--mmproj", str(model_dir / "PaddleOCR-VL-1.6-GGUF-mmproj.gguf"),
                      "--host", "127.0.0.1", "--port", str(SERVER_PORT),
                      "--ctx-size", str(SERVER_CONTEXT_TOKENS), "--n-gpu-layers", "99",
                      "--parallel", "1", "--threads", "4", "--temp", "0"]
    summary: dict[str, Any] = {"status": "failed", "reason": None, "conversions_attempted": 0}
    with (output_dir / "server.log").open("wb") as log:
        server = subprocess.Popen(server_command, cwd=output_dir, stdout=log,
                                  stderr=subprocess.STDOUT,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            ready, reason = _wait_for_server(server, started, sample_log)
            if not ready:
                summary["reason"] = reason
            else:
                try:
                    summary["server"] = _verify_server(model_dir / "PaddleOCR-VL-1.6-GGUF.gguf")
                except (ContractError, OSError, ValueError, TypeError, KeyError) as exc:
                    summary["reason"] = f"server_preflight: {type(exc).__name__}: {exc}"
                    ready = False
            if ready:
                for index, item in enumerate(selected):
                    if time.perf_counter() - started > TOTAL_TIMEOUT_SECONDS:
                        summary["reason"] = "total_timeout"
                        break
                    source = source_path(corpus_root, item["source_id"])
                    folder = output_dir / "docs" / item["doc_id"]
                    outcome = _run_worker(worker_python, source, layout_dir, folder, server, sample_log)
                    summary["conversions_attempted"] += 1
                    receipt = {"doc_id": item["doc_id"], "source_sha256": item["source_sha256"],
                               "source_size_bytes": item["source_size_bytes"],
                               "page_count": pages_by_doc[item["doc_id"]], **outcome}
                    raw = folder / "raw"
                    saved = [raw / f"page-{page:02d}.json"
                             for page in range(receipt["page_count"])]
                    premerge = [raw / f"premerge-page-{page:02d}.json"
                                for page in range(receipt["page_count"])]
                    exact_pages = (set(raw.glob("page-*.json")) == set(saved)
                                   and set(raw.glob("premerge-page-*.json")) == set(premerge))
                    if (outcome["exit_code"] == 0 and outcome["stop_reason"] == "finished"
                            and exact_pages and all(path.is_file() for path in [*premerge, *saved])):
                        receipt["page_outputs"] = [{"file": path.name, "sha256": sha256_file(path)}
                                                   for path in saved]
                        receipt["premerge_outputs"] = [{"file": path.name, "sha256": sha256_file(path)}
                                                       for path in premerge]
                        for path in [*premerge, *saved]:
                            os.replace(path, folder / path.name)
                        receipt["status"] = "success"
                    else:
                        receipt["page_outputs"] = []
                        receipt["premerge_outputs"] = []
                        receipt["status"] = "failed"
                    _write_json(folder / "conversion.json", receipt)
                    if index == 0:
                        try:
                            if receipt["status"] != "success":
                                raise ContractError("smoke conversion failed")
                            pages = [json.loads((folder / item["file"]).read_text(encoding="utf-8"))
                                     for item in receipt["page_outputs"]]
                            _cells, _rows, stats = table_strings(pages)
                            receipt["smoke_parser"] = stats
                            if stats["valid_tables"] < 1:
                                raise ContractError("smoke produced no structured table HTML")
                            if (outcome["peak_process_tree_rss_bytes"] > SMOKE_MAX_RSS_BYTES
                                    or outcome["min_host_available_bytes"] < SMOKE_MIN_AVAILABLE_BYTES
                                    or outcome["min_gpu_free_mib"] is None
                                    or outcome["min_gpu_free_mib"] < SMOKE_MIN_GPU_FREE_MIB):
                                raise ContractError("smoke exceeded promotion resource thresholds")
                            _write_json(folder / "conversion.json", receipt)
                        except (ContractError, OSError, ValueError, TypeError, KeyError) as exc:
                            summary["reason"] = f"smoke_no_go: {type(exc).__name__}: {exc}"
                            break
                    if receipt["status"] != "success" and outcome["stop_reason"] != "finished":
                        summary["reason"] = f"conversion_stopped: {item['doc_id']}: {outcome['stop_reason']}"
                        break
                else:
                    summary["status"] = "complete"
        finally:
            _kill_tree(server)
    summary["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    summary["scoring"] = score_saved(output_dir, gold, selected)
    summary["premerge_scoring"] = score_saved(output_dir, gold, selected, page_variant="premerge")
    _write_json(output_dir / "run.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("selection", "cohort", "corpus-root", "gold", "model-dir", "layout-dir",
                 "server-exe", "worker-python", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    summary = run(selection=args.selection, cohort=args.cohort, corpus_root=args.corpus_root,
                  gold=args.gold, model_dir=args.model_dir, layout_dir=args.layout_dir,
                  server_exe=args.server_exe, worker_python=args.worker_python,
                  output_dir=args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
