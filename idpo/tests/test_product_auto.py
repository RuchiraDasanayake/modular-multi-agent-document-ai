"""Acceptance checks for the isolated product auto-extraction path."""

from __future__ import annotations

import hashlib
import json
import sys
import types
from pathlib import Path

from idpo.product_auto import process_auto
from idpo.product_auto.provider import ModelReply, OpenAICompatibleChat
from product_eval.contracts import load_jsonl


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
    assert sidecar["api_cost_usd"] is None
    assert candidate["measurements"]["latency_ms"] >= 0
    assert "api_cost_usd" not in candidate["measurements"]
    _assert_exact_evidence(candidate, sidecar)
    manifest = [json.loads(line) for line in (Path(run["run_dir"]) / "manifest.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(manifest) == 1
    receipt = manifest[0]
    assert receipt["doc_id"] == candidate["doc_id"]
    assert receipt["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert receipt["source_hash_kind"] == "raw_file"
    assert receipt["document_status"] == "needs_review"
    assert receipt["run_id"] == "invoice"
    assert receipt["duration_ms"] >= 0
    assert json.loads((Path(run["run_dir"]) / "run.json").read_text(encoding="utf-8"))["doc_count"] == 1


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
    assert candidate["document_status"] == "needs_review"
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
    assert candidate["document_status"] == "needs_review"
    assert candidate["proposed_schema"] == []
    assert candidate["extracted_values"] == []
    assert sidecar["reason"] == "invalid_schema_model_response"


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
    assert captured["request"]["model"] == "example-model"
    assert (reply.prompt_tokens, reply.completion_tokens, reply.finish_reason) == (7, 4, "stop")

    def raise_with_secret(**kwargs):
        raise RuntimeError(secret)

    model.client.chat.completions.create = raise_with_secret
    error_reply = model.complete_json(system="system", prompt="prompt")
    assert error_reply.error == "RuntimeError"
    assert secret not in str(error_reply)
