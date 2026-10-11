"""Native-PDF table comparator on the frozen twelve VRDU ad-buy documents.

The two strategies are fixed before parsing. No OCR or per-document tuning is
performed. Gold is opened only after all source documents have been parsed.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
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
PDFPLUMBER_VERSION = "0.11.10"
PROFILES = {
    "lines": {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
    "text": {"vertical_strategy": "text", "horizontal_strategy": "text"},
}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def extract_source(source: Path, settings: dict[str, str]) -> dict[str, Any]:
    import pdfplumber

    tables = []
    native_chars = 0
    with pdfplumber.open(source) as pdf:
        page_count = len(pdf.pages)
        for page_number, page in enumerate(pdf.pages, 1):
            native_chars += len(page.chars)
            for table in page.find_tables(table_settings=settings):
                matrix = table.extract()
                tables.append({
                    "page": page_number,
                    "bbox": list(table.bbox),
                    "cells": [list(box) if box is not None else None for box in table.cells],
                    "rows": matrix,
                })
            page.close()
    return {"page_count": page_count, "native_chars": native_chars, "tables": tables}


def table_strings(raw: dict[str, Any]) -> tuple[list[str], list[list[str]], dict[str, int]]:
    tables = raw.get("tables")
    if not isinstance(tables, list):
        raise ContractError("pdfplumber output lacks tables")
    cells: list[str] = []
    rows: list[list[str]] = []
    for table in tables:
        if not isinstance(table, dict) or not isinstance(table.get("rows"), list):
            raise ContractError("pdfplumber table rows invalid")
        if type(table.get("page")) is not int or table["page"] < 1:
            raise ContractError("pdfplumber table page invalid")
        for row in table["rows"]:
            if not isinstance(row, list) or any(cell is not None and not isinstance(cell, str) for cell in row):
                raise ContractError("pdfplumber cell text invalid")
            strings = [normalize(cell) for cell in row if cell is not None and normalize(cell)]
            if strings:
                rows.append(strings)
                cells.extend(strings)
    return cells, rows, {"tables": len(tables), "rows": len(rows), "nonempty_cells": len(cells)}


def score_saved(output_dir: Path, gold_path: Path, selected: list[dict[str, Any]]) -> dict[str, Any]:
    if sha256_file(gold_path) != GOLD_SHA256:
        raise ContractError("frozen VRDU gold hash mismatch")
    gold = load_jsonl(gold_path, kind="gold")
    if not {row["doc_id"] for row in selected} <= set(gold):
        raise ContractError("selected public PDFs missing from frozen gold")
    by_profile: dict[str, Any] = {}
    for profile in PROFILES:
        per_document = []
        for row in selected:
            folder = output_dir / "docs" / row["doc_id"] / profile
            receipt = json.loads((folder / "conversion.json").read_text(encoding="utf-8"))
            if receipt.get("doc_id") != row["doc_id"] or receipt.get("source_sha256") != row["source_sha256"]:
                raise ContractError("pdfplumber conversion receipt differs from frozen selection")
            raw_path = folder / "tables.json"
            if sha256_file(raw_path) != receipt.get("tables_sha256"):
                raise ContractError("saved pdfplumber tables differ from conversion receipt")
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
            cells, rows, parser = table_strings(raw)
            metrics = score_tables(gold_linked_rows(gold[row["doc_id"]]), cells, rows)
            per_document.append({
                "doc_id": row["doc_id"], "source_sha256": row["source_sha256"],
                "status": receipt["status"], "duration_ms": receipt["duration_ms"],
                "page_count": raw["page_count"], "native_chars": raw["native_chars"],
                "parser": parser, "metrics": metrics,
            })
        by_profile[profile] = {
            "selected_documents": len(selected),
            "documents_with_tables": sum(doc["parser"]["tables"] > 0 for doc in per_document),
            "no_table_or_failed_documents": sum(doc["status"] != "success" for doc in per_document),
            "duration_ms_sum": round(sum(doc["duration_ms"] for doc in per_document), 3),
            "metrics": {key: sum(doc["metrics"][key] for doc in per_document)
                        for key in per_document[0]["metrics"]},
            "per_document": per_document,
        }
    return {
        "diagnostic_version": DIAGNOSTIC_VERSION,
        "scope": "Native-PDF table rows and cells only; no OCR, field attribution, or end-to-end extraction.",
        "profiles": by_profile,
        "matching_caveat": "Uses the same score_tables function and frozen linked gold as the Docling diagnostic. Presence and partial co-location are upper bounds; complete rows require one-to-one gold-to-parser row matching. Gold has no page evidence.",
    }


def run(*, selection: Path, cohort: Path, corpus_root: Path, gold: Path,
        output_dir: Path) -> dict[str, Any]:
    selected = verify_selection(selection, cohort, corpus_root)
    if sha256_file(gold) != GOLD_SHA256:
        raise ContractError("frozen VRDU gold hash mismatch")
    version = importlib.metadata.version("pdfplumber")
    if version != PDFPLUMBER_VERSION:
        raise ContractError(f"pdfplumber {PDFPLUMBER_VERSION} required; found {version}")
    if output_dir.exists():
        raise ContractError("output directory must be new so partial runs are not overwritten")
    if output_dir.resolve().is_relative_to(Path(__file__).resolve().parents[1]):
        raise ContractError("raw parser outputs must stay outside the repository")
    output_dir.mkdir(parents=True)
    started_utc = datetime.now(timezone.utc).isoformat()
    for index, row in enumerate(selected, 1):
        source = source_path(corpus_root, row["source_id"])
        for profile, settings in PROFILES.items():
            folder = output_dir / "docs" / row["doc_id"] / profile
            started = time.perf_counter()
            status = "exception"
            error_type = None
            try:
                raw = extract_source(source, settings)
                status = "success" if raw["tables"] else (
                    "no_native_text_no_tables" if raw["native_chars"] == 0 else "no_tables"
                )
            except Exception as exc:  # noqa: BLE001
                error_type = type(exc).__name__
                raw = {"page_count": None, "native_chars": None, "tables": []}
            raw_path = folder / "tables.json"
            write_json(raw_path, raw)
            write_json(folder / "conversion.json", {
                "doc_id": row["doc_id"], "source_sha256": row["source_sha256"],
                "profile": profile, "status": status, "exception_type": error_type,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                "tables_sha256": sha256_file(raw_path),
            })
        print(f"{index}/{len(selected)} {row['doc_id']} both profiles complete", flush=True)
    score = score_saved(output_dir, gold, selected)
    score_path = output_dir / "score.json"
    write_json(score_path, score)
    metadata = {
        "diagnostic_version": DIAGNOSTIC_VERSION, "complete": True,
        "started_utc": started_utc, "completed_utc": datetime.now(timezone.utc).isoformat(),
        "selection_sha256": SELECTION_SHA256, "gold_sha256": GOLD_SHA256,
        "source_hashes_verified": True, "selected_documents": len(selected),
        "runner_sha256": sha256_file(Path(__file__)),
        "pdfplumber_version": version,
        "pdfminer_six_version": importlib.metadata.version("pdfminer.six"),
        "profiles": PROFILES, "ocr": False, "score_sha256": sha256_file(score_path),
        "raw_outputs_outside_git": True,
    }
    write_json(output_dir / "run.json", metadata)
    return metadata


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, default=Path(__file__).parent / "fixtures" / "vrdu_ad_buy_table12.jsonl")
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--score", action="store_true")
    args = parser.parse_args()
    selected = verify_selection(args.selection, args.cohort, args.corpus_root)
    if args.check:
        print(json.dumps({"selected": len(selected), "selection_sha256": SELECTION_SHA256}, indent=2))
    elif args.score:
        score = score_saved(args.output_dir, args.gold, selected)
        print(json.dumps({name: item["metrics"] for name, item in score["profiles"].items()}, indent=2))
    else:
        result = run(selection=args.selection, cohort=args.cohort, corpus_root=args.corpus_root,
                     gold=args.gold, output_dir=args.output_dir)
        print(json.dumps({"selected": result["selected_documents"], "complete": result["complete"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
