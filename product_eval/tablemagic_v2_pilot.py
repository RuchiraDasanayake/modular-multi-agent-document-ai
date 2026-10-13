"""Guarded CPU PP-TableMagic v2 parser pilot on the frozen VRDU ad-buy 12.

Model acquisition is external and must finish before `--run`. The worker sees
only one source PDF and local models; gold is opened after all conversions.
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
from product_eval.tablemagic_v2_table_diagnostic import score_saved, table_strings

MODEL_MANIFEST = Path(__file__).parent / "fixtures" / "tablemagic_v2_models.json"
MODEL_MANIFEST_SHA256 = "85199082278e21b5d46a3c3d6db5f1d417b7a222964d4a48838d44c9bd53d335"
RUNTIME_LOCK = Path(__file__).parent / "fixtures" / "paddleocr_vl_16_runtime.json"
RUNTIME_LOCK_SHA256 = "43661458b1d981f046b616903c2190457b7abfb6545bf357eae67f1a69653b79"
WORKER = Path(__file__).parent / "tablemagic_v2_worker.py"
SCORER = Path(__file__).parent / "tablemagic_v2_table_diagnostic.py"
WORKER_SHA256 = "db3cb931e84e93f9d9f6e7c46516d923495e400323db213437a3048578aa1d2c"
SCORER_SHA256 = "bd9cbfdb33fd5b8e18cfb846aa8df845efc48596c44dd56fba481de06c87dcec"
OUTPUT_DIR = Path(r"E:\DocAI-Benchmarks\tablemagic-v2-adbuy12-xet2-no-onednn")
NO_ONEDNN_ENV = {"PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT": "False"}
MAX_DOCUMENTS = 12
MAX_PAGES = 20
MAX_FILE_BYTES = 2_000_000
STARTUP_TIMEOUT_SECONDS = 180
SMOKE_TIMEOUT_SECONDS = 600
DOCUMENT_TIMEOUT_SECONDS = 480
TOTAL_TIMEOUT_SECONDS = 3600
MAX_PROCESS_TREE_RSS_BYTES = 8 * 1024**3
MIN_INITIAL_AVAILABLE_BYTES = 6 * 1024**3
MIN_AVAILABLE_BYTES = 3 * 1024**3
MIN_C_FREE_BYTES = 4 * 1024**3
MIN_E_FREE_BYTES = 2 * 1024**3


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
                         encoding="utf-8")
    os.replace(temporary, path)


def _git_blob_sha1(path: Path) -> str:
    content = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(content)).encode("ascii") + b"\0" + content).hexdigest()


def _normalized_source_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _manifest_digest(manifest: dict[str, Any]) -> str:
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def verify_models(models_root: Path, manifest_path: Path = MODEL_MANIFEST) -> dict[str, Any]:
    """Require exact active model directory inventories and pinned file bytes."""
    if (not models_root.is_dir() or models_root.is_symlink()
            or models_root.resolve().drive.upper() != "C:"):
        raise ContractError("active TableMagic models must be local non-symlink C: directories")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if _manifest_digest(manifest) != MODEL_MANIFEST_SHA256:
        raise ContractError("TableMagic model manifest differs from frozen content")
    profile = manifest.get("profile", {})
    expected_profile = {"use_doc_orientation_classify": False, "use_doc_unwarping": False,
                        "use_layout_detection": True, "use_ocr_model": True,
                        "use_table_orientation_classify": True,
                        "device": "cpu", "engine": "paddle_static"}
    if (manifest.get("format_version") != 1
            or any(profile.get(key) != value for key, value in expected_profile.items())
            or manifest.get("paddlex_version") != "3.7.2"):
        raise ContractError("TableMagic model/profile manifest differs from frozen protocol")
    names = profile.get("active_model_names")
    models = manifest.get("models")
    if (not isinstance(names, list) or len(names) != 9 or len(set(names)) != 9
            or not isinstance(models, list) or len(models) != 10
            or {item.get("name") for item in models} != set(names) | {"UVDoc"}):
        raise ContractError("TableMagic default/active model inventory differs")
    if any(path.is_symlink() for path in models_root.iterdir()):
        raise ContractError("model root contains symlink")
    checked = 0
    for model in models:
        if model["name"] not in names:
            continue
        if (model.get("repo") != f"PaddlePaddle/{model['name']}"
                or model.get("license") != "apache-2.0"
                or not isinstance(model.get("revision"), str)
                or len(model["revision"]) != 40):
            raise ContractError("model provenance differs from official lock")
        folder = models_root / model["name"]
        if not folder.is_dir() or folder.is_symlink():
            raise ContractError(f"active model directory missing: {model['name']}")
        files = model.get("files")
        if not isinstance(files, list) or not files:
            raise ContractError("model lock contains no files")
        expected_names = {entry["path"] for entry in files}
        actual_names = {entry.name for entry in folder.iterdir() if entry.is_file()}
        if (len(expected_names) != len(files) or actual_names != expected_names
                or any(entry.is_symlink() or entry.is_dir() for entry in folder.iterdir())):
            raise ContractError(f"active model file inventory differs: {model['name']}")
        for entry in files:
            path = folder / entry["path"]
            if (not path.is_file() or path.is_symlink()
                    or path.stat().st_size != entry["size_bytes"]):
                raise ContractError(f"model size differs: {model['name']}/{entry['path']}")
            if "sha256" in entry:
                expected, actual = entry["sha256"], sha256_file(path)
            elif "git_blob_sha1" in entry:
                expected, actual = entry["git_blob_sha1"], _git_blob_sha1(path)
            else:
                raise ContractError("model file has no content digest")
            if actual != expected:
                raise ContractError(f"model digest differs: {model['name']}/{entry['path']}")
            checked += 1
    return {"manifest_canonical_sha256": _manifest_digest(manifest),
            "manifest_file_sha256": sha256_file(manifest_path),
            "active_model_names": names, "verified_model_files": checked}


def verify_runtime(worker_python: Path) -> dict[str, Any]:
    if not worker_python.is_file() or not RUNTIME_LOCK.is_file():
        raise ContractError("isolated Paddle Python or runtime lock missing")
    if sha256_file(RUNTIME_LOCK) != RUNTIME_LOCK_SHA256:
        raise ContractError("Paddle runtime lock differs from frozen bytes")
    lock = json.loads(RUNTIME_LOCK.read_text(encoding="utf-8"))
    script = ("import importlib.metadata as m,json,sys;"
              "print(json.dumps({'python':sys.version.split()[0],"
              "'paddlepaddle':m.version('paddlepaddle'),"
              "'paddleocr':m.version('paddleocr'),'paddlex':m.version('paddlex')}))")
    versions = json.loads(subprocess.run([str(worker_python), "-c", script],
                                      capture_output=True, text=True, check=True,
                                      timeout=20).stdout)
    if versions != lock.get("core_versions"):
        raise ContractError("isolated Paddle runtime versions differ")
    freeze = subprocess.run([str(worker_python), "-m", "pip", "freeze", "--all"],
                            capture_output=True, text=True, check=True, timeout=30).stdout
    if hashlib.sha256(freeze.encode("utf-8")).hexdigest() != lock.get("pip_freeze_sha256"):
        raise ContractError("isolated Paddle package closure differs")
    package_script = ("import importlib.metadata as m,json;"
                      "print(json.dumps({d.metadata['Name'].lower():d.version "
                      "for d in m.distributions()},sort_keys=True))")
    packages = json.loads(subprocess.run([str(worker_python), "-c", package_script],
                                     capture_output=True, text=True, check=True,
                                     timeout=30).stdout)
    if packages != lock.get("package_versions"):
        raise ContractError("installed Paddle packages differ from runtime lock")
    subprocess.run([str(worker_python), "-m", "pip", "check"], capture_output=True,
                   text=True, check=True, timeout=30)
    config_path = worker_python.parents[1] / "Lib" / "site-packages" / "paddlex" / "configs" / "pipelines" / "table_recognition_v2.yaml"
    manifest = json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))
    if sha256_file(config_path) != manifest["installed_default_config_sha256"]:
        raise ContractError("installed PaddleX default table config differs")
    backend_script = (
        "import json;"
        "from paddleocr._common_args import parse_common_args,prepare_common_init_args;"
        "from paddlex.inference.models.runners.paddle_static.config.pp_option "
        "import get_default_run_mode;"
        "from paddlex.utils.flags import ENABLE_MKLDNN_BYDEFAULT;"
        "args=parse_common_args({'device':'cpu','engine':'paddle_static',"
        "'enable_mkldnn':False,'cpu_threads':4},default_enable_hpi=None);"
        "cfg=prepare_common_init_args(None,args);"
        "print(json.dumps({'wrapper_run_mode':cfg['engine_config']['run_mode'],"
        "'default_run_mode':get_default_run_mode('PP-OCRv4_server_det','cpu'),"
        "'mkldnn_default_enabled':ENABLE_MKLDNN_BYDEFAULT}))"
    )
    backend_env = os.environ.copy()
    backend_env.update(NO_ONEDNN_ENV)
    backend_result = subprocess.run(
        [str(worker_python), "-c", backend_script], env=backend_env,
        capture_output=True, text=True, check=True, timeout=30,
    )
    backend = json.loads(backend_result.stdout.strip().splitlines()[-1])
    if backend != {"wrapper_run_mode": "paddle", "default_run_mode": "paddle",
                   "mkldnn_default_enabled": False}:
        raise ContractError("isolated Paddle CPU backend does not disable oneDNN")
    return {"runtime_lock_sha256": sha256_file(RUNTIME_LOCK),
            "core_versions": versions, "pip_freeze_sha256": lock["pip_freeze_sha256"],
            "package_count": len(packages), "default_config_sha256": sha256_file(config_path),
            "cpu_backend": backend}


def _sample(process: subprocess.Popen[Any] | None) -> dict[str, int]:
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
            "e_free_bytes": shutil.disk_usage("E:\\").free}


def _resource_error(sample: dict[str, int]) -> str | None:
    if sample["process_tree_rss_bytes"] > MAX_PROCESS_TREE_RSS_BYTES:
        return "process_tree_rss_limit"
    if sample["host_available_bytes"] < MIN_AVAILABLE_BYTES:
        return "host_ram_floor"
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


def _run_worker(worker_python: Path, source: Path, source_sha256: str,
                models_root: Path, folder: Path, resource_log: Path,
                *, smoke: bool) -> dict[str, Any]:
    folder.mkdir(parents=True, exist_ok=False)
    raw = folder / "raw"
    env = os.environ.copy()
    env.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                "PADDLE_PDX_MODEL_SOURCE": "huggingface",
                "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "True",
                "OMP_NUM_THREADS": "4", "MKL_NUM_THREADS": "4",
                "OPENBLAS_NUM_THREADS": "4", "FLAGS_cpu_num_threads": "4"})
    env.update(NO_ONEDNN_ENV)
    command = [str(worker_python), str(WORKER), "--source", str(source),
               "--models-root", str(models_root), "--output-dir", str(raw)]
    started = time.perf_counter()
    peak_rss = 0
    min_ram = sys.maxsize
    reason = "finished"
    with (folder / "worker.log").open("wb") as log:
        worker = subprocess.Popen(command, cwd=Path(__file__).resolve().parents[1],
                                  env=env, stdout=log, stderr=subprocess.STDOUT,
                                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            while worker.poll() is None:
                sample = _sample(worker)
                elapsed = time.perf_counter() - started
                with resource_log.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps({"source_sha256": source_sha256,
                                             "elapsed_seconds": round(elapsed, 3),
                                             **sample}) + "\n")
                peak_rss = max(peak_rss, sample["process_tree_rss_bytes"])
                min_ram = min(min_ram, sample["host_available_bytes"])
                if elapsed > STARTUP_TIMEOUT_SECONDS and not (raw / "startup.json").is_file():
                    reason = "model_startup_timeout"
                elif elapsed > (SMOKE_TIMEOUT_SECONDS if smoke else DOCUMENT_TIMEOUT_SECONDS):
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
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "peak_process_tree_rss_bytes": peak_rss,
            "min_host_available_bytes": min_ram if min_ram != sys.maxsize else None}


def run(*, selection: Path, cohort: Path, corpus_root: Path, gold: Path,
        models_root: Path, worker_python: Path, output_dir: Path) -> dict[str, Any]:
    repo = Path(__file__).resolve().parents[1]
    if (output_dir.exists() or output_dir.resolve().is_relative_to(repo)
            or output_dir.resolve() != OUTPUT_DIR.resolve()):
        raise ContractError("amended TableMagic output must be the new locked E: directory")
    if (_normalized_source_sha256(WORKER) != WORKER_SHA256
            or _normalized_source_sha256(SCORER) != SCORER_SHA256):
        raise ContractError("TableMagic worker or scorer differs from frozen source")
    selected = verify_selection(selection, cohort, corpus_root)
    if len(selected) != MAX_DOCUMENTS or sha256_file(gold) != GOLD_SHA256:
        raise ContractError("frozen ad-buy selection or gold hash differs")
    runtime = verify_runtime(worker_python)
    model_receipt = verify_models(models_root)
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
    initial = _sample(None)
    if initial["host_available_bytes"] < MIN_INITIAL_AVAILABLE_BYTES:
        raise ContractError("initial host RAM below six-GiB startup floor")
    if reason := _resource_error(initial):
        raise ContractError(f"initial resource guard: {reason}")
    output_dir.mkdir(parents=True)
    started = time.perf_counter()
    lock = {"started_utc": datetime.now(timezone.utc).isoformat(),
            "selection_sha256": sha256_file(selection), "cohort_sha256": sha256_file(cohort),
            "gold_sha256": GOLD_SHA256,
            "source_sha256": {item["doc_id"]: item["source_sha256"] for item in selected},
            "pages_by_doc": pages_by_doc, "runtime": runtime, "models": model_receipt,
            "worker_normalized_sha256": WORKER_SHA256,
            "scorer_normalized_sha256": SCORER_SHA256,
            "runner_sha256": sha256_file(Path(__file__)), "initial_resources": initial,
            "cpu_backend": {"paddleocr_enable_mkldnn": False,
                            "paddlex_enable_mkldnn_bydefault": NO_ONEDNN_ENV[
                                "PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT"],
                            "run_mode": "paddle"},
            "limits": {"max_file_bytes": MAX_FILE_BYTES, "max_pages": MAX_PAGES,
                       "startup_timeout_seconds": STARTUP_TIMEOUT_SECONDS,
                       "smoke_timeout_seconds": SMOKE_TIMEOUT_SECONDS,
                       "document_timeout_seconds": DOCUMENT_TIMEOUT_SECONDS,
                       "total_timeout_seconds": TOTAL_TIMEOUT_SECONDS,
                       "max_process_tree_rss_bytes": MAX_PROCESS_TREE_RSS_BYTES,
                       "min_initial_available_bytes": MIN_INITIAL_AVAILABLE_BYTES,
                       "min_available_bytes": MIN_AVAILABLE_BYTES,
                       "min_c_free_bytes": MIN_C_FREE_BYTES,
                       "min_e_free_bytes": MIN_E_FREE_BYTES}}
    _write_json(output_dir / "run-lock.json", lock)
    summary: dict[str, Any] = {"status": "failed", "reason": None,
                               "conversions_attempted": 0}
    resource_log = output_dir / "resource-samples.jsonl"
    for index, item in enumerate(selected):
        if time.perf_counter() - started > TOTAL_TIMEOUT_SECONDS:
            summary["reason"] = "total_timeout"
            break
        source = source_path(corpus_root, item["source_id"])
        folder = output_dir / "docs" / item["doc_id"]
        outcome = _run_worker(worker_python, source, item["source_sha256"], models_root, folder,
                              resource_log, smoke=index == 0)
        summary["conversions_attempted"] += 1
        raw = folder / "raw"
        expected = [raw / f"page-{page:02d}.json"
                    for page in range(pages_by_doc[item["doc_id"]])]
        rasters = [raw / f"page-{page:02d}.png"
                   for page in range(pages_by_doc[item["doc_id"]])]
        geometry = [raw / f"geometry-{page:02d}.json"
                    for page in range(pages_by_doc[item["doc_id"]])]
        complete = (outcome["exit_code"] == 0 and outcome["stop_reason"] == "finished"
                    and (raw / "startup.json").is_file()
                    and set(raw.glob("page-*.json")) == set(expected)
                    and set(raw.glob("page-*.png")) == set(rasters)
                    and set(raw.glob("geometry-*.json")) == set(geometry)
                    and all(path.is_file() for path in [*expected, *rasters, *geometry]))
        receipt = {"doc_id": item["doc_id"], "source_sha256": item["source_sha256"],
                   "source_size_bytes": item["source_size_bytes"],
                   "page_count": pages_by_doc[item["doc_id"]], **outcome,
                   "status": "success" if complete else "failed", "pages": [],
                   "worker_log_sha256": sha256_file(folder / "worker.log"),
                   "raw_json_outputs": [{"file": path.name, "sha256": sha256_file(path)}
                                        for path in sorted(raw.glob("*.json"))],
                   "raw_raster_outputs": [{"file": path.name, "sha256": sha256_file(path)}
                                          for path in sorted(raw.glob("*.png"))]}
        if complete:
            receipt["pages"] = [{"page_index": page, "file": f"raw/page-{page:02d}.json",
                                 "sha256": sha256_file(expected[page]),
                                 "raster_file": f"raw/page-{page:02d}.png",
                                 "raster_sha256": sha256_file(rasters[page]),
                                 "geometry_file": f"raw/geometry-{page:02d}.json",
                                 "geometry_sha256": sha256_file(geometry[page])}
                                for page in range(len(expected))]
        _write_json(folder / "conversion.json", receipt)
        if index == 0:
            try:
                if not complete:
                    raise ContractError("smoke conversion failed")
                pages = [json.loads(path.read_text(encoding="utf-8")) for path in expected]
                geometries = [json.loads(path.read_text(encoding="utf-8")) for path in geometry]
                _, _, stats = table_strings(pages, geometries)
                receipt["smoke_parser"] = stats
                _write_json(folder / "conversion.json", receipt)
                if (stats["valid_html_tables"] < 1 or stats["valid_cell_boxes"] < 1
                        or stats["valid_table_regions"] < 1 or stats["valid_ocr_boxes"] < 1):
                    raise ContractError("smoke lacks full table HTML or source boxes")
            except (ContractError, OSError, ValueError, TypeError, KeyError) as exc:
                summary["reason"] = f"smoke_no_go: {type(exc).__name__}: {exc}"
                break
        if receipt["status"] != "success" and outcome["stop_reason"] != "finished":
            summary["reason"] = f"conversion_stopped: {item['doc_id']}: {outcome['stop_reason']}"
            break
    else:
        summary["status"] = "complete"
    summary["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    try:
        summary["scoring"] = score_saved(output_dir, gold, selected)
    except (ContractError, OSError, ValueError, TypeError, KeyError) as exc:
        summary["status"] = "failed"
        summary["reason"] = f"scoring_integrity_failure: {type(exc).__name__}: {exc}"
        _write_json(output_dir / "run.json", summary)
        raise
    _write_json(output_dir / "run.json", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="explicitly enable local inference")
    for name in ("selection", "cohort", "corpus-root", "gold", "models-root",
                 "worker-python", "output-dir"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if not args.run:
        parser.error("prepared pilot is inactive; pass --run only after resource release")
    summary = run(selection=args.selection, cohort=args.cohort,
                  corpus_root=args.corpus_root, gold=args.gold,
                  models_root=args.models_root, worker_python=args.worker_python,
                  output_dir=args.output_dir)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
