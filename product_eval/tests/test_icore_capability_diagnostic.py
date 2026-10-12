"""Offline checks for the bounded ICORE research diagnostic."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from product_eval.icore_capability_diagnostic import (
    MAX_OUTPUT_TOKENS,
    append_minimax_schema_probe,
    call_model,
    load_credential,
    parse_strict_probe,
    request_body,
    run,
    strict_format,
)


def test_credential_loader_ignores_adjoining_page_text(tmp_path: Path) -> None:
    key = "iba_" + "x" * 34
    path = tmp_path / "attachment.txt"
    path.write_text(f"Old revoked token {key}Connect with ICORE\nSave this key now {key} Copy key")
    assert load_credential(path) == key
    path.write_text("No copy control here")
    with pytest.raises(ValueError, match="exactly one"):
        load_credential(path)


def test_strict_probe_rejects_extra_and_duplicate_keys() -> None:
    assert parse_strict_probe('{"invoice_number":"INV-2047","total_due":50}') == {
        "valid_json": True, "exact_shape": True, "correct_facts": True,
    }
    extra = parse_strict_probe('{"invoice_number":"INV-2047","total_due":50,"debug":1}')
    assert extra["valid_json"] and not extra["exact_shape"]
    duplicate = parse_strict_probe('{"invoice_number":"X","invoice_number":"Y","total_due":50}')
    assert not duplicate["valid_json"]


def test_call_receipt_never_saves_exception_message() -> None:
    secret = "iba_example_credential_never_log"

    class FailingCompletion:
        def create(self, **_: object) -> object:
            raise RuntimeError("provider echoed " + secret)

    client = SimpleNamespace(chat=SimpleNamespace(completions=FailingCompletion()))
    body = request_body("innobot-luna-6", "public prompt", strict_format())
    receipt, text = call_model(client, body, phase="probe", source_sha256="0" * 64)
    assert text == ""
    assert receipt["error_class"] == "OtherError"
    assert secret not in json.dumps(receipt)
    assert "public prompt" not in json.dumps(receipt)
    assert receipt["max_output_tokens"] == MAX_OUTPUT_TOKENS
    assert receipt["sdk_max_retries"] == 0


def test_six_request_budget_and_continuation_guard() -> None:
    fixture = {"synthetic_documents": {"invoice": {"text": "Invoice INV-2047\nTotal due: 50.00 USD\n"}}}

    class FakeCompletion:
        def create(self, **body: object) -> object:
            if body["response_format"] == {"type": "json_object"}:
                content = '{"fields":[{"field_id":"total_due","type":"decimal"}]}'
            else:
                content = '{"invoice_number":"INV-2047","total_due":50}'
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason="stop")],
                usage=SimpleNamespace(prompt_tokens=10, completion_tokens=10, total_tokens=20),
            )

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletion()))
    report = run(client, fixture=fixture)
    assert report["attempted_chat_requests"] == 6
    assert len(report["receipts"]) == 6
    assert all(receipt["max_output_tokens"] == 1024 for receipt in report["receipts"])
    with pytest.raises(ValueError, match="five-attempt"):
        append_minimax_schema_probe(client, fixture=fixture, report=report)
