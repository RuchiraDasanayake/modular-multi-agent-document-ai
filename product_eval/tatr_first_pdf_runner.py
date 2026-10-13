"""Guarded supervisor for exactly the first frozen VRDU ad-buy TATR PDF.

This research entrypoint never reads gold. It verifies the frozen selection,
starts one CPU worker, watches resource limits, and stops after one PDF with a
pending manual overlay verdict. It does not advance to the other eleven.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from product_eval.docling_table_diagnostic import source_path, verify_selection
from product_eval.tatr_asset_preflight import sha256_file

GIB = 1024**3
PREFLIGHT_RAM_BYTES = 6 * GIB
RUN_RAM_BYTES = 3 * GIB
HOST_DISK_BYTES = 4 * GIB
DATA_DISK_BYTES = 4 * GIB
MAX_TREE_RSS_BYTES = 8 * GIB
STARTUP_SECONDS = 180
CONVERSION_SECONDS = 360
FIRST_WORKER_SECONDS = 600
FULL_RUN_SECONDS = 3600
POLL_SECONDS = 0.5


def _write_new_json(path: Path, value: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False)
        stream.write("\n")


def resource_violation(
    *, available_ram: int, host_disk_free: int, data_disk_free: int,
    tree_rss: int, before_worker: bool,
) -> str | None:
    if available_ram < (PREFLIGHT_RAM_BYTES if before_worker else RUN_RAM_BYTES):
        return "host_ram_floor"
    if host_disk_free < HOST_DISK_BYTES:
        return "host_disk_floor"
    if data_disk_free < DATA_DISK_BYTES:
        return "data_disk_floor"
    if not before_worker and tree_rss > MAX_TREE_RSS_BYTES:
        return "process_tree_rss_ceiling"
    return None


def _resource_sample(
    process: subprocess.Popen[bytes] | None, host_root: Path, data_root: Path,
) -> dict[str, int]:
    import psutil

    tree_rss = 0
    if process is not None:
        try:
            root = psutil.Process(process.pid)
            tree = [root, *root.children(recursive=True)]
        except psutil.NoSuchProcess:
            tree = []
        for member in tree:
            try:
                tree_rss += member.memory_info().rss
            except psutil.NoSuchProcess:
                continue
    return {
        "available_ram": psutil.virtual_memory().available,
        "host_disk_free": psutil.disk_usage(str(host_root)).free,
        "data_disk_free": psutil.disk_usage(str(data_root)).free,
        "tree_rss": tree_rss,
    }


def _stop_process_tree(process: subprocess.Popen[bytes]) -> None:
    import psutil

    try:
        root = psutil.Process(process.pid)
        children = root.children(recursive=True)
        for member in reversed(children):
            try:
                member.terminate()
            except psutil.Error:
                pass
        try:
            root.terminate()
        except psutil.Error:
            pass
        alive = psutil.wait_procs([*children, root], timeout=5)[1]
        for member in alive:
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


def _validate_output_path(
    output_dir: Path, repo_root: Path, corpus_root: Path,
    asset_root: Path, data_root: Path,
) -> None:
    if not output_dir.is_absolute():
        raise ValueError("first-PDF output path must be absolute")
    parent = output_dir.parent.resolve(strict=True)
    destination = (parent / output_dir.name).resolve()
    if destination.exists():
        raise ValueError("fresh first-PDF output directory already exists")
    if destination != output_dir.absolute():
        raise ValueError("first-PDF output path must not use a link or relative traversal")
    if not destination.is_relative_to(data_root.resolve(strict=True)):
        raise ValueError("first-PDF output must be on the declared data disk")
    if any(destination.is_relative_to(root.resolve(strict=True)) for root in
           (repo_root, corpus_root, asset_root)):
        raise ValueError("first-PDF output overlaps repository, corpus or model assets")


def _verify_worker_result(
    output_dir: Path, source_sha256: str, expected_runtime_lock: Path,
) -> dict[str, Any]:
    startup = json.loads((output_dir / "startup.ready.json").read_text(encoding="utf-8"))
    if (startup.get("status") != "models_loaded_offline"
            or startup.get("pdf_opened") is not False
            or startup.get("runtime_lock_sha256") != sha256_file(expected_runtime_lock)
            or startup.get("runtime_manifest_sha256")
            != sha256_file(output_dir / "runtime_manifest.json")):
        raise ValueError("worker startup/runtime provenance is invalid")
    runtime_manifest = json.loads(
        (output_dir / "runtime_manifest.json").read_text(encoding="utf-8")
    )
    expected_manifest = json.loads(expected_runtime_lock.read_text(encoding="utf-8"))
    if runtime_manifest != expected_manifest:
        raise ValueError("worker runtime manifest differs from committed lock")
    if (output_dir / "worker_failure.json").exists():
        raise ValueError("worker wrote a failure receipt")
    receipt = json.loads((output_dir / "worker_receipt.json").read_text(encoding="utf-8"))
    if (receipt.get("status") != "first_pdf_needs_visual_review"
            or receipt.get("source_sha256") != source_sha256
            or receipt.get("gold_opened") is not False
            or receipt.get("manual_source_pixel_verdict") != "pending"
            or receipt.get("can_continue_other_11") is not False
            or receipt.get("table_count", 0) < 1
            or receipt.get("nonempty_cell_count", 0) < 1):
        raise ValueError("worker result did not meet the frozen first-PDF gate")
    for name, key in (
        ("parsed_document.json", "parsed_document_sha256"),
        ("raw_pages.json", "raw_pages_sha256"),
        ("first_nonempty_source_overlay.png", "overlay_sha256"),
    ):
        if sha256_file(output_dir / name) != receipt.get(key):
            raise ValueError(f"worker artifact changed: {name}")
    parsed = json.loads((output_dir / "parsed_document.json").read_text(encoding="utf-8"))
    if parsed.get("contract_version") != 2 or parsed.get("source_sha256") != source_sha256:
        raise ValueError("worker did not emit the source-bound ParsedDocument v2")
    return receipt


def run_first_pdf(
    *, selection: Path, cohort: Path, corpus_root: Path,
    asset_root: Path, cpu_python: Path, tokenizers_sdist: Path,
    torchvision_wheel: Path, expected_runtime_lock: Path,
    output_dir: Path, host_disk_root: Path, data_disk_root: Path,
) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    _validate_output_path(output_dir, repo_root, corpus_root, asset_root, data_disk_root)
    output_dir.mkdir(exist_ok=False)
    started = time.monotonic()
    source: Path | None = None
    first_hash: str | None = None
    process: subprocess.Popen[bytes] | None = None
    peak_tree_rss = 0
    minimum_available = 2**63 - 1
    reason: str | None = None
    exit_code: int | None = None
    try:
        committed_lock = repo_root / "product_eval" / "fixtures" / "tatr_cpu_runtime_lock_v1.json"
        if expected_runtime_lock.resolve(strict=True) != committed_lock.resolve(strict=True):
            raise ValueError("TATR CPU runtime lock must be the committed fixture")
        selected = verify_selection(selection, cohort, corpus_root)
        first = selected[0]
        first_hash = first["source_sha256"]
        source = source_path(corpus_root, first["source_id"]).resolve(strict=True)
        if source.stat().st_size > 2_000_000:
            raise ValueError("first PDF exceeds frozen 2 MB limit")
        if not cpu_python.is_file() or not expected_runtime_lock.is_file():
            raise ValueError("pinned CPU interpreter or runtime lock missing")
        cpu_python = cpu_python.resolve(strict=True)
        asset_root = asset_root.resolve(strict=True)
        tokenizers_sdist = tokenizers_sdist.resolve(strict=True)
        torchvision_wheel = torchvision_wheel.resolve(strict=True)
        expected_runtime_lock = expected_runtime_lock.resolve(strict=True)
        before = _resource_sample(None, host_disk_root, data_disk_root)
        reason = resource_violation(**before, before_worker=True)
        if reason:
            raise RuntimeError(f"first-PDF preflight resource violation: {reason}")
        command = [
            str(cpu_python), "-B", "-m", "product_eval.tatr_first_pdf_worker",
            "--source", str(source), "--source-sha256", first["source_sha256"],
            "--asset-root", str(asset_root),
            "--tokenizers-sdist", str(tokenizers_sdist),
            "--torchvision-wheel", str(torchvision_wheel),
            "--expected-runtime-lock", str(expected_runtime_lock),
            "--output-dir", str(output_dir),
        ]
        environment = {
            **os.environ,
            "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1", "OMP_NUM_THREADS": "4",
            "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": str(repo_root),
        }
        with (output_dir / "worker.log").open("xb") as log:
            process = subprocess.Popen(
                command, cwd=repo_root, env=environment,
                stdout=log, stderr=subprocess.STDOUT,
            )
            ready_at: float | None = None
            while True:
                now = time.monotonic()
                sample = _resource_sample(process, host_disk_root, data_disk_root)
                peak_tree_rss = max(peak_tree_rss, sample["tree_rss"])
                minimum_available = min(minimum_available, sample["available_ram"])
                reason = resource_violation(**sample, before_worker=False)
                if reason:
                    break
                if ready_at is None and (output_dir / "startup.ready.json").is_file():
                    ready_at = now
                if ready_at is None and now - started > STARTUP_SECONDS:
                    reason = "startup_timeout"
                    break
                if ready_at is not None and now - ready_at > CONVERSION_SECONDS:
                    reason = "conversion_timeout"
                    break
                if now - started > min(FIRST_WORKER_SECONDS, FULL_RUN_SECONDS):
                    reason = "first_worker_timeout"
                    break
                exit_code = process.poll()
                if exit_code is not None:
                    if ready_at is None:
                        reason = "worker_exited_before_ready"
                    elif exit_code != 0:
                        reason = "worker_failed"
                    break
                time.sleep(POLL_SECONDS)
            if reason and process.poll() is None:
                _stop_process_tree(process)
            if exit_code is None:
                exit_code = process.poll()
        if reason:
            raise RuntimeError(f"first-PDF worker stopped: {reason}")
        result = _verify_worker_result(
            output_dir, first["source_sha256"], expected_runtime_lock,
        )
        status = result["status"]
        receipt = {
            "status": status, "first_document_id": first["doc_id"],
            "source_sha256": first["source_sha256"],
            "other_selected_documents": "11 unattempted",
            "manual_overlay_verdict": "pending", "can_continue_other_11": False,
            "gold_opened": False, "worker_exit_code": exit_code,
            "worker_wall_seconds": round(time.monotonic() - started, 3),
            "peak_tree_rss_bytes": peak_tree_rss,
            "minimum_host_available_bytes": minimum_available,
            "worker_log_sha256": sha256_file(output_dir / "worker.log"),
            "worker_receipt_sha256": sha256_file(output_dir / "worker_receipt.json"),
        }
    except Exception as exc:  # noqa: BLE001 - every worker/preflight failure needs a receipt
        receipt = {
            "status": "failed", "reason": reason or type(exc).__name__,
            "message": str(exc), "source_sha256": first_hash,
            "other_selected_documents": "11 unattempted",
            "gold_opened": False, "can_continue_other_11": False,
            "worker_exit_code": exit_code,
            "worker_wall_seconds": round(time.monotonic() - started, 3),
            "peak_tree_rss_bytes": peak_tree_rss,
            "minimum_host_available_bytes": None if minimum_available == 2**63 - 1 else minimum_available,
            "worker_log_sha256": sha256_file(output_dir / "worker.log")
            if (output_dir / "worker.log").is_file() else None,
        }
    finally:
        if process is not None and process.poll() is None:
            _stop_process_tree(process)
    _write_new_json(output_dir / "first_pdf_receipt.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument("--cpu-python", type=Path, required=True)
    parser.add_argument("--tokenizers-sdist", type=Path, required=True)
    parser.add_argument("--torchvision-wheel", type=Path, required=True)
    parser.add_argument("--expected-runtime-lock", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--host-disk-root", type=Path, required=True)
    parser.add_argument("--data-disk-root", type=Path, required=True)
    args = parser.parse_args()
    receipt = run_first_pdf(**vars(args))
    print(json.dumps({"receipt": str(args.output_dir / "first_pdf_receipt.json"),
                      "status": receipt["status"]}))
    if receipt["status"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
