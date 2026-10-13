"""Exact, row-indexed scores for the derived linked-field gold representation.

This is a diagnostic for the product evaluation contract, not the official VRDU
matcher. A row index is a document-local ordinal; it is meaningful only when the
candidate uses the same annotation ordering as the derived gold.
"""

from __future__ import annotations

from collections import Counter
from typing import Any


def _cells(values: dict[str, dict[str, Any]], field_ids: set[str], *, accepted_only: bool) -> set[tuple[str, int, str]]:
    result: set[tuple[str, int, str]] = set()
    for field_id in field_ids:
        record = values.get(field_id)
        if record is None or (accepted_only and record.get("status") != "accepted"):
            continue
        entries = record.get("value")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if accepted_only and isinstance(entry, dict) and entry.get("status", record.get("status")) != "accepted":
                continue
            if isinstance(entry, dict) and type(entry.get("row")) is int and isinstance(entry.get("value"), str):
                result.add((field_id, entry["row"], entry["value"]))
    return result


def _rows(cells: set[tuple[str, int, str]]) -> dict[int, tuple[tuple[str, str], ...]]:
    by_row: dict[int, list[tuple[str, str]]] = {}
    for field_id, row, value in cells:
        by_row.setdefault(row, []).append((field_id, value))
    return {row: tuple(sorted(fields)) for row, fields in by_row.items()}


def linked_row_counts(
    gold_schema: dict[str, dict[str, Any]],
    gold_values: dict[str, dict[str, Any]],
    proposed_schema: dict[str, dict[str, Any]],
    extracted_values: dict[str, dict[str, Any]],
) -> dict[str, Counter[str]]:
    """Count exact linked cells and complete rows before and after review gating."""
    gold_ids = {field_id for field_id, field in gold_schema.items() if field["type"] == "array[object]"}
    candidate_ids = {field_id for field_id, field in proposed_schema.items() if field["type"] == "array[object]"}
    candidate_ids |= {
        field_id for field_id, field in extracted_values.items()
        if isinstance(field.get("value"), list)
        and all(isinstance(entry, dict) and "row" in entry for entry in field["value"])
    }
    gold_cells = _cells(gold_values, gold_ids, accepted_only=False)
    proposed_cells = _cells(extracted_values, candidate_ids, accepted_only=False)
    accepted_cells = _cells(extracted_values, candidate_ids, accepted_only=True)
    gold_rows = _rows(gold_cells)
    proposed_rows = _rows(proposed_cells)
    accepted_rows = _rows(accepted_cells)
    result: dict[str, Counter[str]] = {
        "totals": Counter({
            "gold_linked_fields": len(gold_ids),
            "candidate_linked_fields": len(candidate_ids),
            "gold_cells": len(gold_cells),
            "gold_rows": len(gold_rows),
            "candidate_cells": len(proposed_cells),
            "candidate_rows": len(proposed_rows),
        }),
    }
    for name, actual in (("proposed_cells", proposed_cells), ("accepted_cells", accepted_cells)):
        result[name] = Counter({
            "tp": len(gold_cells & actual),
            "fp": len(actual - gold_cells),
            "fn": len(gold_cells - actual),
        })
    for name, actual in (("proposed_complete_rows", proposed_rows), ("accepted_complete_rows", accepted_rows)):
        exact = {row for row, fields in actual.items() if gold_rows.get(row) == fields}
        result[name] = Counter({
            "tp": len(exact),
            "fp": len(actual) - len(exact),
            "fn": len(gold_rows) - len(exact),
        })
    return result
