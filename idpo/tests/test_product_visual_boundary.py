"""Local source provenance, complete coverage, strict review and real SDK wire tests."""

from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from PIL import Image, ImageDraw

from idpo.product_auto.provider import OpenAICompatibleChat
from idpo.product_auto.visual_input import (
    MAX_REQUEST_BYTES, VisualInputError, plan_visual_requests, prepare_visual_document,
)
from idpo.product_auto.visual_output import compile_visual_response_format, parse_visual_values_reply
from idpo.product_auto.strict_output import compile_confirmed_values_response_format, parse_confirmed_strict_values_reply

FIELDS = [{"field_id": "item", "type": "array[object]"}, {"field_id": "total", "type": "decimal"}]


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def image_source(tmp_path: Path, *, size=(100, 80)) -> Path:
    source = tmp_path / "source.png"
    with Image.new("RGB", size, "white") as image:
        image.save(source)
    return source


def image_pages(source: Path):
    with Image.open(source) as image:
        width, height = image.size
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="PNG")
    return [{"page": 1, "text": "Widget", "ocr_lines": [
        {"line_index": 0, "text": "Widget", "start": 0, "end": 6, "score": 0.9,
         "polygon": [[0, 0], [width, 0], [width, height], [0, height]]}],
        "ocr_provenance": {"input_png_sha256": digest(buffer.getvalue()), "image_size_px": [width, height],
                           "text_sha256": digest(b"Widget")}}]


def prepared_image(tmp_path: Path):
    source = image_source(tmp_path)
    pages = image_pages(source)
    prepared = prepare_visual_document(source, expected_source_sha256=digest(source.read_bytes()), pages=pages)
    return source, pages, prepared


def request_for(prepared):
    return plan_visual_requests(prepared, fields=FIELDS, intent="Read items and total", model="test-luna", max_tokens=8192)


def test_image_is_bound_to_original_and_geometry_transform(tmp_path):
    source = image_source(tmp_path, size=(3000, 2000))
    pages = image_pages(source)
    prepared = prepare_visual_document(source, expected_source_sha256=digest(source.read_bytes()), pages=pages)
    receipt = prepared[0].receipt()
    assert receipt["raster_size"] == [3000, 2000]
    assert receipt["payload_size"] == [2048, 1365]
    assert receipt["source_sha256"] == digest(source.read_bytes())
    assert receipt["raster_png_sha256"] != receipt["payload_png_sha256"]
    assert receipt["scale_xy"] == [2048 / 3000, 1365 / 2000]
    assert json.loads(prepared[0].ocr_json)["lines"][0]["polygon"][2] == [2048.0, 1365.0]
    request = request_for(prepared)[0]
    data = json.loads(request.body_json)
    url = data["messages"][1]["content"][2]["image_url"]["url"]
    assert digest(base64.b64decode(url.split(",", 1)[1])) == receipt["payload_png_sha256"]
    assert len(request.body_json) <= MAX_REQUEST_BYTES
    public = json.dumps(request.receipt())
    assert "base64" not in public and "Widget" not in public and str(source) not in public


@pytest.mark.parametrize("change", [
    lambda p: p[0]["ocr_provenance"].update(input_png_sha256="0" * 64),
    lambda p: p[0]["ocr_lines"][0].update(start=1),
    lambda p: p[0]["ocr_lines"][0].update(polygon=[[0, 0], [101, 0], [101, 80], [0, 80]]),
])
def test_foreign_raster_offsets_and_outside_geometry_rejected_before_send(tmp_path, change):
    source = image_source(tmp_path)
    pages = image_pages(source)
    change(pages)
    with pytest.raises(VisualInputError):
        prepare_visual_document(source, expected_source_sha256=digest(source.read_bytes()), pages=pages)


def test_source_and_prepared_payload_tamper_are_rejected(tmp_path):
    source, pages, prepared = prepared_image(tmp_path)
    request = request_for(prepared)[0]
    for altered in (replace(prepared[0], png=b"other"), replace(prepared[0], ocr_json=b"{}")):
        with pytest.raises(VisualInputError, match="payload_changed"):
            request_for([altered])
    with pytest.raises(VisualInputError, match="request_changed"):
        replace(request, body_json=request.body_json + b" ").validated_body(model="test-luna", max_tokens=8192)
    source.write_bytes(b"changed original")
    with pytest.raises(VisualInputError, match="source_changed"):
        request.validated_body(model="test-luna", max_tokens=8192)
    with pytest.raises(VisualInputError, match="source_changed"):
        prepare_visual_document(source, expected_source_sha256=prepared[0].source_sha256, pages=pages)


def test_two_page_pdf_actual_shared_renders_and_missing_page_refusal(tmp_path):
    source = tmp_path / "two.pdf"
    with Image.new("RGB", (100, 200), "white") as first, Image.new("RGB", (200, 100), "white") as second:
        ImageDraw.Draw(first).text((10, 10), "Widget", fill="black")
        ImageDraw.Draw(second).text((10, 10), "Widget 10.50", fill="black")
        first.save(source, format="PDF", save_all=True, append_images=[second])
    sha = digest(source.read_bytes())
    pages = [{"page": 1, "text": "Widget"}, {"page": 2, "text": "Widget 10.50"}]
    with pytest.raises(VisualInputError, match="complete_page_coverage"):
        prepare_visual_document(source, expected_source_sha256=sha, pages=pages[:1])
    prepared = prepare_visual_document(source, expected_source_sha256=sha, pages=pages)
    assert [p.receipt()["render"]["renderer"] for p in prepared] == ["pdfium", "pdfium"]
    assert prepared[0].receipt()["raster_png_sha256"] != prepared[1].receipt()["raster_png_sha256"]
    requests = request_for(prepared)
    assert len(requests) == 1
    assert requests[0].receipt()["covered_pages"] == [1, 2]
    with pytest.raises(VisualInputError, match="complete_page_coverage"):
        request_for(prepared[:1])
    values = {"values": [
        {"field_id": "item", "value": [{"row": 0, "value": "Widget", "page": 1, "quote": "Widget"},
            {"row": 1, "value": "Widget", "page": 2, "quote": None}], "page": None, "quote": None},
        {"field_id": "total", "value": "10.50", "page": 2, "quote": "10.50"}]}
    projected = parse_visual_values_reply(json.dumps(values), FIELDS, pages)
    assert projected["total"]["status"] == "needs_review"
    assert projected["total"]["evidence"]["kind"] == "text_match"
    first, second = projected["item"]["value"]
    assert first["evidence"]["page"] == 1 and first["evidence"]["kind"] == "text_match"
    assert second["visual_page"] == 2 and "evidence" not in second
    assert all(c["status"] == "needs_review" and c["visual_grounding_verified"] is False for c in [first, second])
    assert parse_confirmed_strict_values_reply(json.dumps(values), FIELDS, pages) is None


def test_png_and_multiframe_limits_are_explicit(tmp_path):
    source = image_source(tmp_path, size=(4097, 1))
    with pytest.raises(VisualInputError, match="raster_size"):
        prepare_visual_document(source, expected_source_sha256=digest(source.read_bytes()), pages=[{"page": 1, "text": ""}])
    source = tmp_path / "multi.tiff"
    with Image.new("RGB", (10, 10)) as image:
        image.save(source, save_all=True, append_images=[image])
    with pytest.raises(VisualInputError, match="multiframe"):
        prepare_visual_document(source, expected_source_sha256=digest(source.read_bytes()), pages=[{"page": 1, "text": ""}])


def copies(prepared, count):
    # Synthetic repeated pages test the packer without rendering 49 documents.
    result = []
    for i in range(count):
        ocr = json.loads(prepared[0].ocr_json)
        ocr["page"] = i + 1
        encoded = json.dumps(ocr).encode()
        receipt = prepared[0].receipt()
        receipt.update(page=i + 1, total_pages=count, ocr_payload_sha256=digest(encoded))
        result.append(replace(prepared[0], page=i + 1, total_pages=count,
                              ocr_json=encoded, receipt_json=json.dumps(receipt).encode()))
    return result


def test_request_count_and_total_coverage_are_planned_before_any_send(tmp_path):
    _, _, prepared = prepared_image(tmp_path)
    requests = request_for(copies(prepared, 48))
    assert len(requests) == 4
    assert [len(r.receipt()["covered_pages"]) for r in requests] == [12] * 4
    assert all(r.receipt()["planned_covered_pages"] == list(range(1, 49)) for r in requests)
    with pytest.raises(VisualInputError, match="complete_coverage_budget"):
        request_for(copies(prepared, 49))


def test_exact_body_limit_splits_and_refuses_one_oversized_page(tmp_path, monkeypatch):
    import idpo.product_auto.visual_input as module
    _, _, prepared = prepared_image(tmp_path)
    singleton_size = len(request_for(prepared)[0].body_json)
    monkeypatch.setattr(module, "MAX_REQUEST_BYTES", singleton_size + 5)
    requests = request_for(copies(prepared, 2))
    assert len(requests) == 2
    assert all(len(r.body_json) <= singleton_size + 5 for r in requests)
    monkeypatch.setattr(module, "MAX_REQUEST_BYTES", singleton_size - 1)
    with pytest.raises(VisualInputError, match="single_page_request"):
        request_for(prepared)


def test_visual_schema_and_local_parser_remain_closed_and_review_only():
    visual = compile_visual_response_format(FIELDS)
    text = compile_confirmed_values_response_format(FIELDS)
    path = lambda v: v["json_schema"]["schema"]["properties"]["values"]["items"]["properties"]["value"]["items"]
    assert path(visual)["properties"]["quote"]["type"] == ["string", "null"]
    assert path(text)["properties"]["quote"]["type"] == "string"
    assert path(visual)["additionalProperties"] is False
    assert path(visual)["required"] == ["row", "value", "page", "quote"]
    values = {"values": [{"field_id": "item", "value": None, "page": None, "quote": None},
                        {"field_id": "total", "value": "10.50", "page": 1, "quote": None}]}
    pages = [{"page": 1, "text": "unreadable OCR"}]
    assert parse_visual_values_reply(json.dumps(values), FIELDS, pages)["total"]["status"] == "needs_review"
    for mutation in (lambda v: v["values"].pop(), lambda v: v["values"][1].update(page=2),
                     lambda v: v["values"][1].update(extra=True), lambda v: v["values"][1].update(page=None)):
        invalid = copy.deepcopy(values)
        mutation(invalid)
        assert parse_visual_values_reply(json.dumps(invalid), FIELDS, pages) is None
    assert parse_visual_values_reply('{"values":' + '[' * 2000 + 'null' + ']' * 2000 + '}', FIELDS, pages) is None


def test_real_sdk_wire_matches_exact_preflight_and_never_retries(tmp_path, monkeypatch):
    _, _, prepared = prepared_image(tmp_path)
    request = request_for(prepared)[0]
    seen = []
    real_client = httpx.Client

    def respond(wire):
        seen.append(wire)
        assert wire.content == request.body_json
        assert wire.headers["authorization"] == "Bearer local-no-auth"
        return httpx.Response(400, json={"error": {"message": "private provider detail", "type": "bad_request"}})

    class ClientWithFakeTransport(real_client):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(httpx, "Client", ClientWithFakeTransport)
    model = OpenAICompatibleChat(base_url="http://127.0.0.1:19999/v1", model="test-luna",
                                 api_key_env="SYNTHETIC_KEY", max_tokens=8192)
    try:
        reply = model.complete_visual_json(request)
        assert (reply.error, reply.error_category, reply.sdk_attempts) == ("http_400", "request_rejected", 1)
        assert len(seen) == 1 and "private provider detail" not in str(reply)
    finally:
        model.client.close()


def test_sdk_encoding_change_is_stopped_before_transport(tmp_path, monkeypatch):
    # A future SDK changing the actual JSON bytes must fail closed, without
    # falling back to an unbounded request or silently dropping the images.
    _, _, prepared = prepared_image(tmp_path)
    request = request_for(prepared)[0]
    real_client = httpx.Client
    seen = []

    class ChangedEncodingClient(real_client):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(lambda request: seen.append(request)), **kwargs)

        def build_request(self, *args, **kwargs):
            original = super().build_request(*args, **kwargs)
            return httpx.Request(original.method, original.url, content=original.content + b" ",
                                 headers=original.headers)

    # Construct the base SDK before replacing the transport factory.
    model = OpenAICompatibleChat(base_url="http://127.0.0.1:19999/v1", model="test-luna",
                                 api_key_env="SYNTHETIC_KEY", max_tokens=8192)
    monkeypatch.setattr(httpx, "Client", ChangedEncodingClient)
    try:
        reply = model.complete_visual_json(request)
        assert reply.error is not None and reply.sdk_attempts == 1
        assert seen == []
    finally:
        model.client.close()
