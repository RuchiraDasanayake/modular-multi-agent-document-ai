"""Source-free protocol and paired product tests: no provider calls or OCR."""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from idpo.product_auto.provider import ModelReply
from idpo.product_auto.visual_input import PreparedVisualRequest
from idpo.product_auto.workflow import _doc_id
from product_eval import product_candidate_dev as trial
from product_eval.final_gate_freeze import digest_file, read_json, write_new
from product_eval.final_gate_ledger import GateStopped, Ledger

GOOD = '{"values":[{"field_id":"total","value":42,"page":1,"quote":"42"}]}'


def good_reply(text=GOOD):
    return ModelReply(text, 1.5, prompt_tokens=10, completion_tokens=7, finish_reason="stop", sdk_attempts=1)


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    sources, schemas = [], {}
    for index, family in enumerate(trial.FAMILIES):
        for number in range(2):
            source = tmp_path / f"{index}-{number}.png"
            Image.new("RGB", (30, 30), (index * 40 + number, 20, 30)).save(source)
            sha = digest_file(source)
            sources.append({"family": family, "doc_id": _doc_id(source.name, sha, 0), "source_path": str(source),
                            "source_sha256": sha, "source_size_bytes": source.stat().st_size})
        schema = tmp_path / f"{family}.json"
        sha = write_new(schema, {
            "contract_version": 1, "brief_id": "brief_" + "a" * 32, "revision": 2,
            "audit_event_id": "b" * 32, "state": "confirmed", "owner_user_id": "synthetic-evaluator",
            "job_id": "c" * 32, "intent": "Read the final total", "payload_sha256": "f" * 64,
            "fields": [{"field_id": "total", "type": "integer", "description": "Final amount", "example_values": []}],
            "sample_sources": [{"file_id": item["doc_id"], "source_sha256": item["source_sha256"]}
                               for item in sources if item["family"] == family],
        })
        schemas[family] = {"path": str(schema), "sha256": sha}
    baseline = tmp_path / "baseline.json"
    baseline_sha = write_new(baseline, {"sources": sources, "schemas": schemas})
    monkeypatch.setattr(trial, "BASELINE_SHA256", baseline_sha)
    monkeypatch.setattr(trial, "code_receipt", lambda: {"commit": "test"})
    runtime = {"ocr_config": {"python": str(Path(sys.executable).resolve()), "work_dir": str(scratch)}, "synthetic": True}
    monkeypatch.setattr(trial, "runtime_receipt", lambda: runtime)
    output = tmp_path / "trial"
    sha = trial.prepare(baseline, output, rapidocr_python=Path(sys.executable), scratch=scratch)
    monkeypatch.setenv("SYNTHETIC_KEY", "private-synthetic-key")
    return SimpleNamespace(output=output, sha=sha, sources=sources, schemas=schemas, baseline=baseline, runtime=runtime, scratch=scratch)


def install_mocks(monkeypatch, output, *, first_reply=None):
    from idpo.product_auto import workflow
    ocr_inputs, calls = [], []

    class Ocr:
        def run(self, payload, _context):
            document = payload["document"]
            ocr_inputs.append(document.path)
            document.pages = [replace(page, text="Total: 42", metadata={**page.metadata,
                              "ocr_engine_used": "rapidocr", "ocr_confidence": 1.0}) for page in document.pages]
            return SimpleNamespace(artifacts={"document": document, "signal": None})

    class Provider:
        def __init__(self, **kwargs):
            assert kwargs["max_tokens"] == 8192 and kwargs["timeout_s"] == 180
            self.model, self.max_tokens = trial.MODEL, 8192
            self.client = SimpleNamespace(max_retries=0, close=lambda: None)

        def respond(self, kind):
            state = Ledger(output / "ledger.sqlite3").snapshot()
            assert state["attempts"][-1]["state"] == "request_begun"
            calls.append(kind)
            if isinstance(first_reply, BaseException) and len(calls) == 1:
                raise first_reply
            return first_reply if first_reply is not None and len(calls) == 1 else good_reply()

        def complete_json(self, **kwargs):
            assert kwargs["response_format"]["json_schema"]["strict"] is True
            return self.respond("text")

        def complete_visual_json(self, request):
            assert request.validated_body(model=self.model, max_tokens=self.max_tokens)
            return self.respond("visual")

    monkeypatch.setattr(workflow, "OcrAgent", Ocr)
    monkeypatch.setattr(trial, "OpenAICompatibleChat", Provider)
    return ocr_inputs, calls


def test_prepare_is_source_only_and_preserves_schema_bytes_and_order(frozen):
    protocol = read_json(frozen.output / "protocol.json")
    assert protocol["sources"] == frozen.sources
    assert Ledger(frozen.output / "ledger.sqlite3").snapshot()["attempts"] == []
    assert not (frozen.output / "run-started.json").exists()
    assert [row["arm"] for row in protocol["schedule"]] == ["text", "visual", "visual", "text"] * 3
    for family, old in frozen.schemas.items():
        new = frozen.output / protocol["schemas"][family]["path"]
        assert new.read_bytes() == Path(old["path"]).read_bytes()
    assert protocol["labels_opened"] is False


def test_prepare_rejects_a_changed_baseline(frozen, tmp_path):
    frozen.baseline.write_text("{}")
    with pytest.raises(ValueError, match="baseline protocol changed"):
        trial.prepare(frozen.baseline, tmp_path / "another", rapidocr_python=Path(sys.executable), scratch=frozen.scratch)


def test_full_paired_product_paths_use_fresh_ocr_and_keep_visual_review_only(frozen, monkeypatch):
    ocr_inputs, calls = install_mocks(monkeypatch, frozen.output)
    result = trial.run(frozen.output, frozen.sha, api_key_env="SYNTHETIC_KEY")
    summary = result["summary"]
    assert len(ocr_inputs) == 12 and len(calls) == 12
    assert summary["stop_reason"] is None and summary["all_product_slots_executed"]
    assert calls == ["text", "visual", "visual", "text"] * 3
    for arm, expected_route in (("text", "text"), ("visual", "visual")):
        report = summary["arms"][arm]
        assert report["selected_originals"] == report["valid_complete_extractions"] == 6
        assert report["route_counts"] == {expected_route: 6}
        assert report["execution"]["distinct_sources"] == 6
        assert len((frozen.output / "arms" / arm / "candidates.jsonl").read_text().splitlines()) == 6
    visual_records = summary["arms"]["visual"]["documents"]
    assert all(record["metrics"]["accepted_scalars"] == 0 for record in visual_records)
    assert all(record["metrics"]["requires_review"] for record in visual_records)
    assert all(record["metrics"]["visual_grounding_verified"] is False for record in visual_records)
    seal = read_json(frozen.output / "prediction-seal.json")
    for path, digest in seal["files"].items():
        assert digest_file(frozen.output / path) == digest


@pytest.mark.parametrize("category,error", [("authentication", "http_401"), ("rate_limit", "http_429"), ("transport_timeout", "APITimeoutError")])
def test_first_provider_error_stops_both_arms_and_keeps_unattempted_denominators(frozen, monkeypatch, category, error):
    failure = ModelReply("", 1, error=error, error_category=category, sdk_attempts=1)
    ocr_inputs, calls = install_mocks(monkeypatch, frozen.output, first_reply=failure)
    summary = trial.run(frozen.output, frozen.sha, api_key_env="SYNTHETIC_KEY")["summary"]
    assert len(calls) == len(ocr_inputs) == 1
    assert summary["model_calls"] == 1 and summary["stop_reason"] == category
    assert summary["selected_source_arm_slots"] == 12 and summary["all_slots_accounted"]
    assert not summary["all_product_slots_executed"]
    assert summary["arms"]["text"]["selected_originals"] == summary["arms"]["visual"]["selected_originals"] == 6
    assert summary["arms"]["visual"]["reason_counts"] == {"unattempted_after_global_stop": 6}
    if category == "transport_timeout":
        assert summary["arms"]["text"]["uncertain_attempts"] == 1


def test_run_started_marker_blocks_replay_even_when_nothing_called(frozen, monkeypatch):
    _ocr, calls = install_mocks(monkeypatch, frozen.output)
    write_new(frozen.output / "run-started.json", {"interrupted": True})
    with pytest.raises(ValueError, match="replay"):
        trial.run(frozen.output, frozen.sha, api_key_env="SYNTHETIC_KEY")
    assert calls == []


def test_interruption_after_request_begun_keeps_unknown_attempt_and_forbids_replay(frozen, monkeypatch):
    _ocr, calls = install_mocks(monkeypatch, frozen.output, first_reply=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        trial.run(frozen.output, frozen.sha, api_key_env="SYNTHETIC_KEY")
    state = Ledger(frozen.output / "ledger.sqlite3").snapshot()
    assert state["attempts"][0]["state"] == "request_begun"
    assert (frozen.output / "run-started.json").exists()
    with pytest.raises(ValueError, match="replay"):
        trial.run(frozen.output, frozen.sha, api_key_env="SYNTHETIC_KEY")
    assert len(calls) == 1


@pytest.mark.parametrize("change", ["source", "schema", "runtime", "code", "protocol"])
def test_changed_frozen_input_fails_before_marker_or_provider(frozen, monkeypatch, change):
    _ocr, calls = install_mocks(monkeypatch, frozen.output)
    if change == "source":
        Path(frozen.sources[0]["source_path"]).write_bytes(b"changed")
    elif change == "schema":
        (frozen.output / "schemas/receipt.json").write_bytes(b"{}")
    elif change == "runtime":
        monkeypatch.setattr(trial, "runtime_receipt", lambda: {"different": True})
    elif change == "code":
        monkeypatch.setattr(trial, "code_receipt", lambda: {"commit": "different"})
    else:
        (frozen.output / "protocol.json").write_bytes(b"{}")
    with pytest.raises(ValueError):
        trial.run(frozen.output, frozen.sha, api_key_env="SYNTHETIC_KEY")
    assert calls == [] and not (frozen.output / "run-started.json").exists()


def recorder_fixture(frozen, *, callback=None):
    source = frozen.sources[0]
    ledger = Ledger(frozen.output / "ledger.sqlite3")
    ledger.claim(trial.slot_id("text", source))
    provider = SimpleNamespace(complete_json=callback or (lambda **_: good_reply()), model=trial.MODEL, max_tokens=8192)
    return trial.RecordedTrial(provider, frozen.output, "text", source, "active_key_123"), ledger


def test_key_redacted_and_request_receipts_are_unique_per_slot(frozen):
    model, ledger = recorder_fixture(frozen, callback=lambda **_: good_reply("active_key_123 iba_abcdefghijklmnopqrstuvwxyz123456"))
    response_format = {"type": "json_schema"}
    for _ in range(2):
        reply = model.complete_json(system="system", prompt="same prompt", response_format=response_format)
        assert "active_key_123" not in reply.text and "iba_" not in reply.text
    files = list((frozen.output / "arms/text/requests").rglob("*.body.json"))
    assert len(files) == 2 and files[0] != files[1] and files[0].read_bytes() == files[1].read_bytes()
    assert len(ledger.snapshot()["attempts"]) == 2
    for path in (frozen.output / "arms/text/requests").rglob("*.json"):
        assert "active_key_123" not in path.read_text()


def test_request_budget_refuses_fifth_source_arm_call(frozen):
    count = []
    model, ledger = recorder_fixture(frozen, callback=lambda **_: (count.append(1), good_reply())[1])
    for _ in range(4):
        model.complete_json(system="s", prompt="p", response_format={"type": "json_schema"})
    with pytest.raises(GateStopped):
        model.complete_json(system="s", prompt="p", response_format={"type": "json_schema"})
    assert len(count) == len(ledger.snapshot()["attempts"]) == 4


def test_global_budget_stops_at_48_provider_invocations(frozen):
    count = []
    provider = SimpleNamespace(complete_json=lambda **_: (count.append(1), good_reply())[1], model=trial.MODEL, max_tokens=8192)
    ledger = Ledger(frozen.output / "ledger.sqlite3")
    for source in frozen.sources:
        for arm in trial.ARMS:
            ledger.claim(trial.slot_id(arm, source))
            model = trial.RecordedTrial(provider, frozen.output, arm, source, "")
            for _ in range(4):
                model.complete_json(system="s", prompt="p", response_format={"type": "json_schema"})
    with pytest.raises(GateStopped, match="global_call_budget"):
        model.complete_json(system="s", prompt="p", response_format={"type": "json_schema"})
    assert len(count) == len(ledger.snapshot()["attempts"]) == 48


def test_uncommitted_marker_failure_prevents_provider_call(frozen, monkeypatch):
    count = []
    model, _ = recorder_fixture(frozen, callback=lambda **_: count.append(1))
    def fail(*_):
        raise OSError("synthetic disk failure")
    monkeypatch.setattr(Ledger, "begin_attempt", fail)
    with pytest.raises(OSError):
        model.complete_json(system="s", prompt="p", response_format={"type": "json_schema"})
    assert count == []


def test_visual_wrapper_preserves_exact_body_bytes_and_source_receipt(frozen):
    source = frozen.sources[0]
    ledger = Ledger(frozen.output / "ledger.sqlite3")
    ledger.claim(trial.slot_id("visual", source))
    body = b'{"model":"innobot-luna-6","max_tokens":8192,"messages":[]}'
    receipt = {"request_sha256": hashlib.sha256(body).hexdigest(), "covered_pages": [1]}
    request = PreparedVisualRequest(Path(source["source_path"]), source["source_sha256"], body, json.dumps(receipt).encode())
    provider = SimpleNamespace(complete_visual_json=lambda request: good_reply(), model=trial.MODEL, max_tokens=8192)
    model = trial.RecordedTrial(provider, frozen.output, "visual", source, "")
    model.complete_visual_json(request)
    entry = model.receipts[0]
    assert (frozen.output / entry["request_path"]).read_bytes() == body
    assert entry["visual_receipt"] == receipt
    assert ledger.snapshot()["attempts"][0]["request_sha256"] == receipt["request_sha256"]


def test_http_success_with_invalid_reply_is_not_complete_extraction(frozen, monkeypatch):
    _ocr, calls = install_mocks(monkeypatch, frozen.output, first_reply=good_reply("bad JSON"))
    summary = trial.run(frozen.output, frozen.sha, api_key_env="SYNTHETIC_KEY")["summary"]
    assert len(calls) == 12 and summary["stop_reason"] is None
    assert summary["arms"]["text"]["valid_complete_extractions"] == 5
    assert summary["arms"]["visual"]["valid_complete_extractions"] == 6
