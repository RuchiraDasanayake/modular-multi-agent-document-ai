from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from PIL import Image

from product_eval import icore_vision_dev3 as runner


def test_image_request_keeps_fixed_fields_and_enforces_byte_budget() -> None:
    fields = [{"field_id": "total", "type": "string", "description": "Final total"}]
    body = runner.request_body(b"image-bytes", fields, "Keep exact values", [{"page": 1, "text": "Total 42"}])
    parts = body["messages"][1]["content"]
    assert body["model"] == "innobot-luna-6"
    assert body["max_tokens"] == 8192
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")
    data = json.loads(parts[0]["text"].split("Document data: ")[1])
    assert data["fields"] == fields
    assert data["pages"] == [{"page": 1, "text": "Total 42"}]
    with pytest.raises(ValueError, match="image byte limit"):
        runner.request_body(b"x" * (runner.MAX_IMAGE_BYTES + 1), fields, "", [])


def test_image_limits_preserve_complete_aspect_and_never_upscale() -> None:
    small = Image.new("RGB", (2200, 1700))
    assert runner.bounded_image(small) is small
    bounded = runner.bounded_image(Image.new("RGB", (4000, 4000)))
    assert bounded.width == bounded.height
    assert bounded.width <= 3072 and bounded.width * bounded.height <= 6_000_000


def test_visual_proposals_and_text_matches_both_require_review() -> None:
    source = {"doc_id": "test", "source_sha256": "a" * 64, "image_sha256": "b" * 64}
    fields = [{"field_id": "total", "type": "string"}, {"field_id": "name", "type": "array[object]", "group": "items"}]
    text = json.dumps({"values": [{"field_id": "total", "value": "42", "page": 1, "quote": "Total 42"},
                                 {"field_id": "name", "value": [{"row": 2, "value": "Visual item", "page": 1, "quote": None}]}]})
    candidate, receipt = runner.project_reply(text, source, fields, [{"page": 1, "text": "Total 42"}])
    assert candidate["document_status"] == "needs_review"
    assert candidate["extracted_values"][0]["status"] == "needs_review"
    cell = candidate["extracted_values"][1]["value"][0]
    assert cell == {"row": 2, "value": "Visual item", "status": "needs_review"}
    assert receipt["text_quote_checks_passed"] == 1
    assert receipt["visual_grounding_verified"] is False


def test_first_image_rejection_stops_remaining_calls_and_keeps_denominator(tmp_path: Path, monkeypatch) -> None:
    frozen_code = {"commit": "fixture", "python_files": {}}
    monkeypatch.setattr(runner, "code_receipt", lambda: frozen_code)
    monkeypatch.setattr(runner, "load_credential", lambda path: "fixture-key")
    shared = tmp_path / "source.bin"
    shared.write_bytes(b"synthetic fixture")
    schema = tmp_path / "schema.json"
    runner.write(schema, {"fields": [{"field_id": "total", "type": "string"}]})
    request = tmp_path / "request.json"
    runner.write(request, runner.request_body(b"fixture", [{"field_id": "total", "type": "string"}], "", []))
    sources = [{"doc_id": doc_id, "source_path": str(shared), "source_sha256": runner.sha(shared),
                "image_path": str(shared), "image_sha256": runner.sha(shared),
                "baseline_result_path": str(shared), "baseline_result_sha256": runner.sha(shared),
                "schema_path": str(schema), "schema_sha256": runner.sha(schema),
                "request_path": str(request), "request_sha256": runner.sha(request), "pages": []}
               for doc_id in runner.SELECTED]
    protocol = {"code": frozen_code, "sources": sources, "mode": "source_free_fixture"}
    runner.write(tmp_path / "protocol.json", protocol)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400, json={"error": {"message": "Unsupported image input", "type": "invalid_request_error"}})

    import openai  # noqa: F401

    class MockClient(httpx.Client):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "Client", MockClient)
    result = runner.run(tmp_path, runner.sha(tmp_path / "protocol.json"), tmp_path / "credential")
    assert len(calls) == result["calls"] == 1
    assert result["stopped"] == "request_rejected"
    assert len(result["receipts"]) == 3
    assert len((tmp_path / "candidates.jsonl").read_text().splitlines()) == 3
    assert (tmp_path / "http-response-01.json").exists()
    assert not (tmp_path / "http-response-02.json").exists()
