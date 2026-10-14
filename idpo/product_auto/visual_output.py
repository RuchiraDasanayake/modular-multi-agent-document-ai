"""Strict visual proposals remain review-only, including exact OCR text matches."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from idpo.product_auto.logic import coerce_value, parse_values_reply
from idpo.product_auto.strict_output import (
    _decode_confirmed_values,
    compile_confirmed_values_response_format,
    compile_confirmed_values_response_format_v2,
    project_confirmed_values_v2_reply,
)

PROFILE = "strict_visual_confirmed_values_v1"
PROFILE_V2 = "strict_visual_confirmed_values_v2"


def compile_visual_response_format(
    fields: Sequence[Mapping[str, object]], *, profile: str = PROFILE,
) -> dict[str, object]:
    if profile not in {PROFILE, PROFILE_V2}:
        raise ValueError("Unsupported visual response format profile")
    if profile == PROFILE_V2:
        result = compile_confirmed_values_response_format_v2(fields, allow_unquoted_cells=True)
        result["json_schema"]["name"] = "docai_visual_confirmed_values_v2"
        return result
    result = compile_confirmed_values_response_format(fields)
    named = result["json_schema"]
    named["name"] = "docai_visual_confirmed_values_v1"
    value = named["schema"]["properties"]["values"]["items"]["properties"]["value"]
    if "items" in value:
        value["items"]["properties"]["quote"] = {"type": ["string", "null"]}
    return result


def parse_visual_values_reply(
    text: str, fields: Sequence[Mapping[str, object]], pages: list[dict[str, object]],
    *, profile: str = PROFILE,
) -> dict[str, dict[str, object]] | None:
    """Validate exact fields and page membership; never infer visual grounding."""
    if profile == PROFILE_V2:
        local_text = project_confirmed_values_v2_reply(
            text, fields, pages, allow_unquoted_cells=True,
        )
        return (parse_visual_values_reply(local_text, fields, pages)
                if local_text is not None else None)
    if profile != PROFILE:
        raise ValueError("Unsupported visual response format profile")
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
    field_types = {field["field_id"]: field["type"] for field in fields}
    for field_id, projected in result.items():
        field_type = field_types[field_id]
        if field_type != "array[object]" and not coerce_value(projected["value"], field_type)[1]:
            # Review-only metadata does not make an invalid typed scalar
            # consumable by the UI. Reject the reply before claiming coverage.
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
