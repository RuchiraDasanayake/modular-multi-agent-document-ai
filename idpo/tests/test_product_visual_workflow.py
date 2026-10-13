"""Product visual routing with real local source preparation and fake model replies."""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw

from idpo.agents.preprocess import OcrAgent
from idpo.core.types import AgentResult
from idpo.product_auto.confirmed_schema import load_confirmed_schema
from idpo.product_auto.provider import ModelReply
from idpo.product_auto.visual_input import prepare_visual_document
from idpo.product_auto.workflow import process_auto
from idpo.tests.test_confirmed_schema_routing import snapshot

FIELDS = [
    {"field_id": "item", "type": "array[object]", "group": "items", "description": "Item name", "example_values": ["Widget"]},
    {"field_id": "total", "type": "integer", "description": "Final total", "example_values": ["100"]},
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_image(tmp_path):
    source = tmp_path / "source.png"
    with Image.new("RGB", (200, 100), "white") as image:
        ImageDraw.Draw(image).text((5, 5), "Widget 100", fill="black")
        image.save(source)
    return source


def source_pdf(tmp_path, count=2):
    source = tmp_path / "source.pdf"
    images = [Image.new("RGB", (200, 100), "white") for _ in range(count)]
    try:
        for index, image in enumerate(images):
            ImageDraw.Draw(image).text((5, 5), f"Widget {100 + index}", fill="black")
        images[0].save(source, format="PDF", save_all=True, append_images=images[1:])
    finally:
        for image in images:
            image.close()
    return source


def fake_ocr(monkeypatch, *, texts=None, engines=None, mutate=None, failure=None):
    def run(self, payload, ctx):
        document = payload["document"]
        pages = [replace(page, text=texts[index] if texts is not None else page.text,
                         metadata={**page.metadata, "ocr_engine_used": engines[index] if engines else "rapidocr"})
                 for index, page in enumerate(document.pages)]
        document.pages = pages
        if mutate:
            mutate(document)
        return AgentResult(artifacts={"document": document, "signal": SimpleNamespace(failure_reason=failure)})
    monkeypatch.setattr(OcrAgent, "run", run)


def reply(*, page=1, total=100, quote=None, linked=True):
    return ModelReply(text=json.dumps({"values": [
        {"field_id": "item", "value": [{"row": 0, "value": "Widget", "page": page, "quote": quote}]
         if linked else None, "page": None, "quote": None},
        {"field_id": "total", "value": total, "page": page, "quote": str(total) if quote else None},
    ]}), latency_ms=2, finish_reason="stop", sdk_attempts=1, prompt_tokens=10, completion_tokens=5)


class Model:
    model = "synthetic-visual"
    max_tokens = 8192

    def __init__(self, make_reply=None):
        self.visual_calls = []
        self.text_calls = []
        self.make_reply = make_reply or (lambda request, index: reply(page=request.receipt()["covered_pages"][0]))

    def complete_visual_json(self, request):
        request.validated_body(model=self.model, max_tokens=self.max_tokens)
        self.visual_calls.append(request.receipt())
        return self.make_reply(request, len(self.visual_calls) - 1)

    def complete_json(self, **kwargs):
        self.text_calls.append(kwargs)
        return reply(quote="Widget")


def run_product(tmp_path, source, model, *, profile="bounded_visual_v1", fields=FIELDS, **kwargs):
    schema_path, digest = snapshot(tmp_path, fields=fields)
    schema = load_confirmed_schema(schema_path, digest)
    result = process_auto(source, model=model, confirmed_schema=schema, visual_document_profile=profile,
                          run_id="visual", output_root=tmp_path / "runs", **kwargs)
    directory = Path(result["run_dir"])
    candidate = json.loads((directory / "candidates.jsonl").read_text())
    sidecar = json.loads((directory / "docs" / candidate["doc_id"] / "result.json").read_text())
    manifest = json.loads((directory / "manifest.jsonl").read_text())
    marker = json.loads((directory / "run.json").read_text())
    return candidate, sidecar, manifest, marker


@pytest.mark.parametrize("text,fields,expected_reason", [
    ("Widget 100", FIELDS, "selective_repeated_fields"),
    ("", [FIELDS[1]], "selective_no_usable_text"),
    ("Widget 100 " + "x" * 24_000, [FIELDS[1]], "selective_long_text"),
    ("Widget 100", [FIELDS[1]], "selective_scalar_text"),
], ids=["repeated_fields", "empty_ocr", "long_text", "scalar_text"])
def test_selective_route_runs_only_the_chosen_model_path(tmp_path, monkeypatch, text, fields, expected_reason):
    source = source_image(tmp_path)
    fake_ocr(monkeypatch, texts=[text])

    class SelectiveModel(Model):
        def _answer(self, visual):
            values = [{"field_id": "total", "value": 100, "page": 1, "quote": None if visual else "100"}]
            if len(fields) == 2:
                values.insert(0, {"field_id": "item", "value": [
                    {"row": 0, "value": "Widget", "page": 1, "quote": None}], "page": None, "quote": None})
            return ModelReply(text=json.dumps({"values": values}), latency_ms=1, finish_reason="stop", sdk_attempts=1)

        def complete_visual_json(self, request):
            self.visual_calls.append(request.receipt())
            return self._answer(True)

        def complete_json(self, **kwargs):
            self.text_calls.append(kwargs)
            return self._answer(False)

    model = SelectiveModel()
    candidate, sidecar, manifest, marker = run_product(tmp_path, source, model, fields=fields,
        profile="bounded_visual_selective_v2", long_document_profile="bounded_text_segments_v1")
    visual = expected_reason != "selective_scalar_text"
    assert (len(model.visual_calls), len(model.text_calls)) == ((1, 0) if visual else (0, 1))
    assert candidate["document_status"] == "needs_review"
    assert candidate["extracted_values"][-1]["value"] == 100
    assert sidecar["visual_document"]["route_reason"] == expected_reason
    for receipt in (sidecar["visual_document"], manifest["visual_document"], marker["visual_document"]):
        assert receipt["profile"] == "bounded_visual_selective_v2"
    if visual:
        assert all(value["status"] == "needs_review" for value in candidate["extracted_values"])
    else:
        assert model.text_calls[0]["response_format"]["json_schema"]["strict"] is True


def test_selective_router_keeps_coverage_guards_and_exact_text_boundary():
    from idpo.product_auto.visual_workflow import select_visual_route
    profile = "bounded_visual_selective_v2"
    pages = [{"page": 1, "text": "x" * 24_000}]
    ocr = [{"page": 1, "engine": "rapidocr"}]
    assert select_visual_route(".png", pages, ocr, [1], profile=profile) == (False, "selective_scalar_text")
    assert select_visual_route(".pdf", pages, ocr, [1, 2], profile=profile) == (True, "pdf_ocr_page_coverage_incomplete")
    assert select_visual_route(".pdf", pages, [{"page": 1, "engine": "native_text"}], [1],
        profile=profile, fields=tuple(FIELDS)) == (False, "pdf_all_native_text")
    assert select_visual_route(".txt", pages, ocr, [1], profile=profile, fields=tuple(FIELDS)) == (False, "native_or_text_source")


def test_image_empty_ocr_uses_original_and_keeps_all_proposals_pending(tmp_path, monkeypatch):
    source = source_image(tmp_path)
    fake_ocr(monkeypatch, texts=[""], failure="rapidocr_no_text")
    model = Model()
    candidate, sidecar, manifest, marker = run_product(tmp_path, source, model)
    assert len(model.visual_calls) == 1 and not model.text_calls
    assert candidate["document_status"] == "needs_review"
    assert all(value["status"] == "needs_review" for value in candidate["extracted_values"])
    assert candidate["extracted_values"][0]["value"][0]["visual_page"] == 1
    assert candidate["extracted_values"][1]["visual_pages"] == [1]
    assert sidecar["visual_ocr_failure"] == "rapidocr_no_text"
    for receipt in [sidecar["visual_document"], manifest["visual_document"], marker["visual_document"]["document_receipts"][0]]:
        assert receipt["route"] == "visual" and receipt["route_reason"] == "source_image"
        assert receipt["source_sha256"] == sha(source)
        assert receipt["planned_pages"] == receipt["attempted_pages"] == receipt["valid_pages"] == [1]
        assert receipt["full_source_covered"] is True
        assert "base64" not in json.dumps(receipt)
    assert manifest["response_format_profile"] == sidecar["response_format_profile"] == "strict_visual_confirmed_values_v1"
    assert marker["configured_response_format_profile"] == "plain_json"
    assert marker["effective_response_format_profiles"] == ["strict_visual_confirmed_values_v1"]
    assert marker["model_sdk_attempt_count"] == 1


def test_mixed_pdf_uses_all_pages_with_native_text_as_context(tmp_path, monkeypatch):
    source = source_pdf(tmp_path)
    fake_ocr(monkeypatch, texts=["Widget 100", "Widget 101"], engines=["native_text", "rapidocr"])
    model = Model(lambda request, index: reply(quote="Widget"))
    candidate, sidecar, manifest, _ = run_product(tmp_path, source, model)
    assert model.visual_calls[0]["covered_pages"] == [1, 2] and not model.text_calls
    assert sidecar["visual_document"]["route_reason"] == "pdf_requires_ocr"
    value = candidate["extracted_values"][1]
    assert value["status"] == "needs_review" and value["evidence"]["kind"] == "text_match"
    assert manifest["visual_document"]["valid_requests"] == 1


@pytest.mark.parametrize("kind", ["text", "office", "native_pdf"])
def test_enabled_native_sources_keep_strict_text_route(tmp_path, monkeypatch, kind):
    if kind == "text":
        source = tmp_path / "source.txt"
        source.write_text("Widget 100")
    elif kind == "office":
        from docx import Document
        source = tmp_path / "source.docx"
        document = Document()
        document.add_paragraph("Widget 100")
        document.save(source)
    else:
        source = source_pdf(tmp_path)
    fake_ocr(monkeypatch, texts=["Widget 100"] * (2 if kind == "native_pdf" else 1), engines=["native_text"] * 2)
    model = Model()
    _, sidecar, manifest, marker = run_product(tmp_path, source, model)
    assert not model.visual_calls and len(model.text_calls) == 1
    assert model.text_calls[0]["response_format"]["json_schema"]["strict"] is True
    assert sidecar["visual_document"]["route"] == "text"
    assert manifest["response_format_profile"] == "strict_confirmed_values_v1"
    assert marker["visual_document"]["text_doc_count"] == 1


def test_multi_request_merge_preserves_rows_and_conflicting_scalar_pages(tmp_path, monkeypatch):
    from idpo.product_auto import visual_input
    monkeypatch.setattr(visual_input, "MAX_IMAGES", 1)
    source = source_pdf(tmp_path)
    fake_ocr(monkeypatch, texts=["Widget 100", "Widget 101"])
    model = Model(lambda request, index: reply(page=index + 1, total=100 + index, quote="Widget"))
    candidate, sidecar, manifest, _ = run_product(tmp_path, source, model)
    assert len(model.visual_calls) == 2
    assert [(c["row"], c["visual_page"]) for c in candidate["extracted_values"][0]["value"]] == [(0, 1), (1, 2)]
    assert candidate["extracted_values"][1]["value"] is None
    assert candidate["extracted_values"][1]["status"] == "needs_review"
    assert [v["visual_page"] for v in sidecar["scalar_conflicts"]["total"]] == [1, 2]
    assert manifest["visual_document"]["full_source_covered"] is True


@pytest.mark.parametrize("bad", [
    ModelReply(text="broken", latency_ms=1, finish_reason="stop", sdk_attempts=1),
    ModelReply(text="", latency_ms=1, finish_reason="length", sdk_attempts=1),
    ModelReply(text="", latency_ms=1, finish_reason="stop", refusal=True, sdk_attempts=1),
    ModelReply(text="", latency_ms=1, error="http_400", sdk_attempts=1),
    reply(page=99),
    RuntimeError("private adapter detail"),
])
def test_failure_never_exposes_partial_candidate_or_falls_back(tmp_path, monkeypatch, bad):
    from idpo.product_auto import visual_input
    monkeypatch.setattr(visual_input, "MAX_IMAGES", 1)
    source = source_pdf(tmp_path, 3)
    fake_ocr(monkeypatch, texts=["Widget 100"] * 3)
    def make_reply(request, index):
        if index == 0:
            return reply(page=1)
        if isinstance(bad, Exception):
            raise bad
        return bad
    model = Model(make_reply)
    candidate, sidecar, manifest, marker = run_product(tmp_path, source, model)
    assert len(model.visual_calls) == 2 and not model.text_calls
    assert candidate["document_status"] == "failed" and candidate["extracted_values"] == []
    assert len(sidecar["visual_request_proposals"]) == 1
    receipt = sidecar["visual_document"]
    assert receipt["planned_requests"] == 3 and receipt["attempted_requests"] == 2 and receipt["valid_requests"] == 1
    assert receipt["requests"][2]["outcome"] == "not_attempted_after_failure"
    assert manifest["visual_document"]["full_source_covered"] is False
    assert marker["visual_document"]["full_source_covered_docs"] == 0
    assert "private adapter detail" not in json.dumps(sidecar)


@pytest.mark.parametrize("mode", ["missing_page", "source_changed"])
def test_complete_source_preflight_prevents_calls(tmp_path, monkeypatch, mode):
    source = source_pdf(tmp_path)
    def mutate(document):
        if mode == "missing_page":
            document.pages = document.pages[:1]
        else:
            source.write_bytes(b"changed after intake")
    fake_ocr(monkeypatch, texts=["Widget 100"] * 2, mutate=mutate)
    model = Model()
    candidate, sidecar, manifest, _ = run_product(tmp_path, source, model)
    assert not model.visual_calls and not model.text_calls
    assert candidate["document_status"] == "failed"
    assert manifest["visual_document"]["attempted_requests"] == 0
    assert sidecar["reason"] in {"visual_ocr_page_coverage_incomplete", "visual_source_changed"}
    assert sidecar["visual_document"]["source_pages"] == [1, 2]


def test_unsupported_fifth_request_fails_complete_planning(tmp_path, monkeypatch):
    from idpo.product_auto import visual_input
    monkeypatch.setattr(visual_input, "MAX_IMAGES", 1)
    source = source_pdf(tmp_path, 5)
    fake_ocr(monkeypatch, texts=[""] * 5)
    model = Model()
    candidate, sidecar, _, _ = run_product(tmp_path, source, model)
    assert not model.visual_calls and not model.text_calls
    assert candidate["document_status"] == "failed"
    assert sidecar["reason"] == "visual_complete_coverage_budget_exceeded"


def test_profile_preconditions_fail_before_artifacts(tmp_path):
    source = source_image(tmp_path)
    schema_path, digest = snapshot(tmp_path, fields=FIELDS)
    schema = load_confirmed_schema(schema_path, digest)
    for index, kwargs in enumerate([
        {"model": Model()}, {"model": None, "confirmed_schema": schema},
        {"model": SimpleNamespace(complete_json=lambda **kw: None), "confirmed_schema": schema},
        {"model": SimpleNamespace(complete_visual_json=lambda **kw: None, model="x", max_tokens=0), "confirmed_schema": schema},
    ]):
        with pytest.raises(ValueError):
            process_auto(source, visual_document_profile="bounded_visual_v1", run_id=f"bad{index}",
                         output_root=tmp_path / "runs", **kwargs)
    assert not (tmp_path / "runs").exists()


def test_disabled_keeps_existing_text_call_and_artifact_shape(tmp_path, monkeypatch):
    source = source_image(tmp_path)
    fake_ocr(monkeypatch, texts=["Widget 100"])
    model = Model()
    _, sidecar, manifest, marker = run_product(tmp_path, source, model, profile="disabled")
    assert not model.visual_calls and len(model.text_calls) == 1
    assert "response_format" not in model.text_calls[0]
    assert all("visual_document" not in value for value in [sidecar, manifest, marker])


def test_enabled_long_text_keeps_existing_segment_route(tmp_path, monkeypatch):
    source = tmp_path / "long.txt"
    source.write_text("Widget 100\n" + "filler words " * 4000)
    fake_ocr(monkeypatch, engines=["native_text"])
    model = Model()
    candidate, sidecar, manifest, _ = run_product(tmp_path, source, model,
        long_document_profile="bounded_text_segments_v1")
    assert not model.visual_calls and 2 <= len(model.text_calls) <= 4
    assert candidate["document_status"] == "needs_review"
    assert sidecar["visual_document"]["route"] == "text"
    assert manifest["long_document"]["full_source_covered"] is True


def test_rotated_jpeg_preserves_exact_rapidocr_pixel_grid(tmp_path):
    source = tmp_path / "rotated.jpg"
    with Image.new("RGB", (200, 100), "white") as image:
        ImageDraw.Draw(image).rectangle((0, 0, 60, 40), fill="red")
        exif = image.getexif()
        exif[274] = 6
        image.save(source, exif=exif)
    with Image.open(source) as raw:
        grid = raw.convert("RGB")
        encoded = io.BytesIO()
        grid.save(encoded, format="PNG")
        grid.close()
    text = "Widget"
    lines = [{"line_index": 0, "start": 0, "end": len(text), "text": text, "score": 0.9,
              "polygon": [[0, 0], [60, 0], [60, 40], [0, 40]]}]
    prepared = prepare_visual_document(source, expected_source_sha256=sha(source), pages=[{
        "page": 1, "text": text, "ocr_lines": lines, "ocr_provenance": {
            "input_png_sha256": hashlib.sha256(encoded.getvalue()).hexdigest(), "image_size_px": [200, 100],
            "text_sha256": hashlib.sha256(text.encode()).hexdigest()}}])
    receipt = prepared[0].receipt()
    assert receipt["raster_size"] == [200, 100]
    assert receipt["render"]["source_exif_orientation"] == 6
    assert receipt["render"]["exif_transpose_applied"] is False
    assert json.loads(prepared[0].ocr_json)["lines"][0]["polygon"] == lines[0]["polygon"]
    with Image.open(io.BytesIO(prepared[0].png)) as transmitted:
        assert transmitted.size == (200, 100)
        assert transmitted.getexif().get(274) is None
