"""Offline limits and scoring checks for the ICORE public pilot runner."""

from __future__ import annotations

import json
from pathlib import Path

from idpo.product_auto.provider import ModelReply
from product_eval.icore_real_dev_runner import AuditedChat, CallBudget, _alias_schema


class FakeChat:
    model = "innobot-luna-6"

    def __init__(self, reply: ModelReply):
        self.reply = reply
        self.calls = 0

    def complete_json(self, *, system: str, prompt: str) -> ModelReply:
        self.calls += 1
        return self.reply


def _audited(tmp_path: Path, reply: ModelReply) -> tuple[AuditedChat, FakeChat, CallBudget]:
    fake = FakeChat(reply)
    budget = CallBudget(tmp_path / "calls.jsonl")
    audited = AuditedChat(fake, budget)  # type: ignore[arg-type]
    audited.for_source({"source_sha256": "a" * 64, "doc_id": "synthetic_doc"})
    return audited, fake, budget


def test_prompt_cap_blocks_request_before_billable_attempt(tmp_path: Path) -> None:
    audited, fake, budget = _audited(tmp_path, ModelReply(text="{}", latency_ms=1, sdk_attempts=1))
    reply = audited.complete_json(system="JSON", prompt="x" * 12001)
    assert reply.error == "prompt_cap"
    assert reply.sdk_attempts == 0
    assert budget.attempts == 0
    assert fake.calls == 0


def test_success_receipt_hashes_request_and_omits_prompt_text(tmp_path: Path) -> None:
    audited, fake, budget = _audited(tmp_path, ModelReply(
        text='{"fields":[]}', latency_ms=12, prompt_tokens=25, completion_tokens=8,
        finish_reason="stop", sdk_attempts=1,
    ))
    reply = audited.complete_json(system="JSON", prompt="private-looking synthetic prompt")
    assert reply.finish_reason == "stop"
    assert fake.calls == budget.attempts == 1
    assert budget.reported_tokens == 33
    rows = [json.loads(line) for line in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert [row["event"] for row in rows] == ["attempt_started", "attempt_completed"]
    assert rows[1]["canonical_request_sha256"] == rows[0]["canonical_request_sha256"]
    assert "private-looking synthetic prompt" not in json.dumps(rows)
    assert rows[1]["response_chars"] == len(reply.text)


def test_ambiguous_transport_stops_after_one_attempt(tmp_path: Path) -> None:
    audited, fake, budget = _audited(tmp_path, ModelReply(
        text="", latency_ms=3000, error="APIConnectionError",
        error_category="transport_other", sdk_attempts=1,
    ))
    audited.complete_json(system="JSON", prompt="first")
    assert budget.stop_reason == "ambiguous_transport"
    audited.complete_json(system="JSON", prompt="second")
    assert fake.calls == budget.attempts == 1


def test_missing_usage_stops_after_one_attempt(tmp_path: Path) -> None:
    audited, fake, budget = _audited(tmp_path, ModelReply(
        text="{}", latency_ms=2, finish_reason="stop", sdk_attempts=1,
    ))
    audited.complete_json(system="JSON", prompt="first")
    assert budget.stop_reason == "missing_usage"
    audited.complete_json(system="JSON", prompt="second")
    assert fake.calls == budget.attempts == 1


def test_predeclared_aliases_preserve_raw_and_unmatched_names() -> None:
    gold = {"doc": {"gold_schema": [
        {"field_id": "registration_num", "type": "string"},
        {"field_id": "signer_name", "type": "string"},
    ]}}
    candidate = {"doc": {"proposed_schema": [
        {"field_id": "registration_number", "type": "string"},
        {"field_id": "unsupported_guess", "type": "string"},
    ]}}
    aliases = {"registration-form": {
        "registration_num": {"aliases": ["registration_number"]},
        "signer_name": {"aliases": ["signatory_name"]},
    }}
    score = _alias_schema(gold, candidate, "registration-form", aliases)
    assert (score["matched"], score["gold_fields"], score["unmatched_proposals"]) == (1, 2, 1)
    assert score["per_document"][0]["raw_proposed_field_ids"] == [
        "registration_number", "unsupported_guess",
    ]
    assert score["per_document"][0]["unmatched_proposed_field_ids"] == ["unsupported_guess"]
