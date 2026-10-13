"""Complete visual extraction with bounded requests and conservative review merging."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Callable

from idpo.product_auto.long_document import SegmentMergeError, merge_segment_values
from idpo.product_auto.provider import ModelReply
from idpo.product_auto.segments import MAX_SEGMENT_CHARS
from idpo.product_auto.visual_input import (
    JPEG95_ENCODING_PROFILE,
    PNG_ENCODING_PROFILE,
    VisualInputError,
    plan_visual_requests,
    prepare_visual_document,
)
from idpo.product_auto.visual_output import parse_visual_values_reply
from idpo.product_auto.visual_output import PROFILE as VISUAL_VALUES_PROFILE

PROFILE = "bounded_visual_v1"
SELECTIVE_PROFILE = "bounded_visual_selective_v2"
JPEG95_PROFILE = "bounded_visual_selective_jpeg95_v1"
PROFILES = frozenset({PROFILE, SELECTIVE_PROFILE, JPEG95_PROFILE})
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


def visual_receipt(source_sha256: str, profile: str = PROFILE) -> dict[str, object]:
    return {"profile": profile, "source_sha256": source_sha256, "route": "not_executed",
            "route_reason": "not_prepared", "plan_sha256": None, "requests": [],
            "source_pages": [], "observed_ocr_pages": [], "planned_pages": [], "attempted_pages": [], "valid_pages": [],
            "planned_requests": 0, "attempted_requests": 0, "valid_requests": 0,
            "full_source_covered": False, "failure_reason": None}


def select_visual_route(
    extension: str, pages: list[dict], ocr_pages: list[dict], original_page_numbers: list[int],
    *, profile: str = PROFILE, fields: tuple[dict, ...] = (),
) -> tuple[bool, str]:
    if profile not in PROFILES:
        raise ValueError("Unknown visual routing profile")
    eligible, reason = _visual_source_route(extension, pages, ocr_pages, original_page_numbers)
    if not eligible or profile == PROFILE or reason == "pdf_ocr_page_coverage_incomplete":
        return eligible, reason
    # Choose before inference. A failed or truncated text call never silently
    # incurs another paid image call. Preserve v1 for the frozen comparison.
    if any(field.get("type") == "array[object]" for field in fields):
        return True, "selective_repeated_fields"
    if not any(page["text"].strip() for page in pages):
        return True, "selective_no_usable_text"
    if sum(len(page["text"]) for page in pages) > MAX_SEGMENT_CHARS:
        return True, "selective_long_text"
    return False, "selective_scalar_text"


def _visual_source_route(
    extension: str, pages: list[dict], ocr_pages: list[dict], original_page_numbers: list[int],
) -> tuple[bool, str]:
    if extension in IMAGE_EXTENSIONS:
        return True, "source_image"
    if extension != ".pdf":
        return False, "native_or_text_source"
    if [page["page"] for page in pages] != original_page_numbers or \
            [page.get("page") for page in ocr_pages] != original_page_numbers:
        return True, "pdf_ocr_page_coverage_incomplete"
    if any(page.get("engine") != "native_text" or page.get("pdf_native_text_rejected") or
           isinstance(page.get("pdf_native_layer"), dict) and page["pdf_native_layer"].get("requires_ocr")
           for page in ocr_pages):
        return True, "pdf_requires_ocr"
    return False, "pdf_all_native_text"


def extract_visual_values(
    *, source: Path, source_sha256: str, pages: list[dict], ocr_pages: list[dict],
    fields: list[dict], schema: list[dict], intent: str, model, sidecar: dict,
    record_call: Callable[[dict, str, ModelReply], None],
    response_format_profile: str = VISUAL_VALUES_PROFILE,
) -> tuple[dict | None, dict, str | None]:
    receipt = sidecar["visual_document"]
    receipt["observed_ocr_pages"] = [page["page"] for page in pages]
    sidecar["visual_request_proposals"] = []

    def fail(reason: str) -> tuple[None, dict, str]:
        receipt["failure_reason"] = reason
        for request in receipt["requests"]:
            if request["outcome"] == "planned":
                request["outcome"] = "not_attempted_after_failure"
        return None, {}, reason

    try:
        if len(pages) > 48:
            raise VisualInputError("visual_complete_coverage_budget_exceeded")
        if receipt["observed_ocr_pages"] != receipt["source_pages"]:
            raise VisualInputError("visual_ocr_page_coverage_incomplete")
        if [page.get("page") for page in ocr_pages] != [page["page"] for page in pages]:
            raise VisualInputError("visual_ocr_page_coverage_incomplete")
        joined = [{**page, "ocr_lines": ocr_page.get("ocr_lines") or [],
                   "ocr_provenance": ocr_page.get("ocr_provenance") or {}}
                  for page, ocr_page in zip(pages, ocr_pages, strict=True)]
        encoding_profile = JPEG95_ENCODING_PROFILE if receipt["profile"] == JPEG95_PROFILE else PNG_ENCODING_PROFILE
        prepared = prepare_visual_document(source, expected_source_sha256=source_sha256, pages=joined,
                                           encoding_profile=encoding_profile)
        requests = plan_visual_requests(prepared, fields=fields, intent=intent,
                                        model=model.model, max_tokens=model.max_tokens,
                                        response_format_profile=response_format_profile,
                                        encoding_profile=encoding_profile)
        # Validate all immutable request bodies and current source identity before
        # the first send. The provider also validates again before each send.
        for request in requests:
            request.validated_body(model=model.model, max_tokens=model.max_tokens)
    except VisualInputError as exc:
        if receipt["profile"] == JPEG95_PROFILE and exc.details is not None:
            receipt["admission_failure"] = dict(exc.details)
        return fail(str(exc))
    except Exception:
        return fail("visual_preparation_failed")
    planned = [request.receipt() for request in requests]
    receipt.update(plan_sha256=hashlib.sha256(json.dumps(planned, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False).encode("utf-8")).hexdigest(),
                   planned_pages=[page["page"] for page in pages], planned_requests=len(requests),
                   requests=[{**item, "outcome": "planned", "model_call_index": None} for item in planned])
    completed = []
    for index, request in enumerate(requests):
        attempt = receipt["requests"][index]
        receipt["attempted_requests"] += 1
        receipt["attempted_pages"].extend(attempt["covered_pages"])
        started = time.perf_counter()
        try:
            reply = model.complete_visual_json(request)
        except Exception as exc:
            reply = ModelReply(text="", latency_ms=(time.perf_counter() - started) * 1000,
                               error=type(exc).__name__, error_category="adapter_error")
        record_call(sidecar, "visual_values", reply)
        call = sidecar["model_calls"][-1]
        call["visual_request_index"] = index
        attempt["model_call_index"] = len(sidecar["model_calls"]) - 1
        attempt["usage"] = dict(call)
        if reply.error or reply.refusal or reply.finish_reason != "stop":
            attempt["outcome"] = "failed"
            return fail("visual_request_provider_error" if reply.error else "visual_request_incomplete")
        try:
            batch_pages = [page for page in pages if page["page"] in attempt["covered_pages"]]
            parsed = parse_visual_values_reply(reply.text, schema, batch_pages,
                                               profile=response_format_profile)
        except (TypeError, ValueError, RecursionError, OverflowError):
            parsed = None
        if parsed is None:
            attempt["outcome"] = "invalid"
            return fail("visual_request_invalid_values")
        completed.append(parsed)
        sidecar["visual_request_proposals"].append({"request_index": index, "values": list(parsed.values())})
        attempt["outcome"] = "valid"
        receipt["valid_requests"] += 1
        receipt["valid_pages"].extend(attempt["covered_pages"])
    try:
        merged, conflicts, group_rows = merge_segment_values(completed, schema)
    except SegmentMergeError:
        return fail("visual_request_merge_failed")
    # The shared merger intentionally handles only text evidence. Restore each
    # visual scalar's page without inventing pixel evidence or changing conflicts.
    for field_id, value in merged.items():
        if value.get("value") is not None:
            value.update(status="needs_review", review_state="pending", visual_grounding_verified=False)
            if not isinstance(value["value"], list):
                matching = [part[field_id] for part in completed if part[field_id].get("value") == value["value"]]
                value["visual_pages"] = sorted({part["visual_page"] for part in matching})
    for field_id, alternatives in conflicts.items():
        for alternative in alternatives:
            original = completed[alternative["segment_index"]][field_id]
            alternative.update(visual_page=original["visual_page"], visual_grounding_verified=False)
    receipt["full_source_covered"] = (receipt["valid_pages"] == receipt["planned_pages"] == receipt["source_pages"]
                                     and receipt["valid_requests"] == receipt["planned_requests"])
    if not receipt["full_source_covered"]:
        return fail("visual_coverage_incomplete")
    sidecar["linked_group_row_counts"] = group_rows
    return merged, conflicts, None
