"""Acceptance checks for the isolated product auto-extraction path."""

from __future__ import annotations

import hashlib
import json
import sys
import types
from pathlib import Path

import pytest
from PIL import Image

from idpo.agents.preprocess import OcrAgent
from idpo.product_auto import process_auto
from idpo.product_auto.provider import ModelReply, OpenAICompatibleChat
from product_eval.contracts import load_jsonl
from product_eval.execution import verify_run


def _result(run_dir: str) -> tuple[dict, dict]:
    directory = Path(run_dir)
    candidates = load_jsonl(directory / "candidates.jsonl", kind="candidate")
    assert len(candidates) == 1
    candidate = next(iter(candidates.values()))
    sidecar = json.loads((directory / "docs" / candidate["doc_id"] / "result.json").read_text(encoding="utf-8"))
    return candidate, sidecar


def _assert_exact_evidence(candidate: dict, sidecar: dict) -> None:
    pages = {page["page"]: page["text"] for page in sidecar["pages"]}
    for field in candidate["extracted_values"]:
        evidence = field.get("evidence")
        if field["status"] == "accepted":
            assert evidence is not None
        if evidence is None:
            continue
        assert pages[evidence["page"]][evidence["start"] : evidence["end"]] == evidence["quote"]


class FakeModel:
    model = "mock-model"

    def __init__(self, *replies: ModelReply) -> None:
        self.replies = list(replies)
        self.calls: list[str] = []

    def complete_json(self, *, system: str, prompt: str) -> ModelReply:
        self.calls.append(prompt)
        return self.replies.pop(0)


def test_invoice_baseline_preserves_zero_and_exact_spans(tmp_path: Path) -> None:
    source = tmp_path / "invoice.txt"
    source.write_text("Invoice Number: INV-42\nTotal: 0.00\nCustomer: Ada Lovelace\n", encoding="utf-8")

    run = process_auto(source, run_id="invoice", output_root=tmp_path / "runs")
    candidate, sidecar = _result(run["run_dir"])

    assert candidate["document_status"] == "needs_review"
    values = {item["field_id"]: item for item in candidate["extracted_values"]}
    assert values["total"]["value"] == 0.0
    assert values["total"]["status"] == "needs_review"
    assert values["total"]["review_state"] == "pending"
    assert values["invoice_number"]["value"] == "INV-42"
    assert sidecar["reason"] == "unapproved_dynamic_schema"
    assert sidecar["ocr_pages"][0]["page"] == 1
    assert sidecar["ocr_pages"][0]["rerun_attempted"] is False
    assert sidecar["api_cost_usd"] is None
    assert sidecar["stage_timings_ms"]["ocr"] >= 0
    assert sidecar["source_prepare_ms"] >= 0
    usage = sidecar["resource_usage"]
    assert usage["worker_process_cpu_ms"] >= usage["source_prepare_worker_process_cpu_ms"] >= 0
    assert usage["worker_rss_before_bytes"] is None or usage["worker_rss_before_bytes"] >= 0
    assert usage["worker_rss_after_bytes"] is None or usage["worker_rss_after_bytes"] >= 0
    assert candidate["measurements"]["latency_ms"] >= 0
    assert "api_cost_usd" not in candidate["measurements"]
    _assert_exact_evidence(candidate, sidecar)
    manifest = [json.loads(line) for line in (Path(run["run_dir"]) / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(manifest) == 1
    receipt = manifest[0]
    assert receipt["doc_id"] == candidate["doc_id"]
    assert receipt["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert receipt["result_sha256"] == hashlib.sha256(
        (Path(run["run_dir"]) / "docs" / candidate["doc_id"] / "result.json").read_bytes()
    ).hexdigest()
    assert receipt["source_hash_kind"] == "raw_file"
    assert receipt["document_status"] == "needs_review"
    assert receipt["run_id"] == "invoice"
    assert receipt["duration_ms"] >= 0
    assert receipt["resource_usage"] == usage
    run_metadata = json.loads((Path(run["run_dir"]) / "run.json").read_text(encoding="utf-8"))
    assert run_metadata["doc_count"] == 1
    assert run_metadata["resource_usage"]["worker_process_cpu_ms"] >= 0
    assert run_metadata["resource_usage"]["rss_method"] == "boundary_snapshots; not peak memory"
    assert run_metadata["compute_cost_usd"] is None
    assert verify_run(run["run_dir"])["distinct_sources"] == 1


def test_product_sidecar_whitelists_pdf_renderer_provenance(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "scan.pdf"
    Image.new("RGB", (80, 60), "white").save(source, "PDF", resolution=100)
    monkeypatch.setattr(OcrAgent, "_ocr_image", lambda self, page, settings, engine_name="paddle": (
        "Invoice Number INV-42", True, None, {"ocr_engine_used": "test", "ocr_confidence": 80.0}
    ))

    run = process_auto(source, run_id="pdf-renderer", output_root=tmp_path / "runs")
    _, sidecar = _result(run["run_dir"])
    page = sidecar["ocr_pages"][0]
    renderer_fields = {key: value for key, value in page.items() if key.startswith("pdf_")}

    assert set(renderer_fields) == {
        "pdf_renderer", "pdf_renderer_fallback_reason", "pdf_page_index",
        "pdf_page_rotation_deg", "pdf_rendered_dpi", "pdf_render_size_px",
        "pdf_native_layer", "pdf_native_text_sha256", "pdf_native_text_rejected",
        "pdf_render_plan",
    }
    assert page["pdf_renderer"] == "pdfium"
    assert page["pdf_renderer_fallback_reason"] is None
    assert page["pdf_page_index"] == 0
    assert page["pdf_page_rotation_deg"] == 0
    assert page["pdf_rendered_dpi"] == pytest.approx(100)
    assert 79 <= page["pdf_render_size_px"][0] <= 81
    assert 59 <= page["pdf_render_size_px"][1] <= 61
    assert page["pdf_render_plan"]["requested_dpi"] == 300
    assert "source_sha256" in sidecar
    assert not any(str(source) in str(value) for value in renderer_fields.values())

    native = tmp_path / "native.txt"
    native.write_text("Invoice Number INV-42", encoding="utf-8")
    native_run = process_auto(native, run_id="native-renderer", output_root=tmp_path / "runs")
    _, native_sidecar = _result(native_run["run_dir"])
    assert native_sidecar["ocr_pages"][0]["pdf_renderer"] is None
    assert native_sidecar["ocr_pages"][0]["pdf_render_size_px"] is None


def test_product_auto_sets_single_initial_ocr_profile(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "invoice.txt"
    source.write_text("Invoice Number: INV-42\n", encoding="utf-8")
    seen: list[tuple[int, int, list[int], bool, int | None, float, float]] = []
    original_run = OcrAgent.run

    def inspect_run(self, payload, ctx):
        preprocessing = ctx.config.preprocessing
        seen.append((
            preprocessing.ocr_psm,
            preprocessing.ocr_passes,
            preprocessing.ocr_alt_psm,
            preprocessing.ocr_initial_single_pass,
            preprocessing.ocr_retry_max_candidates,
            preprocessing.ocr_tesseract_call_timeout_s,
            preprocessing.ocr_tesseract_page_budget_s,
        ))
        return original_run(self, payload, ctx)

    monkeypatch.setattr(OcrAgent, "run", inspect_run)
    run = process_auto(source, run_id="fast_ocr", output_root=tmp_path / "runs")
    run_payload = json.loads((Path(run["run_dir"]) / "run.json").read_text(encoding="utf-8"))

    assert seen == [(6, 1, [], True, 8, 30.0, 120.0)]
    assert run_payload["ocr_profile"] == "psm6_single_initial_quality_retry"
    assert run_payload["ocr_retry_max_candidates"] == 8
    assert run_payload["ocr_call_timeout_s"] == 30.0
    assert run_payload["ocr_page_budget_s"] == 120.0


def test_numeric_identifiers_keep_leading_zeros(tmp_path: Path) -> None:
    source = tmp_path / "identifiers.txt"
    source.write_text("Invoice Number: 00042\nZip Code: 00123\nItem Count: 3\n", encoding="utf-8")
    run = process_auto(source, run_id="identifiers", output_root=tmp_path / "runs")
    candidate, _ = _result(run["run_dir"])
    schema = {item["field_id"]: item["type"] for item in candidate["proposed_schema"]}
    values = {item["field_id"]: item["value"] for item in candidate["extracted_values"]}
    assert schema["invoice_number"] == schema["zip_code"] == "string"
    assert values["invoice_number"] == "00042"
    assert values["zip_code"] == "00123"
    assert (schema["item_count"], values["item_count"]) == ("integer", 3)


def test_over_page_limit_pdf_abstains_before_ocr(tmp_path: Path) -> None:
    from pypdf import PdfWriter

    source = tmp_path / "many_pages.pdf"
    writer = PdfWriter()
    for _ in range(51):
        writer.add_blank_page(width=72, height=72)
    with source.open("wb") as handle:
        writer.write(handle)
    run = process_auto(source, run_id="many_pages", output_root=tmp_path / "runs")
    candidate, sidecar = _result(run["run_dir"])
    assert candidate["document_status"] == "unsupported"
    assert candidate["proposed_schema"] == []
    assert sidecar["reason"] == "too_many_pages"
    assert sidecar["resource_usage"]["worker_process_cpu_ms"] >= 0


def test_narrative_without_model_abstains_and_empty_document_is_unsupported(tmp_path: Path) -> None:
    narrative = tmp_path / "narrative.txt"
    narrative.write_text("Alice met Bob at the station. They discussed the weather.", encoding="utf-8")
    run = process_auto(narrative, run_id="narrative", output_root=tmp_path / "runs")
    candidate, sidecar = _result(run["run_dir"])
    assert candidate["document_status"] == "needs_review"
    assert candidate["proposed_schema"] == []
    assert sidecar["reason"] == "no_fields_discovered"

    empty = tmp_path / "empty.txt"
    empty.write_text("", encoding="utf-8")
    run = process_auto(empty, run_id="empty", output_root=tmp_path / "runs")
    candidate, sidecar = _result(run["run_dir"])
    assert candidate["document_status"] == "unsupported"
    assert sidecar["reason"] == "no_text_after_ocr"


def test_empty_ocr_with_engine_failure_is_a_failed_run_not_an_unsupported_source(
    tmp_path: Path, monkeypatch,
) -> None:
    source = tmp_path / "scan.txt"
    source.write_text("", encoding="utf-8")

    def failing_ocr(self, payload, ctx):
        return types.SimpleNamespace(artifacts={
            "document": payload["document"],
            "signal": types.SimpleNamespace(failure_reason="ocr_failed"),
        })

    monkeypatch.setattr(OcrAgent, "run", failing_ocr)
    run = process_auto(source, run_id="ocr_dependency_failure", output_root=tmp_path / "runs")
    candidate, sidecar = _result(run["run_dir"])
    assert candidate["document_status"] == "failed"
    assert sidecar["reason"] == "ocr_failed"


@pytest.mark.parametrize(
    ("ocr_text", "expected_status", "expected_reason"),
    [
        ("", "failed", "ocr_timeout"),
        ("Invoice Number: INV-42\nTotal: 100", "needs_review", "ocr_partial_failure"),
    ],
)
def test_product_tesseract_timeout_classifies_empty_and_partial_ocr(
    tmp_path: Path, monkeypatch, ocr_text: str, expected_status: str, expected_reason: str,
) -> None:
    source = tmp_path / "scan.png"
    Image.new("RGB", (80, 40), "white").save(source)

    def timed_out_ocr(self, page, settings, engine_name):
        return ocr_text, True, "ocr_timeout", {
            "ocr_engine_used": "tesseract", "ocr_candidate_count": 1,
        }

    monkeypatch.setattr(OcrAgent, "_ocr_image", timed_out_ocr)
    run = process_auto(source, run_id="ocr_timeout", output_root=tmp_path / "runs")
    candidate, sidecar = _result(run["run_dir"])
    assert candidate["document_status"] == expected_status
    assert sidecar["reason"] == expected_reason
    assert sidecar["ocr_pages"][0]["failure_reason"] == "ocr_timeout"
    assert sidecar["model_calls"] == []


@pytest.mark.parametrize("overrides", [{"ocr_call_timeout_s": 0}, {"ocr_page_budget_s": float("inf")}])
def test_product_rejects_invalid_ocr_budgets_before_creating_run(tmp_path: Path, overrides: dict) -> None:
    source = tmp_path / "invoice.txt"
    source.write_text("Invoice Number INV-42", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a finite positive number"):
        process_auto(source, run_id="invalid_budget", output_root=tmp_path / "runs", **overrides)
    assert not (tmp_path / "runs").exists()


def test_missing_marker_stays_distinct_from_numeric_zero(tmp_path: Path) -> None:
    source = tmp_path / "account.txt"
    source.write_text("Balance: 0\nAccount Number: N/A\nFee: 5\n", encoding="utf-8")
    run = process_auto(source, run_id="missing_marker", output_root=tmp_path / "runs")
    candidate, sidecar = _result(run["run_dir"])
    values = {item["field_id"]: item for item in candidate["extracted_values"]}
    assert values["balance"]["value"] == 0
    assert values["balance"]["status"] == "needs_review"
    assert values["account_number"]["value"] is None
    assert values["account_number"]["status"] == "missing"
    assert values["fee"]["value"] == 5
    assert candidate["document_status"] == "needs_review"
    _assert_exact_evidence(candidate, sidecar)


def test_model_discovers_field_with_grounded_value_and_records_usage(tmp_path: Path) -> None:
    source = tmp_path / "letter.txt"
    source.write_text("A letter from Acme Corp was received today.", encoding="utf-8")
    model = FakeModel(
        ModelReply(
            text=json.dumps({"fields": [{"field_id": "sender", "type": "string", "group": "header"}]}),
            latency_ms=12.5,
            prompt_tokens=91,
            completion_tokens=19,
            finish_reason="stop",
        ),
        ModelReply(
            text=json.dumps({"values": [{"field_id": "sender", "value": "Acme Corp", "page": 1, "quote": "Acme Corp"}]}),
            latency_ms=15.25,
            prompt_tokens=88,
            completion_tokens=24,
            finish_reason="stop",
        ),
    )

    run = process_auto(source, run_id="model_valid", model=model, output_root=tmp_path / "runs")
    candidate, sidecar = _result(run["run_dir"])

    assert len(model.calls) == 2
    assert candidate["document_status"] == "needs_review"
    assert candidate["extracted_values"][0]["value"] == "Acme Corp"
    assert candidate["extracted_values"][0]["status"] == "accepted"
    assert candidate["extracted_values"][0]["review_state"] == "pending"
    assert [(call["prompt_tokens"], call["completion_tokens"]) for call in sidecar["model_calls"]] == [(91, 19), (88, 24)]
    _assert_exact_evidence(candidate, sidecar)


def test_invalid_quote_or_page_never_accepts_model_value(tmp_path: Path) -> None:
    source = tmp_path / "letter.txt"
    source.write_text("A letter from Acme Corp was received today.", encoding="utf-8")
    for name, quote, page in (("invented", "Other Company", 1), ("wrong_page", "Acme Corp", 9)):
        model = FakeModel(
            ModelReply(text='{"fields":[{"field_id":"sender","type":"string"}]}', latency_ms=1),
            ModelReply(
                text=json.dumps({"values": [{"field_id": "sender", "value": "Acme Corp", "page": page, "quote": quote}]}),
                latency_ms=1,
            ),
        )
        run = process_auto(source, run_id=name, model=model, output_root=tmp_path / "runs")
        candidate, _ = _result(run["run_dir"])
        value = candidate["extracted_values"][0]
        assert candidate["document_status"] == "needs_review"
        assert value["status"] == "needs_review"
        assert "evidence" not in value


def test_truncated_schema_response_abstains_without_baseline_fallback(tmp_path: Path) -> None:
    source = tmp_path / "invoice.txt"
    source.write_text("Invoice Number: INV-42\n", encoding="utf-8")
    model = FakeModel(ModelReply(text='{"fields":[{"field_id":"invoice_number","type":"string"}]}', latency_ms=1, finish_reason="length"))
    run = process_auto(source, run_id="truncated", model=model, output_root=tmp_path / "runs")
    candidate, sidecar = _result(run["run_dir"])
    assert candidate["document_status"] == "failed"
    assert candidate["proposed_schema"] == []
    assert candidate["extracted_values"] == []
    assert sidecar["reason"] == "invalid_schema_model_response"
    assert len(model.calls) == 1


def test_invalid_schema_model_response_abstains(tmp_path: Path) -> None:
    source = tmp_path / "invoice.txt"
    source.write_text("Invoice Number: INV-42\n", encoding="utf-8")
    model = FakeModel(ModelReply(text='{"fields":[{"field_id":"invoice_number","type":"object"}]}', latency_ms=1))
    run = process_auto(source, run_id="invalid_schema", model=model, output_root=tmp_path / "runs")
    candidate, sidecar = _result(run["run_dir"])
    assert candidate["document_status"] == "failed"
    assert candidate["proposed_schema"] == []
    assert candidate["extracted_values"] == []
    assert sidecar["reason"] == "invalid_schema_model_response"


@pytest.mark.parametrize("invalid_reply", [
    ModelReply(text='{"values":', latency_ms=1),
    ModelReply(text='{"values":[{"field_id":"invoice_number","value":"INV-42",'
                    '"page":1,"quote":"INV-42"}]}', latency_ms=1, refusal=True),
])
def test_invalid_discovered_values_response_fails_without_second_value_call(
    tmp_path: Path, invalid_reply: ModelReply,
) -> None:
    source = tmp_path / "invoice.txt"
    source.write_text("Invoice Number: INV-42\n", encoding="utf-8")
    model = FakeModel(
        ModelReply(text='{"fields":[{"field_id":"invoice_number","type":"string"}]}', latency_ms=1),
        invalid_reply,
    )
    run = process_auto(source, run_id="invalid_values", model=model, output_root=tmp_path / "runs")
    candidate, sidecar = _result(run["run_dir"])
    assert len(model.calls) == 2
    assert candidate["document_status"] == "failed"
    assert sidecar["reason"] == "invalid_values_model_response"
    assert [value["status"] for value in candidate["extracted_values"]] == ["missing"]


def test_refused_schema_response_fails_even_with_parseable_body(tmp_path: Path) -> None:
    source = tmp_path / "invoice.txt"
    source.write_text("Invoice Number: INV-42\n", encoding="utf-8")
    model = FakeModel(ModelReply(
        text='{"fields":[{"field_id":"invoice_number","type":"string"}]}',
        latency_ms=1, refusal=True,
    ))
    run = process_auto(source, run_id="refused_schema", model=model, output_root=tmp_path / "runs")
    candidate, sidecar = _result(run["run_dir"])
    assert len(model.calls) == 1
    assert candidate["document_status"] == "failed"
    assert sidecar["reason"] == "invalid_schema_model_response"
    assert candidate["proposed_schema"] == []


@pytest.mark.parametrize(
    ("phase", "expected_reason", "expected_attempts"),
    [
        ("schema", "schema_provider_error", 1),
        ("values", "values_provider_error", 2),
    ],
)
def test_provider_failure_is_failed_and_counts_known_sdk_attempts(
    tmp_path: Path, phase: str, expected_reason: str, expected_attempts: int,
) -> None:
    source = tmp_path / "invoice.txt"
    source.write_text("Invoice Number: INV-42\n", encoding="utf-8")
    failure = ModelReply(
        text="", latency_ms=10, error="APIConnectionError",
        error_category="transport_timeout", sdk_attempts=1,
    )
    schema = ModelReply(
        text='{"fields":[{"field_id":"invoice_number","type":"string"}]}',
        latency_ms=1, sdk_attempts=1,
    )
    model = FakeModel(failure) if phase == "schema" else FakeModel(schema, failure)

    run = process_auto(source, run_id=f"provider_{phase}", model=model, output_root=tmp_path / "runs")
    candidate, sidecar = _result(run["run_dir"])
    run_dir = Path(run["run_dir"])
    receipt = json.loads((run_dir / "manifest.jsonl").read_text(encoding="utf-8"))
    run_metadata = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))

    assert candidate["document_status"] == "failed"
    assert sidecar["reason"] == expected_reason
    assert sidecar["model_calls"][-1]["error_category"] == "transport_timeout"
    assert len(model.calls) == expected_attempts
    assert receipt["model_call_count"] == expected_attempts
    assert receipt["model_sdk_attempt_count"] == expected_attempts
    assert run_metadata["model_call_count"] == expected_attempts
    assert run_metadata["model_sdk_attempt_count"] == expected_attempts


def test_unexpected_document_error_after_model_calls_does_not_abort_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from idpo.product_auto import workflow

    sources = tmp_path / "sources"
    sources.mkdir()
    for name, person in (("01.txt", "Alpha"), ("02.txt", "Beta")):
        (sources / name).write_text(f"Name: {person}", encoding="utf-8")
    schema_reply = ModelReply(text='{"fields":[{"field_id":"name","type":"string"}]}',
                              latency_ms=1, sdk_attempts=1)
    values_reply = ModelReply(text='{"values":[{"field_id":"name","value":"Alpha",'
                                   '"page":1,"quote":"Alpha"}]}', latency_ms=1, sdk_attempts=1)
    second_values_reply = ModelReply(text='{"values":[{"field_id":"name","value":"Beta",'
                                          '"page":1,"quote":"Beta"}]}', latency_ms=1, sdk_attempts=1)
    model = FakeModel(schema_reply, values_reply, schema_reply, second_values_reply)
    original = workflow._process_document
    first = True

    def crash_after_model_reply(*args, **kwargs):
        nonlocal first
        result = original(*args, **kwargs)
        if first:
            first = False
            raise RuntimeError("private provider or document detail")
        return result

    monkeypatch.setattr(workflow, "_process_document", crash_after_model_reply)
    run = process_auto(sources, run_id="isolated_failure", model=model, output_root=tmp_path / "runs")
    run_dir = Path(run["run_dir"])
    candidates = [json.loads(line) for line in (run_dir / "candidates.jsonl").read_text(encoding="utf-8").splitlines()]
    receipts = [json.loads(line) for line in (run_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    marker = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    first_sidecar = json.loads((run_dir / "docs" / candidates[0]["doc_id"] / "result.json").read_text(encoding="utf-8"))

    assert len(model.calls) == 4  # No automatic replay of either paid phase.
    assert [candidate["document_status"] for candidate in candidates] == ["failed", "needs_review"]
    assert first_sidecar["reason"] == "document_processing_failed"
    assert first_sidecar["model_attempts_uncertain"] is True
    assert "private provider or document detail" not in json.dumps(first_sidecar)
    assert [call["phase"] for call in first_sidecar["model_calls"]] == ["schema", "values"]
    assert receipts[0]["model_call_count"] == 2
    assert receipts[0]["model_sdk_attempt_count"] is None
    assert receipts[0]["model_attempts_uncertain"] is True
    assert marker["model_call_count"] == 4
    assert marker["model_sdk_attempt_count"] is None
    assert marker["model_attempts_uncertain_doc_count"] == 1
    assert marker["doc_count"] == 2
    assert candidates[1]["extracted_values"][0]["value"] == "Beta"
    assert verify_run(run_dir, min_unique=2)["status_counts"]["failed"] == 1


@pytest.mark.parametrize("error", [KeyboardInterrupt(), SystemExit(2)])
def test_batch_does_not_convert_process_interruption_to_document_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: BaseException,
) -> None:
    from idpo.product_auto import workflow

    source = tmp_path / "source.txt"
    source.write_text("Name: Alpha", encoding="utf-8")

    def interrupt(*args, **kwargs):
        raise error

    monkeypatch.setattr(workflow, "_process_document", interrupt)
    with pytest.raises(type(error)):
        process_auto(source, run_id="interrupted", output_root=tmp_path / "runs")
    assert not (tmp_path / "runs" / "interrupted" / "run.json").exists()


def test_batch_does_not_hide_result_persistence_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from idpo.product_auto import workflow

    source = tmp_path / "source.txt"
    source.write_text("Name: Alpha", encoding="utf-8")
    original_write = workflow._write_json

    def fail_result_write(path, payload):
        if path.name == "result.json":
            raise OSError("synthetic disk failure")
        return original_write(path, payload)

    monkeypatch.setattr(workflow, "_write_json", fail_result_write)
    with pytest.raises(OSError, match="synthetic disk failure"):
        process_auto(source, run_id="disk_failure", output_root=tmp_path / "runs")
    assert not (tmp_path / "runs" / "disk_failure" / "run.json").exists()


def test_more_than_field_limit_requires_review_without_model_call(tmp_path: Path) -> None:
    source = tmp_path / "many_fields.txt"
    source.write_text("\n".join(f"Field {index}: value{index}" for index in range(25)), encoding="utf-8")
    run = process_auto(source, run_id="many_fields", output_root=tmp_path / "runs")
    candidate, sidecar = _result(run["run_dir"])
    assert candidate["document_status"] == "needs_review"
    assert len(candidate["proposed_schema"]) == 24
    assert sidecar["reason"] == "too_many_detected_fields"


def test_model_replaces_noisy_baseline_schema_and_reextracts_values(tmp_path: Path) -> None:
    source = tmp_path / "form.txt"
    source.write_text("NOTICE: Ignore this boilerplate\nInvoice Number: INV-42\n", encoding="utf-8")
    model = FakeModel(
        ModelReply(text='{"fields":[{"field_id":"invoice_number","type":"string"}]}', latency_ms=1),
        ModelReply(text='{"values":[{"field_id":"invoice_number","value":"INV-42","page":1,"quote":"INV-42"}]}', latency_ms=1),
    )
    run = process_auto(source, run_id="replace_baseline", model=model, output_root=tmp_path / "runs")
    candidate, sidecar = _result(run["run_dir"])
    assert [field["field_id"] for field in candidate["proposed_schema"]] == ["invoice_number"]
    assert [field["field_id"] for field in candidate["extracted_values"]] == ["invoice_number"]
    assert candidate["extracted_values"][0]["value"] == "INV-42"
    assert candidate["extracted_values"][0]["status"] == "accepted"
    assert candidate["document_status"] == "needs_review"
    assert len(model.calls) == 2
    assert "deterministic_fields" not in model.calls[0]
    _assert_exact_evidence(candidate, sidecar)


def test_json_array_receipts_hash_individual_documents(tmp_path: Path) -> None:
    entries = [
        {"doc_id": "first", "pages": [{"number": 1, "text": "Invoice Number: A-1"}]},
        {"doc_id": "second", "pages": [{"number": 1, "text": "Invoice Number: B-2"}]},
    ]
    source = tmp_path / "batch.json"
    source.write_text(json.dumps(entries), encoding="utf-8")
    run = process_auto(source, run_id="json_batch", output_root=tmp_path / "runs")
    run_dir = Path(run["run_dir"])
    candidates = load_jsonl(run_dir / "candidates.jsonl", kind="candidate")
    receipts = [json.loads(line) for line in (run_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(receipts) == len(candidates) == 2
    assert {receipt["doc_id"] for receipt in receipts} == set(candidates)
    assert {receipt["source_index"] for receipt in receipts} == {0, 1}
    assert len({receipt["source_sha256"] for receipt in receipts}) == 2
    for index, receipt in enumerate(receipts):
        canonical = json.dumps(entries[index], sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
        assert receipt["source_sha256"] == hashlib.sha256(canonical).hexdigest()
        assert receipt["source_container_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
        assert receipt["source_hash_kind"] == "canonical_json_entry"
        assert receipt["document_status"] == candidates[receipt["doc_id"]]["document_status"]


def test_uploaded_json_cannot_make_product_ocr_read_an_external_image(tmp_path: Path, monkeypatch) -> None:
    secret = tmp_path / "outside.png"
    secret.write_bytes(b"private image bytes")
    source = tmp_path / "untrusted.json"
    source.write_text(json.dumps({
        "doc_id": "untrusted", "pages": [{"number": 1, "text": "", "image_path": str(secret)}],
    }), encoding="utf-8")
    calls: list[bool] = []

    def forbidden_ocr(*args, **kwargs):
        calls.append(True)
        raise AssertionError("Uploaded JSON referenced a server-side file")

    monkeypatch.setattr(OcrAgent, "_ocr_image", forbidden_ocr)
    run = process_auto(source, run_id="untrusted_json", output_root=tmp_path / "runs")
    candidate, sidecar = _result(run["run_dir"])
    assert calls == []
    assert candidate["document_status"] == "unsupported"
    assert sidecar["reason"] == "no_text_after_ocr"


def test_uploaded_json_page_limit_is_checked_before_ocr(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "many.json"
    source.write_text(json.dumps({
        "doc_id": "many", "pages": [{"number": index + 1, "text": "A: 1"} for index in range(51)],
    }), encoding="utf-8")
    calls: list[bool] = []

    def forbidden_ocr(*args, **kwargs):
        calls.append(True)
        raise AssertionError("Too many pages reached OCR")

    monkeypatch.setattr(OcrAgent, "run", forbidden_ocr)
    run = process_auto(source, run_id="too_many_json_pages", output_root=tmp_path / "runs")
    candidate, sidecar = _result(run["run_dir"])
    assert calls == []
    assert candidate["document_status"] == "unsupported"
    assert sidecar["reason"] == "too_many_pages"


def test_cli_process_auto_without_model_uses_runtime_data_root(tmp_path: Path, monkeypatch, capsys) -> None:
    from idpo.cli import main

    source = tmp_path / "invoice.txt"
    source.write_text("Invoice ID: ID\nTotal: $0\n", encoding="utf-8")
    monkeypatch.setenv("IDPO_DATA_DIR", str(tmp_path / "runtime"))
    monkeypatch.setattr(sys, "argv", ["idpo", "process-auto", "--input", str(source), "--run-id", "cli_test"])
    main()
    printed = json.loads(capsys.readouterr().out)
    run_dir = tmp_path / "runtime" / "product_runs" / "cli_test"
    assert printed["run_dir"] == str(run_dir)
    candidate, sidecar = _result(printed["run_dir"])
    values = {item["field_id"]: item for item in candidate["extracted_values"]}
    assert values["invoice_id"]["evidence"]["quote"] == "ID"
    assert values["invoice_id"]["evidence"]["start"] > 0
    assert values["total"]["value"] == 0.0
    _assert_exact_evidence(candidate, sidecar)


@pytest.mark.parametrize("flag,value", [
    ("--max-tokens", "0"), ("--max-tokens", "16385"), ("--max-tokens", "1.5"),
    ("--timeout-s", "0"), ("--timeout-s", "601"), ("--timeout-s", "1e2"),
])
def test_cli_process_auto_rejects_out_of_bounds_model_budget(tmp_path: Path, monkeypatch, flag: str, value: str) -> None:
    from idpo.cli import main

    source = tmp_path / "invoice.txt"
    source.write_text("Total: 100", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["idpo", "process-auto", "--input", str(source), flag, value])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


def test_openai_compatible_adapter_uses_env_key_and_sanitizes_errors(monkeypatch) -> None:
    secret = "test-secret-that-must-not-be-logged"
    monkeypatch.setenv("PRODUCT_TEST_KEY", secret)
    captured: dict = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured["request"] = kwargs
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(message=types.SimpleNamespace(content='{"fields":[]}'), finish_reason="stop")],
                usage=types.SimpleNamespace(prompt_tokens=7, completion_tokens=4),
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.chat = types.SimpleNamespace(completions=FakeCompletions())

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    model = OpenAICompatibleChat(base_url="https://example.invalid/v1", model="example-model", api_key_env="PRODUCT_TEST_KEY")
    reply = model.complete_json(system="system", prompt="prompt")
    assert captured["client"]["api_key"] == secret
    assert captured["client"]["max_retries"] == 0
    assert captured["request"]["model"] == "example-model"
    assert (reply.prompt_tokens, reply.completion_tokens, reply.finish_reason) == (7, 4, "stop")
    assert reply.sdk_attempts == 1

    def raise_with_secret(**kwargs):
        raise RuntimeError(secret)

    model.client.chat.completions.create = raise_with_secret
    error_reply = model.complete_json(system="system", prompt="prompt")
    assert error_reply.error == "RuntimeError"
    assert error_reply.error_category == "provider_other"
    assert error_reply.sdk_attempts == 1
    assert secret not in str(error_reply)


def test_openai_compatible_adapter_classifies_transport_and_http_errors_without_messages(monkeypatch) -> None:
    secret = "private-document-or-key-must-not-appear"
    monkeypatch.setenv("PRODUCT_TEST_KEY", secret)

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))

        def create(self, **kwargs):
            try:
                raise TimeoutError(secret)
            except TimeoutError as cause:
                raise APIConnectionError(secret) from cause

    class APIConnectionError(Exception):
        pass

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    model = OpenAICompatibleChat(base_url="https://example.invalid/v1", model="example-model", api_key_env="PRODUCT_TEST_KEY")
    reply = model.complete_json(system="system", prompt="prompt")
    assert (reply.error, reply.error_category, reply.sdk_attempts) == ("APIConnectionError", "transport_timeout", 1)
    assert secret not in str(reply)

    class HttpFailure(Exception):
        status_code = 429

    def rate_limited(**kwargs):
        raise HttpFailure(secret)

    model.client.chat.completions.create = rate_limited
    reply = model.complete_json(system="system", prompt="prompt")
    assert (reply.error, reply.error_category, reply.sdk_attempts) == ("http_429", "rate_limit", 1)
    assert secret not in str(reply)


def test_openai_sdk_503_uses_one_mock_transport_attempt(monkeypatch) -> None:
    openai = pytest.importorskip("openai")
    httpx = pytest.importorskip("httpx")
    secret = "private-document-or-key-must-not-appear"
    monkeypatch.setenv("PRODUCT_TEST_KEY", secret)
    requests: list[object] = []

    def respond(request):
        requests.append(request)
        return httpx.Response(503, json={"error": {"message": secret, "type": "server_error"}})

    real_openai = openai.OpenAI

    def client_factory(**kwargs):
        return real_openai(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(respond)))

    monkeypatch.setattr(openai, "OpenAI", client_factory)
    model = OpenAICompatibleChat(base_url="https://example.invalid/v1", model="example-model", api_key_env="PRODUCT_TEST_KEY")
    try:
        reply = model.complete_json(system="system", prompt="prompt")
    finally:
        model.client.close()
    assert len(requests) == 1
    assert (reply.error, reply.error_category, reply.sdk_attempts) == ("http_503", "provider_server", 1)
    assert secret not in str(reply)


def test_openai_compatible_adapter_allows_keyless_loopback_only(monkeypatch) -> None:
    monkeypatch.delenv("PRODUCT_TEST_KEY", raising=False)
    captured: dict = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=FakeOpenAI))
    model = OpenAICompatibleChat(
        base_url="http://127.0.0.1:8080/v1",
        model="local-model",
        api_key_env="PRODUCT_TEST_KEY",
    )
    assert model.model == "local-model"
    assert captured["api_key"] == "local-no-auth"
    assert captured["base_url"] == "http://127.0.0.1:8080/v1"

    monkeypatch.setenv("PRODUCT_TEST_KEY", "cloud-secret")
    OpenAICompatibleChat(
        base_url="http://localhost:8080/v1", model="local-model", api_key_env="PRODUCT_TEST_KEY"
    )
    assert captured["api_key"] == "local-no-auth"
    monkeypatch.delenv("PRODUCT_TEST_KEY")

    with pytest.raises(ValueError, match="PRODUCT_TEST_KEY is not set"):
        OpenAICompatibleChat(
            base_url="https://remote.example/v1", model="remote-model", api_key_env="PRODUCT_TEST_KEY"
        )
    with pytest.raises(ValueError, match="HTTPS or local HTTP"):
        OpenAICompatibleChat(
            base_url="http://localhost.evil.example/v1", model="remote-model", api_key_env="PRODUCT_TEST_KEY"
        )
