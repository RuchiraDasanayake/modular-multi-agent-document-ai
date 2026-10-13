"""Validation for product evaluation JSONL; intentionally independent of IDPO."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

CONTRACT_VERSION = 1
DOCUMENT_STATUSES = {"processed", "needs_review", "unsupported", "failed"}
FIELD_STATUSES = {"accepted", "needs_review", "missing", "rejected"}
REVIEW_STATES = {"none", "pending", "completed"}
MEASUREMENTS = {
    "latency_ms",
    "api_cost_usd",
    "compute_cost_usd",
    "total_cost_usd",
    "review_minutes",
}


class ContractError(ValueError):
    """An input record cannot be interpreted under contract version 1."""


def load_jsonl(path: str | Path, *, kind: str) -> dict[str, dict[str, Any]]:
    if kind not in {"gold", "candidate"}:
        raise ValueError("kind must be 'gold' or 'candidate'")
    records: dict[str, dict[str, Any]] = {}
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line, parse_constant=_reject_nonfinite)
            except (ValueError, json.JSONDecodeError) as exc:
                raise ContractError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            label = f"{path}:{line_number}"
            validate_record(record, kind=kind, label=label)
            doc_id = record["doc_id"]
            if doc_id in records:
                raise ContractError(f"{label}: duplicate doc_id {doc_id!r}")
            records[doc_id] = record
    if not records and kind == "gold":
        raise ContractError(f"{path}: no records")
    return records


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"non-finite JSON number {value}")


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be an object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractError(f"{label} must be an array")
    return value


def _require_name(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} must be a non-empty string")
    return value


def _unique_fields(items: Any, label: str) -> dict[str, dict[str, Any]]:
    fields: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(_require_list(items, label)):
        item = _require_object(raw, f"{label}[{index}]")
        field_id = _require_name(item.get("field_id"), f"{label}[{index}].field_id")
        if field_id in fields:
            raise ContractError(f"{label}: duplicate field_id {field_id!r}")
        fields[field_id] = item
    return fields


def _validate_schema(schema: Any, label: str, *, gold: bool) -> dict[str, dict[str, Any]]:
    fields = _unique_fields(schema, label)
    for field_id, item in fields.items():
        field_label = f"{label}.{field_id}"
        _require_name(item.get("type"), f"{field_label}.type")
        if "group" in item and item["group"] is not None:
            _require_name(item["group"], f"{field_label}.group")
        if gold and not isinstance(item.get("critical"), bool):
            raise ContractError(f"{field_label}.critical must be boolean")
    return fields


def _validate_gold_evidence(value: Any, pages: dict[int, str], label: str) -> None:
    evidence = _require_object(value, label)
    page = evidence.get("page")
    start = evidence.get("start")
    end = evidence.get("end")
    quote = evidence.get("quote")
    if type(page) is not int or page not in pages:
        raise ContractError(f"{label}.page must reference a source page")
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(pages[page]):
        raise ContractError(f"{label} has an invalid half-open character span")
    if not isinstance(quote, str) or quote != pages[page][start:end]:
        raise ContractError(f"{label}.quote must equal the source text span")


def _validate_linked_entries(value: Any, label: str) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        raise ContractError(f"{label} must be null or a row-indexed array")
    seen_rows: set[int] = set()
    for index, raw in enumerate(value):
        entry = _require_object(raw, f"{label}[{index}]")
        row = entry.get("row")
        if type(row) is not int or row < 0 or row in seen_rows:
            raise ContractError(f"{label}[{index}].row must be a unique non-negative integer")
        seen_rows.add(row)
        _require_name(entry.get("value"), f"{label}[{index}].value")
        if "status" in entry and entry["status"] not in FIELD_STATUSES:
            raise ContractError(f"{label}[{index}].status is invalid")
        if "evidence" in entry and entry["evidence"] is not None and not isinstance(entry["evidence"], dict):
            raise ContractError(f"{label}[{index}].evidence must be an object or null")


def validate_record(record: Any, *, kind: str, label: str = "record") -> None:
    record = _require_object(record, label)
    if type(record.get("contract_version")) is not int or record["contract_version"] != CONTRACT_VERSION:
        raise ContractError(f"{label}.contract_version must be {CONTRACT_VERSION}")
    _require_name(record.get("doc_id"), f"{label}.doc_id")

    if kind == "gold":
        pages: dict[int, str] = {}
        for index, raw in enumerate(_require_list(record.get("pages"), f"{label}.pages")):
            page = _require_object(raw, f"{label}.pages[{index}]")
            number = page.get("page")
            if type(number) is not int or number < 1 or number in pages:
                raise ContractError(f"{label}.pages[{index}].page must be a unique positive integer")
            if not isinstance(page.get("text"), str):
                raise ContractError(f"{label}.pages[{index}].text must be a string")
            pages[number] = page["text"]
        schema = _validate_schema(record.get("gold_schema"), f"{label}.gold_schema", gold=True)
        values = _unique_fields(record.get("gold_values"), f"{label}.gold_values")
        if values.keys() != schema.keys():
            raise ContractError(f"{label}.gold_values must contain every gold_schema field exactly once, including nulls")
        for field_id, item in values.items():
            if "value" not in item:
                raise ContractError(f"{label}.gold_values.{field_id}.value is required (null means absent)")
            if schema[field_id]["type"] == "array[object]":
                _validate_linked_entries(item["value"], f"{label}.gold_values.{field_id}.value")
            if item["value"] is None and item.get("evidence") is not None:
                raise ContractError(f"{label}.gold_values.{field_id}: absent values cannot have evidence")
            if item.get("evidence") is not None:
                _validate_gold_evidence(item["evidence"], pages, f"{label}.gold_values.{field_id}.evidence")
        return

    if kind != "candidate":
        raise ValueError("kind must be 'gold' or 'candidate'")
    status = record.get("document_status")
    if not isinstance(status, str) or status not in DOCUMENT_STATUSES:
        raise ContractError(f"{label}.document_status must be one of {sorted(DOCUMENT_STATUSES)}")
    schema = _validate_schema(record.get("proposed_schema"), f"{label}.proposed_schema", gold=False)
    values = _unique_fields(record.get("extracted_values"), f"{label}.extracted_values")
    for field_id, item in values.items():
        field_label = f"{label}.extracted_values.{field_id}"
        if "value" not in item:
            raise ContractError(f"{field_label}.value is required (null means absent)")
        if isinstance(item["value"], list) or (
            field_id in schema and schema[field_id]["type"] == "array[object]"
        ):
            _validate_linked_entries(item["value"], f"{field_label}.value")
        if not isinstance(item.get("status"), str) or item["status"] not in FIELD_STATUSES:
            raise ContractError(f"{field_label}.status must be one of {sorted(FIELD_STATUSES)}")
        if not isinstance(item.get("review_state"), str) or item["review_state"] not in REVIEW_STATES:
            raise ContractError(f"{field_label}.review_state must be one of {sorted(REVIEW_STATES)}")
        if "evidence" in item and item["evidence"] is not None and not isinstance(item["evidence"], dict):
            raise ContractError(f"{field_label}.evidence must be an object or null")
    measurements = record.get("measurements", {})
    _require_object(measurements, f"{label}.measurements")
    for name in MEASUREMENTS:
        if name not in measurements:
            continue
        value = measurements[name]
        if type(value) not in {int, float} or not math.isfinite(value) or value < 0:
            raise ContractError(f"{label}.measurements.{name} must be a finite non-negative number")
