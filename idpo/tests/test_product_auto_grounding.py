"""Fail-closed checks for typed product proposals and source quotes."""

from __future__ import annotations

import json
from pathlib import Path

from idpo.product_auto import process_auto
from idpo.product_auto.logic import coerce_value, parse_values_reply
from idpo.product_auto.provider import ModelReply
from product_eval.contracts import load_jsonl


def _value_reply(field_id: str, field_type: str, value: object, quote: str) -> dict[str, object]:
    fields = [{"field_id": field_id, "type": field_type}]
    pages = [{"page": 1, "text": quote}]
    reply = json.dumps({"values": [{"field_id": field_id, "value": value, "page": 1, "quote": quote}]})
    result = parse_values_reply(reply, fields, pages)
    assert result is not None
    return result[field_id]


def test_boolean_quote_with_both_polarities_requires_review() -> None:
    ambiguous = _value_reply("approved", "boolean", True, "Yes / No")
    assert ambiguous["status"] == "needs_review"
    assert ambiguous["evidence"] == {"page": 1, "start": 0, "end": 8, "quote": "Yes / No"}

    unambiguous = _value_reply("approved", "boolean", True, "Yes")
    assert unambiguous["status"] == "accepted"
    assert unambiguous["value"] is True


def test_identifier_quote_must_be_the_complete_value() -> None:
    partial = _value_reply("invoice_number", "string", "INV-42", "INV-42-A")
    assert partial["status"] == "needs_review"
    assert partial["evidence"]["quote"] == "INV-42-A"

    complete = _value_reply("invoice_number", "string", "INV-42-A", "INV-42-A")
    assert complete["status"] == "accepted"


def test_json_numeric_values_must_remain_exact_and_finite() -> None:
    safe = _value_reply("count", "integer", 2**53 - 1, str(2**53 - 1))
    assert safe["status"] == "accepted"
    assert safe["value"] == 2**53 - 1

    unsafe = _value_reply("count", "integer", 2**53, str(2**53))
    assert unsafe["status"] == "needs_review"
    assert unsafe["value"] == str(2**53)

    rounded = _value_reply("amount", "decimal", "0.123456789123456789", "0.123456789123456789")
    assert rounded["status"] == "needs_review"
    assert rounded["value"] == "0.123456789123456789"
    assert coerce_value("0.10", "decimal") == (0.1, True)


def test_nonfinite_or_nested_model_values_reject_reply() -> None:
    fields = [{"field_id": "amount", "type": "decimal"}]
    pages = [{"page": 1, "text": "Amount: 100"}]
    for value in ("NaN", "Infinity", "1e400", '{"nested":1}'):
        reply = '{"values":[{"field_id":"amount","value":' + value + '}]} '
        assert parse_values_reply(reply, fields, pages) is None


def test_invalid_model_number_fails_with_valid_json_artifact(tmp_path: Path) -> None:
    class Model:
        def __init__(self) -> None:
            self.replies = [
                ModelReply(text='{"fields":[{"field_id":"amount","type":"decimal"}]}', latency_ms=1),
                ModelReply(text='{"values":[{"field_id":"amount","value":1e400,"page":1,"quote":"100"}]}', latency_ms=1),
            ]

        def complete_json(self, *, system: str, prompt: str) -> ModelReply:
            return self.replies.pop(0)

    source = tmp_path / "amount.txt"
    source.write_text("Amount: 100", encoding="utf-8")
    run = process_auto(source, run_id="invalid_number", model=Model(), output_root=tmp_path / "runs")
    run_dir = Path(run["run_dir"])
    candidate = next(iter(load_jsonl(run_dir / "candidates.jsonl", kind="candidate").values()))
    sidecar = json.loads((run_dir / "docs" / candidate["doc_id"] / "result.json").read_text(encoding="utf-8"))
    assert candidate["document_status"] == "failed"
    assert candidate["extracted_values"] == [
        {"field_id": "amount", "value": None, "status": "missing", "review_state": "pending"}
    ]
    assert sidecar["reason"] == "invalid_values_model_response"
