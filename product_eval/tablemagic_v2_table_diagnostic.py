"""HTML-only table scoring and separate cell-box audit for PP-TableMagic v2.

The frozen 12-document gold is opened only after conversion. Box/text matches
are diagnostics, never automatic proof that an HTML cell is source-grounded.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from product_eval.contracts import ContractError, load_jsonl
from product_eval.docling_table_diagnostic import (
    GOLD_SHA256,
    _one_to_one_match,
    gold_linked_rows,
    normalize,
    score_tables,
    sha256_file,
)

EXPECTED_GOLD_ROWS = 219
EXPECTED_GOLD_CELLS = 808
STAT_KEYS = (
    "tables", "valid_html_tables", "invalid_html_tables", "rows", "nonempty_cells",
    "physical_html_cells", "valid_cell_boxes", "invalid_cell_boxes",
    "valid_table_regions", "invalid_table_regions", "tables_with_equal_cell_counts",
    "ocr_tokens", "valid_ocr_boxes", "invalid_ocr_boxes",
    "html_cells_with_any_exact_ocr_box", "html_cells_with_unique_exact_ocr_box",
)


def _empty_stats() -> dict[str, int]:
    return dict.fromkeys(STAT_KEYS, 0)


def _rectangle(value: Any, width: int, height: int) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    if any(type(number) not in (int, float) or not math.isfinite(number) for number in value):
        return None
    x0, y0, x1, y1 = (float(number) for number in value)
    if not (0 <= x0 < x1 <= width + 1 and 0 <= y0 < y1 <= height + 1):
        return None
    return [x0, y0, x1, y1]


def _table_html(markup: Any) -> tuple[list[str], list[list[str]], list[str]] | None:
    """Keep spans on their start row, as in the prior locked HTML scorer."""
    from lxml import etree, html

    if not isinstance(markup, str) or "<table" not in markup.lower():
        return None
    try:
        fragments = html.fragments_fromstring(markup)
        tables = [element for item in fragments if isinstance(item, html.HtmlElement)
                  for element in ([item] if item.tag.lower() == "table" else item.xpath(".//table"))]
        if len(tables) != 1 or tables[0].xpath(".//table"):
            return None
        cells: list[str] = []
        rows: list[list[str]] = []
        physical: list[str] = []
        for row in tables[0].xpath(".//tr"):
            row_cells = []
            for cell in row.xpath("./th|./td"):
                value = normalize(" ".join(cell.itertext()))
                physical.append(value)
                if value:
                    cells.append(value)
                    row_cells.append(value)
            if row_cells:
                rows.append(row_cells)
        return cells, rows, physical
    except (etree.LxmlError, TypeError, ValueError):
        return None


def _box_texts(boxes: list[list[float]], ocr: Any, width: int,
               height: int, stats: dict[str, int]) -> list[str]:
    if not isinstance(ocr, dict):
        return [""] * len(boxes)
    texts, raw_boxes = ocr.get("rec_texts"), ocr.get("rec_boxes")
    if not isinstance(texts, list) or not isinstance(raw_boxes, list):
        return [""] * len(boxes)
    stats["ocr_tokens"] += len(texts)
    if len(texts) != len(raw_boxes):
        stats["invalid_ocr_boxes"] += max(len(texts), len(raw_boxes))
        return [""] * len(boxes)
    tokens = []
    for text, raw_box in zip(texts, raw_boxes, strict=True):
        rectangle = _rectangle(raw_box, width, height)
        if rectangle is None or not isinstance(text, str):
            stats["invalid_ocr_boxes"] += 1
            continue
        stats["valid_ocr_boxes"] += 1
        tokens.append((text, (rectangle[0] + rectangle[2]) / 2,
                       (rectangle[1] + rectangle[3]) / 2))
    return [normalize(" ".join(text for text, x, y in tokens
                               if box[0] <= x <= box[2] and box[1] <= y <= box[3]))
            for box in boxes]


def table_strings(pages: list[dict[str, Any]],
                  geometries: list[dict[str, Any]]) -> tuple[list[str], list[list[str]], dict[str, int]]:
    """Read only official `pred_html`; audit geometry independently of scoring."""
    if len(pages) != len(geometries):
        raise ContractError("table page and geometry counts differ")
    cells: list[str] = []
    rows: list[list[str]] = []
    stats = _empty_stats()
    for page_index, (output, geometry) in enumerate(zip(pages, geometries, strict=True)):
        page = output.get("res", output)
        if not isinstance(page, dict) or page.get("page_index") != page_index:
            raise ContractError("TableMagic page order/index is incomplete")
        settings = page.get("model_settings")
        if not isinstance(settings, dict) or any(settings.get(key) is not expected for key, expected in (
            ("use_layout_detection", True), ("use_ocr_model", True),
            ("use_doc_preprocessor", False),
        )):
            raise ContractError("TableMagic output does not use the frozen full table profile")
        tables = page.get("table_res_list")
        layout = page.get("layout_det_res")
        width, height = geometry.get("image_width"), geometry.get("image_height")
        region_ids = geometry.get("table_region_ids")
        if (not isinstance(tables, list) or not isinstance(layout, dict)
                or not isinstance(layout.get("boxes"), list)
                or type(width) is not int or type(height) is not int
                or width <= 0 or height <= 0 or not isinstance(region_ids, list)
                or geometry.get("page_index") != page_index
                or len(region_ids) != len(tables)
                or any(type(value) is not int or value <= 0 for value in region_ids)):
            raise ContractError("TableMagic page lacks tables, layout or source geometry")
        for region in layout.get("boxes", []):
            if not isinstance(region, dict) or str(region.get("label", "")).lower() != "table":
                continue
            key = "valid_table_regions" if _rectangle(region.get("coordinate"), width, height) else "invalid_table_regions"
            stats[key] += 1
        for table in tables:
            stats["tables"] += 1
            if not isinstance(table, dict):
                stats["invalid_html_tables"] += 1
                continue
            parsed = _table_html(table.get("pred_html"))
            if parsed is None:
                stats["invalid_html_tables"] += 1
                continue
            stats["valid_html_tables"] += 1
            table_cells, table_rows, physical = parsed
            cells.extend(table_cells)
            rows.extend(table_rows)
            stats["physical_html_cells"] += len(physical)
            raw_boxes = table.get("cell_box_list")
            boxes = []
            if isinstance(raw_boxes, list):
                for item in raw_boxes:
                    rectangle = _rectangle(item, width, height)
                    if rectangle is None:
                        stats["invalid_cell_boxes"] += 1
                    else:
                        boxes.append(rectangle)
                        stats["valid_cell_boxes"] += 1
                if len(raw_boxes) == len(physical) and not any(
                    _rectangle(item, width, height) is None for item in raw_boxes
                ):
                    stats["tables_with_equal_cell_counts"] += 1
            else:
                stats["invalid_cell_boxes"] += 1
            box_texts = _box_texts(boxes, table.get("table_ocr_pred"), width, height, stats)
            candidates = [[index for index, value in enumerate(box_texts) if value == text]
                          for text in physical if text]
            stats["html_cells_with_any_exact_ocr_box"] += sum(bool(item) for item in candidates)
            unique = [item[0] for item in candidates if len(item) == 1]
            counts = Counter(unique)
            stats["html_cells_with_unique_exact_ocr_box"] += sum(counts[item[0]] == 1
                                                                  for item in candidates if len(item) == 1)
    stats["rows"] = len(rows)
    stats["nonempty_cells"] = len(cells)
    return cells, rows, stats


def _manual_audit_candidates(doc_id: str, gold_rows: dict[int, list[str]],
                             pages: list[dict[str, Any]],
                             parser_rows: list[list[str]]) -> list[dict[str, Any]]:
    """Reconstruct the primary match, retaining page/table/row for the visual sample."""
    locators = []
    for page_index, output in enumerate(pages):
        page = output.get("res", output)
        for table_index, table in enumerate(page["table_res_list"]):
            parsed = _table_html(table.get("pred_html")) if isinstance(table, dict) else None
            if parsed is None:
                continue
            for html_row_index, values in enumerate(parsed[1]):
                locators.append({"page_index": page_index, "table_index": table_index,
                                 "html_nonempty_row_index": html_row_index,
                                 "parser_cells": values})
    if len(locators) != len(parser_rows):
        raise ContractError("manual audit row locators differ from primary parser rows")
    ids, gold_values = list(gold_rows), list(gold_rows.values())
    adjacency = [[index for index, row in enumerate(parser_rows)
                  if not Counter(values) - Counter(row)] for values in gold_values]
    matches = _one_to_one_match(adjacency, len(parser_rows))
    return [{"doc_id": doc_id, "gold_row_id": ids[gold_index],
             "gold_cells": gold_values[gold_index], "parser_row_index": parser_index,
             **locators[parser_index]}
            for gold_index, parser_index in sorted(matches.items(),
                                                    key=lambda pair: ids[pair[0]])]


def score_saved(output_dir: Path, gold_path: Path,
                selected: list[dict[str, Any]]) -> dict[str, Any]:
    """Rescore SHA-bound saved outputs with the unchanged 219-row denominator."""
    if sha256_file(gold_path) != GOLD_SHA256:
        raise ContractError("frozen VRDU gold hash mismatch")
    gold = load_jsonl(gold_path, kind="gold")
    per_document = []
    audit_candidates = []
    for source in selected:
        folder = output_dir / "docs" / source["doc_id"]
        receipt_file = folder / "conversion.json"
        receipt = (json.loads(receipt_file.read_text(encoding="utf-8")) if receipt_file.exists()
                   else {"status": "not_run", "source_sha256": source["source_sha256"],
                         "duration_ms": 0, "pages": []})
        if (receipt.get("doc_id", source["doc_id"]) != source["doc_id"]
                or receipt.get("source_sha256") != source["source_sha256"]):
            raise ContractError("conversion receipt identity differs from selection")
        pages: list[dict[str, Any]] = []
        geometries: list[dict[str, Any]] = []
        parser_status = "not_run"
        if receipt.get("status") == "success":
            entries = receipt.get("pages")
            if not isinstance(entries, list) or len(entries) != receipt.get("page_count"):
                raise ContractError("successful TableMagic document has missing pages")
            for index, entry in enumerate(entries):
                if (not isinstance(entry, dict) or entry.get("page_index") != index
                        or entry.get("file") != f"raw/page-{index:02d}.json"
                        or entry.get("raster_file") != f"raw/page-{index:02d}.png"
                        or entry.get("geometry_file") != f"raw/geometry-{index:02d}.json"):
                    raise ContractError("TableMagic receipt has invalid page index or path")
                page_file = folder / entry["file"]
                raster_file = folder / entry["raster_file"]
                geometry_file = folder / entry["geometry_file"]
                if (sha256_file(page_file) != entry["sha256"]
                        or sha256_file(raster_file) != entry["raster_sha256"]
                        or sha256_file(geometry_file) != entry["geometry_sha256"]):
                    raise ContractError("saved TableMagic page differs from receipt")
            try:
                for index, entry in enumerate(entries):
                    page_file, geometry_file = folder / entry["file"], folder / entry["geometry_file"]
                    pages.append(json.loads(page_file.read_text(encoding="utf-8")))
                    geometries.append(json.loads(geometry_file.read_text(encoding="utf-8")))
                cells, rows, parser = table_strings(pages, geometries)
                parser_status = "valid"
            except (ContractError, OSError, ValueError, TypeError, KeyError):
                cells, rows, parser = [], [], _empty_stats()
                parser_status = "invalid"
        else:
            cells, rows, parser = [], [], _empty_stats()
            if receipt.get("status") != "not_run":
                parser_status = "failed"
        gold_rows = gold_linked_rows(gold[source["doc_id"]])
        metrics = score_tables(gold_rows, cells, rows)
        if parser_status == "valid":
            candidates = _manual_audit_candidates(source["doc_id"], gold_rows, pages, rows)
            if len(candidates) != metrics["complete_rows_exact_cells_one_to_one"]:
                raise ContractError("manual audit candidates differ from primary matches")
            audit_candidates.extend(candidates)
        per_document.append({"doc_id": source["doc_id"], "source_sha256": source["source_sha256"],
                             "status": receipt["status"], "parser_status": parser_status,
                             "duration_ms": receipt.get("duration_ms", 0),
                             "parser": parser, "metrics": metrics})
    aggregate = {key: sum(item["metrics"][key] for item in per_document)
                 for key in per_document[0]["metrics"]}
    if (len(selected) != 12 or aggregate["gold_rows"] != EXPECTED_GOLD_ROWS
            or aggregate["gold_cells"] != EXPECTED_GOLD_CELLS):
        raise ContractError("frozen twelve-document linked table denominator changed")
    return {"selected_documents": len(selected),
            "conversion_successes": sum(item["status"] == "success" for item in per_document),
            "metrics": aggregate,
            "parser_totals": {key: sum(item["parser"][key] for item in per_document)
                              for key in STAT_KEYS},
            "per_document": per_document,
            "manual_overlay_audit": {"sample_rule": "first 20 exact matched rows in frozen document order, then ascending gold row ID; inspect every nonempty physical HTML cell",
                                     "max_rows": 20,
                                     "status": "pending_visual_review" if audit_candidates else "no_exact_matched_rows",
                                     "candidates": audit_candidates[:20]},
            "cell_alignment_caveat": "Exact OCR text in a detected box is a heuristic; official JSON has no HTML-cell-to-box ID. No field attribution."}
