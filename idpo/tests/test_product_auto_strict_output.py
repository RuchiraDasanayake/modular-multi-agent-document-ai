"""Strict confirmed-value output remains complete, typed, and review gated."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from idpo.product_auto.confirmed_schema import load_confirmed_schema
from idpo.product_auto.provider import ModelReply
from idpo.product_auto.strict_output import (
    PROFILE,
    compile_confirmed_values_response_format,
    parse_confirmed_strict_values_reply,
)
from idpo.product_auto.workflow import process_auto
from idpo.tests.test_confirmed_schema_routing import snapshot


FIELDS = [
    {"field_id": "item_name", "type": "array[object]", "group": "items",
     "description": "Item labels", "example_values": ["Widget"]},
    {"field_id": "quantity", "type": "array[object]", "group": "items",
     "description": "Item quantities", "example_values": ["2"]},
    {"field_id": "total", "type": "decimal", "description": "Final payable total",
     "example_values": ["12.50"]},
]
SCHEMA_FIELDS = [{"field_id": field["field_id"], "type": field["type"],
                  **({"group": field["group"]} if "group" in field else {})} for field in FIELDS]
PAGES = [{"page": 1, "text": "Widget\nTotal: 12.50"}]
VALUES = {"values": [
    {"field_id": "item_name", "value": [{"row": 0, "value": "Widget", "page": 1,
                                           "quote": "Widget"}], "page": None, "quote": None},
    {"field_id": "quantity", "value": None, "page": None, "quote": None},
    {"field_id": "total", "value": "12.50", "page": 1, "quote": "12.50"},
]}


def test_excessively_nested_reply_is_rejected_without_aborting_a_batch() -> None:
    reply = '{"values":' + '[' * 2000 + 'null' + ']' * 2000 + '}'
    assert parse_confirmed_strict_values_reply(reply, SCHEMA_FIELDS, PAGES) is None


class StrictRecordingModel:
    model = "synthetic-model"

    def __init__(self, reply: ModelReply) -> None:
        self.reply = reply
        self.calls: list[dict[str, object]] = []

    def complete_json(self, *, system: str, prompt: str,
                      response_format: dict[str, object]) -> ModelReply:
        self.calls.append({"system": system, "prompt": prompt, "response_format": response_format})
        return self.reply


def _strict_run(tmp_path: Path, reply: ModelReply, *, run_id: str) -> tuple[dict, dict, dict, dict, StrictRecordingModel]:
    schema_path, digest = snapshot(tmp_path, fields=FIELDS)
    schema = load_confirmed_schema(schema_path, digest)
    source = tmp_path / "invoice.txt"
    source.write_text(PAGES[0]["text"], encoding="utf-8")
    model = StrictRecordingModel(reply)
    run = process_auto(source, run_id=run_id, model=model, confirmed_schema=schema,
                       response_format_profile=PROFILE, output_root=tmp_path / "runs")
    directory = Path(run["run_dir"])
    candidate = json.loads((directory / "candidates.jsonl").read_text())
    sidecar = json.loads((directory / "docs" / candidate["doc_id"] / "result.json").read_text())
    manifest = json.loads((directory / "manifest.jsonl").read_text())
    marker = json.loads((directory / "run.json").read_text())
    return candidate, sidecar, manifest, marker, model


def test_compiler_uses_bounded_required_closed_objects_and_nullable_missing_fields() -> None:
    format_ = compile_confirmed_values_response_format(SCHEMA_FIELDS)
    assert format_["type"] == "json_schema"
    named = format_["json_schema"]
    assert named["strict"] is True
    envelope = named["schema"]
    assert envelope["required"] == ["values"]
    assert envelope["additionalProperties"] is False
    item = envelope["properties"]["values"]["items"]
    assert item["required"] == ["field_id", "value", "page", "quote"]
    assert item["additionalProperties"] is False
    assert item["properties"]["field_id"]["enum"] == ["item_name", "quantity", "total"]
    assert item["properties"]["page"]["type"] == ["integer", "null"]
    assert item["properties"]["quote"]["type"] == ["string", "null"]
    assert item["properties"]["value"]["items"]["required"] == ["row", "value", "page", "quote"]
    assert item["properties"]["value"]["items"]["additionalProperties"] is False


def test_parser_retains_grounded_partial_rows_and_missing_other_column() -> None:
    result = parse_confirmed_strict_values_reply(json.dumps(VALUES), SCHEMA_FIELDS, PAGES)
    assert result is not None
    assert set(result) == {"item_name", "quantity", "total"}
    assert result["item_name"]["value"][0]["status"] == "accepted"
    assert result["quantity"]["status"] == "missing"
    assert result["total"]["status"] == "accepted"
    altered = copy.deepcopy(VALUES)
    altered["values"][2]["quote"] = "fabricated"
    ungrounded = parse_confirmed_strict_values_reply(json.dumps(altered), SCHEMA_FIELDS, PAGES)
    assert ungrounded is not None
    assert ungrounded["total"]["status"] == "needs_review"


@pytest.mark.parametrize("mutation", [
    lambda value: value["values"].pop(),
    lambda value: value["values"][1].update(field_id="item_name"),
    lambda value: value["values"][1].update(field_id="other"),
    lambda value: value.update(extra="unknown"),
    lambda value: value["values"][0].update(extra="unknown"),
    lambda value: value["values"][2].update(value={"wrong": "type"}),
    lambda value: value["values"][2].update(page=True),
    lambda value: value["values"][0]["value"].append(
        {"row": 0, "value": "Widget", "page": 1, "quote": "Widget"}),
    lambda value: value["values"][0]["value"][0].update(quote=None),
])
def test_parser_rejects_incomplete_extra_or_wrongly_typed_payloads(mutation) -> None:
    changed = copy.deepcopy(VALUES)
    mutation(changed)
    assert parse_confirmed_strict_values_reply(json.dumps(changed), SCHEMA_FIELDS, PAGES) is None


@pytest.mark.parametrize("text", [
    pytest.param('{"values":[],"values":[]}', id="duplicate-property"),
    pytest.param('{"values":[{"field_id":"item_name","value":NaN,"page":null,"quote":null}]}',
                 id="nonfinite-value"),
    pytest.param("\ud800", id="invalid-unicode"),
    pytest.param(" " * 1_000_001, id="oversized-reply"),
])
def test_parser_rejects_duplicate_nonfinite_invalid_unicode_or_oversized_reply(text: str) -> None:
    assert parse_confirmed_strict_values_reply(text, SCHEMA_FIELDS, PAGES) is None


def test_workflow_pins_format_and_retains_human_review(tmp_path: Path) -> None:
    reply = ModelReply(text=json.dumps(VALUES), latency_ms=1, finish_reason="stop", sdk_attempts=1)
    candidate, sidecar, receipt, run, model = _strict_run(tmp_path, reply, run_id="strict-success")
    assert len(model.calls) == 1
    assert "every listed field exactly once" in model.calls[0]["prompt"]
    assert model.calls[0]["response_format"] == compile_confirmed_values_response_format(SCHEMA_FIELDS)
    assert candidate["document_status"] == "needs_review"
    assert [value["status"] for value in candidate["extracted_values"]] == ["needs_review", "missing", "accepted"]
    assert all(value["review_state"] == "pending" for value in candidate["extracted_values"])
    assert sidecar["reason"] == "confirmed_schema_requires_review"
    assert sidecar["model_calls"][0]["refusal"] is False
    assert run["response_format_profile"] == receipt["response_format_profile"] == \
        sidecar["response_format_profile"] == PROFILE
    assert run["response_format_sha256"] == receipt["response_format_sha256"] == \
        sidecar["response_format_sha256"]
    assert len(run["response_format_sha256"]) == 64


@pytest.mark.parametrize("reply,reason,status", [
    (ModelReply(text=json.dumps(VALUES), latency_ms=1, finish_reason="length", sdk_attempts=1),
     "invalid_strict_values_model_response", "failed"),
    (ModelReply(text=json.dumps(VALUES), latency_ms=1, finish_reason="stop", refusal=True, sdk_attempts=1),
     "invalid_strict_values_model_response", "failed"),
    (ModelReply(text='{"values":', latency_ms=1, finish_reason="stop", sdk_attempts=1),
     "invalid_strict_values_model_response", "failed"),
    (ModelReply(text="", latency_ms=1, error="http_400", error_category="request_rejected", sdk_attempts=1),
     "values_provider_error", "failed"),
])
def test_strict_incomplete_refusal_or_provider_error_never_falls_back(
    tmp_path: Path, reply: ModelReply, reason: str, status: str,
) -> None:
    candidate, sidecar, _, _, model = _strict_run(tmp_path, reply, run_id="strict-failure")
    assert len(model.calls) == 1
    assert sidecar["reason"] == reason
    assert candidate["document_status"] == status
    assert all(value["status"] == "missing" for value in candidate["extracted_values"])


def test_complete_all_null_reply_is_reviewable_absence(tmp_path: Path) -> None:
    absent = {"values": [{"field_id": field["field_id"], "value": None,
                          "page": None, "quote": None} for field in SCHEMA_FIELDS]}
    candidate, sidecar, _, _, model = _strict_run(
        tmp_path, ModelReply(text=json.dumps(absent), latency_ms=1, finish_reason="stop", sdk_attempts=1),
        run_id="strict-all-null",
    )
    assert len(model.calls) == 1
    assert candidate["document_status"] == "needs_review"
    assert sidecar["reason"] == "confirmed_schema_no_grounded_values"
    assert all(value["status"] == "missing" for value in candidate["extracted_values"])


def test_strict_requires_confirmed_schema_before_writing_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "invoice.txt"
    source.write_text("Total: 12.50", encoding="utf-8")
    model = StrictRecordingModel(ModelReply(text=json.dumps(VALUES), latency_ms=1))
    for name, profile in [("strict-without-schema", PROFILE), ("unknown-profile", "arbitrary")]:
        with pytest.raises(ValueError, match="confirmed schema|Unsupported product response format"):
            process_auto(source, run_id=name, model=model, response_format_profile=profile,
                         output_root=tmp_path / "runs")
        assert not (tmp_path / "runs" / name).exists()
    assert not model.calls
