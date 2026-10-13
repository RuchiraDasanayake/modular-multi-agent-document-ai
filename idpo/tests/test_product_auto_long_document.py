"""Bounded long-document extraction preserves source offsets and fails closed."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from idpo.product_auto.confirmed_schema import load_confirmed_schema
from idpo.product_auto.long_document import (
    PROFILE, SegmentMergeError, merge_segment_values, plan_receipt, remap_segment_values,
    validate_segment_plan,
)
from idpo.product_auto.provider import ModelReply
from idpo.product_auto.segments import plan_segments
from idpo.product_auto.strict_output import PROFILE as STRICT_PROFILE
from idpo.product_auto.workflow import process_auto
from idpo.tests.test_confirmed_schema_routing import snapshot


FILLER = ("filler " * 100 + "\n") * 36


class SegmentModel:
    model = "synthetic-segment-model"

    def __init__(self, make_reply) -> None:
        self.make_reply = make_reply
        self.calls: list[dict[str, object]] = []

    def complete_json(self, *, system: str, prompt: str,
                      response_format: dict[str, object]) -> ModelReply:
        self.calls.append({"prompt": prompt, "response_format": response_format})
        return self.make_reply(prompt, len(self.calls) - 1)


def _strict_reply(values: list[dict]) -> ModelReply:
    return ModelReply(text=json.dumps({"values": values}), latency_ms=1, finish_reason="stop", sdk_attempts=1)


def _item(field_id: str, value, quote: str | None = None) -> dict:
    return {"field_id": field_id, "value": value, "page": 1 if quote else None, "quote": quote}


def _source_text(prompt: str) -> str:
    data = json.loads(prompt.split("Document data: ", 1)[1].split(" This is one bounded", 1)[0])
    return "\n".join(page["text"] for page in data["pages"])


def _run(tmp_path: Path, fields: list[dict], text: str, model: SegmentModel,
         run_id: str = "long") -> tuple[dict, dict, dict, dict]:
    schema_path, digest = snapshot(tmp_path, fields=fields)
    schema = load_confirmed_schema(schema_path, digest)
    source = tmp_path / "long.txt"
    source.write_text(text, encoding="utf-8")
    run = process_auto(source, model=model, run_id=run_id, confirmed_schema=schema,
                       response_format_profile=STRICT_PROFILE, long_document_profile=PROFILE,
                       output_root=tmp_path / "runs")
    run_dir = Path(run["run_dir"])
    candidate = json.loads((run_dir / "candidates.jsonl").read_text())
    sidecar = json.loads((run_dir / "docs" / candidate["doc_id"] / "result.json").read_text())
    manifest = json.loads((run_dir / "manifest.jsonl").read_text())
    marker = json.loads((run_dir / "run.json").read_text())
    return candidate, sidecar, manifest, marker


def test_two_segments_remap_evidence_and_pin_complete_coverage(tmp_path: Path) -> None:
    fields = [
        {"field_id": "invoice_id", "type": "string", "description": "Invoice identifier",
         "example_values": ["A1"]},
        {"field_id": "total", "type": "decimal", "description": "Final total",
         "example_values": ["12.50"]},
    ]
    text = "Invoice ID: A1\n" + FILLER + "\nTotal: 12.50\n"

    def reply(prompt: str, index: int) -> ModelReply:
        source = _source_text(prompt)
        return _strict_reply([_item("invoice_id", "A1", "A1") if "Invoice ID: A1" in source else
                              _item("invoice_id", None),
                              _item("total", "12.50", "12.50") if "Total: 12.50" in source else
                              _item("total", None)])

    model = SegmentModel(reply)
    candidate, sidecar, manifest, run = _run(tmp_path, fields, text, model)
    assert len(model.calls) == 2
    assert all(call["response_format"]["json_schema"]["strict"] is True for call in model.calls)
    assert candidate["document_status"] == "needs_review"
    assert [value["status"] for value in candidate["extracted_values"]] == ["accepted", "accepted"]
    assert all(value["review_state"] == "pending" for value in candidate["extracted_values"])
    total_evidence = candidate["extracted_values"][1]["evidence"]
    source_text = sidecar["pages"][0]["text"]
    assert total_evidence["start"] > 24_000
    assert source_text[total_evidence["start"]:total_evidence["end"]] == "12.50"
    plan, coverage = sidecar["long_document_plan"], sidecar["long_document_coverage"]
    assert plan["planned_char_count"] == plan["source_char_count"] == len(source_text)
    assert plan["boundary_policy"] in {"page_paragraph", "packed_whitespace"}
    assert plan["merge_profile"] == "conservative_segment_merge_v1"
    assert coverage == {"source_char_count": len(source_text), "planned_char_count": len(source_text),
                        "completed_char_count": len(source_text), "planned_segments": 2,
                        "attempted_segments": 2, "completed_segments": 2, "full_source_covered": True}
    assert [call["segment_index"] for call in sidecar["model_calls"]] == [0, 1]
    assert manifest["long_document"]["plan_sha256"] == plan["plan_sha256"]
    assert manifest["long_document"]["full_source_covered"] is True
    assert run["long_document"]["plan_count"] == 1
    assert run["long_document"]["full_source_covered_docs"] == 1
    assert run["long_document"]["completed_char_count"] == len(source_text)


def test_conflicting_scalars_become_null_with_both_source_alternatives(tmp_path: Path) -> None:
    fields = [{"field_id": "reference", "type": "string", "description": "Reference code",
               "example_values": ["A1"]}]
    text = "Reference: A1\n" + FILLER + "\nReference: B2\n"
    model = SegmentModel(lambda prompt, index: _strict_reply([
        _item("reference", "A1", "A1") if "Reference: A1" in _source_text(prompt) else
        _item("reference", "B2", "B2")]))
    candidate, sidecar, _, _ = _run(tmp_path, fields, text, model)
    assert len(model.calls) == 2
    assert candidate["document_status"] == "needs_review"
    assert candidate["extracted_values"][0]["value"] is None
    assert candidate["extracted_values"][0]["status"] == "needs_review"
    assert sidecar["reason"] == "long_document_scalar_conflict"
    alternatives = sidecar["scalar_conflicts"]["reference"]
    assert [item["value"] for item in alternatives] == ["A1", "B2"]
    for item in alternatives:
        evidence = item["evidence"]
        assert sidecar["pages"][0]["text"][evidence["start"]:evidence["end"]] == evidence["quote"]


def test_linked_columns_keep_shared_segment_row_offsets_and_absent_cells(tmp_path: Path) -> None:
    fields = [
        {"field_id": "item_name", "type": "array[object]", "group": "items",
         "description": "Item name", "example_values": ["WidgetA"]},
        {"field_id": "quantity", "type": "array[object]", "group": "items",
         "description": "Item quantity", "example_values": ["2"]},
    ]
    text = "WidgetA\n" + FILLER + "\nWidgetB 2\n"

    def reply(prompt: str, index: int) -> ModelReply:
        name, quantity = (("WidgetA", None) if "WidgetA" in _source_text(prompt) else ("WidgetB", "2"))
        return _strict_reply([
            _item("item_name", [{"row": 0, "value": name, "page": 1, "quote": name}]),
            _item("quantity", [{"row": 0, "value": quantity, "page": 1, "quote": quantity}]
                  if quantity is not None else None),
        ])

    model = SegmentModel(reply)
    candidate, sidecar, _, _ = _run(tmp_path, fields, text, model)
    assert len(model.calls) == 2
    item_cells = candidate["extracted_values"][0]["value"]
    quantity_cells = candidate["extracted_values"][1]["value"]
    assert [(cell["row"], cell["value"]) for cell in item_cells] == [(0, "WidgetA"), (1, "WidgetB")]
    assert [(cell["row"], cell["value"]) for cell in quantity_cells] == [(1, "2")]
    assert sidecar["linked_group_row_counts"] == {"items": 2}
    assert sidecar["reason"] == "confirmed_schema_requires_review"
    quantity_evidence = quantity_cells[0]["evidence"]
    assert sidecar["pages"][0]["text"][quantity_evidence["start"]:quantity_evidence["end"]] == "2"


def test_second_segment_failure_stops_and_keeps_partial_proposals_out_of_candidate(tmp_path: Path) -> None:
    fields = [{"field_id": "reference", "type": "string", "description": "Reference code",
               "example_values": ["A1"]}]
    text = "Reference: A1\n" + FILLER * 2 + "\nTail value\n"
    model = SegmentModel(lambda prompt, index: _strict_reply([_item("reference", "A1", "A1")])
                         if index == 0 else ModelReply(text="not JSON", latency_ms=1,
                                                        finish_reason="stop", sdk_attempts=1))
    candidate, sidecar, manifest, run = _run(tmp_path, fields, text, model)
    assert len(model.calls) == 2
    assert candidate["document_status"] == "failed"
    assert candidate["extracted_values"][0]["value"] is None
    assert sidecar["reason"] == "long_document_segment_invalid_values"
    assert sidecar["failed_segment_index"] == 1
    assert sidecar["segment_proposals"][0]["values"][0]["value"] == "A1"
    assert sidecar["long_document_coverage"]["completed_segments"] == 1
    assert sidecar["long_document_coverage"]["planned_segments"] >= 3
    assert sidecar["long_document_coverage"]["attempted_segments"] == 2
    assert sidecar["long_document_coverage"]["full_source_covered"] is False
    assert manifest["long_document"]["full_source_covered"] is False
    assert run["long_document"]["full_source_covered_docs"] == 0


def test_unsupported_fifth_segment_never_calls_model_or_exposes_partial_candidate(tmp_path: Path) -> None:
    fields = [{"field_id": "reference", "type": "string", "description": "Reference code",
               "example_values": ["A1"]}]
    model = SegmentModel(lambda prompt, index: pytest.fail("unsupported source must not call model"))
    candidate, sidecar, manifest, _ = _run(tmp_path, fields, "word " * 20_000, model)
    assert not model.calls
    assert candidate["document_status"] == "failed"
    assert candidate["extracted_values"][0]["status"] == "missing"
    assert sidecar["reason"] == "long_document_plan_unsupported"
    assert sidecar["long_document_plan"]["reason"] == "source_exceeds_segment_budget"
    assert manifest["long_document"]["completed_segments"] == 0


def test_short_source_uses_one_existing_value_call_under_bounded_profile(tmp_path: Path) -> None:
    fields = [{"field_id": "total", "type": "decimal", "description": "Final total",
               "example_values": ["12.50"]}]
    model = SegmentModel(lambda prompt, index: _strict_reply([_item("total", "12.50", "12.50")]))
    candidate, sidecar, manifest, run = _run(tmp_path, fields, "Total: 12.50", model)
    assert len(model.calls) == 1
    assert candidate["extracted_values"][0]["status"] == "accepted"
    assert sidecar["long_document_plan"] is None
    assert manifest["long_document"] is None
    assert run["long_document"]["segmented_doc_count"] == 0


def test_bounded_profile_requires_confirmed_schema_before_artifact_creation(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("A1", encoding="utf-8")
    model = SegmentModel(lambda prompt, index: pytest.fail("must not call model"))
    with pytest.raises(ValueError, match="confirmed schema"):
        process_auto(source, model=model, run_id="no-schema", long_document_profile=PROFILE,
                     output_root=tmp_path / "runs")
    assert not (tmp_path / "runs" / "no-schema").exists()


def test_pure_merge_rejects_row_overflow_and_remap_detects_source_change() -> None:
    field = {"field_id": "item", "type": "array[object]", "group": "items"}
    proposals = {"item": {"field_id": "item", "value": [{"row": 127, "value": "x"}],
                          "status": "needs_review"}}
    with pytest.raises(SegmentMergeError, match="row budget"):
        merge_segment_values([proposals, proposals], [field])
    pages = [{"page": 1, "text": "alpha beta"}]
    plan = plan_segments(pages, max_chars=8)
    assert plan.supported and plan_receipt(plan)["planned_char_count"] == len(pages[0]["text"])
    values = {"name": {"field_id": "name", "value": "alpha", "status": "accepted",
                       "evidence": {"page": 1, "start": 0, "end": 5, "quote": "alpha"}}}
    with pytest.raises(SegmentMergeError, match="hash"):
        remap_segment_values(values, plan.segments[0], [{"page": 1, "text": "alpha zeta"}])
    first_segment = plan.segments[0]
    moved_slice = replace(first_segment.slices[0], start=1)
    bad_plan = replace(plan, segments=(replace(first_segment, slices=(moved_slice,)), *plan.segments[1:]))
    with pytest.raises(SegmentMergeError, match="coverage"):
        validate_segment_plan(bad_plan, pages)


def test_identical_typed_scalars_collapse_but_different_types_conflict() -> None:
    fields = [{"field_id": "total", "type": "decimal"}]
    first = {"total": {"field_id": "total", "value": 12.5, "status": "accepted",
                       "evidence": {"page": 1, "start": 0, "end": 4, "quote": "12.5"}}}
    second = {"total": {"field_id": "total", "value": 12.5, "status": "needs_review"}}
    merged, conflicts, _ = merge_segment_values([first, second], fields)
    assert merged["total"]["value"] == 12.5
    assert merged["total"]["status"] == "accepted"
    assert not conflicts
    second["total"]["value"] = "12.5"
    merged, conflicts, _ = merge_segment_values([first, second], fields)
    assert merged["total"]["value"] is None
    assert merged["total"]["status"] == "needs_review"
    assert [item["value"] for item in conflicts["total"]] == [12.5, "12.5"]


def test_provider_error_stops_before_next_segment(tmp_path: Path) -> None:
    fields = [{"field_id": "reference", "type": "string", "description": "Reference code",
               "example_values": ["A1"]}]
    text = "Reference: A1\n" + FILLER + "\nTail value\n"
    model = SegmentModel(lambda prompt, index: ModelReply(
        text="", latency_ms=1, error="http_400", error_category="request_rejected", sdk_attempts=1))
    candidate, sidecar, manifest, _ = _run(tmp_path, fields, text, model)
    assert len(model.calls) == 1
    assert sidecar["reason"] == "long_document_segment_provider_error"
    assert sidecar["long_document_coverage"]["attempted_segments"] == 1
    assert sidecar["long_document_coverage"]["completed_segments"] == 0
    assert not sidecar["segment_proposals"]
    assert candidate["document_status"] == "failed"
    assert manifest["long_document"]["full_source_covered"] is False


def test_plan_guard_includes_empty_pages_and_checks_source_page_receipt() -> None:
    pages = [{"page": 1, "text": ""}, {"page": 2, "text": "alpha beta"}]
    plan = plan_segments(pages, max_chars=8)
    assert plan.supported
    validate_segment_plan(plan, pages)
    first = plan.segments[0]
    missing_empty = replace(plan, segments=(replace(first, slices=tuple(
        part for part in first.slices if part.page != 1)), *plan.segments[1:]))
    with pytest.raises(SegmentMergeError, match="coverage"):
        validate_segment_plan(missing_empty, pages)
    altered_receipt = replace(plan, source_pages=(replace(plan.source_pages[0], source_text_sha256="0" * 64),
                                                  *plan.source_pages[1:]))
    with pytest.raises(SegmentMergeError, match="source-page receipt"):
        validate_segment_plan(altered_receipt, pages)
