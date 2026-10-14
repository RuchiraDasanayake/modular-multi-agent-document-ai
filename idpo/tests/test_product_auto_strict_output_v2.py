"""Opt-in keyed strict replies require every confirmed field before grounding."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from idpo.product_auto.confirmed_schema import load_confirmed_schema
from idpo.product_auto.provider import ModelReply
from idpo.product_auto.logic import keyed_values_example, values_prompt
from idpo.product_auto.strict_output import (
    PROFILE,
    PROFILE_V2,
    compile_confirmed_values_response_format_v2,
    parse_confirmed_strict_values_reply,
    parse_confirmed_strict_values_reply_v2,
)
from idpo.product_auto.visual_output import (
    PROFILE_V2 as VISUAL_PROFILE_V2,
    compile_visual_response_format,
    parse_visual_values_reply,
)
from idpo.product_auto.visual_input import INSTRUCTIONS as V1_VISUAL_INSTRUCTIONS
from idpo.product_auto.workflow import process_auto
from idpo.tests.test_confirmed_schema_routing import snapshot
from idpo.tests.test_product_visual_workflow import fake_ocr, source_image


FIELDS = [
    {"field_id": "item_name", "type": "array[object]", "group": "items",
     "description": "Item name", "example_values": ["Widget"]},
    {"field_id": "quantity", "type": "array[object]", "group": "items",
     "description": "Item quantity", "example_values": ["2"]},
    {"field_id": "total", "type": "decimal", "description": "Final amount",
     "example_values": ["12.50"]},
]
SCHEMA = [{"field_id": field["field_id"], "type": field["type"],
           **({"group": field["group"]} if "group" in field else {})} for field in FIELDS]
PAGES = [{"page": 1, "text": "Widget 2 Total: 12.50"}]
VALUES = {"values": {
    "item_name": {"value": [{"row": 0, "value": "Widget", "page": 1, "quote": "Widget"}],
                  "page": None, "quote": None},
    "quantity": {"value": [{"row": 0, "value": "2", "page": 1, "quote": "2"}],
                 "page": None, "quote": None},
    "total": {"value": "12.50", "page": 1, "quote": "12.50"},
}}


def test_compiler_requires_exact_typed_field_keys_and_nullable_values() -> None:
    wire = compile_confirmed_values_response_format_v2(SCHEMA)
    assert wire["type"] == "json_schema" and wire["json_schema"]["strict"] is True
    assert wire["json_schema"]["name"] == "docai_confirmed_values_v2"
    outer = wire["json_schema"]["schema"]
    assert outer["required"] == ["values"] and outer["additionalProperties"] is False
    values = outer["properties"]["values"]
    assert values["type"] == "object" and values["additionalProperties"] is False
    assert values["required"] == ["item_name", "quantity", "total"]
    for item in values["properties"].values():
        assert item["required"] == ["value", "page", "quote"]
        assert item["additionalProperties"] is False
    assert values["properties"]["total"]["properties"]["value"]["type"] == ["number", "string", "null"]
    assert values["properties"]["item_name"]["properties"]["value"]["type"] == ["array", "null"]
    assert values["properties"]["item_name"]["properties"]["page"] == {"type": "null"}
    assert values["properties"]["item_name"]["properties"]["quote"] == {"type": "null"}
    assert values["properties"]["item_name"]["properties"]["value"]["items"]["properties"]["quote"] == {"type": "string"}
    visual = compile_visual_response_format(SCHEMA, profile=VISUAL_PROFILE_V2)
    assert visual["json_schema"]["name"] == "docai_visual_confirmed_values_v2"
    assert visual["json_schema"]["schema"]["properties"]["values"]["required"] == values["required"]
    assert visual["json_schema"]["schema"]["properties"]["values"]["properties"]["item_name"]["properties"]["page"] == {"type": "null"}
    assert visual["json_schema"]["schema"]["properties"]["values"]["properties"]["item_name"]["properties"]["quote"] == {"type": "null"}
    assert visual["json_schema"]["schema"]["properties"]["values"]["properties"]["item_name"]["properties"]["value"]["items"]["properties"]["quote"] == {"type": ["string", "null"]}


def test_keyed_parser_distinguishes_required_null_from_missing_key_and_preserves_v1() -> None:
    result = parse_confirmed_strict_values_reply_v2(json.dumps(VALUES), SCHEMA, PAGES)
    assert result is not None and set(result) == {"item_name", "quantity", "total"}
    assert result["total"]["status"] == "accepted"
    assert result["item_name"]["value"][0]["status"] == "accepted"
    missing = copy.deepcopy(VALUES)
    missing["values"]["quantity"] = {"value": None, "page": None, "quote": None}
    parsed_missing = parse_confirmed_strict_values_reply_v2(json.dumps(missing), SCHEMA, PAGES)
    assert parsed_missing is not None and parsed_missing["quantity"]["status"] == "missing"
    omitted = copy.deepcopy(missing)
    del omitted["values"]["quantity"]
    assert parse_confirmed_strict_values_reply_v2(json.dumps(omitted), SCHEMA, PAGES) is None
    assert parse_confirmed_strict_values_reply(json.dumps(VALUES), SCHEMA, PAGES) is None
    old = {"values": [{"field_id": field_id, **item} for field_id, item in VALUES["values"].items()]}
    assert parse_confirmed_strict_values_reply(json.dumps(old), SCHEMA, PAGES) is not None
    assert parse_confirmed_strict_values_reply_v2(json.dumps(old), SCHEMA, PAGES) is None


def test_v1_prompt_bytes_remain_frozen_and_v2_example_is_keyed_only() -> None:
    fields = [{"field_id": "total", "type": "decimal"}]
    pages = [{"page": 1, "text": "Total: 12.50"}]
    old = values_prompt(pages, fields, "Extract total")
    assert hashlib.sha256(old.encode()).hexdigest() == "dd5c2e7b97ef7040c3ce3e570260fb13b1d99942456e9eeb53b41eaad331c1f0"
    assert hashlib.sha256(V1_VISUAL_INSTRUCTIONS.encode()).hexdigest() == \
        "a16f2ba3019320c44fcdffdb350647506bdc5c6573fb4603cb5d8e36f95fe25c"
    keyed = values_prompt(pages, fields, "Extract total", output_shape="keyed_v2")
    assert '{"values":{"total":{"value":null,"page":null,"quote":null}}}' in keyed
    assert '{"values":[' not in keyed
    assert '"field_id":"..."' not in keyed
    assert "outer page and quote are null" in keyed
    with pytest.raises(ValueError, match="Unknown values prompt shape"):
        values_prompt(pages, fields, output_shape="not_versioned")


@pytest.mark.parametrize("mutation", [
    lambda value: value["values"].update(extra={"value": None, "page": None, "quote": None}),
    lambda value: value.update(extra=True),
    lambda value: value["values"]["total"].update(extra=True),
    lambda value: value["values"]["total"].pop("value"),
    lambda value: value["values"]["total"].update(value={"wrong": "type"}),
    lambda value: value["values"]["total"].update(value=True),
    lambda value: value["values"]["total"].update(page=2),
    lambda value: value["values"]["total"].update(page=True),
    lambda value: value["values"]["item_name"]["value"][0].update(page=2),
    lambda value: value["values"]["item_name"]["value"][0].update(quote=None),
    lambda value: value["values"]["item_name"].update(page=1, quote="Widget"),
    lambda value: value["values"]["quantity"].update(value=None, page=1),
    lambda value: value["values"]["item_name"]["value"].append(
        {"row": 0, "value": "Widget", "page": 1, "quote": "Widget"}),
])
def test_rejects_extra_missing_wrong_type_and_source_bounds(mutation) -> None:
    changed = copy.deepcopy(VALUES)
    mutation(changed)
    assert parse_confirmed_strict_values_reply_v2(json.dumps(changed), SCHEMA, PAGES) is None


@pytest.mark.parametrize("text", [
    '{"values":{"total":{"value":null,"value":"12.50","page":1,"quote":"12.50"}}}',
    '{"values":{"total":{"value":NaN,"page":1,"quote":"12.50"}}}',
    '{"values":{"total":{"value":1e999,"page":1,"quote":"12.50"}}}',
    " " * 1_000_001,
    '{"values":' + '[' * 2000 + 'null' + ']' * 2000 + '}',
], ids=["duplicate-key", "nan", "overflow", "oversized", "nested"])
def test_rejects_duplicate_nonfinite_oversized_or_deep_reply(text: str) -> None:
    assert parse_confirmed_strict_values_reply_v2(text, SCHEMA, PAGES) is None


def test_empty_linked_cells_stay_pending_and_are_not_invented() -> None:
    changed = copy.deepcopy(VALUES)
    changed["values"]["quantity"]["value"] = []
    parsed = parse_confirmed_strict_values_reply_v2(json.dumps(changed), SCHEMA, PAGES)
    assert parsed is not None
    assert parsed["quantity"]["value"] == []
    assert parsed["quantity"]["status"] == "needs_review"


class TextModel:
    model = "synthetic-text"

    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.calls: list[dict] = []

    def complete_json(self, **kwargs) -> ModelReply:
        self.calls.append(kwargs)
        return ModelReply(text=self.replies[len(self.calls) - 1], latency_ms=1,
                          finish_reason="stop", sdk_attempts=1)


def _run_text(tmp_path: Path, source_text: str, model: TextModel, *, segmented: bool = False):
    schema_path, digest = snapshot(tmp_path, fields=FIELDS)
    schema = load_confirmed_schema(schema_path, digest)
    source = tmp_path / "source.txt"
    source.write_text(source_text, encoding="utf-8")
    run = process_auto(source, model=model, confirmed_schema=schema, response_format_profile=PROFILE_V2,
                       long_document_profile="bounded_text_segments_v1" if segmented else "reject",
                       output_root=tmp_path / "runs")
    run_dir = Path(run["run_dir"])
    candidate = json.loads((run_dir / "candidates.jsonl").read_text())
    sidecar = json.loads((run_dir / "docs" / candidate["doc_id"] / "result.json").read_text())
    manifest = json.loads((run_dir / "manifest.jsonl").read_text())
    marker = json.loads((run_dir / "run.json").read_text())
    return candidate, sidecar, manifest, marker


def test_text_workflow_pins_v2_and_hashes_actual_raw_reply(tmp_path: Path) -> None:
    raw = json.dumps(VALUES, separators=(",", ":"))
    model = TextModel([raw])
    candidate, sidecar, manifest, run = _run_text(tmp_path, PAGES[0]["text"], model)
    assert len(model.calls) == 1
    assert "object keyed by every confirmed field_id" in model.calls[0]["prompt"]
    assert keyed_values_example(FIELDS) in model.calls[0]["prompt"]
    assert '{"values":[' not in model.calls[0]["prompt"]
    assert "outer page and quote are null" in model.calls[0]["prompt"]
    assert model.calls[0]["response_format"] == compile_confirmed_values_response_format_v2(SCHEMA)
    assert [item["field_id"] for item in candidate["extracted_values"]] == list(VALUES["values"])
    assert candidate["document_status"] == "needs_review"
    assert run["response_format_profile"] == manifest["response_format_profile"] == \
        sidecar["response_format_profile"] == PROFILE_V2
    assert sidecar["model_calls"][0]["raw_reply_sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    assert "values" not in sidecar["model_calls"][0]
    assert len({run["response_format_sha256"], manifest["response_format_sha256"],
                sidecar["response_format_sha256"]}) == 1


def test_text_workflow_rejects_omitted_field_without_a_second_call(tmp_path: Path) -> None:
    incomplete = copy.deepcopy(VALUES)
    del incomplete["values"]["quantity"]
    raw = json.dumps(incomplete)
    model = TextModel([raw])
    candidate, sidecar, _, _ = _run_text(tmp_path, PAGES[0]["text"], model)
    assert len(model.calls) == 1
    assert sidecar["reason"] == "invalid_strict_values_model_response"
    assert candidate["document_status"] == "needs_review"
    assert all(item["value"] is None for item in candidate["extracted_values"])
    assert sidecar["model_calls"][0]["raw_reply_sha256"] == hashlib.sha256(raw.encode()).hexdigest()


def test_segmented_v2_requires_every_key_in_every_segment_and_keeps_coverage(tmp_path: Path) -> None:
    filler = ("filler " * 100 + "\n") * 36
    source = "Widget 2\n" + filler + "\nTotal: 12.50\n"

    class SegmentModel(TextModel):
        def complete_json(self, **kwargs) -> ModelReply:
            self.calls.append(kwargs)
            segment = kwargs["prompt"].split("Document data: ", 1)[1].split(" This is one bounded", 1)[0]
            segment_text = json.loads(segment)["pages"][0]["text"]
            payload = copy.deepcopy(VALUES)
            if "Widget" not in segment_text:
                for key in ("item_name", "quantity"):
                    payload["values"][key] = {"value": None, "page": None, "quote": None}
            if "12.50" not in segment_text:
                payload["values"]["total"] = {"value": None, "page": None, "quote": None}
            return ModelReply(text=json.dumps(payload), latency_ms=1, finish_reason="stop", sdk_attempts=1)

    model = SegmentModel([])
    candidate, sidecar, manifest, _ = _run_text(tmp_path, source, model, segmented=True)
    assert len(model.calls) == 2
    assert all('{"values":[' not in call["prompt"] and
               keyed_values_example(FIELDS) in call["prompt"]
               for call in model.calls)
    assert manifest["long_document"]["full_source_covered"] is True
    assert all(call["raw_reply_sha256"] for call in sidecar["model_calls"])
    assert candidate["extracted_values"][2]["value"] == 12.5
    assert candidate["extracted_values"][2]["evidence"]["page"] == 1


@pytest.mark.parametrize("visual_profile", ["bounded_visual_v1", "bounded_visual_selective_jpeg95_v1"])
def test_visual_workflow_uses_v2_wire_and_retains_review_only(tmp_path: Path, monkeypatch, visual_profile: str) -> None:
    source = source_image(tmp_path)
    fake_ocr(monkeypatch, texts=["Widget 2 Total: 12.50"])
    schema_path, digest = snapshot(tmp_path, fields=FIELDS)
    schema = load_confirmed_schema(schema_path, digest)
    raw_values = copy.deepcopy(VALUES)
    raw_values["values"]["item_name"]["value"][0]["quote"] = None
    raw = json.dumps(raw_values)

    class VisualModel:
        model = "synthetic-visual"
        max_tokens = 8192

        def __init__(self):
            self.requests = []

        def complete_visual_json(self, request):
            body = request.validated_body(model=self.model, max_tokens=self.max_tokens)
            self.requests.append(body)
            return ModelReply(text=raw, latency_ms=1, finish_reason="stop", sdk_attempts=1)

        def complete_json(self, **kwargs):
            pytest.fail("visual route must not incur a text call")

    model = VisualModel()
    run = process_auto(source, model=model, confirmed_schema=schema, response_format_profile=PROFILE_V2,
                       visual_document_profile=visual_profile, output_root=tmp_path / "runs")
    run_dir = Path(run["run_dir"])
    candidate = json.loads((run_dir / "candidates.jsonl").read_text())
    sidecar = json.loads((run_dir / "docs" / candidate["doc_id"] / "result.json").read_text())
    manifest = json.loads((run_dir / "manifest.jsonl").read_text())
    assert len(model.requests) == 1
    assert model.requests[0]["response_format"] == compile_visual_response_format(SCHEMA, profile=VISUAL_PROFILE_V2)
    image_url = model.requests[0]["messages"][1]["content"][2]["image_url"]["url"]
    expected_mime = "image/jpeg" if visual_profile == "bounded_visual_selective_jpeg95_v1" else "image/png"
    assert image_url.startswith(f"data:{expected_mime};base64,")
    visual_prompt = model.requests[0]["messages"][1]["content"][0]["text"]
    instructions, document_json = visual_prompt.split("Document data: ", 1)
    assert "object keyed by every confirmed field_id" in instructions
    assert keyed_values_example(FIELDS) in instructions
    assert "outer page and quote are null" in instructions
    assert '{"values":[' not in instructions
    assert set(json.loads(document_json)) == {"fields", "pages", "user_intent"}
    assert candidate["document_status"] == "needs_review"
    assert all(item["status"] == "needs_review" for item in candidate["extracted_values"] if item["value"] is not None)
    assert sidecar["response_format_profile"] == manifest["response_format_profile"] == VISUAL_PROFILE_V2
    marker = json.loads((run_dir / "run.json").read_text())
    assert marker["configured_response_format_profile"] == PROFILE_V2
    assert sidecar["model_calls"][0]["raw_reply_sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    assert sidecar["visual_document"]["full_source_covered"] is True


def test_v2_requires_confirmation_before_artifacts(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text(PAGES[0]["text"], encoding="utf-8")
    model = TextModel([json.dumps(VALUES)])
    with pytest.raises(ValueError, match="confirmed schema"):
        process_auto(source, model=model, response_format_profile=PROFILE_V2,
                     output_root=tmp_path / "runs")
    assert not (tmp_path / "runs").exists()
    assert not model.calls
    assert PROFILE == "strict_confirmed_values_v1"


def test_visual_v2_rejects_missing_key_and_out_of_source_page() -> None:
    valid = copy.deepcopy(VALUES)
    valid["values"]["item_name"]["value"][0]["quote"] = None
    assert parse_visual_values_reply(json.dumps(valid), SCHEMA, PAGES, profile=VISUAL_PROFILE_V2) is not None
    del valid["values"]["quantity"]
    assert parse_visual_values_reply(json.dumps(valid), SCHEMA, PAGES, profile=VISUAL_PROFILE_V2) is None
    valid = copy.deepcopy(VALUES)
    valid["values"]["item_name"]["value"][0]["page"] = 99
    assert parse_visual_values_reply(json.dumps(valid), SCHEMA, PAGES, profile=VISUAL_PROFILE_V2) is None
    valid = copy.deepcopy(VALUES)
    valid["values"]["item_name"].update(page=1, quote="Widget")
    assert parse_visual_values_reply(json.dumps(valid), SCHEMA, PAGES, profile=VISUAL_PROFILE_V2) is None


def test_visual_workflow_rejects_omitted_key_without_partial_candidate(tmp_path: Path, monkeypatch) -> None:
    source = source_image(tmp_path)
    fake_ocr(monkeypatch, texts=["Widget 2 Total: 12.50"])
    schema_path, digest = snapshot(tmp_path, fields=FIELDS)
    schema = load_confirmed_schema(schema_path, digest)
    incomplete = copy.deepcopy(VALUES)
    del incomplete["values"]["quantity"]
    raw = json.dumps(incomplete)

    class IncompleteModel:
        model = "synthetic-visual"
        max_tokens = 8192
        calls = 0

        def complete_visual_json(self, request):
            self.calls += 1
            return ModelReply(text=raw, latency_ms=1, finish_reason="stop", sdk_attempts=1)

        def complete_json(self, **kwargs):
            pytest.fail("must not retry using text")

    model = IncompleteModel()
    run = process_auto(source, model=model, confirmed_schema=schema, response_format_profile=PROFILE_V2,
                       visual_document_profile="bounded_visual_v1", output_root=tmp_path / "runs")
    run_dir = Path(run["run_dir"])
    candidate = json.loads((run_dir / "candidates.jsonl").read_text())
    sidecar = json.loads((run_dir / "docs" / candidate["doc_id"] / "result.json").read_text())
    assert model.calls == 1
    assert sidecar["reason"] == "visual_request_invalid_values"
    assert sidecar["model_calls"][0]["raw_reply_sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    assert candidate["document_status"] == "failed" and candidate["extracted_values"] == []
