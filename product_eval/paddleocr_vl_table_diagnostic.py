"""Parser-only scorer for PaddleOCR-VL 1.6 table-region HTML on frozen ad-buy PDFs.

Only `parsing_res_list` blocks labeled `table` contribute cells or rows.
Table-region boxes are tracked separately; they are not cell-level evidence.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from product_eval.contracts import ContractError, load_jsonl
from product_eval.docling_table_diagnostic import (
    GOLD_SHA256,
    gold_linked_rows,
    normalize,
    score_tables,
    sha256_file,
)

EXPECTED_GOLD_ROWS = 219
EXPECTED_GOLD_CELLS = 808


def _rectangle(value: Any) -> list[float] | None:
    if (not isinstance(value, list) or len(value) != 4
            or any(isinstance(coordinate, bool) or not isinstance(coordinate, (int, float))
                   or not math.isfinite(coordinate) for coordinate in value)):
        return None
    x0, y0, x1, y1 = (float(coordinate) for coordinate in value)
    if x0 < 0 or y0 < 0 or x1 <= x0 or y1 <= y0:
        return None
    return [x0, y0, x1, y1]


def table_strings(page_outputs: list[dict[str, Any]]) -> tuple[list[str], list[list[str]], dict[str, int]]:
    """Extract each HTML table once from official page JSON, never Markdown."""
    from lxml import etree, html

    cells: list[str] = []
    rows: list[list[str]] = []
    table_blocks = valid_tables = invalid_tables = valid_boxes = invalid_boxes = 0
    for expected_page, output in enumerate(page_outputs):
        page = output.get("res", output)
        if not isinstance(page, dict) or page.get("page_index") != expected_page:
            raise ContractError("PaddleOCR-VL output page order/index is incomplete")
        settings = page.get("model_settings")
        if not isinstance(settings, dict) or settings.get("use_layout_detection") is not True:
            raise ContractError("PaddleOCR-VL full layout pipeline was not used")
        blocks = page.get("parsing_res_list")
        if not isinstance(blocks, list):
            raise ContractError("PaddleOCR-VL output lacks parsing_res_list")
        for block in blocks:
            if not isinstance(block, dict) or block.get("block_label") != "table":
                continue
            table_blocks += 1
            if _rectangle(block.get("block_bbox")) is None:
                invalid_boxes += 1
            else:
                valid_boxes += 1
            content = block.get("block_content")
            if not isinstance(content, str) or "<table" not in content.lower():
                invalid_tables += 1
                continue
            try:
                fragments = html.fragments_fromstring(content)
                tables = [element for item in fragments if isinstance(item, html.HtmlElement)
                          for element in ([item] if item.tag.lower() == "table" else item.xpath(".//table"))]
                if len(tables) != 1 or tables[0].xpath(".//table"):
                    invalid_tables += 1
                    continue
                valid_tables += 1
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
    return cells, rows, {"table_blocks": table_blocks, "valid_tables": valid_tables,
                         "invalid_tables": invalid_tables, "valid_region_boxes": valid_boxes,
                         "invalid_region_boxes": invalid_boxes, "rows": len(rows),
                         "nonempty_cells": len(cells)}


def score_saved(output_dir: Path, gold_path: Path, selected: list[dict[str, Any]]) -> dict[str, Any]:
    """Score immutable saved page JSON; all 12 gold sources remain in denominator."""
    if sha256_file(gold_path) != GOLD_SHA256:
        raise ContractError("frozen VRDU gold hash mismatch")
    gold = load_jsonl(gold_path, kind="gold")
    per_document = []
    for source in selected:
        folder = output_dir / "docs" / source["doc_id"]
        receipt_path = folder / "conversion.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.exists() else {
            "source_sha256": source["source_sha256"], "status": "not_run", "page_outputs": [],
            "duration_ms": 0,
        }
        if receipt.get("source_sha256") != source["source_sha256"]:
            raise ContractError("PaddleOCR-VL receipt source hash differs from lock")
        parser_status = "missing"
        cells: list[str] = []
        rows: list[list[str]] = []
        stats = {"table_blocks": 0, "valid_tables": 0, "invalid_tables": 0,
                 "valid_region_boxes": 0, "invalid_region_boxes": 0,
                 "rows": 0, "nonempty_cells": 0}
        if receipt.get("status") == "success":
            try:
                saved = receipt["page_outputs"]
                if not isinstance(saved, list) or len(saved) != receipt["page_count"]:
                    raise ContractError("PaddleOCR-VL receipt has incomplete pages")
                page_outputs = []
                for page_number, item in enumerate(saved):
                    path = folder / f"page-{page_number:02d}.json"
                    if item.get("file") != path.name or sha256_file(path) != item.get("sha256"):
                        raise ContractError("PaddleOCR-VL page JSON differs from receipt")
                    page_outputs.append(json.loads(path.read_text(encoding="utf-8")))
                cells, rows, stats = table_strings(page_outputs)
                parser_status = "valid"
            except (ContractError, OSError, ValueError, TypeError, KeyError, UnicodeError):
                parser_status = "invalid"
        metrics = score_tables(gold_linked_rows(gold[source["doc_id"]]), cells, rows)
        per_document.append({"doc_id": source["doc_id"], "source_sha256": source["source_sha256"],
                             "status": receipt.get("status"), "parser_status": parser_status,
                             "duration_ms": receipt.get("duration_ms"), "parser": stats,
                             "metrics": metrics, "page_count": receipt.get("page_count"),
                             "peak_process_tree_rss_bytes": receipt.get("peak_process_tree_rss_bytes"),
                             "min_host_available_bytes": receipt.get("min_host_available_bytes"),
                             "min_gpu_free_mib": receipt.get("min_gpu_free_mib")})
    aggregate = {key: sum(item["metrics"][key] for item in per_document)
                 for key in per_document[0]["metrics"]}
    if aggregate["gold_rows"] != EXPECTED_GOLD_ROWS or aggregate["gold_cells"] != EXPECTED_GOLD_CELLS:
        raise ContractError("frozen ad-buy row/cell denominator changed")
    return {"selected_documents": len(selected), "metrics": aggregate,
            "conversion_successes": sum(item["status"] == "success" for item in per_document),
            "missing_or_invalid_outputs": sum(item["parser_status"] != "valid" for item in per_document),
            "parser_totals": {key: sum(item["parser"][key] for item in per_document)
                              for key in per_document[0]["parser"]},
            "per_document": per_document}
