"""Offline source-lock, call-limit, and denominator checks for the ICORE arm."""

from __future__ import annotations

import json
from pathlib import Path

from idpo.product_auto.provider import ModelReply
from product_eval.icore_two_public_runner import (
    LOCK_PATH,
    LOCK_SHA256,
    MAX_ATTEMPTS,
    PARENT_LOCK,
    FourCallBudget,
    TwoCallProductChat,
    _canonical_lf_sha256,
    _inside_git,
    _safe_reason,
    _score_two,
)


class FakeChat:
    model = "innobot-luna-6"

    def __init__(self, reply: ModelReply):
        self.reply = reply
        self.calls = 0

    def complete_json(self, *, system: str, prompt: str) -> ModelReply:
        self.calls += 1
        return self.reply


def _chat(tmp_path: Path, reply: ModelReply) -> tuple[TwoCallProductChat, FakeChat, FourCallBudget]:
    underlying = FakeChat(reply)
    budget = FourCallBudget(tmp_path / "calls.jsonl")
    chat = TwoCallProductChat(underlying, budget)  # type: ignore[arg-type]
    return chat, underlying, budget


def test_frozen_two_sources_are_exact_rank_six_subset_of_prior_lock() -> None:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    prior = json.loads(PARENT_LOCK.read_text(encoding="utf-8"))
    expected = [
        row for family in ("registration-form", "ad-buy-form")
        for row in prior["sources"]
        if row["family"] == family and row["selection_rank"] == 6
    ]
    assert len(lock["sources"]) == len(expected) == 2
    for locked, parent in zip(lock["sources"], expected, strict=True):
        assert all(locked[key] == value for key, value in parent.items() if key in locked)
    assert len({row["source_sha256"] for row in lock["sources"]}) == 2
    assert lock["max_authenticated_chat_attempts"] == MAX_ATTEMPTS == 4


def test_source_lock_hash_is_stable_on_windows_crlf_checkout(tmp_path: Path) -> None:
    converted = tmp_path / "lock.json"
    converted.write_bytes(LOCK_PATH.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert _canonical_lf_sha256(LOCK_PATH) == _canonical_lf_sha256(converted) == LOCK_SHA256


def test_global_four_request_cap_blocks_fifth_sdk_call(tmp_path: Path) -> None:
    reply = ModelReply(text='{"fields":[]}', latency_ms=1, prompt_tokens=5,
                       completion_tokens=3, finish_reason="stop", sdk_attempts=1)
    chat, underlying, budget = _chat(tmp_path, reply)
    for index in range(2):
        chat.for_source({"source_sha256": f"{index + 1:064x}", "doc_id": f"synthetic_{index}"})
        chat.complete_json(system="JSON", prompt="schema")
        chat.complete_json(system="JSON", prompt="values")
    assert underlying.calls == budget.attempts == 4
    chat.for_source({"source_sha256": "f" * 64, "doc_id": "synthetic_third"})
    blocked = chat.complete_json(system="JSON", prompt="schema")
    assert blocked.sdk_attempts == 0
    assert budget.stop_reason == "attempt_cap"
    assert underlying.calls == 4


def test_third_product_phase_and_ambiguous_transport_stop_locally(tmp_path: Path) -> None:
    reply = ModelReply(text='{"fields":[]}', latency_ms=1, prompt_tokens=5,
                       completion_tokens=3, finish_reason="stop", sdk_attempts=1)
    chat, underlying, budget = _chat(tmp_path, reply)
    chat.for_source({"source_sha256": "a" * 64, "doc_id": "synthetic"})
    chat.complete_json(system="JSON", prompt="schema")
    chat.complete_json(system="JSON", prompt="values")
    blocked = chat.complete_json(system="JSON", prompt="unexpected")
    assert blocked.sdk_attempts == 0
    assert budget.stop_reason == "unexpected_third_product_call"
    assert underlying.calls == 2

    transport = ModelReply(text="", latency_ms=1, error="APIConnectionError",
                           error_category="transport_connect", sdk_attempts=1)
    other = tmp_path / "other"
    other.mkdir()
    chat, underlying, budget = _chat(other, transport)
    chat.for_source({"source_sha256": "b" * 64, "doc_id": "synthetic_other"})
    chat.complete_json(system="JSON", prompt="schema")
    chat.complete_json(system="JSON", prompt="values")
    assert underlying.calls == 1
    assert budget.stop_reason == "ambiguous_transport"


def test_truncated_reply_stops_before_value_call(tmp_path: Path) -> None:
    reply = ModelReply(text="{", latency_ms=1, prompt_tokens=10,
                       completion_tokens=1536, finish_reason="length", sdk_attempts=1)
    chat, underlying, budget = _chat(tmp_path, reply)
    chat.for_source({"source_sha256": "c" * 64, "doc_id": "synthetic"})
    chat.complete_json(system="JSON", prompt="schema")
    blocked = chat.complete_json(system="JSON", prompt="values")
    assert budget.stop_reason == "output_truncated"
    assert blocked.sdk_attempts == 0
    assert underlying.calls == 1


def test_report_reason_allowlist_drops_untrusted_text(tmp_path: Path) -> None:
    (tmp_path / ".git").write_text("gitdir: somewhere", encoding="utf-8")
    assert _inside_git(tmp_path / "new" / "output")
    assert _safe_reason("schema_provider_error") == "schema_provider_error"
    assert _safe_reason("private source text and key") == "other"


def test_oversized_prompt_stops_before_any_sdk_call(tmp_path: Path) -> None:
    reply = ModelReply(text="{}", latency_ms=1, prompt_tokens=1,
                       completion_tokens=1, finish_reason="stop", sdk_attempts=1)
    chat, underlying, budget = _chat(tmp_path, reply)
    chat.for_source({"source_sha256": "d" * 64, "doc_id": "synthetic"})
    blocked = chat.complete_json(system="JSON", prompt="x" * 12_001)
    assert blocked.sdk_attempts == 0
    assert underlying.calls == budget.attempts == 0
    assert budget.stop_reason == "prompt_cap"


def test_scoring_retains_missing_second_document(tmp_path: Path) -> None:
    fixtures = Path(__file__).resolve().parents[1] / "fixtures"
    inventory = [
        {"family": "registration-form", "doc_id": "synthetic-invoice-1"},
        {"family": "ad-buy-form", "doc_id": "synthetic-request-1"},
    ]
    candidate = json.loads((fixtures / "candidate.jsonl").read_text(encoding="utf-8").splitlines()[0])
    report = _score_two(fixtures / "gold.jsonl", inventory,
                        {candidate["doc_id"]: candidate}, tmp_path)
    assert report["registration-form"]["documents"]["candidate"] == 1
    assert report["ad-buy-form"]["documents"]["gold"] == 1
    assert report["ad-buy-form"]["documents"]["missing_candidate"] == 1
    assert report["ad-buy-form"]["schema"]["fn"] == 3
    assert "per_field" not in report["ad-buy-form"]
