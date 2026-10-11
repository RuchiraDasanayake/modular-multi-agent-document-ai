"""Failure-inclusive PP-StructureV3 table comparison on frozen VRDU ad-buy PDFs.

This is a research harness, not a product parser. Run only after the explicit
resource gate; no package or model downloads are performed by this module.
Each PDF is converted in a bounded child process and raw outputs stay outside
Git. Gold is opened only after all twelve conversions have completed.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from product_eval.contracts import ContractError, load_jsonl
from product_eval.docling_table_diagnostic import (
    GOLD_SHA256,
    SELECTION_SHA256,
    gold_linked_rows,
    normalize,
    score_tables,
    sha256_file,
    source_path,
    verify_selection,
)

DIAGNOSTIC_VERSION = 1
EXPECTED_GOLD_ROWS = 219
MAX_PAGES = 20
MAX_FILE_BYTES = 2_000_000
MAX_PAGE_PIXELS = 25_000_000
RENDER_SCALE = 2.0
DOCUMENT_TIMEOUT_SECONDS = 360
PACKAGE_VERSIONS = {
    "paddleocr": "3.7.0",
    "paddlepaddle": "3.2.1",
    "pypdfium2": "5.14.0",
    "lxml": "6.1.1",
    "PyYAML": "6.0.3",
    "psutil": "7.2.2",
}
ROOT_FLAGS = {
    "use_doc_preprocessor": False,
    "use_seal_recognition": False,
    "use_table_recognition": True,
    "use_formula_recognition": False,
    "use_chart_recognition": False,
    "use_region_detection": True,
}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def package_versions() -> dict[str, str]:
    found = {}
    for name, expected in PACKAGE_VERSIONS.items():
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError as exc:
            raise ContractError(f"required package missing: {name}=={expected}") from exc
        if actual != expected:
            raise ContractError(f"{name}=={expected} required; found {actual}")
        found[name] = actual
    found["paddlex"] = importlib.metadata.version("paddlex")
    return found


def active_model_dirs(config: dict[str, Any]) -> list[Path]:
    """Require local weights for every module used by the fixed pilot profile."""
    if config.get("pipeline_name") != "PP-StructureV3" or any(
        config.get(name) is not expected for name, expected in ROOT_FLAGS.items()
    ):
        raise ContractError("PP-StructureV3 config is outside the fixed table-only profile")
    root_modules = config.get("SubModules")
    pipelines = config.get("SubPipelines")
    if not isinstance(root_modules, dict) or not isinstance(pipelines, dict):
        raise ContractError("PP-StructureV3 config lacks modules")
    active = [root_modules.get("LayoutDetection"), root_modules.get("RegionDetection"),
              pipelines.get("GeneralOCR"), pipelines.get("TableRecognition")]
    if any(not isinstance(item, dict) for item in active):
        raise ContractError("PP-StructureV3 active layout/OCR/table module missing")
    if pipelines["GeneralOCR"].get("use_doc_preprocessor") is not False:
        raise ContractError("GeneralOCR preprocessing must be disabled")
    table = pipelines["TableRecognition"]
    if table.get("use_doc_preprocessor") is not False or table.get("use_layout_detection") is not False:
        raise ContractError("nested table preprocessing/layout must be disabled")
    dirs: set[Path] = set()

    def walk(node: dict[str, Any]) -> None:
        if "module_name" in node:
            model_dir = node.get("model_dir")
            if not isinstance(model_dir, str) or not model_dir.strip():
                raise ContractError(f"active model has no local model_dir: {node.get('model_name')}")
            path = Path(model_dir)
            if not path.is_absolute() or not path.is_dir() or path.is_symlink():
                raise ContractError("active model_dir must be an existing absolute non-symlink directory")
            dirs.add(path.resolve())
        for key in ("SubModules", "SubPipelines"):
            children = node.get(key, {})
            if not isinstance(children, dict):
                raise ContractError(f"invalid {key} in active pipeline")
            for child in children.values():
                if not isinstance(child, dict):
                    raise ContractError(f"invalid child in {key}")
                walk(child)

    for item in active:
        walk(item)
    return sorted(dirs)


def verify_model_lock(config_path: Path, lock_path: Path) -> dict[str, Any]:
    import yaml

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ContractError("invalid PP-StructureV3 YAML config")
    model_dirs = active_model_dirs(config)
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("config_sha256") != sha256_file(config_path):
        raise ContractError("PP-StructureV3 YAML differs from locked config")
    if lock.get("packages") != package_versions():
        raise ContractError("installed parser packages differ from model lock")
    artifacts = lock.get("files")
    if not isinstance(artifacts, list) or not artifacts:
        raise ContractError("model lock requires files")
    all_entries = [entry for folder in model_dirs for entry in folder.rglob("*")]
    if any(entry.is_symlink() for entry in all_entries):
        raise ContractError("active model tree contains symlink")
    actual_files = {file.resolve() for file in all_entries if file.is_file()}
    locked_files: set[Path] = set()
    for artifact in artifacts:
        if not isinstance(artifact, dict) or set(artifact) != {"path", "sha256", "size_bytes"}:
            raise ContractError("invalid model lock entry")
        path = Path(artifact["path"])
        if not path.is_absolute() or path.is_symlink() or path.resolve() in locked_files:
            raise ContractError("model lock has non-absolute, symlink, or duplicate file")
        path = path.resolve()
        locked_files.add(path)
        if not path.is_file() or path.stat().st_size != artifact["size_bytes"] or sha256_file(path) != artifact["sha256"]:
            raise ContractError(f"model artifact differs from lock: {path.name}")
    if actual_files != locked_files:
        raise ContractError("active model files differ from locked inventory")
    return {"config_sha256": sha256_file(config_path), "model_lock_sha256": sha256_file(lock_path),
            "active_model_directories": len(model_dirs), "model_files": len(locked_files)}


def make_model_lock(config_path: Path, lock_path: Path) -> dict[str, Any]:
    """Freeze local model bytes before any inference; never overwrite a prior lock."""
    import yaml

    if lock_path.exists():
        raise ContractError("model lock already exists")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ContractError("invalid PP-StructureV3 YAML config")
    dirs = active_model_dirs(config)
    all_entries = [entry for folder in dirs for entry in folder.rglob("*")]
    if any(entry.is_symlink() for entry in all_entries):
        raise ContractError("active model tree contains symlink")
    files = sorted({entry.resolve() for entry in all_entries if entry.is_file()})
    if not files:
        raise ContractError("no active model files to lock")
    lock = {"config_sha256": sha256_file(config_path), "packages": package_versions(), "files": [
        {"path": str(path), "sha256": sha256_file(path), "size_bytes": path.stat().st_size}
        for path in files
    ]}
    write_json(lock_path, lock)
    return verify_model_lock(config_path, lock_path)


def bounded_worker(command: list[str], env: dict[str, str], cwd: Path) -> tuple[str, int | None, int]:
    """Bound a heavy child process and sample its process-tree RSS."""
    import psutil

    process = subprocess.Popen(command, cwd=cwd, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    started = time.perf_counter()
    peak_rss = 0
    timed_out = False
    try:
        try:
            observer = psutil.Process(process.pid)
        except psutil.NoSuchProcess:
            observer = None
        while process.poll() is None:
            try:
                members = [observer, *observer.children(recursive=True)] if observer else []
                rss = sum(member.memory_info().rss for member in members if member.is_running())
                peak_rss = max(peak_rss, rss)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            if time.perf_counter() - started >= DOCUMENT_TIMEOUT_SECONDS:
                timed_out = True
                for child in observer.children(recursive=True) if observer else []:
                    try:
                        child.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
                process.kill()
                break
            time.sleep(0.25)
        code = process.wait(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
    return ("timeout" if timed_out else "finished", code, peak_rss)


def table_strings(pages: list[dict[str, Any]]) -> tuple[list[str], list[list[str]], dict[str, int]]:
    """Read only official pred_html table rows; spans belong to their start row."""
    from lxml import etree, html

    cells: list[str] = []
    rows: list[list[str]] = []
    table_count = cell_boxes = invalid_cell_boxes = 0
    for page in pages:
        payload = page.get("res", page)
        if not isinstance(payload, dict):
            raise ContractError("PP-StructureV3 page result invalid")
        tables = payload.get("table_res_list")
        if not isinstance(tables, list):
            raise ContractError("PP-StructureV3 page lacks table_res_list")
        for table in tables:
            if not isinstance(table, dict) or not isinstance(table.get("pred_html"), str):
                raise ContractError("PP-StructureV3 table lacks pred_html")
            try:
                fragments = html.fragments_fromstring(table["pred_html"])
            except (etree.LxmlError, ValueError) as exc:
                raise ContractError("PP-StructureV3 pred_html cannot be parsed") from exc
            elements = [element for item in fragments if isinstance(item, html.HtmlElement)
                        for element in ([item] if item.tag.lower() == "table" else item.xpath(".//table"))]
            if len(elements) != 1 or elements[0].xpath(".//table"):
                raise ContractError("PP-StructureV3 pred_html must contain one non-nested table")
            table_count += 1
            for row in elements[0].xpath(".//tr"):
                row_cells = []
                for cell in row.xpath("./th|./td"):
                    value = normalize(" ".join(cell.itertext()))
                    if value:
                        cells.append(value)
                        row_cells.append(value)
                if row_cells:
                    rows.append(row_cells)
            boxes = table.get("cell_box_list")
            if not isinstance(boxes, list):
                raise ContractError("PP-StructureV3 table lacks cell_box_list")
            for box in boxes:
                if not isinstance(box, (list, tuple)) or len(box) not in (4, 8) or any(
                    not isinstance(value, (int, float)) or isinstance(value, bool) for value in box
                ):
                    invalid_cell_boxes += 1
                else:
                    cell_boxes += 1
    return cells, rows, {"tables": table_count, "rows": len(rows), "nonempty_cells": len(cells),
                         "cell_boxes": cell_boxes, "invalid_cell_boxes": invalid_cell_boxes}


def score_saved(output_dir: Path, gold_path: Path, selected: list[dict[str, Any]]) -> dict[str, Any]:
    if sha256_file(gold_path) != GOLD_SHA256:
        raise ContractError("frozen VRDU gold hash mismatch")
    gold = load_jsonl(gold_path, kind="gold")
    if not {row["doc_id"] for row in selected} <= set(gold):
        raise ContractError("selected PDFs missing from frozen gold")
    per_document = []
    for row in selected:
        folder = output_dir / "docs" / row["doc_id"]
        receipt = json.loads((folder / "conversion.json").read_text(encoding="utf-8"))
        if receipt.get("doc_id") != row["doc_id"] or receipt.get("source_sha256") != row["source_sha256"]:
            raise ContractError("conversion receipt differs from frozen selection")
        entries = receipt.get("pages", [])
        if not isinstance(entries, list) or any(
            not isinstance(entry, dict) or entry.get("page_index") != index
            for index, entry in enumerate(entries)
        ):
            raise ContractError("conversion page indices are not contiguous")
        if receipt.get("status") == "success" and len(entries) != receipt.get("page_count"):
            raise ContractError("successful conversion has missing page outputs")
        pages = []
        raw_invalid = False
        for entry in entries:
            path = folder / entry["file"]
            if sha256_file(path) != entry["sha256"]:
                raise ContractError("saved PP-StructureV3 page differs from conversion receipt")
            image = folder / entry["image_file"]
            if sha256_file(image) != entry["image_sha256"]:
                raise ContractError("rendered page image differs from conversion receipt")
            try:
                pages.append(json.loads(path.read_text(encoding="utf-8")))
            except (ValueError, UnicodeError):
                raw_invalid = True
        try:
            if raw_invalid:
                raise ContractError("saved PP-StructureV3 page is not valid JSON")
            cells, rows, parser = table_strings(pages)
            parser_status = "valid" if receipt["status"] == "success" else "partial_or_failed"
        except (ContractError, ValueError, TypeError):
            cells, rows = [], []
            parser = {"tables": 0, "rows": 0, "nonempty_cells": 0,
                      "cell_boxes": 0, "invalid_cell_boxes": 0}
            parser_status = "invalid"
        metrics = score_tables(gold_linked_rows(gold[row["doc_id"]]), cells, rows)
        per_document.append({"doc_id": row["doc_id"], "source_sha256": row["source_sha256"],
                             "status": receipt["status"], "parser_status": parser_status,
                             "duration_ms": receipt["duration_ms"], "parser": parser, "metrics": metrics})
    aggregate = {key: sum(item["metrics"][key] for item in per_document)
                 for key in per_document[0]["metrics"]}
    if len(selected) == 12 and aggregate["gold_rows"] != EXPECTED_GOLD_ROWS:
        raise ContractError("frozen twelve-document linked-row denominator changed")
    return {"diagnostic_version": DIAGNOSTIC_VERSION, "selected_documents": len(selected),
            "conversion_successes": sum(item["status"] == "success" for item in per_document),
            "conversion_failures_or_partial": sum(item["status"] != "success" for item in per_document),
            "missing_or_invalid_parser_outputs": sum(item["parser_status"] != "valid" for item in per_document),
            "duration_ms_sum": round(sum(item["duration_ms"] for item in per_document), 3),
            "parser_totals": {key: sum(item["parser"][key] for item in per_document)
                              for key in per_document[0]["parser"]},
            "metrics": aggregate, "per_document": per_document,
            "matching_caveat": "Same exact one-to-one text/row scorer as Docling and pdfplumber; no field attribution. Cell boxes are counted, not treated as mapped evidence until alignment is verified. Gold has no page/box annotations."}


def convert_one(source: Path, folder: Path, config: Path, expected_sha256: str) -> dict[str, Any]:
    import pypdfium2
    from paddleocr import PPStructureV3

    if sha256_file(source) != expected_sha256:
        raise ContractError("source PDF changed before child conversion")
    document = pypdfium2.PdfDocument(str(source))
    try:
        if len(document) > MAX_PAGES:
            return {"status": "over_page_limit", "pages": [], "page_count": len(document)}
        pipeline = PPStructureV3(paddlex_config=str(config), device="cpu", engine="paddle",
                                 use_doc_orientation_classify=False, use_doc_unwarping=False,
                                 use_seal_recognition=False,
                                 use_table_recognition=True, use_formula_recognition=False,
                                 use_chart_recognition=False, use_region_detection=True,
                                 cpu_threads=4)
        entries = []
        for index in range(len(document)):
            page = document[index]
            try:
                width_points, height_points = page.get_size()
                if min(width_points, height_points) <= 0 or (
                    width_points * height_points * RENDER_SCALE * RENDER_SCALE > MAX_PAGE_PIXELS
                ):
                    raise ContractError("PDF page exceeds fixed render pixel cap")
                bitmap = page.render(scale=RENDER_SCALE)
                image = bitmap.to_pil().convert("RGB").copy()
            finally:
                page.close()
            if image.width * image.height > MAX_PAGE_PIXELS:
                raise ContractError("rendered page exceeds fixed pixel cap")
            png = folder / f"page-{index:03d}.png"
            image.save(png, format="PNG")
            results = list(pipeline.predict(str(png)))
            if len(results) != 1 or not isinstance(results[0].json, dict):
                raise ContractError("PP-StructureV3 returned non-single page result")
            output = folder / f"page-{index:03d}.json"
            write_json(output, results[0].json)
            entries.append({"page_index": index, "image_file": png.name,
                            "image_sha256": sha256_file(png),
                            "image_width": image.width, "image_height": image.height,
                            "file": output.name, "sha256": sha256_file(output)})
        return {"status": "success", "pages": entries, "page_count": len(document)}
    finally:
        document.close()


def run(selection: Path, cohort: Path, corpus_root: Path, gold: Path, config: Path,
        model_lock: Path, output_dir: Path) -> dict[str, Any]:
    selected = verify_selection(selection, cohort, corpus_root)
    if sha256_file(gold) != GOLD_SHA256:
        raise ContractError("frozen VRDU gold hash mismatch")
    versions = package_versions()
    model_receipt = verify_model_lock(config, model_lock)
    if output_dir.exists() or output_dir.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
        raise ContractError("new output directory outside Git required")
    output_dir.mkdir(parents=True)
    started_utc = datetime.now(timezone.utc).isoformat()
    for index, row in enumerate(selected, 1):
        folder = output_dir / "docs" / row["doc_id"]
        folder.mkdir(parents=True)
        started = time.perf_counter()
        source = source_path(corpus_root, row["source_id"])
        status = "exception"
        error_type = None
        peak_rss = None
        page_count = None
        pages: list[dict[str, Any]] = []
        try:
            if sha256_file(source) != row["source_sha256"]:
                raise ContractError("source bytes changed after selection preflight")
            if source.stat().st_size > MAX_FILE_BYTES:
                status = "over_file_limit"
            else:
                env = os.environ.copy()
                env.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                            "OMP_NUM_THREADS": "4", "MKL_NUM_THREADS": "4"})
                worker_status, exit_code, peak_rss = bounded_worker(
                    [sys.executable, "-m", "product_eval.ppstructure_table_diagnostic", "--convert-one",
                     "--source", str(source), "--source-sha256", row["source_sha256"],
                     "--folder", str(folder), "--config", str(config)],
                    env=env, cwd=Path(__file__).resolve().parents[1],
                )
                worker = folder / "worker.json"
                if worker_status == "timeout":
                    status = "timeout"
                elif exit_code == 0 and worker.exists():
                    outcome = json.loads(worker.read_text(encoding="utf-8"))
                    status = outcome["status"]
                    pages = outcome["pages"]
                    error_type = outcome.get("error_type")
                    page_count = outcome.get("page_count")
                else:
                    status = "worker_failed"
        except Exception as exc:  # noqa: BLE001 - every source remains in denominator
            error_type = type(exc).__name__
        write_json(folder / "conversion.json", {"doc_id": row["doc_id"],
                   "source_sha256": row["source_sha256"], "status": status,
                   "error_type": error_type, "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                   "peak_process_tree_rss_bytes": peak_rss,
                   "page_count": page_count, "pages": pages})
        print(f"{index}/{len(selected)} {row['doc_id']} {status}", flush=True)
    score = score_saved(output_dir, gold, selected)
    score_path = output_dir / "score.json"
    write_json(score_path, score)
    metadata = {"diagnostic_version": DIAGNOSTIC_VERSION, "complete": True,
                "started_utc": started_utc, "completed_utc": datetime.now(timezone.utc).isoformat(),
                "selection_sha256": SELECTION_SHA256, "gold_sha256": GOLD_SHA256,
                "runner_sha256": sha256_file(Path(__file__)), "source_hashes_verified": True,
                "selected_documents": len(selected), "versions": versions,
                "model_receipt": model_receipt,
                "configuration": {"device": "cpu", "engine": "paddle", "threads": 4,
                                  "render": "PDFium 144 DPI", "max_pages": MAX_PAGES,
                                  "max_file_bytes": MAX_FILE_BYTES,
                                  "document_timeout_seconds": DOCUMENT_TIMEOUT_SECONDS,
                                  "formula_chart_seal_preprocess": False},
                "score_sha256": sha256_file(score_path), "raw_outputs_outside_git": True}
    write_json(output_dir / "run.json", metadata)
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=Path(__file__).parent / "fixtures" / "vrdu_ad_buy_table12.jsonl")
    parser.add_argument("--cohort", type=Path)
    parser.add_argument("--corpus-root", type=Path)
    parser.add_argument("--gold", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--model-lock", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--source-sha256")
    parser.add_argument("--folder", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    for name in ("check", "run", "score", "convert-one", "make-lock"):
        mode.add_argument(f"--{name}", action="store_true")
    args = parser.parse_args()
    if args.make_lock:
        if not args.config or not args.model_lock:
            parser.error("--make-lock requires --config and --model-lock")
        print(json.dumps(make_model_lock(args.config, args.model_lock), indent=2))
        return 0
    if args.convert_one:
        if not all((args.source, args.source_sha256, args.folder, args.config)):
            parser.error("--convert-one requires --source, --source-sha256, --folder, --config")
        try:
            outcome = convert_one(args.source, args.folder, args.config, args.source_sha256)
        except Exception as exc:  # noqa: BLE001
            outcome = {"status": "exception", "pages": [], "error_type": type(exc).__name__}
        write_json(args.folder / "worker.json", outcome)
        return 0
    if not all((args.cohort, args.corpus_root, args.gold, args.output_dir)):
        parser.error("--cohort, --corpus-root, --gold, --output-dir are required")
    selected = verify_selection(args.selection, args.cohort, args.corpus_root)
    if args.score:
        result = score_saved(args.output_dir, args.gold, selected)
        print(json.dumps({"selected": len(selected), "metrics": result["metrics"]}, indent=2))
    elif args.check:
        if not args.config or not args.model_lock:
            parser.error("--check requires --config and --model-lock")
        print(json.dumps({"selected": len(selected), "packages": package_versions(),
                          "models": verify_model_lock(args.config, args.model_lock)}, indent=2))
    else:
        if not args.config or not args.model_lock:
            parser.error("--run requires --config and --model-lock")
        result = run(args.selection, args.cohort, args.corpus_root, args.gold,
                     args.config, args.model_lock, args.output_dir)
        print(json.dumps({"selected": result["selected_documents"], "complete": result["complete"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
