from __future__ import annotations

import json

from idpo.product_auto.provider import ModelReply
from product_eval.icore_confirmed_dev import MAX_CALLS, MODEL, RecordedChat


class FakeChat:
    def __init__(self, reply=None):
        self.reply = reply or ModelReply('{"values":[]}', 1, 3, 5, "stop", sdk_attempts=1)
        self.calls = 0

    def complete_json(self, **_kwargs):
        self.calls += 1
        return self.reply


def test_global_six_attempt_cap_and_each_source_cap(tmp_path):
    underlying = FakeChat()
    wrapper = RecordedChat(underlying, tmp_path, "fake-secret")
    for index in range(MAX_CALLS):
        wrapper.for_source({"doc_id": str(index), "source_sha256": "a" * 64})
        assert wrapper.complete_json(system="JSON only", prompt="synthetic values").sdk_attempts == 1
        assert wrapper.complete_json(system="JSON only", prompt="unexpected second").sdk_attempts == 0
    wrapper.for_source({"doc_id": "seventh", "source_sha256": "b" * 64})
    assert wrapper.complete_json(system="JSON only", prompt="synthetic values").sdk_attempts == 0
    assert underlying.calls == MAX_CALLS
    assert len(list(tmp_path.glob("reply-*.json"))) == MAX_CALLS
    assert all(json.loads(p.read_text())["model"] == MODEL for p in tmp_path.glob("request-*.json"))


def test_response_bodies_redact_credential_without_saving_headers(tmp_path):
    key = "iba_" + "synthetic_secret_for_test" * 2
    underlying = FakeChat(ModelReply(key, 1, 2, 3, "stop", sdk_attempts=1))
    wrapper = RecordedChat(underlying, tmp_path, key)
    wrapper.for_source({"doc_id": "source", "source_sha256": "a" * 64})
    wrapper.complete_json(system="JSON only", prompt="synthetic values")

    class Response:
        status_code = 200
        text = '{"data":"' + key + '"}'

        def read(self):
            return self.text.encode()

    wrapper.http_response(Response())
    for path in (tmp_path / "reply-01.json", tmp_path / "http-response-01.json"):
        assert key not in path.read_text()
        assert "[REDACTED]" in path.read_text()
    assert json.loads((tmp_path / "http-response-01.json").read_text())["headers_saved"] is False


def test_ambiguous_transport_stops_subsequent_sources(tmp_path):
    underlying = FakeChat(ModelReply("", 1, error="APITimeoutError", error_category="transport_timeout", sdk_attempts=1))
    wrapper = RecordedChat(underlying, tmp_path, "fake-secret")
    for index in range(2):
        wrapper.for_source({"doc_id": str(index), "source_sha256": "a" * 64})
        wrapper.complete_json(system="JSON only", prompt="synthetic values")
    assert underlying.calls == 1
    assert wrapper.stop_reason == "transport_timeout"
