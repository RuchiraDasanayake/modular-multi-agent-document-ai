"""Synthetic paired quality campaigns; real product workflow, no OCR or API calls."""

from __future__ import annotations

import json
import sys
from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from idpo.product_auto.provider import ModelReply
from product_eval import final_model_gate as gate
from product_eval import quality_comparison as quality
from product_eval.final_gate_freeze import digest_file, read_json, write_new
from product_eval.final_gate_ledger import Ledger


class InlinePool:
    """Keep mocks in process; assert production requests the spawn context."""

    def __init__(self, *, max_workers, mp_context):
        assert max_workers == 1 and mp_context.get_start_method() == "spawn"

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def submit(self, function, *args):
        future = Future()
        try:
            future.set_result(function(*args))
        except BaseException as exc:  # noqa: BLE001 - emulate Future delivery of injected interruptions
            future.set_exception(exc)
        return future


@pytest.fixture
def frozen(tmp_path, monkeypatch, request):
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(quality, "FAMILIES", {name: 2 for name in quality.FAMILIES})
    if hasattr(request, "param"):
        monkeypatch.setattr(quality, "ARM_MAX_CALLS", request.param["arm_max_calls"])
        monkeypatch.setattr(quality, "GLOBAL_MAX_CALLS", 2 * request.param["arm_max_calls"])
    schemas, sources = {}, []
    for family_index, family in enumerate(quality.FAMILIES):
        for index in range(2):
            path = tmp_path / f"{family_index}-{index}.png"
            Image.new("RGB", (40, 40), (family_index * 40 + index, 10, 20)).save(path)
            sources.append({"family": family, "source_path": str(path), "source_sha256": digest_file(path),
                            "source_size_bytes": path.stat().st_size, "dataset_id": "synthetic"})
        fields = [{"field_id": "total", "type": "integer", "description": "Total amount", "example_values": []}]
        if family_index:
            fields.append({"field_id": "item", "type": "array[object]", "group": "items", "description": "Item name", "example_values": []})
        path = tmp_path / f"{family}.schema.json"
        sha = write_new(path, {
            "contract_version": 1, "brief_id": "brief_" + "a" * 32, "revision": 2,
            "audit_event_id": "b" * 32, "state": "confirmed", "owner_user_id": "synthetic-evaluator",
            "job_id": "c" * 32, "intent": "Extract total and any item names", "payload_sha256": "f" * 64,
            "fields": fields, "sample_sources": [{"file_id": "d" * 32, "source_sha256": "e" * 64}],
        })
        schemas[family] = {"path": str(path), "sha256": sha}
    inventory = tmp_path / "inventory.json"
    baseline = tmp_path / "baseline.json"
    monkeypatch.setattr(quality, "INVENTORY_SHA256", write_new(inventory, {"sources": sources}))
    monkeypatch.setattr(quality, "BASELINE_SHA256", write_new(baseline, {"schemas": schemas}))
    monkeypatch.setattr(quality, "SCHEMA_SHA256", {family: row["sha256"] for family, row in schemas.items()})
    monkeypatch.setattr(quality.freeze_helpers, "code_receipt", lambda: {"commit": "synthetic"})
    runtime = {"ocr_config": {"python": str(Path(sys.executable).resolve()), "work_dir": str(scratch)}}
    monkeypatch.setattr(quality.freeze_helpers, "runtime_receipt", lambda: runtime)
    monkeypatch.setattr(quality, "ProcessPoolExecutor", InlinePool)
    monkeypatch.setenv("SYNTHETIC_KEY", "private-synthetic-key")
    output = tmp_path / "campaign"
    sha = quality.prepare(inventory, baseline, output, rapidocr_python=Path(sys.executable), scratch=scratch)
    return SimpleNamespace(output=output, sha=sha, sources=sources, schemas=schemas,
                           inventory=inventory, baseline=baseline, scratch=scratch, runtime=runtime)


def install_mocks(monkeypatch, frozen, *, first_reply=None):
    from idpo.product_auto import workflow
    calls, ocr_inputs = [], []

    class Ocr:
        def run(self, payload, _context):
            document = payload["document"]
            ocr_inputs.append(document.path)
            document.pages = [replace(page, text="Widget Total: 42", metadata={**page.metadata,
                              "ocr_engine_used": "rapidocr", "ocr_confidence": 1.0}) for page in document.pages]
            return SimpleNamespace(artifacts={"document": document, "signal": None})

    class Provider:
        def __init__(self, **kwargs):
            assert kwargs["max_tokens"] == 8192 and kwargs["timeout_s"] == 180
            self.model, self.max_tokens = "innobot-luna-6", 8192
            self.client = SimpleNamespace(max_retries=0, close=lambda: None)

        def respond(self, kind, response_format):
            begun = [(arm, row) for arm in quality.ARMS for row in Ledger(frozen.output / "arms" / arm / "ledger.sqlite3").snapshot()["attempts"]
                     if row["state"] == "request_begun"]
            assert len(begun) == 1
            calls.append((begun[0][0], kind))
            if first_reply is not None and len(calls) == 1:
                if isinstance(first_reply, BaseException):
                    raise first_reply
                return first_reply
            fields = response_format["json_schema"]["schema"]["properties"]["values"]["items"]["properties"]["field_id"]["enum"]
            values = [{"field_id": "total", "value": 42, "page": 1, "quote": "42"}]
            if "item" in fields:
                values.append({"field_id": "item", "value": [{"row": 0, "value": "Widget", "page": 1, "quote": "Widget"}],
                               "page": None, "quote": None})
            return ModelReply(json.dumps({"values": values}), 2, prompt_tokens=10, completion_tokens=8,
                              finish_reason="stop", sdk_attempts=1)

        def complete_json(self, **kwargs):
            return self.respond("text", kwargs["response_format"])

        def complete_visual_json(self, request):
            body = request.validated_body(model=self.model, max_tokens=self.max_tokens)
            return self.respond("visual", body["response_format"])

    monkeypatch.setattr(workflow, "OcrAgent", Ocr)
    monkeypatch.setattr(gate, "OpenAICompatibleChat", Provider)
    return calls, ocr_inputs


def execute(frozen, **kwargs):
    return quality.run(frozen.output, frozen.sha, api_key_env="SYNTHETIC_KEY", **kwargs)


def test_freeze_exact_sources_schemas_caps_and_counterbalance(frozen):
    protocol = quality.verify_freeze(frozen.output, frozen.sha)
    assert len(protocol["sources"]) == 6 and len(protocol["schedule"]) == 12
    assert [row["family"] for row in [next(s for s in protocol["sources"] if s["doc_id"] == x["doc_id"])
                                      for x in protocol["schedule"][::2]]] == list(quality.FAMILIES) * 2
    assert [row["arm"] for row in protocol["schedule"][::2]] == ["text"] * 3 + ["candidate"] * 3
    assert sum(profile["max_calls"] for profile in protocol["profiles"].values()) == 1920
    for arm in quality.ARMS:
        assert Ledger(frozen.output / "arms" / arm / "ledger.sqlite3").snapshot()["attempts"] == []
        for family, item in frozen.schemas.items():
            assert (frozen.output / "arms" / arm / "schemas" / f"{family}.json").read_bytes() == Path(item["path"]).read_bytes()


def test_actual_product_two_paths_fresh_ocr_and_full_denominators(frozen, monkeypatch):
    calls, ocr = install_mocks(monkeypatch, frozen)
    result = execute(frozen)
    assert len(calls) == len(ocr) == 12
    assert calls.count(("candidate", "visual")) == 4
    assert calls.count(("candidate", "text")) == 2
    report = result["summary"]
    assert report["selected_source_arm_slots"] == 12 and report["request_begun_attempts"] == 12
    for arm in quality.ARMS:
        assert report["arms"][arm]["valid_full_coverage_originals"] == 6
        assert len((frozen.output / "arms" / arm / "candidates.jsonl").read_text().splitlines()) == 6
    seal = read_json(frozen.output / "prediction-seal.json")
    assert seal["labels_opened"] is False
    for path, sha in seal["files"].items():
        assert digest_file(frozen.output / path) == sha
    with pytest.raises(ValueError, match="permanently closed"):
        execute(frozen, resume=True)
    assert len(calls) == 12


def test_checkpoint_resume_calls_only_unstarted_slots(frozen, monkeypatch):
    calls, _ = install_mocks(monkeypatch, frozen)
    monkeypatch.setattr(quality, "BATCH_ORIGINALS", 1)
    # Re-freeze the synthetic plan to bind the small checkpoint width.
    protocol = read_json(frozen.output / "protocol.json")
    protocol["batch_originals"] = 1
    (frozen.output / "protocol.json").write_bytes(quality.encoded(protocol))
    frozen.sha = digest_file(frozen.output / "protocol.json")
    for arm in quality.ARMS:
        with Ledger(frozen.output / "arms" / arm / "ledger.sqlite3").transaction() as db:
            db.execute("UPDATE settings SET value=? WHERE key='protocol_sha256'", (frozen.sha,))
    first = execute(frozen, batches=1)
    assert first["request_begun_attempts"] == 2 and len(calls) == 2
    with pytest.raises(ValueError, match="already started"):
        execute(frozen)
    result = execute(frozen, resume=True)
    assert result["summary"]["request_begun_attempts"] == len(calls) == 12


@pytest.mark.parametrize("category", ["authentication", "rate_limit", "transport_timeout"])
def test_first_provider_failure_stops_both_and_ack_resumes_untouched(frozen, monkeypatch, category):
    failure = ModelReply("", 1, error="sanitized", error_category=category, sdk_attempts=1)
    calls, _ = install_mocks(monkeypatch, frozen, first_reply=failure)
    stopped = execute(frozen)
    assert len(calls) == 1 and stopped["selected_source_arm_slots"] == 12
    assert stopped["arms"]["candidate"]["source_states"] == {"unstarted": 6}
    execute(frozen, resume=True)
    assert len(calls) == 1
    result = execute(frozen, resume=True, acknowledge=stopped["stop_receipt_sha256"])
    assert len(calls) == 12 and result["summary"]["arms"]["text"]["valid_full_coverage_originals"] == 5
    if category == "transport_timeout":
        assert result["summary"]["arms"]["text"]["source_states"]["uncertain"] == 1


def test_crash_after_request_marker_never_replays_paid_slot(frozen, monkeypatch):
    calls, _ = install_mocks(monkeypatch, frozen, first_reply=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        execute(frozen)
    state = Ledger(frozen.output / "arms/text/ledger.sqlite3").snapshot()
    assert state["attempts"][0]["state"] == "request_begun"
    stopped = execute(frozen, resume=True)
    assert len(calls) == 1 and stopped["arms"]["text"]["uncertain_attempts"] == 1
    result = execute(frozen, resume=True, acknowledge=stopped["stop_receipt_sha256"])
    assert len(calls) == 12 and result["summary"]["arms"]["text"]["source_states"]["uncertain"] == 1


@pytest.mark.parametrize("change", ["source", "schema", "runtime", "code", "protocol", "sealed_reply"])
def test_integrity_change_prevents_any_next_call(frozen, monkeypatch, change):
    calls, _ = install_mocks(monkeypatch, frozen)
    if change == "source":
        Path(frozen.sources[0]["source_path"]).write_bytes(b"changed")
    elif change == "schema":
        (frozen.output / "arms/candidate/schemas/receipt.json").write_text("{}")
    elif change == "runtime":
        monkeypatch.setattr(quality.freeze_helpers, "runtime_receipt", dict)
    elif change == "code":
        monkeypatch.setattr(quality.freeze_helpers, "code_receipt", dict)
    elif change == "protocol":
        (frozen.output / "protocol.json").write_text("{}")
    else:
        # Pause at an auth failure with an existing sanitized reply.
        failure = ModelReply("", 1, error="http_401", error_category="authentication", sdk_attempts=1)
        calls, _ = install_mocks(monkeypatch, frozen, first_reply=failure)
        execute(frozen)
        next((frozen.output / "arms/text/replies").glob("*.json")).write_text("{}")
    before = len(calls)
    with pytest.raises((ValueError, KeyError)):
        execute(frozen, resume=True)
    assert len(calls) == before


def test_explicit_incomplete_seal_keeps_unattempted_denominators_and_closes_calls(frozen, monkeypatch):
    calls, _ = install_mocks(monkeypatch, frozen)
    with pytest.raises(ValueError, match="Unfinished slots"):
        quality.seal(frozen.output, frozen.sha)
    result = quality.seal(frozen.output, frozen.sha, include_unattempted=True)
    assert result["summary"]["request_begun_attempts"] == 0
    for arm in quality.ARMS:
        assert len((frozen.output / "arms" / arm / "candidates.jsonl").read_text().splitlines()) == 6
    with pytest.raises(ValueError, match="permanently closed"):
        execute(frozen, resume=True)
    assert calls == []


def test_invalid_reply_is_failure_not_global_provider_stop(frozen, monkeypatch):
    bad = ModelReply("not json", 1, prompt_tokens=5, completion_tokens=2, finish_reason="stop", sdk_attempts=1)
    calls, _ = install_mocks(monkeypatch, frozen, first_reply=bad)
    result = execute(frozen)
    assert len(calls) == 12 and result["summary"]["stop"] is None
    assert result["summary"]["arms"]["text"]["valid_full_coverage_originals"] == 5


def test_nonresumable_sdk_contract_violation_cannot_be_acknowledged(frozen, monkeypatch):
    bad = ModelReply("", 1, error="unknown", error_category="provider_other", sdk_attempts=None)
    calls, _ = install_mocks(monkeypatch, frozen, first_reply=bad)
    report = execute(frozen)
    assert not report["stop"]["resumable"]
    with pytest.raises(ValueError, match="resumable stop"):
        execute(frozen, resume=True, acknowledge=report["stop_receipt_sha256"])
    assert len(calls) == 1


def test_reply_saved_before_source_seal_remains_uncertain_without_paid_replay(frozen, monkeypatch):
    calls, _ = install_mocks(monkeypatch, frozen)
    original = Ledger.seal_source
    invoked = []

    def interrupted(self, *args, **kwargs):
        invoked.append(1)
        if len(invoked) == 1:
            raise KeyboardInterrupt()
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Ledger, "seal_source", interrupted)
    with pytest.raises(KeyboardInterrupt):
        execute(frozen)
    state = Ledger(frozen.output / "arms/text/ledger.sqlite3").snapshot()
    assert state["attempts"][0]["state"] == "replied" and state["sources"][0]["state"] == "started"
    stopped = execute(frozen, resume=True)
    assert len(calls) == 1 and stopped["arms"]["text"]["source_states"]["uncertain"] == 1
    result = execute(frozen, resume=True, acknowledge=stopped["stop_receipt_sha256"])
    assert len(calls) == 12 and result["summary"]["arms"]["text"]["valid_full_coverage_originals"] == 5
    candidate = json.loads((frozen.output / "arms/text/candidates.jsonl").read_text().splitlines()[0])
    assert candidate["document_status"] == "failed" and candidate["extracted_values"] == []
    assert list((frozen.output / "arms/text/outcomes").glob("*.json"))  # Original partial artifacts remain private.


@pytest.mark.parametrize("frozen", [{"arm_max_calls": 2}], indirect=True)
def test_durable_arm_caps_bound_total_calls_across_both_arms(frozen, monkeypatch):
    calls, _ = install_mocks(monkeypatch, frozen)
    report = execute(frozen)
    assert len(calls) == report["request_begun_attempts"] == report["global_max_calls"] == 4
    assert report["stop"] and not report["stop"]["resumable"]
    assert report["selected_source_arm_slots"] == 12
    for arm in quality.ARMS:
        snapshot = Ledger(frozen.output / "arms" / arm / "ledger.sqlite3").snapshot()
        assert len(snapshot["attempts"]) == int(snapshot["settings"]["max_calls"]) == 2
    execute(frozen, resume=True)
    assert len(calls) == 4
