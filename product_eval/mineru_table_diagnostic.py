"""Bounded local MinerU 4.0.9 Basic table diagnostic on the frozen VRDU slice.

This is parser-only research. Raw outputs and model weights stay outside Git.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from product_eval.contracts import ContractError, load_jsonl
from product_eval.docling_table_diagnostic import (
    GOLD_SHA256,
    gold_linked_rows,
    native_text_chars,
    normalize,
    score_tables,
    sha256_file,
    source_path,
    verify_selection,
)

SOURCE_COMMIT = "fa91b100f5350731064bd267008ca44302589417"
MODEL_REVISION = "358310b4f64b95f9fefc372ad899356e4111f376"
MODEL_LOCK = Path(__file__).parent / "fixtures" / "mineru_4_0_9_onnx_models.json"
PACKAGE_WHEEL_SHA256 = "4d9c0e28e2d4b132a9ca245a64dd970a721380b0f6d3dd0615e50ff12328a260"
MAX_FILE_BYTES = 2_000_000
MAX_PAGES = 20
DOCUMENT_TIMEOUT_SECONDS = 360
MAX_PROCESS_TREE_RSS_BYTES = 8 * 1024**3
MIN_AVAILABLE_MEMORY_BYTES = 2 * 1024**3
SMOKE_MAX_RSS_BYTES = 6 * 1024**3
SMOKE_MIN_AVAILABLE_BYTES = 3 * 1024**3
EXPECTED_GOLD_ROWS = 219
EXPECTED_GOLD_CELLS = 808


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def verify_local_runtime(source_checkout: Path, python_exe: Path, model_dir: Path,
                         wheel_path: Path) -> dict[str, Any]:
    if not MODEL_LOCK.is_file():
        raise ContractError("pinned MinerU model lock is missing")
    if not all(path.is_file() for path in (python_exe, wheel_path)):
        raise ContractError("isolated MinerU Python or pinned package wheel is missing")
    if sha256_file(wheel_path) != PACKAGE_WHEEL_SHA256:
        raise ContractError("MinerU 4.0.9 wheel hash differs from PyPI lock")
    commit = subprocess.run(["git", "-C", str(source_checkout), "rev-parse", "HEAD"],
                            capture_output=True, text=True, check=True, timeout=15).stdout.strip()
    if commit != SOURCE_COMMIT:
        raise ContractError("MinerU source checkout differs from release tag commit")
    dirty = subprocess.run(["git", "-C", str(source_checkout), "status", "--porcelain"],
                           capture_output=True, text=True, check=True, timeout=15).stdout.strip()
    if dirty:
        raise ContractError("MinerU source checkout is modified")
    lock = json.loads(MODEL_LOCK.read_text(encoding="utf-8"))
    if lock.get("repo") != "opendatalab/MinerU-4_models_onnx" or lock.get("revision") != MODEL_REVISION:
        raise ContractError("MinerU model manifest source differs from pinned revision")
    files = lock.get("files")
    if not isinstance(files, list) or len(files) != 16:
        raise ContractError("MinerU model manifest must describe all 16 repository files")
    for item in files:
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ContractError("unsafe MinerU model manifest path")
        path = model_dir / relative
        if not path.is_file() or path.stat().st_size != item["size"] or sha256_file(path) != item["sha256"]:
            raise ContractError(f"MinerU model file differs from pinned bytes: {relative}")
    version = subprocess.run([str(python_exe), "-c",
                              "import importlib.metadata; print(importlib.metadata.version('mineru'))"],
                             capture_output=True, text=True, check=True, timeout=20).stdout.strip()
    if version != "4.0.9":
        raise ContractError(f"isolated MinerU version differs from 4.0.9: {version}")
    return {"source_commit": commit, "model_revision": MODEL_REVISION,
            "model_lock_sha256": sha256_file(MODEL_LOCK), "model_files": len(files),
            "model_bytes": sum(item["size"] for item in files), "package_version": version,
            "package_wheel_sha256": PACKAGE_WHEEL_SHA256}


def _child_environment(config_path: Path, runtime_home: Path, temp_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.update({
        "MINERU_CONFIG": str(config_path), "MINERU_HOME": str(runtime_home),
        "MINERU_MODEL_SOURCE": "local", "MINERU_MODEL_SMALL_BACKEND": "onnx",
        "MINERU_TABLE_DEVICE": "cpu", "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
        "MINERU_INTRA_OP_NUM_THREADS": "4", "MINERU_INTER_OP_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "4", "MKL_NUM_THREADS": "4", "OPENBLAS_NUM_THREADS": "4",
        "TEMP": str(temp_dir), "TMP": str(temp_dir),
    })
    return env


def bounded_child(command: list[str], *, cwd: Path, env: dict[str, str], log_path: Path) -> dict[str, Any]:
    """Guard each parser subprocess and every child with conservative RSS summing."""
    import psutil

    started = time.perf_counter()
    peak_rss = 0
    minimum_available = psutil.virtual_memory().available
    stop_reason = "finished"
    with log_path.open("wb") as log:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            while process.poll() is None:
                try:
                    parent = psutil.Process(process.pid)
                    members = [parent, *parent.children(recursive=True)]
                    rss = sum(member.memory_info().rss for member in members if member.is_running())
                    peak_rss = max(peak_rss, rss)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                available = psutil.virtual_memory().available
                minimum_available = min(minimum_available, available)
                if time.perf_counter() - started > DOCUMENT_TIMEOUT_SECONDS:
                    stop_reason = "timeout"
                elif peak_rss > MAX_PROCESS_TREE_RSS_BYTES or available < MIN_AVAILABLE_MEMORY_BYTES:
                    stop_reason = "resource_limit"
                if stop_reason != "finished":
                    for member in reversed(members if "members" in locals() else []):
                        try:
                            member.kill()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass
                    process.kill()
                    break
                time.sleep(0.5)
            try:
                code = process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                code = process.wait(timeout=15)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=15)
    return {"stop_reason": stop_reason, "exit_code": code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 3),
            "peak_process_tree_rss_bytes": peak_rss,
            "min_host_available_bytes": minimum_available}


def _table_html_from_node(node: Any) -> list[str]:
    """Find table bodies once, preferring a table body's HTML over its parent."""
    if isinstance(node, list):
        return [html for item in node for html in _table_html_from_node(item)]
    if not isinstance(node, dict):
        return []
    kind = node.get("type")
    if kind == "table_body":
        content = node.get("content")
        return [content] if isinstance(content, str) and "<table" in content.lower() else []
    nested = [html for value in node.values() if isinstance(value, (dict, list))
              for html in _table_html_from_node(value)]
    if kind == "table" and not nested:
        content = node.get("content")
        return [content] if isinstance(content, str) and "<table" in content.lower() else []
    return nested


def table_strings(middle: dict[str, Any]) -> tuple[list[str], list[list[str]], dict[str, int]]:
    """Read only MinerU table HTML; keep each HTML tr as one candidate row."""
    from lxml import etree, html

    if middle.get("schema") != "docvortex.middle" or not isinstance(middle.get("pages"), list):
        raise ContractError("MinerU output is not a valid MiddleJson document")
    cells: list[str] = []
    rows: list[list[str]] = []
    html_fragments = _table_html_from_node(middle["pages"])
    invalid_tables = 0
    for fragment in html_fragments:
        try:
            fragments = html.fragments_fromstring(fragment)
            tables = [element for item in fragments if isinstance(item, html.HtmlElement)
                      for element in ([item] if item.tag.lower() == "table" else item.xpath(".//table"))]
            if len(tables) != 1 or tables[0].xpath(".//table"):
                invalid_tables += 1
                continue
            for row in tables[0].xpath(".//tr"):
                row_cells = []
                for cell in row.xpath("./th|./td"):
                    value = normalize(" ".join(cell.itertext()))
                    if value:
                        cells.append(value)
                        row_cells.append(value)
                if row_cells:
                    rows.append(row_cells)
        except (etree.LxmlError, ValueError, TypeError):
            invalid_tables += 1
    return cells, rows, {"tables": len(html_fragments) - invalid_tables,
                         "invalid_tables": invalid_tables, "rows": len(rows),
                         "nonempty_cells": len(cells)}


def score_saved(output_dir: Path, gold_path: Path, selected: list[dict[str, Any]]) -> dict[str, Any]:
    if sha256_file(gold_path) != GOLD_SHA256:
        raise ContractError("frozen VRDU gold hash mismatch")
    gold = load_jsonl(gold_path, kind="gold")
    per_document = []
    for row in selected:
        folder = output_dir / "docs" / row["doc_id"]
        receipt_path = folder / "conversion.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.exists() else {
            "status": "not_run", "duration_ms": 0, "source_sha256": row["source_sha256"],
        }
        if receipt["source_sha256"] != row["source_sha256"]:
            raise ContractError("MinerU receipt source hash differs from frozen selection")
        parser_status = "missing"
        cells: list[str] = []
        rows: list[list[str]] = []
        stats = {"tables": 0, "invalid_tables": 0, "rows": 0, "nonempty_cells": 0}
        if receipt["status"] == "success":
            raw = folder / "middle_json.json"
            if sha256_file(raw) != receipt["output_sha256"]:
                raise ContractError("MinerU output differs from conversion receipt")
            try:
                cells, rows, stats = table_strings(json.loads(raw.read_text(encoding="utf-8")))
                parser_status = "valid"
            except (ContractError, ValueError, TypeError, UnicodeError):
                parser_status = "invalid"
        metrics = score_tables(gold_linked_rows(gold[row["doc_id"]]), cells, rows)
        per_document.append({"doc_id": row["doc_id"], "source_sha256": row["source_sha256"],
                             "status": receipt["status"], "parser_status": parser_status,
                             "duration_ms": receipt["duration_ms"], "parser": stats, "metrics": metrics,
                             "peak_process_tree_rss_bytes": receipt.get("peak_process_tree_rss_bytes"),
                             "min_host_available_bytes": receipt.get("min_host_available_bytes"),
                             "native_text_chars": receipt.get("native_text_chars")})
    aggregate = {key: sum(item["metrics"][key] for item in per_document)
                 for key in per_document[0]["metrics"]}
    if aggregate["gold_rows"] != EXPECTED_GOLD_ROWS or aggregate["gold_cells"] != EXPECTED_GOLD_CELLS:
        raise ContractError("frozen 12-document linked-row denominator changed")
    return {"selected_documents": len(selected),
            "conversion_successes": sum(item["status"] == "success" for item in per_document),
            "conversion_failures_or_not_run": sum(item["status"] != "success" for item in per_document),
            "missing_or_invalid_outputs": sum(item["parser_status"] != "valid" for item in per_document),
            "image_only_documents": sum(item["native_text_chars"] == 0 for item in per_document),
            "metrics": aggregate,
            "parser_totals": {key: sum(item["parser"][key] for item in per_document)
                              for key in per_document[0]["parser"]},
            "per_document": per_document}


def run(*, selection: Path, cohort: Path, corpus_root: Path, gold: Path,
        source_checkout: Path, python_exe: Path, model_dir: Path, wheel_path: Path,
        config_path: Path, runtime_home: Path, output_dir: Path) -> dict[str, Any]:
    selected = verify_selection(selection, cohort, corpus_root)
    if sha256_file(gold) != GOLD_SHA256:
        raise ContractError("frozen gold hash mismatch")
    runtime = verify_local_runtime(source_checkout, python_exe, model_dir, wheel_path)
    if output_dir.exists() or output_dir.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
        raise ContractError("new raw output directory outside Git required")
    output_dir.mkdir(parents=True)
    temp_dir = output_dir / "tmp"
    temp_dir.mkdir()
    env = _child_environment(config_path, runtime_home, temp_dir)
    kit = python_exe.parent / "mineru-kit.exe"
    if not kit.is_file():
        raise ContractError("MinerU CLI is unavailable in isolated environment")
    started = datetime.now(timezone.utc).isoformat()
    receipts: list[dict[str, Any]] = []
    smoke_safe = False
    for index, row in enumerate(selected):
        if index > 0 and not smoke_safe:
            break
        source = source_path(corpus_root, row["source_id"])
        folder = output_dir / "docs" / row["doc_id"]
        folder.mkdir(parents=True)
        page_count, native_chars = native_text_chars(source)
        if source.stat().st_size > MAX_FILE_BYTES or page_count > MAX_PAGES:
            child = {"stop_reason": "input_limit", "exit_code": None, "duration_ms": 0,
                     "peak_process_tree_rss_bytes": 0, "min_host_available_bytes": None}
        else:
            command = [str(kit), "parse", str(source), "-o", str(folder / "middle_json.json"),
                       "--format", "middle_json", "--tier", "basic", "--ocr-mode", "auto",
                       "--disable-image-analysis"]
            child = bounded_child(command, cwd=output_dir, env=env, log_path=folder / "mineru.log")
        output = folder / "middle_json.json"
        status = "success" if child["stop_reason"] == "finished" and child["exit_code"] == 0 and output.is_file() else child["stop_reason"]
        if status == "finished":
            status = "cli_failure"
        receipt = {"doc_id": row["doc_id"], "source_sha256": row["source_sha256"],
                   "page_count": page_count, "native_text_chars": native_chars,
                   "status": status, **child,
                   "output_sha256": sha256_file(output) if status == "success" else None}
        _write_json(folder / "conversion.json", receipt)
        receipts.append(receipt)
        if index == 0:
            smoke_safe = (status == "success" and child["peak_process_tree_rss_bytes"] < SMOKE_MAX_RSS_BYTES
                          and child["min_host_available_bytes"] > SMOKE_MIN_AVAILABLE_BYTES)
        if child["stop_reason"] == "resource_limit":
            smoke_safe = False
            break
    score = score_saved(output_dir, gold, selected)
    result = {"diagnostic_version": 1, "started_utc": started,
              "completed_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "MinerU Basic local ONNX table HTML on 12 public ad-buy PDFs; unlabeled table strings/rows only",
              "runtime": runtime, "selection_sha256": sha256_file(selection),
              "cohort_sha256": sha256_file(cohort), "gold_sha256": GOLD_SHA256,
              "configuration": {"tier": "basic", "small_backend": "onnx", "table_device": "cpu",
                                "model_source": "local", "ocr_mode": "auto", "image_analysis": False,
                                "document_timeout_seconds": DOCUMENT_TIMEOUT_SECONDS,
                                "max_process_tree_rss_bytes": MAX_PROCESS_TREE_RSS_BYTES,
                                "min_host_available_bytes": MIN_AVAILABLE_MEMORY_BYTES,
                                "smoke_max_rss_bytes": SMOKE_MAX_RSS_BYTES,
                                "smoke_min_available_bytes": SMOKE_MIN_AVAILABLE_BYTES},
              "smoke_safe": smoke_safe, "attempted_documents": len(receipts),
              "complete_cohort": len(receipts) == len(selected), "score": score,
              "limitations": ["No field ID mapping or source-box grounding.",
                              "Missing and failed parser documents remain in all 219 gold rows.",
                              "Hardware costs and reviewer labor are unpriced."]}
    _write_json(output_dir / "run.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--cohort", required=True, type=Path)
    parser.add_argument("--corpus-root", required=True, type=Path)
    parser.add_argument("--gold", required=True, type=Path)
    parser.add_argument("--source-checkout", required=True, type=Path)
    parser.add_argument("--python-exe", required=True, type=Path)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--wheel-path", required=True, type=Path)
    parser.add_argument("--config-path", required=True, type=Path)
    parser.add_argument("--runtime-home", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--run", action="store_true")
    args = parser.parse_args()
    selected = verify_selection(args.selection, args.cohort, args.corpus_root)
    if sha256_file(args.gold) != GOLD_SHA256:
        raise ContractError("frozen gold hash mismatch")
    runtime = verify_local_runtime(args.source_checkout, args.python_exe, args.model_dir, args.wheel_path)
    if args.check:
        print(json.dumps({"ready": True, "selected": len(selected), "runtime": runtime}))
        return
    if args.output_dir is None:
        parser.error("--run requires --output-dir")
    result = run(selection=args.selection, cohort=args.cohort, corpus_root=args.corpus_root,
                 gold=args.gold, source_checkout=args.source_checkout, python_exe=args.python_exe,
                 model_dir=args.model_dir, wheel_path=args.wheel_path, config_path=args.config_path,
                 runtime_home=args.runtime_home, output_dir=args.output_dir)
    print(json.dumps({"attempted": result["attempted_documents"],
                      "complete": result["complete_cohort"], "smoke_safe": result["smoke_safe"],
                      "exact_rows": result["score"]["metrics"]["complete_rows_exact_cells_one_to_one"]}))


if __name__ == "__main__":
    main()
