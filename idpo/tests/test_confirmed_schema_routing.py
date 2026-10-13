"""A user-confirmed schema is pinned, source-grounded, and never rediscovered."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from idpo.product_auto.confirmed_schema import load_confirmed_schema
from idpo.product_auto.provider import ModelReply
from idpo.product_auto.workflow import process_auto


def snapshot(tmp_path: Path, *, fields: list[dict] | None = None) -> tuple[Path, str]:
    payload = {
        "contract_version": 1,
        "brief_id": "brief_" + "a" * 32,
        "revision": 2,
        "audit_event_id": "b" * 32,
        "state": "confirmed",
        "owner_user_id": "alice-id",
        "job_id": "c" * 32,
        "intent": "Extract the final payable amount, not a line subtotal",
        "fields": fields or [{"field_id": "total", "type": "integer", "description": "Final amount due",
                              "example_values": ["100"]}],
        "sample_sources": [{"file_id": "d" * 32, "source_sha256": "e" * 64}],
        "payload_sha256": "f" * 64,
    }
    path = tmp_path / "confirmed.schema.json"
    raw = json.dumps(payload, separators=(",", ":")).encode()
    path.write_bytes(raw)
    return path, hashlib.sha256(raw).hexdigest()


class OneReplyModel:
    model = "test-model"

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.prompts: list[str] = []

    def complete_json(self, *, system: str, prompt: str) -> ModelReply:
        self.prompts.append(prompt)
        return ModelReply(text=self.reply, latency_ms=1, finish_reason="stop", sdk_attempts=1)


def test_confirmed_schema_uses_only_value_call_and_source_receipts(tmp_path: Path) -> None:
    schema_path, digest = snapshot(tmp_path)
    schema = load_confirmed_schema(schema_path, digest)
    source = tmp_path / "invoice.txt"
    source.write_text("Invoice\nTotal: 100", encoding="utf-8")
    model = OneReplyModel('{"values":[{"field_id":"total","value":100,"page":1,"quote":"100"}]}')

    run = process_auto(source, run_id="confirmed-test", model=model, confirmed_schema=schema,
                       output_root=tmp_path / "runs")
    directory = Path(run["run_dir"])
    candidate = json.loads((directory / "candidates.jsonl").read_text())
    receipt = json.loads((directory / "manifest.jsonl").read_text())
    sidecar = json.loads((directory / "docs" / candidate["doc_id"] / "result.json").read_text())
    marker = json.loads((directory / "run.json").read_text())

    assert len(model.prompts) == 1
    assert "Final amount due" in model.prompts[0]
    assert "Extract the final payable amount" in model.prompts[0]
    assert '"example_values": ["100"]' in model.prompts[0]
    assert candidate["proposed_schema"] == [{"field_id": "total", "type": "integer"}]
    assert candidate["document_status"] == "needs_review"
    assert candidate["extracted_values"][0]["status"] == "accepted"
    assert candidate["extracted_values"][0]["review_state"] == "pending"
    evidence = candidate["extracted_values"][0]["evidence"]
    assert sidecar["pages"][0]["text"][evidence["start"]:evidence["end"]] == evidence["quote"] == "100"
    assert sidecar["reason"] == "confirmed_schema_requires_review"
    assert [call["phase"] for call in sidecar["model_calls"]] == ["values"]
    assert marker["model_call_count"] == 1
    assert marker["confirmed_schema"] == receipt["confirmed_schema"] == sidecar["confirmed_schema"] == schema.receipt
    assert marker["approved_recipe"] is None


def test_schema_mismatch_or_unquoted_value_stays_review_only(tmp_path: Path) -> None:
    schema_path, digest = snapshot(tmp_path)
    schema = load_confirmed_schema(schema_path, digest)
    source = tmp_path / "invoice.txt"
    source.write_text("Total: 100", encoding="utf-8")
    for run_id, reply in [
        ("wrong-field", '{"values":[{"field_id":"other","value":100,"page":1,"quote":"100"}]}'),
        ("wrong-quote", '{"values":[{"field_id":"total","value":100,"page":1,"quote":"999"}]}'),
    ]:
        run = process_auto(source, run_id=run_id, model=OneReplyModel(reply), confirmed_schema=schema,
                           output_root=tmp_path / "runs")
        candidate = json.loads((Path(run["run_dir"]) / "candidates.jsonl").read_text())
        assert candidate["document_status"] == "needs_review"
        assert candidate["extracted_values"][0]["status"] != "accepted"


def test_snapshot_tamper_and_invalid_fields_fail_before_model(tmp_path: Path) -> None:
    path, digest = snapshot(tmp_path)
    with pytest.raises(ValueError, match="digest mismatch"):
        load_confirmed_schema(path, "0" * 64)
    altered = json.loads(path.read_text())
    altered["state"] = "draft"
    path.write_text(json.dumps(altered))
    with pytest.raises(ValueError, match="identity"):
        load_confirmed_schema(path, hashlib.sha256(path.read_bytes()).hexdigest())
    bad, bad_digest = snapshot(tmp_path, fields=[{"field_id": "bad-id", "type": "string",
                                                 "description": "x", "example_values": []}])
    with pytest.raises(ValueError, match="field"):
        load_confirmed_schema(bad, bad_digest)
    bad, bad_digest = snapshot(tmp_path, fields=[{"field_id": "amount", "type": "decimal",
                                                 "description": "", "example_values": []}])
    with pytest.raises(ValueError, match="field"):
        load_confirmed_schema(bad, bad_digest)
    path, digest = snapshot(tmp_path)
    schema = load_confirmed_schema(path, digest)
    source = tmp_path / "invoice.txt"
    source.write_text("Total: 100", encoding="utf-8")
    with pytest.raises(ValueError, match="configured value extraction model"):
        process_auto(source, run_id="no-model", confirmed_schema=schema, output_root=tmp_path / "runs")
    assert not (tmp_path / "runs" / "no-model").exists()


def test_full_bounded_unicode_brief_fits_worker_snapshot_limit(tmp_path: Path) -> None:
    fields = [{"field_id": f"field_{index}", "type": "string", "description": "界" * 1000,
               "example_values": ["界" * 200] * 3} for index in range(24)]
    path, digest = snapshot(tmp_path, fields=fields)
    assert path.stat().st_size > 64 * 1024
    assert len(load_confirmed_schema(path, digest).fields) == 24


def test_cli_carries_confirmed_schema_without_contacting_model_for_empty_source(tmp_path: Path) -> None:
    schema_path, digest = snapshot(tmp_path)
    source = tmp_path / "empty.txt"
    source.write_text("", encoding="utf-8")
    env = {**os.environ, "IDPO_DATA_DIR": str(tmp_path / "data")}
    command = [sys.executable, "-m", "idpo.cli", "process-auto", "--input", str(source),
               "--model", "local-model", "--api-base-url", "http://127.0.0.1:1/v1",
               "--confirmed-schema-file", str(schema_path), "--confirmed-schema-sha256", digest]
    result = subprocess.run(command + ["--run-id", "confirmed-cli"], capture_output=True, text=True,
                            timeout=30, env=env, check=False)
    assert result.returncode == 0, result.stderr
    marker = json.loads((tmp_path / "data" / "product_runs" / "confirmed-cli" / "run.json").read_text())
    assert marker["confirmed_schema"]["snapshot_sha256"] == digest
    assert marker["model_call_count"] == 0
    rejected = subprocess.run(command[:-1] + ["0" * 64, "--run-id", "rejected-cli"],
                              capture_output=True, text=True, timeout=30, env=env, check=False)
    assert rejected.returncode != 0
    assert not (tmp_path / "data" / "product_runs" / "rejected-cli").exists()
