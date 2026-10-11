"""Local, table-only Docling diagnostic on twelve frozen public VRDU ad-buy PDFs.

The selection manifest is committed before conversion. Gold is opened only by
the scoring phase. Raw Docling documents stay in an output directory outside Git.
This measures table text and row grouping, not field attribution or end-to-end F1.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from product_eval.contracts import ContractError, load_jsonl

DIAGNOSTIC_VERSION = 1
DATASET_COMMIT = "04a4df7ac5cc694e51c48115c03fe428f0e240cc"
SELECTION_SHA256 = "b843d48146a60f02bb206900ee06d446eb82ba484a3781c291235864b5230d2d"
COHORT_SHA256 = "98f4fcbd6521594304da3a80104362cf89174c87c27ed08ce90a1158fef4bc90"
GOLD_SHA256 = "8a631bffbf439ccc8376f84cbf7d4af25c86d35c0ccc7996ce3b23e6085138bf"
MODEL_ARTIFACTS_SHA256 = "3a2c3e36a5db87d85d3952aed37f809d8c7d495dd8cfba64e65b8d622cee8241"
RAPIDOCR_WEIGHT_SHA256 = {
    "PP-OCRv6_det_small.pth": "fbdc74c97ea7b770ab22cbdc1bba01a52bdf1975efcf3442057356d622b05d54",
    "PP-OCRv6_rec_small.pth": "0107b2ad694ccc9b1db7cf9ed3ffbc93d1795d9e08d9cf823127243a87bce516",
    "ch_ppocr_mobile_v2.0_cls_mobile.pth": "bfe13860824b3365c0c7f7ccfcddc8ff11645c60051739ff18bc9913f60c98e1",
}
MAX_DOCUMENTS = 12
MAX_PAGES = 20
MAX_FILE_BYTES = 2_000_000
DOCUMENT_TIMEOUT_SECONDS = 240.0
CPU_THREADS = 4
NATIVE_TEXT_THRESHOLD = 100


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def source_path(corpus_root: Path, source_id: str) -> Path:
    parts = PurePosixPath(source_id).parts
    if (
        len(parts) != 2 or parts[0] != "ad-buy-form" or parts[1] in {"", ".", ".."}
        or "\\" in parts[1] or Path(parts[1]).name != parts[1]
    ):
        raise ContractError(f"invalid frozen source_id: {source_id!r}")
    return corpus_root / "ad-buy-form" / "main" / "pdfs" / parts[1]


def verify_selection(selection: Path, cohort: Path, corpus_root: Path) -> list[dict[str, Any]]:
    if sha256_file(selection) != SELECTION_SHA256 or sha256_file(cohort) != COHORT_SHA256:
        raise ContractError("frozen selection or source cohort hash mismatch")
    chosen = [json.loads(line) for line in selection.read_text(encoding="utf-8").splitlines()]
    cohort_rows = [json.loads(line) for line in cohort.read_text(encoding="utf-8").splitlines()]
    expected = sorted(
        (row for row in cohort_rows if row["family"] == "ad-buy-form"),
        key=lambda row: row["source_sha256"],
    )[:MAX_DOCUMENTS]
    if len(chosen) != MAX_DOCUMENTS or len({row["doc_id"] for row in chosen}) != MAX_DOCUMENTS:
        raise ContractError("frozen selection requires twelve unique document IDs")
    if len({row["source_sha256"] for row in chosen}) != MAX_DOCUMENTS:
        raise ContractError("frozen selection repeats source bytes")
    fields = ("doc_id", "source_id", "source_sha256", "source_size_bytes")
    for actual, original in zip(chosen, expected, strict=True):
        if set(actual) != set(fields) or any(actual[key] != original[key] for key in fields):
            raise ContractError("selection is not the twelve lowest ad-buy source hashes")
        path = source_path(corpus_root, actual["source_id"])
        if path.stat().st_size != actual["source_size_bytes"] or sha256_file(path) != actual["source_sha256"]:
            raise ContractError(f"source bytes differ from frozen selection: {actual['doc_id']}")
    return chosen


def verify_cached_models(manifest: Path) -> dict[str, Any]:
    if sha256_file(manifest) != MODEL_ARTIFACTS_SHA256:
        raise ContractError("cached Docling model artifact manifest changed")
    artifacts = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(artifacts, list) or not artifacts:
        raise ContractError("invalid Docling model artifact manifest")
    for artifact in artifacts:
        path = Path(artifact["path"])
        if path.stat().st_size != artifact["size_bytes"] or sha256_file(path) != artifact["sha256"]:
            raise ContractError(f"cached Docling model artifact changed: {path.name}")
    rapidocr_spec = importlib.util.find_spec("rapidocr")
    if rapidocr_spec is None or rapidocr_spec.origin is None:
        raise ContractError("RapidOCR is unavailable in this Python environment")
    weight_root = Path(rapidocr_spec.origin).parent / "models"
    for filename, expected_hash in RAPIDOCR_WEIGHT_SHA256.items():
        if sha256_file(weight_root / filename) != expected_hash:
            raise ContractError(f"RapidOCR weight changed: {filename}")
    return {
        "docling_model_artifacts_manifest_sha256": MODEL_ARTIFACTS_SHA256,
        "docling_model_artifact_count": len(artifacts),
        "rapidocr_torch_weight_sha256": RAPIDOCR_WEIGHT_SHA256,
    }


def normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def gold_linked_rows(gold: dict[str, Any]) -> dict[int, list[str]]:
    linked_ids = {field["field_id"] for field in gold["gold_schema"] if field["type"] == "array[object]"}
    rows: dict[int, list[str]] = defaultdict(list)
    for field in gold["gold_values"]:
        if field["field_id"] not in linked_ids:
            continue
        for cell in field["value"] or []:
            row, value = cell["row"], cell["value"]
            if type(row) is not int or row < 0 or not isinstance(value, str) or not normalize(value):
                raise ContractError("invalid frozen linked gold cell")
            rows[row].append(normalize(value))
    return dict(rows)


def parsed_tables(document: dict[str, Any] | None) -> tuple[list[str], list[list[str]], dict[str, int]]:
    """Use only actual Docling table cells; attach spanning cells to their start row."""
    if document is None:
        return [], [], {"tables": 0, "rows": 0, "nonempty_cells": 0, "spanning_cells": 0, "invalid_cells": 0}
    tables = document.get("tables")
    pages = document.get("pages")
    if not isinstance(tables, list) or not isinstance(pages, dict):
        raise ContractError("Docling document lacks tables or pages")
    all_cells: list[str] = []
    all_rows: list[list[str]] = []
    spanning = invalid = 0
    for table in tables:
        if not isinstance(table, dict) or not isinstance(table.get("data"), dict):
            raise ContractError("Docling table structure invalid")
        data = table.get("data", {})
        num_rows, num_cols = data.get("num_rows"), data.get("num_cols")
        prov = table.get("prov", [])
        if type(num_rows) is not int or type(num_cols) is not int or num_rows < 0 or num_cols < 0:
            raise ContractError("Docling table dimensions invalid")
        if not isinstance(prov, list) or not prov or any(
            not isinstance(item, dict)
            or type(item.get("page_no")) is not int
            or not 1 <= item["page_no"] <= len(pages)
            for item in prov
        ):
            raise ContractError("Docling table page provenance invalid")
        if not isinstance(data.get("table_cells"), list):
            raise ContractError("Docling table cells invalid")
        rows: list[list[str]] = [[] for _ in range(num_rows)]
        for cell in data["table_cells"]:
            if not isinstance(cell, dict):
                invalid += 1
                continue
            start_row, end_row = cell.get("start_row_offset_idx"), cell.get("end_row_offset_idx")
            start_col, end_col = cell.get("start_col_offset_idx"), cell.get("end_col_offset_idx")
            valid = (
                all(type(value) is int for value in (start_row, end_row, start_col, end_col))
                and 0 <= start_row < end_row <= num_rows
                and 0 <= start_col < end_col <= num_cols
                and isinstance(cell.get("text"), str)
            )
            if not valid:
                invalid += 1
                continue
            if end_row - start_row > 1 or end_col - start_col > 1:
                spanning += 1
            text = normalize(cell["text"])
            if text:
                all_cells.append(text)
                rows[start_row].append(text)
        all_rows.extend(row for row in rows if row)
    return all_cells, all_rows, {
        "tables": len(tables), "rows": len(all_rows), "nonempty_cells": len(all_cells),
        "spanning_cells": spanning, "invalid_cells": invalid,
    }


def _one_to_one_match(adjacency: list[list[int]], right_count: int) -> dict[int, int]:
    """Return left-to-right matches, never reusing one parser row or cell."""
    right_owner: dict[int, int] = {}

    def assign(left: int, seen: set[int]) -> bool:
        for right in adjacency[left]:
            if right in seen:
                continue
            seen.add(right)
            if right not in right_owner or assign(right_owner[right], seen):
                right_owner[right] = left
                return True
        return False

    for left in range(len(adjacency)):
        assign(left, set())
    return {left: right for right, left in right_owner.items() if 0 <= right < right_count}


def _surface_row_match(gold_row: list[str], parsed_row: list[str]) -> bool:
    if len(gold_row) > len(parsed_row):
        return False
    adjacency = [[index for index, cell in enumerate(parsed_row) if value in cell]
                 for value in gold_row]
    return len(_one_to_one_match(adjacency, len(parsed_row))) == len(gold_row)


def score_tables(gold_rows: dict[int, list[str]], parser_cells: list[str],
                 parser_rows: list[list[str]]) -> dict[str, Any]:
    """Separate surface presence, exact cells, and one-to-one complete row links."""
    gold_row_items = [[normalize(value) for value in row] for row in gold_rows.values()]
    parser_cells = [normalize(value) for value in parser_cells]
    parser_rows = [[normalize(value) for value in row] for row in parser_rows]
    gold_items = [value for row in gold_row_items for value in row]
    parser_counts = Counter(parser_cells)
    gold_counts = Counter(gold_items)
    surface_present = sum(any(value in cell for cell in parser_cells) for value in gold_items)
    exact_cells = sum(min(count, parser_counts[value]) for value, count in gold_counts.items())
    exact_adjacency = [
        [index for index, row in enumerate(parser_rows) if not Counter(values) - Counter(row)]
        for values in gold_row_items
    ]
    exact_matches = _one_to_one_match(exact_adjacency, len(parser_rows))
    strict_adjacency = [
        [index for index, row in enumerate(parser_rows) if Counter(values) == Counter(row)]
        for values in gold_row_items
    ]
    strict_matches = _one_to_one_match(strict_adjacency, len(parser_rows))
    surface_adjacency = [
        [index for index, row in enumerate(parser_rows) if _surface_row_match(values, row)]
        for values in gold_row_items
    ]
    surface_matches = _one_to_one_match(surface_adjacency, len(parser_rows))
    return {
        "gold_rows": len(gold_rows),
        "gold_cells": len(gold_items),
        "short_gold_cells_under_3_chars": sum(len(value) < 3 for value in gold_items),
        "gold_cell_surface_present_in_any_table_cell": surface_present,
        "gold_cell_exact_text_one_to_one": exact_cells,
        "complete_rows_surface_colocated_one_to_one": len(surface_matches),
        "complete_rows_exact_cells_one_to_one": len(exact_matches),
        "complete_rows_exact_multiset_one_to_one": len(strict_matches),
        "gold_cells_in_exact_linked_rows": sum(len(gold_row_items[left]) for left in exact_matches),
    }


def native_text_chars(path: Path) -> tuple[int, int]:
    import pypdfium2

    document = pypdfium2.PdfDocument(path)
    try:
        count = 0
        for page in document:
            text_page = page.get_textpage()
            try:
                count += len(text_page.get_text_range())
            finally:
                text_page.close()
                page.close()
        return len(document), count
    finally:
        document.close()


def create_converter(ocr_mode: str) -> Any:
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import (
        AcceleratorDevice,
        AcceleratorOptions,
        OcrMode,
        PdfPipelineOptions,
        RapidOcrOptions,
        TableFormerMode,
        TableStructureOptions,
    )
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions(
        do_ocr=True,
        do_table_structure=True,
        table_structure_options=TableStructureOptions(mode=TableFormerMode.ACCURATE, do_cell_matching=True),
        do_picture_classification=False,
        do_picture_description=False,
        do_chart_extraction=False,
        do_formula_enrichment=False,
        do_code_enrichment=False,
        generate_page_images=False,
        generate_picture_images=False,
        generate_table_images=False,
        enable_remote_services=False,
        allow_external_plugins=False,
        document_timeout=DOCUMENT_TIMEOUT_SECONDS,
        accelerator_options=AcceleratorOptions(num_threads=CPU_THREADS, device=AcceleratorDevice.CPU),
        ocr_options=RapidOcrOptions(lang=["en"], backend="torch", mode=OcrMode(ocr_mode)),
    )
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)})


def score_saved(output_dir: Path, gold_path: Path, selected: list[dict[str, Any]]) -> dict[str, Any]:
    if sha256_file(gold_path) != GOLD_SHA256:
        raise ContractError("frozen VRDU gold hash mismatch")
    all_gold = load_jsonl(gold_path, kind="gold")
    selected_ids = {row["doc_id"] for row in selected}
    if not selected_ids <= set(all_gold):
        raise ContractError("selected public PDFs missing from frozen gold")
    per_document = []
    for row in selected:
        doc_id = row["doc_id"]
        receipt = json.loads((output_dir / "docs" / doc_id / "conversion.json").read_text(encoding="utf-8"))
        if receipt["source_sha256"] != row["source_sha256"]:
            raise ContractError("conversion source hash differs from frozen selection")
        document_path = output_dir / "docs" / doc_id / "document.json"
        try:
            document = json.loads(document_path.read_text(encoding="utf-8")) if document_path.exists() else None
            cells, rows, parser_stats = parsed_tables(document)
            parser_status = "valid" if document is not None else "missing"
        except (ContractError, OSError, ValueError, TypeError):
            cells, rows, parser_stats = parsed_tables(None)
            parser_status = "invalid"
        gold_rows = gold_linked_rows(all_gold[doc_id])
        metrics = score_tables(gold_rows, cells, rows)
        per_document.append({
            "doc_id": doc_id, "source_sha256": row["source_sha256"],
            "conversion_status": receipt["status"], "duration_ms": receipt["duration_ms"],
            "page_count": receipt.get("page_count"), "native_text_chars": receipt.get("native_text_chars"),
            "ocr_mode": receipt.get("ocr_mode"), "parser_status": parser_status,
            "parser": parser_stats, "metrics": metrics,
        })
    total_keys = list(per_document[0]["metrics"])
    aggregate = {key: sum(doc["metrics"][key] for doc in per_document) for key in total_keys}
    parser_keys = list(per_document[0]["parser"])
    parser_totals = {key: sum(doc["parser"][key] for doc in per_document) for key in parser_keys}
    return {
        "diagnostic_version": DIAGNOSTIC_VERSION,
        "scope": "Docling table text and unlabeled row grouping on twelve public ad-buy PDFs; no field attribution or end-to-end extraction.",
        "selected_documents": len(selected),
        "conversion_successes": sum(doc["conversion_status"] == "success" for doc in per_document),
        "conversion_failures_or_partial": sum(doc["conversion_status"] != "success" for doc in per_document),
        "missing_or_invalid_parser_outputs": sum(doc["parser_status"] != "valid" for doc in per_document),
        "duration_ms_sum": round(sum(doc["duration_ms"] for doc in per_document), 3),
        "parser_totals": parser_totals,
        "metrics": aggregate,
        "per_document": per_document,
        "matching_caveat": "Gold linked cells lack page evidence. Normalization is NFKC, casefold and whitespace collapse only. Presence permits substring and repeated reuse; exact cells are one-to-one by string. Complete rows require all gold cells in one parsed table row, with one-to-one gold-to-parser row assignment. Field ID or column mapping is not measured.",
    }


def run(*, selection: Path, cohort: Path, corpus_root: Path, gold: Path,
        model_artifacts: Path, hf_home: Path, output_dir: Path) -> dict[str, Any]:
    selected = verify_selection(selection, cohort, corpus_root)
    if sha256_file(gold) != GOLD_SHA256:
        raise ContractError("frozen VRDU gold hash mismatch")
    model_receipt = verify_cached_models(model_artifacts)
    if output_dir.exists():
        raise ContractError("output directory must be new so partial runs are not overwritten")
    if output_dir.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
        raise ContractError("raw parser outputs must stay outside the repository")
    os.environ["HF_HOME"] = str(hf_home)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["OMP_NUM_THREADS"] = str(CPU_THREADS)
    os.environ["MKL_NUM_THREADS"] = str(CPU_THREADS)
    os.environ["OPENBLAS_NUM_THREADS"] = str(CPU_THREADS)
    output_dir.mkdir(parents=True)
    converters: dict[str, Any] = {}
    started_utc = datetime.now(timezone.utc).isoformat()
    for index, row in enumerate(selected, 1):
        doc_id = row["doc_id"]
        source = source_path(corpus_root, row["source_id"])
        directory = output_dir / "docs" / doc_id
        directory.mkdir(parents=True)
        started = time.perf_counter()
        receipt: dict[str, Any] = {
            "doc_id": doc_id, "source_sha256": row["source_sha256"],
            "status": "failed", "duration_ms": 0.0,
        }
        try:
            page_count, text_chars = native_text_chars(source)
            receipt.update({"page_count": page_count, "native_text_chars": text_chars})
            if page_count > MAX_PAGES:
                receipt["status"] = "over_page_limit"
            else:
                mode = "full_page" if text_chars < NATIVE_TEXT_THRESHOLD else "default"
                receipt["ocr_mode"] = mode
                if mode not in converters:
                    converters[mode] = create_converter(mode)
                result = converters[mode].convert(
                    source, raises_on_error=False, max_num_pages=MAX_PAGES, max_file_size=MAX_FILE_BYTES,
                )
                receipt["status"] = str(getattr(result.status, "value", result.status)).lower()
                receipt["error_count"] = len(result.errors)
                if result.document is not None:
                    _write_json(directory / "document.json", result.document.export_to_dict())
        # A malformed PDF must remain in the twelve-document denominator.
        except Exception as exc:  # noqa: BLE001
            receipt["status"] = "exception"
            receipt["exception_type"] = type(exc).__name__
        receipt["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
        _write_json(directory / "conversion.json", receipt)
        print(f"{index}/{len(selected)} {doc_id} {receipt['status']} {receipt['duration_ms']}ms", flush=True)
    score = score_saved(output_dir, gold, selected)
    _write_json(output_dir / "score.json", score)
    metadata = {
        "diagnostic_version": DIAGNOSTIC_VERSION, "complete": True,
        "started_utc": started_utc, "completed_utc": datetime.now(timezone.utc).isoformat(),
        "selection_sha256": SELECTION_SHA256, "cohort_sha256": COHORT_SHA256, "gold_sha256": GOLD_SHA256,
        "runner_sha256": sha256_file(Path(__file__)), "source_hashes_verified": True,
        "selected_documents": len(selected), "conversion_successes": score["conversion_successes"],
        "conversion_failures_or_partial": score["conversion_failures_or_partial"],
        "missing_or_invalid_parser_outputs": score["missing_or_invalid_parser_outputs"],
        "versions": {name: importlib.metadata.version(name) for name in
                     ("docling", "docling-core", "docling-parse", "rapidocr", "torch", "pypdfium2")},
        "model_artifacts": model_receipt,
        "configuration": {
            "device": "cpu", "threads": CPU_THREADS, "tableformer_mode": "accurate",
            "do_cell_matching": True, "document_timeout_seconds": DOCUMENT_TIMEOUT_SECONDS,
            "max_pages": MAX_PAGES, "max_file_bytes": MAX_FILE_BYTES,
            "ocr": "RapidOCR torch en; full_page only when native chars <100",
            "remote_services": False, "external_plugins": False,
        },
        "raw_document_outputs_outside_git": True,
        "score_sha256": sha256_file(output_dir / "score.json"),
    }
    _write_json(output_dir / "run.json", metadata)
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=Path(__file__).parent / "fixtures" / "vrdu_ad_buy_table12.jsonl")
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--model-artifacts", type=Path, required=True)
    parser.add_argument("--hf-home", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--score", action="store_true")
    args = parser.parse_args()
    selected = verify_selection(args.selection, args.cohort, args.corpus_root)
    if args.check:
        print(json.dumps({"selected": len(selected), "selection_sha256": SELECTION_SHA256,
                          "source_hashes_verified": True}, indent=2))
        return 0
    if args.score:
        result = score_saved(args.output_dir, args.gold, selected)
        print(json.dumps({"selected": result["selected_documents"], "metrics": result["metrics"]}, indent=2))
        return 0
    result = run(selection=args.selection, cohort=args.cohort, corpus_root=args.corpus_root,
                 gold=args.gold, model_artifacts=args.model_artifacts,
                 hf_home=args.hf_home, output_dir=args.output_dir)
    print(json.dumps({"output_dir": str(args.output_dir), "selected": result["selected_documents"],
                      "successes": result["conversion_successes"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
