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

from idpo.product_auto.parsed_document import (
    Box,
    ParsedDocument,
    SourceAnchor,
    SourceUnit,
    Table,
    TableCell,
)
from product_eval.docling_table_diagnostic import source_path, verify_selection
from product_eval.tatr_asset_preflight import sha256_file
from product_eval.tatr_process_env import environment_sha256, isolated_worker_env

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
HOST_VOLUME = "C:"
DATA_VOLUME = "I:"
V2_OUTPUT_DIR = Path(r"I:\DocAI-Benchmarks\tatr-adbuy12-v2")
V1_FAILURE_RECEIPT = Path(r"I:\DocAI-Benchmarks\tatr-adbuy12-v1\first_pdf_receipt.json")
V1_FAILURE_RECEIPT_SHA256 = "3e068faa08cd52208674d1772db1075285653e7dd01f896129ca1b952a78bdc5"


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


def _frozen_volumes(
    repo_root: Path, cpu_python: Path, ocr_python: Path, output_dir: Path,
    host_disk_root: Path, data_disk_root: Path,
) -> dict[str, Any]:
    """Bind the resource samples to this frozen C:/I: research host."""
    host = Path(f"{HOST_VOLUME}\\").resolve(strict=True)
    data = Path(f"{DATA_VOLUME}\\").resolve(strict=True)
    if (repo_root.drive.upper() != HOST_VOLUME
            or cpu_python.drive.upper() != DATA_VOLUME
            or ocr_python.drive.upper() != DATA_VOLUME
            or output_dir.drive.upper() != DATA_VOLUME
            or host_disk_root.resolve(strict=True) != host
            or data_disk_root.resolve(strict=True) != data):
        raise ValueError("trial paths differ from frozen C:/I: volume profile")
    return {
        "host_root": host, "data_root": data,
        "host_volume_id": os.stat(host).st_dev,
        "data_volume_id": os.stat(data).st_dev,
    }


def _code_provenance(repo_root: Path) -> dict[str, Any]:
    status = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain"],
        capture_output=True, text=True, check=True, timeout=20,
    )
    if status.stdout.strip():
        raise ValueError("first-PDF trial requires a clean Git checkout")
    head = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True, timeout=20,
    ).stdout.strip()
    roots = (repo_root / "product_eval", repo_root / "idpo" / "product_auto")
    paths = [repo_root / "idpo" / "__init__.py"]
    for root in roots:
        paths.extend(root.rglob("*.py"))
    names = sorted(path.relative_to(repo_root).as_posix() for path in paths)
    return {"git_commit": head,
            "source_sha256": {name: sha256_file(repo_root / name) for name in names}}


def _verify_trial_gate(
    gate_path: Path, *, code_provenance: dict[str, Any],
    selection: Path, cohort: Path, cpu_lock: Path, ocr_lock: Path,
) -> dict[str, Any]:
    gate = json.loads(gate_path.read_text(encoding="utf-8"))
    required = {
        "version": 2,
        "scope": "one_first_pdf_research_geometry_fallback_v2",
        "document_inference_permitted": True,
        "max_documents": 1,
        "gold_access_permitted": False,
        "output_directory": V2_OUTPUT_DIR.as_posix(),
        "prior_failure_receipt_sha256": V1_FAILURE_RECEIPT_SHA256,
        "selection_sha256": sha256_file(selection),
        "cohort_sha256": sha256_file(cohort),
        "cpu_runtime_lock_sha256": sha256_file(cpu_lock),
        "ocr_runtime_lock_sha256": sha256_file(ocr_lock),
        "code_source_sha256": code_provenance["source_sha256"],
    }
    if not isinstance(gate, dict) or gate != required:
        raise ValueError("first-PDF research inference gate differs from committed inputs")
    return {"gate_sha256": sha256_file(gate_path), **gate}


def _verified_anchor(value: Any, unit_id: str) -> SourceAnchor:
    if not isinstance(value, dict) or value.get("unit_id") != unit_id:
        raise ValueError("table anchor is missing or references another page")
    raw = value.get("raw_box")
    display = value.get("display_box")
    if not isinstance(raw, dict) or not isinstance(display, dict):
        raise TypeError("table anchor lacks raw and rendered source boxes")
    raw_box = Box(**raw)
    display_box = Box(**display)
    if raw_box.space != "pdf_points_bottom_left" or display_box.space != "normalized_top_left":
        raise ValueError("table anchor uses an unexpected coordinate frame")
    if any(value.get(key) is not None for key in ("text_span", "quote", "native_locator")):
        raise ValueError("PDF table anchor contains an unsupported text locator")
    return SourceAnchor(unit_id=unit_id, raw_box=raw_box, display_box=display_box)


def _verify_content_artifacts(output_dir: Path, receipt: dict[str, Any],
                              source_sha256: str) -> None:
    from PIL import Image

    try:
        parsed = json.loads((output_dir / "parsed_document.json").read_text(encoding="utf-8"))
        raw_pages = json.loads((output_dir / "raw_pages.json").read_text(encoding="utf-8"))
        legend = json.loads((output_dir / "first_nonempty_source_overlay_legend.json")
                            .read_text(encoding="utf-8"))
        if (parsed.get("contract_version") != 2
                or parsed.get("source_sha256") != source_sha256
                or parsed.get("source_format") != "pdf"
                or parsed.get("parser_version") != "research-word-route-first-pdf-v3"
                or not isinstance(raw_pages, list)):
            raise ValueError("worker did not emit source-bound PDF parser artifacts")
        unit_data = parsed["units"]
        table_data = parsed["tables"]
        if (not isinstance(unit_data, list) or not isinstance(table_data, list)
                or not 1 <= len(unit_data) <= 20
                or len(raw_pages) != len(unit_data)
                or receipt.get("page_count") != len(unit_data)):
            raise ValueError("parser page count differs from worker receipt")
        units: list[SourceUnit] = []
        for index, (item, detail) in enumerate(zip(unit_data, raw_pages, strict=True)):
            unit = SourceUnit(**item)
            if (unit.unit_id != f"page-{index + 1}" or unit.ordinal != index
                    or unit.kind != "pdf_page" or not unit.text
                    or unit.width is not None or unit.height is not None
                    or not isinstance(detail, dict)
                    or detail.get("page_number") != index + 1
                    or detail.get("pdf_page_size_frame") != "cropbox_after_rotation"
                    or detail.get("pdf_rotation_degrees") not in (0, 90, 180, 270)
                    or detail.get("word_route") not in ("pdfium_native", "ocr_word")
                    or detail.get("native_route_rejected") not in
                    (None, "unprojectable_native_character")
                    or (detail.get("native_route_rejected") is not None
                        and detail.get("word_route") != "ocr_word")
                    or not isinstance(detail.get("tables"), list)):
                raise ValueError("parser page metadata has an inconsistent coordinate frame")
            size = detail.get("rendered_size_pixels")
            if (not isinstance(size, list) or len(size) != 2
                    or any(type(value) is not int or value <= 0 for value in size)
                    or size[0] * size[1] > 35_000_000):
                raise ValueError("parser page has invalid rendered dimensions")
            units.append(unit)

        tables: list[Table] = []
        cell_count = 0
        nonempty_count = 0
        for item in table_data:
            table_id = item["table_id"]
            if not isinstance(table_id, str) or not isinstance(item.get("cells"), list):
                raise TypeError("parser table is malformed")
            page_number = int(table_id.split("-t", 1)[0].removeprefix("p"))
            if not 1 <= page_number <= len(units):
                raise ValueError("parser table refers to an absent page")
            unit_id = f"page-{page_number}"
            anchors = item.get("anchors")
            if not isinstance(anchors, list) or len(anchors) != 1:
                raise ValueError("parser table lacks one source-page anchor")
            table_anchor = _verified_anchor(anchors[0], unit_id)
            raw_details = [detail for detail in raw_pages[page_number - 1]["tables"]
                           if detail.get("table_id") == table_id]
            if len(raw_details) != 1 or len(raw_details[0].get("cells", [])) != len(item["cells"]):
                raise ValueError("parser table differs from raw source detail")
            cells: list[TableCell] = []
            for cell_data, raw_cell in zip(item["cells"], raw_details[0]["cells"], strict=True):
                if (not isinstance(cell_data, dict) or not isinstance(raw_cell, dict)
                        or any(cell_data.get(key) != raw_cell.get(key)
                               for key in ("row", "column", "row_span", "column_span", "text"))):
                    raise ValueError("parser cell differs from raw source detail")
                anchors = cell_data.get("anchors")
                if not isinstance(anchors, list) or len(anchors) != 1:
                    raise ValueError("parser cell lacks one source-page anchor")
                cell_anchor = _verified_anchor(anchors[0], unit_id)
                outer = table_anchor.display_box
                inner = cell_anchor.display_box
                if (inner.x0 < outer.x0 - 1e-6 or inner.y0 < outer.y0 - 1e-6
                        or inner.x1 > outer.x1 + 1e-6 or inner.y1 > outer.y1 + 1e-6):
                    raise ValueError("parser cell lies outside its table anchor")
                cells.append(TableCell(
                    cell_data["row"], cell_data["column"], cell_data["text"],
                    cell_data["row_span"], cell_data["column_span"],
                    anchors=(cell_anchor,),
                ))
                cell_count += 1
                nonempty_count += bool(cell_data["text"].strip())
            tables.append(Table(table_id, tuple(cells), anchors=(table_anchor,)))
        ParsedDocument(source_sha256, "pdf", parsed["parser_id"],
                       parsed["parser_version"], tuple(units), tuple(tables),
                       parser_config_sha256=parsed.get("parser_config_sha256"))
        if (not tables or not nonempty_count or receipt.get("table_count") != len(tables)
                or receipt.get("cell_count") != cell_count
                or receipt.get("nonempty_cell_count") != nonempty_count
                or sum(len(page["tables"]) for page in raw_pages) != len(tables)):
            raise ValueError("worker counts disagree with parsed source tables")
        first = next(table for table in tables if any(cell.text.strip() for cell in table.cells))
        page_number = int(first.table_id.split("-t", 1)[0].removeprefix("p"))
        expected_size = tuple(raw_pages[page_number - 1]["rendered_size_pixels"])
        with Image.open(output_dir / "first_nonempty_source_overlay.png") as overlay:
            if overlay.format != "PNG" or overlay.size != expected_size:
                raise ValueError("source overlay is not the expected rendered PNG")
            overlay.verify()
        if (legend.get("source_sha256") != source_sha256
                or legend.get("page_number") != page_number
                or legend.get("table_id") != first.table_id
                or not isinstance(legend.get("cells"), list)
                or len(legend["cells"]) != len(first.cells)):
            raise ValueError("source overlay legend differs from parsed table")
        for entry, cell in zip(legend["cells"], first.cells, strict=True):
            if (entry.get("label") != f"{first.table_id}:r{cell.row}c{cell.column}"
                    or entry.get("text") != cell.text
                    or entry.get("display_box") != cell.anchors[0].display_box.__dict__):
                raise ValueError("source overlay legend has a mismatched cell")
    except (KeyError, TypeError, IndexError, AttributeError, OverflowError, OSError) as exc:
        raise ValueError("worker parser artifact is malformed") from exc


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
        ("first_nonempty_source_overlay_legend.json", "overlay_legend_sha256"),
    ):
        if sha256_file(output_dir / name) != receipt.get(key):
            raise ValueError(f"worker artifact changed: {name}")
    _verify_content_artifacts(output_dir, receipt, source_sha256)
    return receipt


def run_first_pdf(
    *, selection: Path, cohort: Path, corpus_root: Path,
    asset_root: Path, cpu_python: Path, tokenizers_sdist: Path,
    torchvision_wheel: Path, expected_runtime_lock: Path,
    ocr_python: Path, ocr_runtime_root: Path, ocr_wheelhouse: Path,
    ocr_notices_root: Path,
    trial_gate: Path,
    output_dir: Path, host_disk_root: Path, data_disk_root: Path,
) -> dict[str, Any]:
    repo_root = Path(__file__).resolve().parents[1]
    if output_dir.absolute() != V2_OUTPUT_DIR:
        raise ValueError("second first-PDF output must use the frozen v2 directory")
    volumes = _frozen_volumes(repo_root, cpu_python, ocr_python, output_dir,
                              host_disk_root, data_disk_root)
    _validate_output_path(output_dir, repo_root, corpus_root, asset_root,
                          volumes["data_root"])
    output_dir.mkdir(exist_ok=False)
    started = time.monotonic()
    source: Path | None = None
    first_hash: str | None = None
    process: subprocess.Popen[bytes] | None = None
    peak_tree_rss = 0
    minimum_available = 2**63 - 1
    reason: str | None = None
    exit_code: int | None = None
    code_provenance: dict[str, Any] | None = None
    gate_provenance: dict[str, Any] | None = None
    try:
        code_provenance = _code_provenance(repo_root)
        committed_lock = repo_root / "product_eval" / "fixtures" / "tatr_cpu_runtime_lock_v1.json"
        committed_gate = repo_root / "product_eval" / "fixtures" / "tatr_first_pdf_research_gate_v2.json"
        if expected_runtime_lock.resolve(strict=True) != committed_lock.resolve(strict=True):
            raise ValueError("TATR CPU runtime lock must be the committed fixture")
        if trial_gate.resolve(strict=True) != committed_gate.resolve(strict=True):
            raise ValueError("first-PDF trial gate must be the committed fixture")
        if sha256_file(V1_FAILURE_RECEIPT) != V1_FAILURE_RECEIPT_SHA256:
            raise ValueError("immutable first-PDF v1 failure receipt changed")
        from product_eval.tatr_ocr_word_source_free import LOCK_PATH as OCR_LOCK_PATH

        gate_provenance = _verify_trial_gate(
            trial_gate, code_provenance=code_provenance,
            selection=selection, cohort=cohort,
            cpu_lock=expected_runtime_lock, ocr_lock=OCR_LOCK_PATH,
        )
        selected = verify_selection(selection, cohort, corpus_root)
        first = selected[0]
        first_hash = first["source_sha256"]
        source = source_path(corpus_root, first["source_id"]).resolve(strict=True)
        if source.stat().st_size > 2_000_000:
            raise ValueError("first PDF exceeds frozen 2 MB limit")
        if not cpu_python.is_file() or not expected_runtime_lock.is_file():
            raise ValueError("pinned CPU interpreter or runtime lock missing")
        if (not ocr_python.is_file() or not ocr_runtime_root.is_dir()
                or not ocr_wheelhouse.is_dir() or not ocr_notices_root.is_dir()):
            raise ValueError("pinned OCR interpreter, wheelhouse or notices missing")
        cpu_python = cpu_python.resolve(strict=True)
        asset_root = asset_root.resolve(strict=True)
        tokenizers_sdist = tokenizers_sdist.resolve(strict=True)
        torchvision_wheel = torchvision_wheel.resolve(strict=True)
        expected_runtime_lock = expected_runtime_lock.resolve(strict=True)
        ocr_python = ocr_python.resolve(strict=True)
        ocr_runtime_root = ocr_runtime_root.resolve(strict=True)
        ocr_wheelhouse = ocr_wheelhouse.resolve(strict=True)
        ocr_notices_root = ocr_notices_root.resolve(strict=True)
        if ocr_python.parent.parent != ocr_runtime_root:
            raise ValueError("OCR Python executable is outside pinned runtime")
        before = _resource_sample(None, volumes["host_root"], volumes["data_root"])
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
            "--ocr-python", str(ocr_python),
            "--ocr-runtime-root", str(ocr_runtime_root),
            "--ocr-wheelhouse", str(ocr_wheelhouse),
            "--ocr-notices-root", str(ocr_notices_root),
            "--output-dir", str(output_dir),
        ]
        environment = isolated_worker_env(cpu_python, repo_root)
        worker_env_sha256 = environment_sha256(environment)
        with (output_dir / "worker.log").open("xb") as log:
            process = subprocess.Popen(
                command, cwd=repo_root, env=environment,
                stdout=log, stderr=subprocess.STDOUT,
            )
            ready_at: float | None = None
            while True:
                now = time.monotonic()
                sample = _resource_sample(process, volumes["host_root"], volumes["data_root"])
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
        if _code_provenance(repo_root) != code_provenance:
            raise ValueError("first-PDF runner code changed during the worker run")
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
            "worker_env_keys": sorted(environment),
            "worker_env_sha256": worker_env_sha256,
            "code_provenance": code_provenance,
            "trial_gate": gate_provenance,
            "volume_provenance": {key: str(value) for key, value in volumes.items()},
        }
    except Exception as exc:  # noqa: BLE001 - every worker/preflight failure needs a receipt
        receipt = {
            "status": "failed", "reason": reason or type(exc).__name__,
            "source_sha256": first_hash,
            "other_selected_documents": "11 unattempted",
            "gold_opened": False, "can_continue_other_11": False,
            "worker_exit_code": exit_code,
            "worker_wall_seconds": round(time.monotonic() - started, 3),
            "peak_tree_rss_bytes": peak_tree_rss,
            "minimum_host_available_bytes": None if minimum_available == 2**63 - 1 else minimum_available,
            "worker_log_sha256": sha256_file(output_dir / "worker.log")
            if (output_dir / "worker.log").is_file() else None,
            "code_provenance": code_provenance,
            "trial_gate": gate_provenance,
            "volume_provenance": {key: str(value) for key, value in volumes.items()},
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
    parser.add_argument("--ocr-python", type=Path, required=True)
    parser.add_argument("--ocr-runtime-root", type=Path, required=True)
    parser.add_argument("--ocr-wheelhouse", type=Path, required=True)
    parser.add_argument("--ocr-notices-root", type=Path, required=True)
    parser.add_argument("--trial-gate", type=Path, required=True)
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
