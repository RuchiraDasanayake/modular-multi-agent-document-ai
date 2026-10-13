"""Source-free S1 grammar-probe contract tests."""

from __future__ import annotations

import json

from product_eval.s1_grammar_probe import assess_reply, request_body


def _reply(content: str, finish: str = "stop") -> dict:
    return {"choices": [{"message": {"content": content}, "finish_reason": finish}]}


def test_probe_request_only_contains_synthetic_candidates() -> None:
    body = request_body()
    assert body["response_format"]["schema"]["properties"]["fields"]["items"]["properties"]["candidate_id"]["enum"] == ["probe_candidate"]
    assert "invented_candidate" in body["messages"][0]["content"]
    assert body["max_tokens"] == 512


def test_probe_accepts_constrained_review_only_reply() -> None:
    content = json.dumps({"schema_version": 1, "fields": [{
        "candidate_id": "probe_candidate", "field_id": "probe_field",
        "type": "string", "decision": "propose",
    }]})
    assert assess_reply(_reply(content))["status"] == "passed"


def test_probe_rejects_unconstrained_or_truncated_reply() -> None:
    invalid = json.dumps({"schema_version": 2, "fields": [{
        "candidate_id": "invented_candidate", "field_id": "probe_field",
        "type": "string", "decision": "propose",
    }]})
    assert assess_reply(_reply(invalid))["status"] == "failed"
    assert assess_reply(_reply(invalid, "length"))["status"] == "failed"
