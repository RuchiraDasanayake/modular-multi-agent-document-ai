from __future__ import annotations

import hashlib
import json
import sys
import types
from pathlib import Path

import pytest
from PIL import Image

from product_eval import oracle_vl_diagnostic as vl


def test_sha_selection_and_completed_sidecar_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [
        {"family": family, "doc_id": f"{family}-{index}", "source_sha256": f"{family_number * 10 + index:064x}"}
        for family_number, family in enumerate(vl.FAMILIES)
        for index in range(3)
    ]
    cohort = tmp_path / "cohort.jsonl"
    cohort.write_text("".join(json.dumps(row) + "\n" for row in reversed(rows)), encoding="utf-8")
    monkeypatch.setattr(vl, "COHORT_SHA256", vl.sha256_file(cohort))
    selected = vl.select_cohort(cohort, per_family=1)
    assert len(selected) == 2
    assert {row["doc_id"] for row in selected} == {"registration-form-0", "ad-buy-form-0"}

    root = tmp_path / "runs"
    doc_dir = root / "vrdu_v6_reg_00" / "docs" / selected[0]["doc_id"]
    doc_dir.mkdir(parents=True)
    (doc_dir / "result.json").write_text(json.dumps({
        "source_sha256": selected[0]["source_sha256"],
        "pages": [{"page": 1, "text": "OCR"}],
    }), encoding="utf-8")
    items = vl.inventory(selected, root, "vrdu_v6")
    assert vl.readiness(items)["sidecars_present"] == 1
    assert not vl.readiness(items)["ready"]
    (root / "vrdu_v6_reg_00" / "run.json").write_text("{}", encoding="utf-8")
    assert vl.readiness(vl.inventory(selected, root, "vrdu_v6"))["sidecars_in_completed_runs"] == 1
    (doc_dir / "result.json").write_text(json.dumps({
        "source_sha256": selected[0]["source_sha256"],
        "pages": [{"page": 2, "text": "wrong page"}],
    }), encoding="utf-8")
    with pytest.raises(vl.ContractError, match="contiguous 1-based"):
        vl.inventory(selected, root, "vrdu_v6")


def test_multimodal_prompt_pairs_each_image_with_same_numbered_ocr_page() -> None:
    pages = [{"page": 1, "text": "Page-one OCR"}, {"page": 2, "text": "Page-two OCR"}]
    images = [{"page": 1, "data_url": "data:image/png;base64,AAAA"},
              {"page": 2, "data_url": "data:image/png;base64,BBBB"}]
    messages = vl.build_messages(pages, images, [{"field_id": "permit_id", "type": "string"}])
    content = messages[1]["content"]
    assert [part["type"] for part in content] == ["text", "text", "image_url", "text", "text", "image_url", "text"]
    assert content[1]["text"] == "Page 1 image:"
    assert content[2]["image_url"]["url"].endswith("AAAA")
    assert content[3]["text"].endswith("Page-one OCR")
    assert content[4]["text"] == "Page 2 image:"
    assert content[5]["image_url"]["url"].endswith("BBBB")
    assert content[6]["text"].endswith("Page-two OCR")
    with pytest.raises(vl.ContractError, match="do not match"):
        vl.build_messages(pages, list(reversed(images)), [])


def test_oracle_values_require_exact_saved_ocr_spans_and_exclude_gold_values() -> None:
    pages = [{"page": 1, "text": "Code ABC\nAmount: 12.00\n"}]
    images = [{"page": 1, "data_url": "data:image/png;base64,AAAA"}]
    gold = {"doc_id": "doc-a", "gold_schema": [
        {"field_id": "code", "type": "string", "critical": False},
        {"field_id": "amount", "type": "decimal", "critical": False},
        {"field_id": "aliases", "type": "array[string]", "critical": False},
    ], "gold_values": [{"field_id": "code", "value": "PRIVATE_GOLD_SENTINEL"}]}
    seen: list[list[dict[str, object]]] = []

    def complete(messages: list[dict[str, object]]) -> dict[str, object]:
        seen.append(messages)
        return {"text": json.dumps({"values": [
            {"field_id": "code", "value": "ABC", "page": 1, "quote": "ABC"},
            {"field_id": "amount", "value": 12.0, "page": 1, "quote": "12.00 invented context"},
        ]}), "finish_reason": "stop", "error": None,
                "latency_ms": 1, "prompt_tokens": 10, "completion_tokens": 10}

    candidate, diagnostic = vl.evaluate_document("doc-a", pages, gold, images, complete)
    prompt = json.dumps(seen)
    assert "PRIVATE_GOLD_SENTINEL" not in prompt
    assert '"aliases"' not in prompt
    assert diagnostic["unsupported_gold_field_ids"] == ["aliases"]
    values = {field["field_id"]: field for field in candidate["extracted_values"]}
    assert values["code"]["status"] == "accepted"
    assert values["code"]["evidence"] == {"page": 1, "start": 5, "end": 8, "quote": "ABC"}
    assert values["amount"]["status"] == "needs_review"
    assert "evidence" not in values["amount"]
    assert values["aliases"]["status"] == "needs_review"
    assert candidate["document_status"] == "needs_review"


def test_render_uses_pinned_pdfium_and_keeps_one_based_page_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    rendered_indices: list[int] = []

    class FakePage:
        def __init__(self, index: int):
            self.index = index

        def get_size(self) -> tuple[int, int]:
            return (40, 20)

        def render(self, *, scale: float) -> object:
            assert scale == vl.RENDER_SCALE
            rendered_indices.append(self.index)
            return types.SimpleNamespace(to_pil=lambda: Image.new("RGB", (40, 20), color="white"))

        def close(self) -> None:
            pass

    class FakeDocument:
        def __init__(self, _: str):
            pass

        def __len__(self) -> int:
            return 2

        def __getitem__(self, index: int) -> FakePage:
            return FakePage(index)

        def close(self) -> None:
            pass

    monkeypatch.setattr(vl.importlib.metadata, "version", lambda _: vl.PDFIUM_VERSION)
    monkeypatch.setitem(sys.modules, "pypdfium2", types.SimpleNamespace(PdfDocument=FakeDocument))
    pages = [{"page": 1, "text": "one"}, {"page": 2, "text": "two"}]
    images = vl.render_pdf_pages(tmp_path / "public.pdf", pages, tmp_path / "images")
    assert rendered_indices == [0, 1]
    assert [image["page"] for image in images] == [1, 2]
    assert [image["path"].name for image in images] == ["page-001.png", "page-002.png"]
    for image in images:
        png = image["path"].read_bytes()
        assert image["sha256"] == hashlib.sha256(png).hexdigest()
        assert image["data_url"].startswith("data:image/png;base64,")
        assert (image["width"], image["height"]) == (40, 20)
        assert image["render_scale"] == vl.RENDER_SCALE


@pytest.mark.parametrize("url", [
    "https://127.0.0.1:18082/v1/chat/completions",
    "http://example.com/v1/chat/completions",
    "http://127.0.0.1:18082/other",
    "http://127.0.0.1:18082/v1/chat/completions?redirect=https://example.com",
])
def test_nonlocal_or_changed_model_endpoint_rejected(url: str) -> None:
    with pytest.raises(ValueError, match="local HTTP"):
        vl._local_url(url)


def test_server_requires_loaded_vision_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    model = tmp_path / vl.MODEL_FILENAME
    replies = {
        "http://127.0.0.1:18082/props": {
            "default_generation_settings": {"n_ctx": vl.CONTEXT_TOKENS},
            "model_path": str(model), "modalities": {"vision": True},
        },
        "http://127.0.0.1:18082/v1/models": {
            "data": [{"id": vl.MODEL_ID, "architecture": {"input_modalities": ["text"]}}],
        },
    }
    monkeypatch.setattr(vl, "_local_json", replies.__getitem__)
    with pytest.raises(vl.ContractError, match="image input"):
        vl.check_server("http://127.0.0.1:18082/v1/chat/completions", model)
    replies["http://127.0.0.1:18082/v1/models"]["data"][0]["architecture"]["input_modalities"].append("image")
    vl.check_server("http://127.0.0.1:18082/v1/chat/completions", model)
    replies["http://127.0.0.1:18082/props"]["model_path"] = str(tmp_path / "other.gguf")
    with pytest.raises(vl.ContractError, match="model path"):
        vl.check_server("http://127.0.0.1:18082/v1/chat/completions", model)


def test_mocked_run_keeps_over_limit_document_in_denominator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    cohort = tmp_path / "cohort.jsonl"
    cohort.write_text("public synthetic cohort\n", encoding="utf-8")
    gold_path = tmp_path / "gold.jsonl"
    gold_rows = []
    for doc_id, value, page_count in (("reg", "ABC", 1), ("ad", "XYZ", 4)):
        gold_rows.append({
            "contract_version": 1, "doc_id": doc_id,
            "pages": [{"page": index, "text": f"Code {value}" if index == 1 else "other"}
                      for index in range(1, page_count + 1)],
            "gold_schema": [{"field_id": "code", "type": "string", "critical": False}],
            "gold_values": [{"field_id": "code", "value": value,
                             "evidence": {"page": 1, "start": 5, "end": 8, "quote": value}}],
        })
    gold_path.write_text("".join(json.dumps(row) + "\n" for row in gold_rows), encoding="utf-8")
    model = tmp_path / vl.MODEL_FILENAME
    model.write_bytes(b"mock model")
    projector = tmp_path / vl.PROJECTOR_FILENAME
    projector.write_bytes(b"mock projector")
    monkeypatch.setattr(vl, "COHORT_SHA256", vl.sha256_file(cohort))
    monkeypatch.setattr(vl, "GOLD_SHA256", vl.sha256_file(gold_path))
    monkeypatch.setattr(vl, "MODEL_SHA256", vl.sha256_file(model))
    monkeypatch.setattr(vl, "PROJECTOR_SHA256", vl.sha256_file(projector))
    monkeypatch.setattr(vl, "verify_sources", lambda _: None)
    monkeypatch.setattr(vl.importlib.metadata, "version", lambda _: vl.PDFIUM_VERSION)
    items = []
    for row, family in zip(gold_rows, vl.FAMILIES, strict=True):
        doc_id = row["doc_id"]
        sidecar = tmp_path / f"{doc_id}-sidecar.json"
        sidecar.write_text(json.dumps({"pages": row["pages"]}), encoding="utf-8")
        items.append({
            "cohort": {"doc_id": doc_id, "family": family,
                       "source_sha256": f"{len(items):064x}", "source_path": str(tmp_path / f"{doc_id}.pdf")},
            "pages": row["pages"], "sidecar_path": sidecar, "run_dir": tmp_path / f"vrdu_v6_{doc_id}",
        })
    calls: list[str] = []

    def fake_render(_source: Path, pages: list[dict[str, object]], _destination: Path) -> list[dict[str, object]]:
        return [{"page": page["page"], "data_url": "data:image/png;base64,AAAA", "sha256": "0" * 64,
                 "width": 10, "height": 10} for page in pages]

    def fake_complete(messages: list[dict[str, object]], url: str) -> dict[str, object]:
        calls.append(url)
        assert "Code ABC" in json.dumps(messages)
        return {"text": json.dumps({"values": [{"field_id": "code", "value": "ABC", "page": 1, "quote": "ABC"}]}),
                "finish_reason": "stop", "error": None, "latency_ms": 2,
                "prompt_tokens": 40, "completion_tokens": 20}

    output = tmp_path / "pilot"
    run = vl.run_diagnostic(items=items, cohort_path=cohort, gold_path=gold_path,
                            model_file=model, projector_file=projector,
                            url="http://127.0.0.1:18082/v1/chat/completions", output_dir=output,
                            render=fake_render, complete=fake_complete, server_check=lambda _url, _model: None)
    score = json.loads((output / "score.json").read_text(encoding="utf-8"))
    candidates = [json.loads(line) for line in (output / "candidates.jsonl").read_text(encoding="utf-8").splitlines()]
    assert run["complete"] and run["selected_docs"] == 2 and run["model_calls"] == 1
    assert len(calls) == 1
    assert score["documents"] == {"gold": 2, "candidate": 2, "missing_candidate": 0, "unsupported": 0, "failed": 0}
    assert score["values"]["tp"] == 1 and score["values"]["fn"] == 1
    assert candidates[1]["document_status"] == "needs_review"
    assert candidates[1]["extracted_values"][0]["status"] == "needs_review"
    assert run["reason_counts"]["document_exceeds_page_limit"] == 1
