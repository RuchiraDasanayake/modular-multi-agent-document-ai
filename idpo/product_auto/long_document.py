"""Conservative segment receipts, evidence remapping, and value merging."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence

from idpo.product_auto.segments import MAX_SEGMENT_CHARS, MAX_SEGMENTS, SegmentPlan, TextSegment

PROFILE = "bounded_text_segments_v1"
MERGE_PROFILE = "conservative_segment_merge_v1"
MAX_MERGED_ROWS_PER_GROUP = 128


class SegmentMergeError(ValueError):
    """A segment cannot be merged into a complete, reviewable document."""


def _canonical_sha256(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                     allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def plan_receipt(plan: SegmentPlan) -> dict[str, object]:
    """Receipt contains offsets and hashes, never another copy of source text."""
    receipt: dict[str, object] = {
        "profile": PROFILE,
        "merge_profile": MERGE_PROFILE,
        "reason": plan.reason,
        "boundary_policy": plan.boundary_policy,
        "overlap_chars": plan.overlap_chars,
        "source_pages": [vars(page) for page in plan.source_pages],
        "source_char_count": sum(page.text_length for page in plan.source_pages),
        "planned_char_count": sum(segment.char_count for segment in plan.segments),
        "segments": [{
            "index": segment.index,
            "char_count": segment.char_count,
            "slices": [{"page": part.page, "start": part.start, "end": part.end,
                        "source_text_sha256": part.source_text_sha256}
                       for part in segment.slices],
        } for segment in plan.segments],
    }
    receipt["plan_sha256"] = _canonical_sha256(receipt)
    return receipt


def validate_segment_plan(plan: SegmentPlan, source_pages: Sequence[Mapping[str, object]]) -> None:
    """Prove no page character is skipped, repeated, changed, or reordered."""
    if not plan.supported or not 1 <= len(plan.segments) <= MAX_SEGMENTS:
        raise SegmentMergeError("Unsupported or oversized segment plan")
    if len({page["page"] for page in source_pages}) != len(source_pages):
        raise SegmentMergeError("Repeated source page")
    originals = {page["page"]: page["text"] for page in source_pages}
    order = {page["page"]: index for index, page in enumerate(source_pages)}
    offsets = {page: 0 for page in originals}
    last_page_order = -1
    for segment_index, segment in enumerate(plan.segments):
        if segment.index != segment_index or not 0 < segment.char_count <= MAX_SEGMENT_CHARS:
            raise SegmentMergeError("Invalid segment order or size")
        for part in segment.slices:
            original = originals.get(part.page)
            if not isinstance(original, str) or order[part.page] < last_page_order or \
                    type(part.start) is not int or type(part.end) is not int or \
                    part.start != offsets[part.page] or not part.start <= part.end <= len(original) or \
                    original[part.start:part.end] != part.text or \
                    hashlib.sha256(original.encode("utf-8")).hexdigest() != part.source_text_sha256:
                raise SegmentMergeError("Segment plan source coverage mismatch")
            offsets[part.page] = part.end
            last_page_order = order[part.page]
    if any(offsets[page] != len(text) for page, text in originals.items()):
        raise SegmentMergeError("Segment plan source coverage incomplete")


def segment_pages(segment: TextSegment) -> list[dict[str, object]]:
    pages = [{"page": part.page, "text": part.text} for part in segment.slices]
    if len({part["page"] for part in pages}) != len(pages):
        raise SegmentMergeError("Repeated page slice inside one segment")
    return pages


def remap_segment_values(
    values: Mapping[str, Mapping[str, object]], segment: TextSegment,
    source_pages: Sequence[Mapping[str, object]],
) -> dict[str, dict[str, object]]:
    """Map segment-relative evidence to the exact original page and verify it."""
    original = {page["page"]: page["text"] for page in source_pages}
    slices = {part.page: part for part in segment.slices}
    if len(slices) != len(segment.slices):
        raise SegmentMergeError("Repeated page slice inside one segment")
    for part in segment.slices:
        text = original.get(part.page)
        if not isinstance(text, str) or hashlib.sha256(text.encode("utf-8")).hexdigest() != part.source_text_sha256 \
                or text[part.start:part.end] != part.text:
            raise SegmentMergeError("Segment source hash or offset mismatch")

    def remap(evidence: object) -> dict[str, object]:
        if not isinstance(evidence, dict):
            raise SegmentMergeError("Invalid segment evidence")
        page, start, end, quote = (evidence.get(key) for key in ("page", "start", "end", "quote"))
        if (type(page) is not int or page not in slices or type(start) is not int or
                type(end) is not int or not isinstance(quote, str)):
            raise SegmentMergeError("Invalid segment evidence")
        part = slices[page]
        if not 0 <= start < end <= len(part.text) or part.text[start:end] != quote:
            raise SegmentMergeError("Segment quote offset mismatch")
        mapped = {"page": page, "start": part.start + start, "end": part.start + end, "quote": quote}
        if original[page][mapped["start"]:mapped["end"]] != quote:
            raise SegmentMergeError("Original source quote mismatch")
        return mapped

    copied = copy.deepcopy(dict(values))
    for value in copied.values():
        if "evidence" in value:
            value["evidence"] = remap(value["evidence"])
        cells = value.get("value")
        if isinstance(cells, list):
            for cell in cells:
                if isinstance(cell, dict) and "evidence" in cell:
                    cell["evidence"] = remap(cell["evidence"])
    return copied


def merge_segment_values(
    segments: Sequence[Mapping[str, Mapping[str, object]]],
    fields: Sequence[Mapping[str, object]],
) -> tuple[dict[str, dict[str, object]], dict[str, list[dict[str, object]]], dict[str, int]]:
    """Merge only complete calls; caller must gate failures before invoking."""
    if not segments:
        raise SegmentMergeError("No completed segment proposals")
    linked_groups: dict[str, list[str]] = {}
    for field in fields:
        if field["type"] == "array[object]":
            group = field.get("group")
            if not isinstance(group, str) or not group:
                raise SegmentMergeError("Linked field has no confirmed group")
            linked_groups.setdefault(group, []).append(str(field["field_id"]))
    row_offsets = {group: 0 for group in linked_groups}
    merged_cells: dict[str, list[dict[str, object]]] = {
        field_id: [] for field_ids in linked_groups.values() for field_id in field_ids
    }
    for proposals in segments:
        for group, field_ids in linked_groups.items():
            max_row = -1
            for field_id in field_ids:
                cells = proposals.get(field_id, {}).get("value")
                if cells is None:
                    continue
                if not isinstance(cells, list):
                    raise SegmentMergeError("Invalid linked segment proposal")
                for cell in cells:
                    if not isinstance(cell, dict) or type(cell.get("row")) is not int or cell["row"] < 0:
                        raise SegmentMergeError("Invalid linked segment row")
                    max_row = max(max_row, cell["row"])
                    shifted = copy.deepcopy(cell)
                    shifted["row"] += row_offsets[group]
                    if shifted["row"] >= MAX_MERGED_ROWS_PER_GROUP:
                        raise SegmentMergeError("Linked group exceeds merged row budget")
                    merged_cells[field_id].append(shifted)
            row_offsets[group] += max_row + 1
            if row_offsets[group] > MAX_MERGED_ROWS_PER_GROUP:
                raise SegmentMergeError("Linked group exceeds merged row budget")

    merged: dict[str, dict[str, object]] = {}
    conflicts: dict[str, list[dict[str, object]]] = {}
    for field in fields:
        field_id = str(field["field_id"])
        if field["type"] == "array[object]":
            cells = merged_cells[field_id]
            merged[field_id] = ({"field_id": field_id, "value": sorted(cells, key=lambda cell: cell["row"]),
                                 "status": "needs_review", "review_state": "pending"} if cells else
                                {"field_id": field_id, "value": None, "status": "missing",
                                 "review_state": "pending"})
            continue
        alternatives = [
            {"segment_index": index, "value": proposal["value"], "status": proposal["status"],
             **({"evidence": proposal["evidence"]} if "evidence" in proposal else {})}
            for index, proposals in enumerate(segments)
            if (proposal := proposals.get(field_id)) is not None and proposal.get("value") is not None
        ]
        if not alternatives:
            merged[field_id] = {"field_id": field_id, "value": None, "status": "missing",
                                "review_state": "pending"}
            continue
        distinct = {(type(item["value"]).__name__, _canonical_sha256(item["value"])) for item in alternatives}
        if len(distinct) > 1:
            conflicts[field_id] = alternatives
            merged[field_id] = {"field_id": field_id, "value": None, "status": "needs_review",
                                "review_state": "pending"}
            continue
        chosen = next((item for item in alternatives if item["status"] == "accepted"), alternatives[0])
        merged[field_id] = {"field_id": field_id, "value": chosen["value"], "status": chosen["status"],
                            "review_state": "pending"}
        if "evidence" in chosen:
            merged[field_id]["evidence"] = chosen["evidence"]
    return merged, conflicts, row_offsets
