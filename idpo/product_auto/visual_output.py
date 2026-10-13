"""Strict visual proposals remain review-only, including exact OCR text matches."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from idpo.product_auto.logic import parse_values_reply
from idpo.product_auto.strict_output import _decode_confirmed_values, compile_confirmed_values_response_format

PROFILE = "strict_visual_confirmed_values_v1"


def compile_visual_response_format(fields: Sequence[Mapping[str, object]]) -> dict[str, object]:
    result = compile_confirmed_values_response_format(fields)
    named = result["json_schema"]
    named["name"] = "docai_visual_confirmed_values_v1"
    value = named["schema"]["properties"]["values"]["items"]["properties"]["value"]
    if "items" in value:
        value["items"]["properties"]["quote"] = {"type": ["string", "null"]}
    return result


def parse_visual_values_reply(
    text: str, fields: Sequence[Mapping[str, object]], pages: list[dict[str, object]],
) -> dict[str, dict[str, object]] | None:
    """Validate exact fields and page membership; never infer visual grounding."""
    payload = _decode_confirmed_values(text, fields, allow_unquoted_cells=True)
    if payload is None or not pages or any(
        type(page.get("page")) is not int or page["page"] < 1 or not isinstance(page.get("text"), str)
        for page in pages
    ):
        return None
    page_ids = {page["page"] for page in pages}
    if len(page_ids) != len(pages):
        return None
    for item in payload["values"]:
        values = item["value"] if isinstance(item["value"], list) else [item]
        for value in values:
            if value["value"] is not None and value["page"] not in page_ids:
                return None
            if value["page"] is not None and value["page"] not in page_ids:
                return None
    result = parse_values_reply(text, [dict(field) for field in fields], pages)
    if result is None:
        return None
    for item in payload["values"]:
        projected = result[item["field_id"]]
        if projected["value"] is None:
            continue
        projected.update(status="needs_review", review_state="pending", visual_grounding_verified=False)
        cells = projected["value"] if isinstance(projected["value"], list) else [projected]
        raw_by_row = {cell["row"]: cell for cell in item["value"]} if isinstance(item["value"], list) else None
        for cell in cells:
            raw = raw_by_row[cell["row"]] if raw_by_row is not None else item
            cell.update(status="needs_review", review_state="pending", visual_page=raw["page"],
                        visual_grounding_verified=False)
            if "evidence" in cell:
                cell["evidence"]["kind"] = "text_match"
    return result
