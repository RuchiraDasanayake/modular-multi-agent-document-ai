"""An explicitly selected recipe skips schema induction and remains review-only."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from idpo.product_auto.approved_recipe import load_approved_recipe
from idpo.product_auto.provider import ModelReply
from idpo.product_auto.worker_server import validate_request
from idpo.product_auto.workflow import process_auto


def snapshot(tmp_path: Path, *, fields: list[dict] | None = None) -> tuple[Path, str]:
    payload = {
        "contract_version": 1,
        "recipe_id": "recipe_" + "a" * 32,
        "revision": 2,
        "audit_event_id": "b" * 32,
        "state": "approved_shadow",
        "owner_user_id": "alice-id",
        "family_name": "Invoice family",
        "source_review_digest_sha256": "c" * 64,
        "fields": fields or [{"field_id": "total", "type": "integer"}],
        "row_groups": [],
    }
    path = tmp_path / "approved.recipe.json"
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


def test_explicit_recipe_uses_one_value_call_and_stays_in_review(tmp_path: Path) -> None:
    recipe_path, digest = snapshot(tmp_path)
    recipe = load_approved_recipe(recipe_path, digest)
    source = tmp_path / "invoice.txt"
    source.write_text("Invoice\nTotal: 100", encoding="utf-8")
    model = OneReplyModel('{"values":[{"field_id":"total","value":100,"page":1,"quote":"100"}]}')

    run = process_auto(source, run_id="recipe-test", model=model, approved_recipe=recipe,
                       output_root=tmp_path / "runs")
    directory = Path(run["run_dir"])
    candidate = json.loads((directory / "candidates.jsonl").read_text())
    receipt = json.loads((directory / "manifest.jsonl").read_text())
    sidecar = json.loads((directory / "docs" / candidate["doc_id"] / "result.json").read_text())
    marker = json.loads((directory / "run.json").read_text())

    assert len(model.prompts) == 1
    assert '"fields": [{"field_id": "total", "type": "integer"}]' in model.prompts[0]
    assert candidate["proposed_schema"] == [{"field_id": "total", "type": "integer"}]
    assert candidate["document_status"] == "needs_review"
    assert candidate["extracted_values"][0]["review_state"] == "pending"
    assert candidate["extracted_values"][0]["status"] == "accepted"
    evidence = candidate["extracted_values"][0]["evidence"]
    assert sidecar["pages"][0]["text"][evidence["start"]:evidence["end"]] == evidence["quote"] == "100"
    assert sidecar["reason"] == "approved_recipe_requires_review"
    assert [call["phase"] for call in sidecar["model_calls"]] == ["values"]
    assert marker["model_call_count"] == 1
    assert marker["approved_recipe"] == receipt["approved_recipe"] == sidecar["approved_recipe"] == recipe.receipt


def test_recipe_value_mismatch_abstains_without_schema_fallback(tmp_path: Path) -> None:
    recipe_path, digest = snapshot(tmp_path)
    recipe = load_approved_recipe(recipe_path, digest)
    source = tmp_path / "other.txt"
    source.write_text("Some other document", encoding="utf-8")
    model = OneReplyModel('{"values":[{"field_id":"different","value":"x","page":1,"quote":"x"}]}')

    run = process_auto(source, run_id="recipe-mismatch", model=model, approved_recipe=recipe,
                       output_root=tmp_path / "runs")
    directory = Path(run["run_dir"])
    candidate = json.loads((directory / "candidates.jsonl").read_text())
    sidecar = json.loads((directory / "docs" / candidate["doc_id"] / "result.json").read_text())
    assert len(model.prompts) == 1
    assert candidate["proposed_schema"] == [{"field_id": "total", "type": "integer"}]
    assert candidate["extracted_values"] == [
        {"field_id": "total", "value": None, "status": "missing", "review_state": "pending"},
    ]
    assert candidate["document_status"] == "needs_review"
    assert sidecar["reason"] == "invalid_values_model_response"


def test_recipe_value_without_exact_source_evidence_requires_review(tmp_path: Path) -> None:
    recipe_path, digest = snapshot(tmp_path)
    recipe = load_approved_recipe(recipe_path, digest)
    source = tmp_path / "invoice.txt"
    source.write_text("Total: 100", encoding="utf-8")
    model = OneReplyModel('{"values":[{"field_id":"total","value":100,"page":1,"quote":"999"}]}')
    run = process_auto(source, run_id="ungrounded", model=model, approved_recipe=recipe,
                       output_root=tmp_path / "runs")
    directory = Path(run["run_dir"])
    candidate = json.loads((directory / "candidates.jsonl").read_text())
    sidecar = json.loads((directory / "docs" / candidate["doc_id"] / "result.json").read_text())
    assert candidate["extracted_values"][0]["status"] == "needs_review"
    assert "evidence" not in candidate["extracted_values"][0]
    assert candidate["document_status"] == "needs_review"
    assert sidecar["reason"] == "approved_recipe_no_grounded_values"


def test_snapshot_digest_state_and_schema_fail_closed(tmp_path: Path) -> None:
    path, _ = snapshot(tmp_path)
    with pytest.raises(ValueError, match="digest mismatch"):
        load_approved_recipe(path, "0" * 64)
    changed = json.loads(path.read_text())
    changed["state"] = "disabled"
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ValueError, match="identity"):
        load_approved_recipe(path, hashlib.sha256(path.read_bytes()).hexdigest())
    invalid_path, invalid_digest = snapshot(tmp_path, fields=[{"field_id": "bad-id", "type": "string"}])
    with pytest.raises(ValueError, match="field"):
        load_approved_recipe(invalid_path, invalid_digest)
    invalid_path, invalid_digest = snapshot(tmp_path, fields=[{"field_id": "_private", "type": "string"}])
    with pytest.raises(ValueError, match="field"):
        load_approved_recipe(invalid_path, invalid_digest)


def test_recipe_requires_model_before_output_is_created(tmp_path: Path) -> None:
    path, digest = snapshot(tmp_path)
    recipe = load_approved_recipe(path, digest)
    source = tmp_path / "invoice.txt"
    source.write_text("Total: 100", encoding="utf-8")
    with pytest.raises(ValueError, match="configured value extraction model"):
        process_auto(source, run_id="no-model", approved_recipe=recipe, output_root=tmp_path / "runs")
    assert not (tmp_path / "runs" / "no-model").exists()


def test_worker_only_accepts_a_recipe_snapshot_for_the_same_staged_run(tmp_path: Path) -> None:
    run_id = "auto_" + "d" * 32
    root = tmp_path / "frontend" / "auto_inputs"
    staged = root / run_id
    staged.mkdir(parents=True)
    (staged / "invoice.txt").write_text("Total: 100", encoding="utf-8")
    source, digest = snapshot(tmp_path)
    expected = root / f"{run_id}.recipe.json"
    expected.write_bytes(source.read_bytes())
    payload = {"run_id": run_id, "input_dir": str(staged), "model": "test", "api_base_url": "http://localhost/v1",
               "approved_recipe_file": str(expected), "approved_recipe_sha256": digest}
    assert validate_request(payload, root=tmp_path)[4].receipt["snapshot_sha256"] == digest
    with pytest.raises(ValueError, match="staging area"):
        validate_request({**payload, "approved_recipe_file": str(source)}, root=tmp_path)
    with pytest.raises(ValueError, match="digest mismatch"):
        validate_request({**payload, "approved_recipe_sha256": "0" * 64}, root=tmp_path)


def test_cli_carries_the_snapshot_without_calling_a_model_for_empty_text(tmp_path: Path) -> None:
    recipe_path, digest = snapshot(tmp_path)
    source = tmp_path / "empty.txt"
    source.write_text("", encoding="utf-8")
    env = {**os.environ, "IDPO_DATA_DIR": str(tmp_path / "data")}
    result = subprocess.run([
        sys.executable, "-m", "idpo.cli", "process-auto", "--input", str(source),
        "--run-id", "recipe-cli", "--model", "local-model", "--api-base-url", "http://127.0.0.1:1/v1",
        "--approved-recipe-file", str(recipe_path), "--approved-recipe-sha256", digest,
    ], capture_output=True, text=True, timeout=30, env=env, check=False)
    assert result.returncode == 0, result.stderr
    marker = json.loads((tmp_path / "data" / "product_runs" / "recipe-cli" / "run.json").read_text())
    assert marker["approved_recipe"]["snapshot_sha256"] == digest
    assert marker["model_call_count"] == 0
    rejected = subprocess.run([
        sys.executable, "-m", "idpo.cli", "process-auto", "--input", str(source),
        "--run-id", "rejected-cli", "--model", "local-model", "--api-base-url", "http://127.0.0.1:1/v1",
        "--approved-recipe-file", str(recipe_path), "--approved-recipe-sha256", "0" * 64,
    ], capture_output=True, text=True, timeout=30, env=env, check=False)
    assert rejected.returncode != 0
    assert not (tmp_path / "data" / "product_runs" / "rejected-cli").exists()
