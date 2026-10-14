"""Synthetic regressions for provider reply isolation and the review contract."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from idpo.agents.preprocess import OcrAgent
from idpo.core.types import AgentResult
from idpo.product_auto.confirmed_schema import load_confirmed_schema
from idpo.product_auto.logic import parse_schema_reply, parse_values_reply
from idpo.product_auto.provider import ModelReply
from idpo.product_auto.visual_output import (
    PROFILE as VISUAL_V1,
)
from idpo.product_auto.visual_output import (
    PROFILE_V2 as VISUAL_V2,
)
from idpo.product_auto.visual_output import (
    parse_visual_values_reply,
)
from idpo.product_auto.workflow import process_auto
from idpo.tests.test_confirmed_schema_routing import snapshot

PROFILES = ["plain_json", "strict_confirmed_values_v1", "strict_confirmed_values_v2"]


def wire(profile: str, field_id: str, value: object, *, quote: str | None = "Alpha") -> str:
    item = {"value": value, "page": 1, "quote": quote}
    values = ({field_id: item} if profile.endswith("_v2") else [{"field_id": field_id, **item}])
    return json.dumps({"values": values}, ensure_ascii=True)


class ReplyModel:
    model = "synthetic-no-network"
    max_tokens = 8192

    def __init__(self, replies: list[str]) -> None:
        self.replies = replies
        self.calls = 0

    def complete_json(self, **kwargs) -> ModelReply:
        reply = self.replies[self.calls]
        self.calls += 1
        return ModelReply(text=reply, latency_ms=1, finish_reason="stop", sdk_attempts=1)

    def complete_visual_json(self, request) -> ModelReply:
        request.validated_body(model=self.model, max_tokens=self.max_tokens)
        return self.complete_json()


def confirmed(tmp_path: Path, field_id: str = "name", field_type: str = "string"):
    directory = tmp_path / "schema"
    directory.mkdir()
    file, digest = snapshot(directory, fields=[
        {"field_id": field_id, "type": field_type, "description": "Requested value", "example_values": []},
    ])
    return load_confirmed_schema(file, digest)


def artifacts(run: dict) -> tuple[list[dict], list[dict]]:
    root = Path(run["run_dir"])
    candidates = [json.loads(line) for line in (root / "candidates.jsonl").read_text(encoding="utf-8").splitlines()]
    results = [json.loads((root / "docs" / item["doc_id"] / "result.json").read_text(encoding="utf-8"))
               for item in candidates]
    assert json.loads((root / "run.json").read_text(encoding="utf-8"))["doc_count"] == len(candidates)
    return candidates, results


NESTED = '{"values":' + "[" * 10_000 + "null" + "]" * 10_000 + "}"


@pytest.mark.parametrize("profile,bad_reply", [
    ("plain_json", NESTED),
    ("plain_json", wire("plain_json", "name", "\ud800")),
    ("strict_confirmed_values_v1", wire("strict_confirmed_values_v1", "name", "\ud800")),
    ("strict_confirmed_values_v2", wire("strict_confirmed_values_v2", "name", "\ud800")),
], ids=["plain-deep", "plain-surrogate", "strict-v1-surrogate", "strict-v2-surrogate"])
def test_hostile_reply_fails_only_its_document_and_completes_batch(
    tmp_path: Path, profile: str, bad_reply: str,
) -> None:
    schema = confirmed(tmp_path)
    sources = tmp_path / "sources"
    sources.mkdir()
    for name in ("01.txt", "02.txt"):
        (sources / name).write_text("Name: Alpha", encoding="utf-8")
    model = ReplyModel([bad_reply, wire(profile, "name", "Alpha")])

    run = process_auto(sources, model=model, confirmed_schema=schema,
                       response_format_profile=profile, output_root=tmp_path / "runs")
    candidates, results = artifacts(run)

    assert model.calls == 2  # One attempt per original, never a retry.
    assert candidates[0]["document_status"] == "failed"
    assert all(item["value"] is None for item in candidates[0]["extracted_values"])
    assert results[0]["reason"] in {"invalid_values_model_response", "invalid_strict_values_model_response"}
    assert candidates[1]["extracted_values"][0]["value"] == "Alpha"
    assert candidates[1]["extracted_values"][0]["status"] == "accepted"


@pytest.mark.parametrize("text", [
    '{"fields":' + "[" * 10_000 + "null" + "]" * 10_000 + "}",
    '{"fields":[{"field_id":"name","type":"string","group":"\\ud800"}]}',
    " " * 1_000_001,
], ids=["deeply-nested", "escaped-surrogate", "oversized"])
def test_malformed_schema_replies_are_rejected_without_raising(text: str) -> None:
    assert parse_schema_reply(text) is None


@pytest.mark.parametrize("profile", PROFILES)
def test_confirmed_unicode_field_id_is_preserved_exactly(tmp_path: Path, profile: str) -> None:
    schema = confirmed(tmp_path, "straße")
    source = tmp_path / "source.txt"
    source.write_text("Name: Alpha", encoding="utf-8")
    model = ReplyModel([wire(profile, "straße", "Alpha")])

    run = process_auto(source, model=model, confirmed_schema=schema,
                       response_format_profile=profile, output_root=tmp_path / "runs")
    candidates, _ = artifacts(run)

    assert model.calls == 1
    assert candidates[0]["proposed_schema"] == [{"field_id": "straße", "type": "string"}]
    assert candidates[0]["extracted_values"][0]["field_id"] == "straße"
    assert candidates[0]["extracted_values"][0]["value"] == "Alpha"
    assert candidates[0]["extracted_values"][0]["status"] == "accepted"


def test_distinct_confirmed_ids_do_not_collide_under_legacy_case_folding() -> None:
    fields = [{"field_id": field_id, "type": "string"} for field_id in ("straße", "strasse")]
    reply = {"values": [{"field_id": field_id, "value": value, "page": 1, "quote": value}
                        for field_id, value in (("straße", "Alpha"), ("strasse", "Beta"))]}
    parsed = parse_values_reply(json.dumps(reply), fields, [{"page": 1, "text": "Alpha Beta"}])
    assert parsed is not None
    assert {field_id: item["value"] for field_id, item in parsed.items()} == {
        "straße": "Alpha", "strasse": "Beta",
    }


@pytest.mark.parametrize("field_id", ["street", "invoice_id"])
def test_quote_case_comparison_matches_frontend_lowercase_contract(field_id: str) -> None:
    fields = [{"field_id": field_id, "type": "string"}]
    pages = [{"page": 1, "text": "Straße"}]
    # The UI uses lowercase, not Unicode case folding that changes ß to ss.
    parsed = parse_values_reply(wire("plain_json", field_id, "STRASSE", quote="Straße"), fields, pages)
    assert parsed is not None and parsed[field_id]["status"] == "needs_review"
    exact = parse_values_reply(wire("plain_json", field_id, "STRAßE", quote="Straße"), fields, pages)
    assert exact is not None and exact[field_id]["status"] == "accepted"


def test_linked_quote_comparison_matches_the_same_frontend_lowercase_contract() -> None:
    fields = [{"field_id": "street", "type": "array[object]", "group": "addresses"}]
    reply = {"values": [{"field_id": "street", "value": [
        {"row": 0, "value": "STRASSE", "page": 1, "quote": "Straße"},
    ]}]}
    parsed = parse_values_reply(json.dumps(reply), fields, [{"page": 1, "text": "Straße"}])
    assert parsed is not None and parsed["street"]["value"][0]["status"] == "needs_review"


@pytest.mark.parametrize("profile", [VISUAL_V1, VISUAL_V2])
@pytest.mark.parametrize("field_type,value", [
    ("integer", "two"), ("decimal", "USD 12.50"), ("boolean", "unknown"),
    ("date", "2026-02-30"), ("string", ""),
])
def test_visual_parser_rejects_values_that_cannot_obey_the_confirmed_type(
    profile: str, field_type: str, value: object,
) -> None:
    fields = [{"field_id": "amount", "type": field_type}]
    assert parse_visual_values_reply(wire(profile, "amount", value, quote=None), fields,
                                     [{"page": 1, "text": ""}], profile=profile) is None


@pytest.mark.parametrize("profile", [VISUAL_V1, VISUAL_V2])
@pytest.mark.parametrize("field_type,value,expected", [
    ("integer", "2", 2), ("decimal", "12.50", 12.5),
    ("boolean", "yes", True), ("date", "2026-10-14", "2026-10-14"),
])
def test_visual_parser_keeps_valid_coercions_review_only(
    profile: str, field_type: str, value: object, expected: object,
) -> None:
    fields = [{"field_id": "amount", "type": field_type}]
    parsed = parse_visual_values_reply(wire(profile, "amount", value, quote=None), fields,
                                      [{"page": 1, "text": ""}], profile=profile)
    assert parsed is not None
    assert parsed["amount"]["value"] == expected
    assert parsed["amount"]["status"] == "needs_review"
    assert parsed["amount"]["visual_grounding_verified"] is False


@pytest.mark.parametrize("profile", PROFILES[1:])
def test_invalid_typed_visual_reply_does_not_claim_complete_source_coverage(
    tmp_path: Path, monkeypatch, profile: str,
) -> None:
    schema = confirmed(tmp_path, "amount", "integer")
    source = tmp_path / "source.png"
    with Image.new("RGB", (200, 100), "white") as image:
        image.save(source)

    def fake_ocr(self, payload, ctx):
        document = payload["document"]
        document.pages = [replace(page, text="", metadata={**page.metadata, "ocr_engine_used": "synthetic"})
                          for page in document.pages]
        return AgentResult(artifacts={"document": document, "signal": SimpleNamespace(failure_reason=None)})

    monkeypatch.setattr(OcrAgent, "run", fake_ocr)
    model = ReplyModel([wire(profile, "amount", "two", quote=None)])
    run = process_auto(source, model=model, confirmed_schema=schema, response_format_profile=profile,
                       visual_document_profile="bounded_visual_v1", output_root=tmp_path / "runs")
    candidates, results = artifacts(run)

    assert model.calls == 1
    assert candidates[0]["document_status"] == "failed"
    assert candidates[0]["extracted_values"] == []
    assert results[0]["reason"] == "visual_request_invalid_values"
    assert results[0]["visual_document"]["full_source_covered"] is False
    assert results[0]["visual_document"]["valid_requests"] == 0
