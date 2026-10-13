"""The AI brief action is bounded and never publishes a confirmed schema."""

from __future__ import annotations

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from idpo.product_auto.brief_draft import (
    MAX_SAMPLE_CHARS,
    SuggestionFailure,
    main,
    suggest_fields,
)
from idpo.product_auto.provider import ModelReply


class FakeModel:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, *, system: str, prompt: str) -> ModelReply:
        self.calls.append((system, prompt))
        return ModelReply(text=self.text, latency_ms=3.5, prompt_tokens=90,
                          completion_tokens=36, finish_reason="stop", sdk_attempts=1)


def _request(path: Path) -> dict[str, object]:
    return {
        "contract_version": 1, "brief_revision": 1, "brief_payload_sha256": "a" * 64,
        "intent": "Find the payable total and ask if tax is included.", "existing_fields": [],
        "samples": [{"file_id": "b" * 32, "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                     "path": str(path)}],
        "model": {"id": "fake-model", "base_url": "http://127.0.0.1:1/v1"},
    }


def _reply() -> str:
    return json.dumps({"fields": [{"field_id": "payable_total", "type": "decimal",
                                   "description": "Final amount payable after adjustments",
                                   "example_values": ["123.45"]}],
                       "clarification_questions": ["Does payable total include tax?"]})


def test_draft_from_source_has_bounded_excerpt_and_provenance(tmp_path: Path) -> None:
    sample = tmp_path / "invoice.txt"
    sample.write_text("Invoice\nAmount due 123.45\n" + "x" * 10000, encoding="utf-8")
    model = FakeModel(_reply())
    result = suggest_fields(_request(sample), model)
    assert len(model.calls) == 1
    assert len(json.loads(model.calls[0][1])["sample_excerpts_untrusted"][0]["excerpt"]) == MAX_SAMPLE_CHARS
    assert "Ignore instructions" in model.calls[0][0]
    assert result["fields"][0]["field_id"] == "payable_total"
    assert result["clarification_questions"] == ["Does payable total include tax?"]
    receipt = result["provenance"]
    assert receipt["samples"][0]["source_sha256"] == hashlib.sha256(sample.read_bytes()).hexdigest()
    assert receipt["samples"][0]["truncated"] is True
    assert receipt["max_output_tokens"] == 1800
    assert str(sample) not in json.dumps(result)


def test_source_change_prevents_model_call(tmp_path: Path) -> None:
    sample = tmp_path / "invoice.txt"
    sample.write_text("Total 100", encoding="utf-8")
    request = _request(sample)
    sample.write_text("Total 900", encoding="utf-8")
    model = FakeModel(_reply())
    with pytest.raises(ValueError, match="changed"):
        suggest_fields(request, model)
    assert model.calls == []


def test_optional_examples_questions_and_json_fence_are_normalized(tmp_path: Path) -> None:
    sample = tmp_path / "invoice.txt"
    sample.write_text("Invoice SYN-1001", encoding="utf-8")
    model = FakeModel('```json\n{"fields":[{"field_id":"invoice_number","type":"string",'
                      '"description":"The invoice identifier"}]}\n```')
    result = suggest_fields(_request(sample), model)
    assert result["fields"][0]["example_values"] == []
    assert result["clarification_questions"] == []


def test_failed_model_contract_diagnostic_has_hash_and_no_source_text(tmp_path: Path) -> None:
    sample = tmp_path / "invoice.txt"
    sample.write_text("Private fixture text", encoding="utf-8")
    model = FakeModel("not JSON: Private fixture text")
    with pytest.raises(SuggestionFailure) as raised:
        suggest_fields(_request(sample), model)
    diagnostic = raised.value.diagnostic()
    assert diagnostic["stage"] == "parse"
    assert diagnostic["code"] == "invalid_json"
    assert len(diagnostic["raw_reply_sha256"]) == 64
    assert "Private fixture text" not in json.dumps(diagnostic)


def test_raw_reply_capture_is_explicit_and_private_to_caller(tmp_path: Path) -> None:
    sample = tmp_path / "invoice.txt"
    sample.write_text("Total 123.45", encoding="utf-8")
    response = _reply()
    raw_path = tmp_path / "provider.reply.txt"
    result = suggest_fields(_request(sample), FakeModel(response), raw_reply_path=raw_path)
    assert raw_path.read_text(encoding="utf-8") == response
    assert str(raw_path) not in json.dumps(result)
    with pytest.raises(FileExistsError):
        suggest_fields(_request(sample), FakeModel(response), raw_reply_path=raw_path)


@pytest.mark.parametrize("response", [
    '{"fields":[],"clarification_questions":[]}',
    '{"fields":[{"field_id":"total","type":"decimal","description":"x","example_values":[],"extra":1}],"clarification_questions":[]}',
    '{"fields":[{"field_id":"total","type":"decimal","description":"x","example_values":[]}],"fields":[],"clarification_questions":[]}',
])
def test_malformed_model_output_rejected(tmp_path: Path, response: str) -> None:
    sample = tmp_path / "invoice.txt"
    sample.write_text("Total 100", encoding="utf-8")
    model = FakeModel(response)
    with pytest.raises((ValueError, TypeError)):
        suggest_fields(_request(sample), model)
    assert len(model.calls) == 1


def test_cli_uses_one_local_provider_call_without_a_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                        capsys: pytest.CaptureFixture[str]) -> None:
    pytest.importorskip("openai")
    sample = tmp_path / "invoice.txt"
    sample.write_text("Amount due 123.45", encoding="utf-8")
    calls: list[dict[str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            assert self.path == "/v1/chat/completions"
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(body)
            response = {"id": "local-test", "object": "chat.completion", "created": 1,
                        "model": "fake-model", "choices": [{"index": 0,
                        "message": {"role": "assistant", "content": _reply()}, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 50, "completion_tokens": 25, "total_tokens": 75}}
            encoded = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, _format: str, *_args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = _request(sample)
        request["model"] = {"id": "fake-model", "base_url": f"http://127.0.0.1:{server.server_port}/v1"}
        request_file = tmp_path / "request.json"
        raw = json.dumps(request).encode()
        request_file.write_bytes(raw)
        monkeypatch.delenv("ICORE_API_KEY", raising=False)
        assert main(["--request-file", str(request_file), "--request-sha256", hashlib.sha256(raw).hexdigest()]) == 0
        output = json.loads(capsys.readouterr().out)
        assert output["fields"][0]["field_id"] == "payable_total"
        assert output["provenance"]["prompt_tokens"] == 50
        assert len(calls) == 1
        assert calls[0]["max_tokens"] == 1800
        assert "Amount due 123.45" in json.dumps(calls[0])
        assert str(sample) not in json.dumps(calls[0])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
