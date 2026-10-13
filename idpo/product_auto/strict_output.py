"""Strict, locally checked value envelopes for an already confirmed schema.

The provider format is only a request hint. Every reply is decoded and checked
here before the existing source-grounding parser sees it.
"""

from __future__ import annotations

import json
import math
import unicodedata
from collections.abc import Mapping, Sequence

from idpo.product_auto.logic import MAX_FIELDS, MAX_LINKED_ROWS_PER_FIELD, parse_values_reply

PROFILE = "strict_confirmed_values_v1"
MAX_REPLY_BYTES = 1_000_000
_FIELD_TYPES = {"string", "integer", "decimal", "boolean", "date", "array[object]"}


def _field_types(fields: Sequence[Mapping[str, object]]) -> dict[str, str]:
    if not 1 <= len(fields) <= MAX_FIELDS:
        raise ValueError("Strict values require 1–24 confirmed fields")
    result: dict[str, str] = {}
    for field in fields:
        field_id, field_type = field.get("field_id"), field.get("type")
        if (not isinstance(field_id, str) or not 1 <= len(field_id) <= 64 or
                not field_id[0].isalpha() or field_id.endswith("_") or
                not all(char.isalnum() or char == "_" for char in field_id) or
                unicodedata.normalize("NFKC", field_id).lower() != field_id or
                field_id in result or not isinstance(field_type, str) or field_type not in _FIELD_TYPES):
            raise ValueError("Invalid or repeated strict confirmed field")
        result[field_id] = field_type
    return result


def compile_confirmed_values_response_format(fields: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Compile the pinned field set into the tested Chat Completions schema shape."""
    field_types = _field_types(fields)
    has_linked = "array[object]" in field_types.values()
    has_scalar = any(field_type != "array[object]" for field_type in field_types.values())
    value_types = (["string", "number", "boolean"] if has_scalar else []) + \
        (["array"] if has_linked else []) + ["null"]
    value_schema: dict[str, object] = {"type": value_types}
    if has_linked:
        value_schema["items"] = {"type": "object", "properties": {
            "row": {"type": "integer"}, "value": {"type": "string"},
            "page": {"type": "integer"}, "quote": {"type": "string"},
        }, "required": ["row", "value", "page", "quote"], "additionalProperties": False}
    envelope = {"type": "object", "properties": {"values": {"type": "array", "items": {
        "type": "object", "properties": {
            "field_id": {"type": "string", "enum": list(field_types)},
            "value": value_schema,
            "page": {"type": ["integer", "null"]},
            "quote": {"type": ["string", "null"]},
        }, "required": ["field_id", "value", "page", "quote"], "additionalProperties": False,
    }}}, "required": ["values"], "additionalProperties": False}
    return {"type": "json_schema", "json_schema": {
        "name": "docai_confirmed_values_v1", "strict": True, "schema": envelope,
    }}


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON property")
        result[key] = value
    return result


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Nonfinite JSON number")
    return number


def _reject_constant(_: str) -> None:
    raise ValueError("Nonfinite JSON number")


def _scalar_type_valid(field_type: str, value: object) -> bool:
    if value is None:
        return True
    if field_type in {"string", "date"}:
        return type(value) is str
    if field_type == "integer":
        return type(value) in {str, int}
    if field_type == "decimal":
        return type(value) in {str, int, float}
    if field_type == "boolean":
        return type(value) in {str, bool}
    return False


def parse_confirmed_strict_values_reply(
    text: str, fields: Sequence[Mapping[str, object]], pages: list[dict[str, object]],
) -> dict[str, dict[str, object]] | None:
    """Reject malformed, incomplete, or extra output before local grounding."""
    field_types = _field_types(fields)
    if not isinstance(text, str):
        return None
    try:
        if len(text.encode("utf-8")) > MAX_REPLY_BYTES:
            return None
        payload = json.loads(text, object_pairs_hook=_unique_object,
                             parse_float=_finite_float, parse_constant=_reject_constant)
    except (TypeError, ValueError, UnicodeError, RecursionError):
        return None
    if not isinstance(payload, dict) or set(payload) != {"values"} or not isinstance(payload["values"], list) or \
            len(payload["values"]) != len(field_types):
        return None
    seen_fields: set[str] = set()
    for item in payload["values"]:
        if not isinstance(item, dict) or set(item) != {"field_id", "value", "page", "quote"}:
            return None
        field_id, value, page, quote = (item[key] for key in ("field_id", "value", "page", "quote"))
        if not isinstance(field_id, str) or field_id not in field_types or field_id in seen_fields or \
                page is not None and (type(page) is not int or page < 1) or \
                quote is not None and (not isinstance(quote, str) or not quote or len(quote) > 24_000):
            return None
        seen_fields.add(field_id)
        field_type = field_types[field_id]
        if field_type != "array[object]":
            if not _scalar_type_valid(field_type, value):
                return None
            continue
        if value is None:
            continue
        if not isinstance(value, list) or len(value) > MAX_LINKED_ROWS_PER_FIELD:
            return None
        seen_rows: set[int] = set()
        for cell in value:
            if not isinstance(cell, dict) or set(cell) != {"row", "value", "page", "quote"} or \
                    type(cell["row"]) is not int or not 0 <= cell["row"] < MAX_LINKED_ROWS_PER_FIELD or \
                    cell["row"] in seen_rows or not isinstance(cell["value"], str) or \
                    not cell["value"].strip() or len(cell["value"]) > 500 or \
                    type(cell["page"]) is not int or cell["page"] < 1 or \
                    not isinstance(cell["quote"], str) or not cell["quote"] or len(cell["quote"]) > 24_000:
                return None
            seen_rows.add(cell["row"])
    return parse_values_reply(text, [dict(field) for field in fields], pages)
