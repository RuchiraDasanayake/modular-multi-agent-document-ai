"""Opt-in full-page JPEG: provenance, unchanged PNG, and fail-closed budgets."""

from __future__ import annotations

import base64
import io
import json
import random
import sys
from dataclasses import replace

import httpx
import pytest
from PIL import Image, JpegImagePlugin

from idpo.product_auto import visual_input as visual
from idpo.product_auto.provider import OpenAICompatibleChat
from idpo.product_auto.visual_workflow import (
    JPEG95_PROFILE,
    SELECTIVE_PROFILE,
    select_visual_route,
)
from idpo.product_auto.workflow import process_auto
from idpo.tests.test_product_visual_boundary import (
    FIELDS,
    copies,
    digest,
    image_pages,
    image_source,
)
from idpo.tests.test_product_visual_workflow import (
    Model,
    fake_ocr,
    run_product,
    source_image,
    source_pdf,
)


def prepare(source, pages=None, *, encoding=visual.JPEG95_ENCODING_PROFILE):
    return visual.prepare_visual_document(source, expected_source_sha256=digest(source.read_bytes()),
                                          pages=pages or image_pages(source), encoding_profile=encoding)


def pack(pages, *, fields=FIELDS, encoding=visual.JPEG95_ENCODING_PROFILE):
    return visual.plan_visual_requests(pages, fields=fields, intent="Read items and total",
                                       model="test-luna", max_tokens=8192, encoding_profile=encoding)


def mutate_receipt(page, **patch):
    receipt = page.receipt()
    receipt.update(patch)
    return replace(page, receipt_json=json.dumps(receipt).encode())


def test_jpeg_retains_ocr_raster_and_geometry_with_explicit_lossy_provenance(tmp_path):
    source = image_source(tmp_path, size=(3000, 2000))
    png = prepare(source, encoding=visual.PNG_ENCODING_PROFILE)[0]
    jpeg = prepare(source)[0]
    again = prepare(source)[0]
    assert jpeg.payload == again.payload and jpeg.receipt_json == again.receipt_json
    assert jpeg.png == b"" and jpeg.encoded_payload == jpeg.payload
    for key in ("source_sha256", "raster_png_sha256", "raster_size", "payload_size", "scale_xy",
                "ocr_geometry_sha256", "payload_geometry_sha256", "ocr_payload_sha256"):
        assert jpeg.receipt()[key] == png.receipt()[key]
    assert jpeg.ocr_json == png.ocr_json
    assert jpeg.receipt()["payload_size"] == [2048, 1365]
    assert "payload_png_sha256" not in jpeg.receipt()
    assert jpeg.receipt()["payload_sha256"] == digest(jpeg.payload)
    assert jpeg.receipt()["payload_lossy"] is True
    assert jpeg.receipt()["encoder"] == {"format": "JPEG", "mode": "RGB", "quality": 95,
                                         "subsampling": 0, "optimize": False, "progressive": False}
    with Image.open(io.BytesIO(jpeg.payload)) as header:
        assert header.format == "JPEG" and header.mode == "RGB" and header.size == (2048, 1365)
        assert JpegImagePlugin.get_sampling(header) == 0
        assert not header.getexif() and "icc_profile" not in header.info and "progressive" not in header.info
    request = pack([jpeg])[0]
    url = json.loads(request.body_json)["messages"][1]["content"][2]["image_url"]["url"]
    assert url.startswith("data:image/jpeg;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == jpeg.payload
    assert request.receipt()["transform_version"] == visual.JPEG95_TRANSFORM_VERSION
    assert "base64" not in request.receipt_json.decode() and "Widget" not in request.receipt_json.decode()


def test_jpeg_strips_source_exif_without_rotating_the_ocr_grid(tmp_path):
    source = tmp_path / "rotated.jpg"
    with Image.new("RGB", (100, 80), "red") as image:
        exif = Image.Exif()
        exif[274] = 6
        exif[270] = "private source metadata"
        image.save(source, exif=exif)
    prepared = prepare(source)[0]
    assert prepared.receipt()["raster_size"] == [100, 80]
    assert prepared.receipt()["render"]["source_exif_orientation"] == 6
    assert prepared.receipt()["render"]["exif_transpose_applied"] is False
    with Image.open(io.BytesIO(prepared.payload)) as image:
        assert image.size == (100, 80) and not image.getexif()
    assert b"private source metadata" not in prepared.payload


def test_dense_synthetic_page_fails_png_cap_and_fits_jpeg_without_downscale(tmp_path):
    source = tmp_path / "noise.png"
    with Image.frombytes("RGB", (1200, 1000), random.Random(100).randbytes(3_600_000)) as image:
        image.save(source)
    with pytest.raises(visual.VisualInputError, match="page_encoded_size"):
        prepare(source, encoding=visual.PNG_ENCODING_PROFILE)
    page = prepare(source)[0]
    assert page.receipt()["raster_size"] == page.receipt()["payload_size"] == [1200, 1000]
    assert page.receipt()["payload_bytes"] <= 3_000_000
    assert len(pack([page])[0].body_json) <= 4 * 1024 * 1024


@pytest.mark.parametrize("patch", [
    {"payload_mime_type": "image/png"}, {"payload_sha256": "0" * 64},
    {"transform_version": visual.TRANSFORM_VERSION}, {"encoding_profile": visual.PNG_ENCODING_PROFILE},
    {"payload_size": [1, 1]}, {"payload_bytes": 1}, {"payload_lossy": False},
    {"encoder": {"format": "JPEG", "quality": 90}}, {"payload_metadata_stripped": False},
])
def test_altered_payload_identity_fails_closed(tmp_path, patch):
    page = prepare(image_source(tmp_path))[0]
    with pytest.raises(visual.VisualInputError):
        pack([mutate_receipt(page, **patch)])


def test_codec_confusion_changed_bytes_and_mixed_plans_fail_closed(tmp_path):
    source = image_source(tmp_path)
    jpeg = prepare(source)[0]
    png = prepare(source, encoding=visual.PNG_ENCODING_PROFILE)[0]
    with pytest.raises(visual.VisualInputError, match="encoding_profile_mismatch"):
        pack([jpeg], encoding=visual.PNG_ENCODING_PROFILE)
    forged = replace(jpeg, encoded_payload=png.png)
    forged = mutate_receipt(forged, payload_sha256=digest(png.png), payload_bytes=len(png.png))
    with pytest.raises(visual.VisualInputError, match="payload_identity"):
        pack([forged])
    with pytest.raises(visual.VisualInputError):
        pack([replace(jpeg, encoded_payload=jpeg.payload[:-2] + b"00")])
    pages = copies([jpeg], 2)
    pages[1] = replace(pages[1], encoding_profile=visual.PNG_ENCODING_PROFILE, png=png.png)
    with pytest.raises(visual.VisualInputError, match="encoding_profile_mismatch"):
        pack(pages)


def test_complete_page_and_exact_body_limits_include_schema_growth(tmp_path, monkeypatch):
    pages = prepare(image_source(tmp_path))
    requests = pack(copies(pages, 48))
    assert len(requests) == 4
    assert [p for request in requests for p in request.receipt()["covered_pages"]] == list(range(1, 49))
    with pytest.raises(visual.VisualInputError, match="complete_coverage_budget"):
        pack(copies(pages, 49))
    with pytest.raises(visual.VisualInputError, match="complete_page_coverage"):
        pack(copies(pages, 2)[:1])
    exact_size = len(pack(pages)[0].body_json)
    monkeypatch.setattr(visual, "MAX_REQUEST_BYTES", exact_size)
    assert len(pack(pages)[0].body_json) == exact_size
    assert len(pack(copies(pages, 2))) == 2
    grown = [{**field, "description": "additional schema context"} for field in FIELDS]
    with pytest.raises(visual.VisualInputError, match="single_page_request"):
        pack(pages, fields=grown)


def test_each_page_and_aggregate_byte_caps_remain_enforced(tmp_path, monkeypatch):
    source = image_source(tmp_path)
    size = len(prepare(source)[0].payload)
    monkeypatch.setattr(visual, "MAX_IMAGE_BYTES", size - 1)
    with pytest.raises(visual.VisualInputError, match="page_encoded_size") as error:
        prepare(source)
    assert error.value.details == {"stage": "page_encoding", "page": 1, "dimensions": [100, 80],
                                   "encoded_bytes": size, "limit_bytes": size - 1}
    monkeypatch.setattr(visual, "MAX_IMAGE_BYTES", size)
    monkeypatch.setattr(visual, "MAX_TOTAL_PNG_BYTES", size - 1)
    with pytest.raises(visual.VisualInputError, match="complete_coverage_budget"):
        prepare(source)


def test_raster_rejection_is_unchanged_and_only_new_profile_adds_diagnostics(tmp_path):
    source = image_source(tmp_path, size=(4097, 1))
    for profile in (visual.PNG_ENCODING_PROFILE, visual.JPEG95_ENCODING_PROFILE):
        with pytest.raises(visual.VisualInputError, match="raster_size") as error:
            prepare(source, pages=[{"page": 1, "text": ""}], encoding=profile)
        if profile == visual.PNG_ENCODING_PROFILE:
            assert error.value.details is None
        else:
            assert error.value.details == {"stage": "raster_admission", "page": 1,
                                           "dimensions": [4097, 1], "edge_limit": 4096, "pixel_limit": 12_000_000}


def test_cli_only_forwards_explicit_jpeg_profile_and_confirmation_still_required(tmp_path, monkeypatch, capsys):
    import idpo.product_auto as product
    from idpo import cli

    seen = []
    monkeypatch.setattr(product, "process_auto", lambda *args, **kwargs: seen.append(kwargs) or {})
    for arguments in ([], ["--visual-document-profile", JPEG95_PROFILE]):
        monkeypatch.setattr(sys, "argv", ["idpo", "process-auto", "--input", "synthetic.txt", *arguments])
        cli.main()
    assert "visual_document_profile" not in seen[0]
    assert seen[1]["visual_document_profile"] == JPEG95_PROFILE
    assert capsys.readouterr().out == "{}\n{}\n"
    source = tmp_path / "synthetic.txt"
    source.write_text("Synthetic input", encoding="utf-8")
    with pytest.raises(ValueError, match="confirmed schema and model"):
        process_auto(source, visual_document_profile=JPEG95_PROFILE,
                     output_root=tmp_path / "no-output")
    assert not (tmp_path / "no-output").exists()


def test_pdf_complete_pages_keep_identical_rasters_and_geometry(tmp_path):
    source = source_pdf(tmp_path)
    pages = [{"page": 1, "text": "Widget 100"}, {"page": 2, "text": "Widget 101"}]
    png = prepare(source, pages, encoding=visual.PNG_ENCODING_PROFILE)
    jpeg = prepare(source, pages)
    assert len(jpeg) == 2
    for old, new in zip(png, jpeg, strict=True):
        assert old.receipt()["raster_png_sha256"] == new.receipt()["raster_png_sha256"]
        assert old.ocr_json == new.ocr_json
    assert pack(jpeg)[0].receipt()["covered_pages"] == [1, 2]


def test_new_route_is_selective_and_product_seals_actual_encoder(tmp_path, monkeypatch):
    for text, fields in [("Widget", FIELDS), ("Widget", [FIELDS[1]]), ("", [FIELDS[1]]),
                         ("x" * 24_001, [FIELDS[1]])]:
        pages = [{"page": 1, "text": text}]
        for extension in (".png", ".pdf", ".txt"):
            kwargs = {"fields": tuple(fields)}
            assert select_visual_route(extension, pages, pages, [1], profile=JPEG95_PROFILE, **kwargs) == \
                select_visual_route(extension, pages, pages, [1], profile=SELECTIVE_PROFILE, **kwargs)
    source = source_image(tmp_path)
    fake_ocr(monkeypatch, texts=["Widget 100"])
    model = Model()
    candidate, sidecar, manifest, marker = run_product(tmp_path, source, model, profile=JPEG95_PROFILE)
    assert candidate["document_status"] == "needs_review" and len(model.visual_calls) == 1 and not model.text_calls
    for receipt in (sidecar["visual_document"], manifest["visual_document"],
                    marker["visual_document"]["document_receipts"][0]):
        assert receipt["profile"] == JPEG95_PROFILE and receipt["full_source_covered"] is True
        assert receipt["plan_sha256"] == sidecar["visual_document"]["plan_sha256"]
    request = sidecar["visual_document"]["requests"][0]
    assert request["encoding_profile"] == visual.JPEG95_ENCODING_PROFILE
    assert request["pages"][0]["payload_lossy"] is True


def test_plan_failure_makes_zero_model_calls_and_no_partial_candidate(tmp_path, monkeypatch):
    source = source_image(tmp_path)
    fake_ocr(monkeypatch, texts=["Widget 100"])
    monkeypatch.setattr(visual, "MAX_REQUEST_BYTES", 1)
    model = Model()
    candidate, sidecar, _, _ = run_product(tmp_path, source, model, profile=JPEG95_PROFILE)
    assert model.visual_calls == model.text_calls == []
    assert candidate["document_status"] == "failed" and candidate["extracted_values"] == []
    assert sidecar["reason"] == "visual_single_page_request_unsupported"
    details = sidecar["visual_document"]["admission_failure"]
    assert details["stage"] == "request_packing" and details["page"] == 1
    assert details["dimensions"] == [200, 100] and details["limit_bytes"] == 1
    assert details["request_bytes"] > details["encoded_bytes"] > 0
    assert "Widget" not in json.dumps(details) and str(source) not in json.dumps(details)


def test_jpeg_real_sdk_sends_exact_mime_and_body_once_to_fake_transport(tmp_path, monkeypatch):
    request = pack(prepare(image_source(tmp_path)))[0]
    seen = []
    original_client = httpx.Client

    def respond(wire):
        seen.append(wire)
        assert wire.content == request.body_json and b"data:image/jpeg;base64," in wire.content
        return httpx.Response(400, json={"error": {"message": "synthetic rejection"}})

    class MockClient(original_client):
        def __init__(self, **kwargs):
            super().__init__(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(httpx, "Client", MockClient)
    monkeypatch.setenv("JPEG_SYNTHETIC_KEY", "local-synthetic")
    model = OpenAICompatibleChat(base_url="http://127.0.0.1:19999/v1", model="test-luna",
                                 api_key_env="JPEG_SYNTHETIC_KEY", max_tokens=8192)
    try:
        reply = model.complete_visual_json(request)
        assert reply.error == "http_400" and reply.sdk_attempts == 1 and len(seen) == 1
    finally:
        model.client.close()
