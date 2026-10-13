"""Exact positive-only CORD summary, linked-cell, and complete-row recall."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from product_eval.contracts import load_jsonl
from product_eval.datasets.cord_test import (
    ROW_FIELDS,
    SCALAR_FIELDS,
    CordSliceError,
    _doc_id,
    _sha256_file,
)


def _load_cohort(path: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    source_hashes: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            item = json.loads(line)
        except ValueError as exc:
            raise CordSliceError(f"Invalid cohort JSON at line {line_number}") from exc
        if not isinstance(item, dict) or not isinstance(item.get("doc_id"), str):
            raise CordSliceError(f"Invalid cohort receipt at line {line_number}")
        doc_id = item["doc_id"]
        source_path = item.get("source_path")
        source_hash = item.get("source_sha256")
        if (
            doc_id in result or not isinstance(source_path, str)
            or not isinstance(source_hash, str) or source_hash in source_hashes
        ):
            raise CordSliceError(f"Duplicate or incomplete cohort receipt: {doc_id}")
        source = Path(source_path)
        if not source.is_file() or _sha256_file(source) != source_hash:
            raise CordSliceError(f"CORD source image changed since cohort freeze: {doc_id}")
        if _doc_id(source.name, source_hash) != doc_id:
            raise CordSliceError(f"CORD runtime document ID mismatch: {doc_id}")
        result[doc_id] = item
        source_hashes.add(source_hash)
    if not result:
        raise CordSliceError("CORD cohort is empty")
    return result


def _outcome(value: Any, expected: str, field: dict[str, Any] | None, entry: dict[str, Any] | None = None) -> str:
    if field is None or value is None:
        return "not_proposed"
    if value != expected:
        return "wrong_or_unvalued"
    review_state = field["review_state"]
    status = entry.get("status", field["status"]) if entry is not None else field["status"]
    if status == "accepted" and review_state == "none":
        return "exact_accepted"
    if review_state == "completed":
        return "exact_post_review"
    if status == "needs_review" or review_state == "pending":
        return "exact_pending_review"
    return "exact_unaccepted_other"


def _candidate_cells(field: dict[str, Any] | None) -> dict[int, dict[str, Any]]:
    if field is None or not isinstance(field.get("value"), list):
        return {}
    return {
        item["row"]: item
        for item in field["value"]
        if isinstance(item, dict) and type(item.get("row")) is int and isinstance(item.get("value"), str)
    }


def _count(counter: Counter[str], per_field: dict[str, Counter[str]], field: str, outcome: str) -> None:
    counter["annotated"] += 1
    counter[outcome] += 1
    field_counts = per_field.setdefault(field, Counter())
    field_counts["annotated"] += 1
    field_counts[outcome] += 1


def score_cord_positive(cohort_path: Path, gold_path: Path, candidate_path: Path) -> dict[str, Any]:
    """Score only published positive values; undefined precision stays absent."""
    cohort = _load_cohort(cohort_path)
    gold = load_jsonl(gold_path, kind="gold")
    candidates = load_jsonl(candidate_path, kind="candidate")
    if set(gold) != set(cohort):
        raise CordSliceError("CORD gold IDs must equal the selected source cohort")
    if not set(candidates) <= set(cohort):
        raise CordSliceError("CORD candidate has a document outside the source cohort")
    scalars: Counter[str] = Counter()
    cells: Counter[str] = Counter()
    rows: Counter[str] = Counter()
    per_field: dict[str, Counter[str]] = {}
    for doc_id, record in gold.items():
        candidate = candidates.get(doc_id)
        predicted_fields = {
            item["field_id"]: item for item in candidate["extracted_values"]
        } if candidate else {}
        gold_values = {item["field_id"]: item["value"] for item in record["gold_values"]}
        gold_rows: dict[int, dict[str, str]] = {}
        candidate_rows: dict[int, dict[str, tuple[str, str]]] = {}
        for field, expected in gold_values.items():
            predicted = predicted_fields.get(field)
            if field in SCALAR_FIELDS:
                if not isinstance(expected, str) or not expected:
                    raise CordSliceError("CORD scalar gold contains a non-positive value")
                outcome = _outcome(predicted.get("value") if predicted else None, expected, predicted)
                _count(scalars, per_field, field, outcome)
                continue
            if field not in ROW_FIELDS or not isinstance(expected, list):
                raise CordSliceError(f"Unsupported CORD gold field: {field}")
            actual = _candidate_cells(predicted)
            for gold_cell in expected:
                row = gold_cell["row"]
                value = gold_cell["value"]
                if not isinstance(value, str) or not value:
                    raise CordSliceError("CORD linked gold contains a non-positive cell")
                gold_rows.setdefault(row, {})[field] = value
                predicted_cell = actual.get(row)
                outcome = _outcome(
                    predicted_cell.get("value") if predicted_cell else None,
                    value, predicted, predicted_cell,
                )
                _count(cells, per_field, field, outcome)
            for row, item in actual.items():
                candidate_rows.setdefault(row, {})[field] = (item["value"], _outcome(item["value"], item["value"], predicted, item))
        for row, expected_fields in gold_rows.items():
            if not {"item_name", "item_price"} <= set(expected_fields):
                continue
            rows["annotated"] += 1
            actual_fields = candidate_rows.get(row, {})
            if not all(actual_fields.get(field, (None, None))[0] == value for field, value in expected_fields.items()):
                rows["not_exact"] += 1
                continue
            statuses = {actual_fields[field][1] for field in expected_fields}
            if statuses == {"exact_accepted"}:
                rows["exact_accepted"] += 1
            elif "exact_pending_review" in statuses:
                rows["exact_pending_review"] += 1
            elif "exact_post_review" in statuses:
                rows["exact_post_review"] += 1
            else:
                rows["exact_unaccepted_other"] += 1
    if not scalars["annotated"] or not cells["annotated"] or not rows["annotated"]:
        raise CordSliceError("CORD selected split lacks scalar, linked-cell or complete-row gold")
    return {
        "dataset_id": "cord_v2_test",
        "metric_scope": "Exact raw-string positive recall only. Linked cells and complete rows require the same published menu row ordinal. No absent-field, precision, schema F1 or OCR evidence claims.",
        "source_count": len(cohort),
        "source_hash_verified_count": len(cohort),
        "candidate_count": len(candidates),
        "missing_candidate_count": len(set(cohort) - set(candidates)),
        "positive_scalars": dict(sorted(scalars.items())),
        "exact_proposed_scalar_recall": (
            scalars["exact_accepted"] + scalars["exact_pending_review"] + scalars["exact_post_review"]
        ) / scalars["annotated"],
        "exact_accepted_scalar_recall": scalars["exact_accepted"] / scalars["annotated"],
        "positive_linked_cells": dict(sorted(cells.items())),
        "exact_proposed_cell_recall": (
            cells["exact_accepted"] + cells["exact_pending_review"] + cells["exact_post_review"]
        ) / cells["annotated"],
        "exact_accepted_cell_recall": cells["exact_accepted"] / cells["annotated"],
        "positive_complete_rows": dict(sorted(rows.items())),
        "exact_proposed_complete_row_recall": (
            rows["exact_accepted"] + rows["exact_pending_review"] + rows["exact_post_review"]
        ) / rows["annotated"],
        "exact_accepted_complete_row_recall": rows["exact_accepted"] / rows["annotated"],
        "per_field": {
            field: dict(sorted(field_counts.items())) for field, field_counts in sorted(per_field.items())
        },
        "input_sha256": {
            "cohort.jsonl": _sha256_file(cohort_path),
            "gold.jsonl": _sha256_file(gold_path),
            "candidates.jsonl": _sha256_file(candidate_path),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = score_cord_positive(args.cohort, args.gold, args.candidate)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "source_count": report["source_count"],
        "exact_proposed_scalar_recall": report["exact_proposed_scalar_recall"],
        "exact_accepted_scalar_recall": report["exact_accepted_scalar_recall"],
        "exact_proposed_cell_recall": report["exact_proposed_cell_recall"],
        "exact_proposed_complete_row_recall": report["exact_proposed_complete_row_recall"],
    }, indent=2))


if __name__ == "__main__":
    main()
