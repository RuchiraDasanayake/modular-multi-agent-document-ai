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
PROFILE_V2 = "strict_confirmed_values_v2"
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


def compile_confirmed_values_response_format_v2(
    fields: Sequence[Mapping[str, object]], *, allow_unquoted_cells: bool = False,
) -> dict[str, object]:
    """Require each confirmed field by ID in the provider-facing object."""
    properties: dict[str, object] = {}
    scalar_types = {
        "string": ["string", "null"], "date": ["string", "null"],
        "integer": ["integer", "string", "null"],
        "decimal": ["number", "string", "null"],
        "boolean": ["boolean", "string", "null"],
    }
    field_types = _field_types(fields)
    for field_id, field_type in field_types.items():
        if field_type == "array[object]":
            value_schema: dict[str, object] = {"type": ["array", "null"], "items": {
                "type": "object", "properties": {
                    "row": {"type": "integer"}, "value": {"type": "string"},
                    "page": {"type": "integer"},
                    "quote": {"type": ["string", "null"] if allow_unquoted_cells else "string"},
                }, "required": ["row", "value", "page", "quote"], "additionalProperties": False,
            }}
        else:
            value_schema = {"type": scalar_types[field_type]}
        properties[field_id] = {"type": "object", "properties": {
            "value": value_schema,
            "page": {"type": ["integer", "null"]},
            "quote": {"type": ["string", "null"]},
        }, "required": ["value", "page", "quote"], "additionalProperties": False}
    envelope = {"type": "object", "properties": {"values": {
        "type": "object", "properties": properties,
        "required": list(field_types), "additionalProperties": False,
    }}, "required": ["values"], "additionalProperties": False}
    return {"type": "json_schema", "json_schema": {
        "name": "docai_confirmed_values_v2", "strict": True, "schema": envelope,
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
    if _decode_confirmed_values(text, fields) is None:
        return None
    return parse_values_reply(text, [dict(field) for field in fields], pages)


def project_confirmed_values_v2_reply(
    text: str, fields: Sequence[Mapping[str, object]], pages: list[dict[str, object]],
    *, allow_unquoted_cells: bool = False,
) -> str | None:
    """Validate the raw v2 wire reply before projecting into the v1 local parser.

    The returned string is transient internal input, never provider provenance.
    """
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
    if not isinstance(payload, dict) or set(payload) != {"values"} or \
            not isinstance(payload["values"], dict) or set(payload["values"]) != set(field_types):
        return None
    if not pages or any(not isinstance(page, dict) or type(page.get("page")) is not int or
                        page["page"] < 1 or not isinstance(page.get("text"), str) for page in pages):
        return None
    page_ids = {page["page"] for page in pages}
    if len(page_ids) != len(pages):
        return None
    projected = []
    for field_id in field_types:
        item = payload["values"][field_id]
        if not isinstance(item, dict) or set(item) != {"value", "page", "quote"}:
            return None
        value, page, quote = item["value"], item["page"], item["quote"]
        if page is not None and (type(page) is not int or page not in page_ids):
            return None
        if value is None and (page is not None or quote is not None):
            return None
        if field_types[field_id] == "array[object]":
            if page is not None or quote is not None:
                return None
            if isinstance(value, list) and any(not isinstance(cell, dict) or
                                               type(cell.get("page")) is not int or
                                               cell["page"] not in page_ids for cell in value):
                return None
        projected.append({"field_id": field_id, **item})
    try:
        local_text = json.dumps({"values": projected}, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        return None
    if _decode_confirmed_values(local_text, fields, allow_unquoted_cells=allow_unquoted_cells) is None:
        return None
    return local_text


def parse_confirmed_strict_values_reply_v2(
    text: str, fields: Sequence[Mapping[str, object]], pages: list[dict[str, object]],
) -> dict[str, dict[str, object]] | None:
    local_text = project_confirmed_values_v2_reply(text, fields, pages)
    if local_text is None:
        return None
    return parse_values_reply(local_text, [dict(field) for field in fields], pages)


def _decode_confirmed_values(
    text: str, fields: Sequence[Mapping[str, object]], *, allow_unquoted_cells: bool = False,
) -> dict[str, object] | None:
    """Shared closed-envelope validation; visual callers opt into unquoted cells."""
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
                    not (allow_unquoted_cells and cell["quote"] is None or
                         isinstance(cell["quote"], str) and 0 < len(cell["quote"]) <= 24_000):
                return None
            seen_rows.add(cell["row"])
    return payload
