"""Offline synthetic artifacts only: no live campaign, reference labels, OCR or API."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from idpo.product_auto.provider import ModelReply
from product_eval import final_gate_freeze as freeze
from product_eval import final_model_gate as gate
from product_eval import final_operational_verification as verifier
from product_eval.final_gate_ledger import Ledger
from product_eval.tests.test_final_model_gate import schema_file, source_file


@pytest.fixture
def campaign(tmp_path, monkeypatch, request):
    output = tmp_path / "campaign"
    output.mkdir()
    inputs = tmp_path / "originals"
    inputs.mkdir()
    rows = [source_file(inputs, 0, suffix=".txt", text="Total: 42"),
            source_file(inputs, 1, suffix=".exe", text="unsupported synthetic file"),
            source_file(inputs, 2, suffix=".txt", text="Total: 7")]
    (output / "schemas").mkdir()
    path, sha = schema_file(output / "schemas")
    path.rename(output / "schemas/receipt.json")
    profile = {**freeze.DEFAULT_PROFILE, "visual_document_profile": "bounded_visual_selective_v2"}
    if getattr(request, "param", None) == "v2":
        profile.update(response_format_profile="strict_confirmed_values_v2", base_url=freeze.PROJECT_BASE_URL)
    protocol = {"version": 1, "mode": "model2000_original_operational", "labels_opened": False,
                "target_distinct_originals": 3, "sources": rows, "profile": profile,
                "schemas": {"receipt": {"path": "schemas/receipt.json", "sha256": sha}},
                "runtime": {"synthetic": True}, "code": {"commit": "a" * 40}}
    protocol_sha = freeze.write_new(output / "protocol.json", protocol)
    ledger = Ledger(output / "ledger.sqlite3")
    ledger.initialize(rows, protocol_sha, 2500)
    calls = []
    all_null = getattr(request, "param", None) == "all_null"

    class Provider:
        def __init__(self, **_):
            self.model, self.max_tokens = "innobot-luna-6", 8192
            self.client = SimpleNamespace(max_retries=0, close=lambda: None)

        def complete_json(self, **_):
            calls.append(1)
            if len(calls) == 1:
                value = {"field_id": "total", "value": None if all_null else 42,
                         "page": None if all_null else 1, "quote": None if all_null else "42"}
                values = ({"total": {key: item for key, item in value.items() if key != "field_id"}}
                          if profile["response_format_profile"] == "strict_confirmed_values_v2" else [value])
                return ModelReply(text=json.dumps({"values": values}),
                                  latency_ms=2, prompt_tokens=8, completion_tokens=4, finish_reason="stop", sdk_attempts=1)
            return ModelReply(text="", error="transport_timeout", error_category="transport_timeout",
                              latency_ms=5, sdk_attempts=1)

    monkeypatch.setattr(gate, "OpenAICompatibleChat", Provider)
    for row in rows:
        assert ledger.claim(row["doc_id"])
        gate._run_source(str(output), row, protocol, "NO_ACTUAL_CREDENTIAL")
    snapshot = ledger.snapshot()
    seal = {key: snapshot[key] for key in ("sources", "attempts", "controls")}
    seal["summary"] = gate.summary(output, protocol)
    (output / "seals").mkdir()
    seal_sha = freeze.write_new(output / "seals/1.json", seal)
    monkeypatch.setattr(verifier, "TARGET_SOURCES", 3)
    monkeypatch.setattr(verifier, "FAMILY_COUNTS", {"receipt": 3})
    monkeypatch.setattr(verifier, "_code_receipts", lambda _: {"synthetic": True})
    assert len(calls) == 2
    return SimpleNamespace(output=output, protocol_sha=protocol_sha, seal_sha=seal_sha, seal=seal, rows=rows)


def verify(campaign):
    return verifier.verify_completed(campaign.output, campaign.protocol_sha, "seals/1.json", campaign.seal_sha)


@pytest.mark.parametrize("campaign", ["v2"], indirect=True)
def test_v2_text_campaign_reparses_wire_and_preserves_uncertain_failures(campaign):
    report = verify(campaign)
    assert report["profile"]["response_format_profile"] == "strict_confirmed_values_v2"
    assert report["counts"]["valid_full_coverage_originals"] == 1
    assert report["counts"]["uncertain_attempts"] == 1
    assert not report["operational_gate_passed"]


def rewrite_seal(campaign):
    path = campaign.output / "seals/1.json"
    path.write_bytes(freeze.encoded(campaign.seal))
    campaign.seal_sha = freeze.digest_file(path)


def test_reconciles_real_workflow_fake_provider_and_preserves_failure_denominators(campaign, monkeypatch):
    def forbidden(*_, **__):
        pytest.fail("offline verification must not access SQLite or construct a provider")
    monkeypatch.setattr(Ledger, "snapshot", forbidden)
    monkeypatch.setattr(gate, "OpenAICompatibleChat", forbidden)
    before = {p.relative_to(campaign.output): freeze.digest_file(p) for p in campaign.output.rglob("*") if p.is_file()}
    report = verify(campaign)
    counts = report["counts"]
    assert counts["selected_originals"] == 3
    assert counts["originals_with_request_begun"] == counts["known_sdk_attempts"] == 2
    assert counts["valid_full_coverage_originals"] == counts["valid_non_null_originals"] == 1
    assert counts["sealed_pre_model_rejections"] == 1
    assert counts["source_states"] == {"sealed": 2, "uncertain": 1}
    assert counts["uncertain_attempts"] == counts["attempts_with_unknown_usage"] == 1
    assert counts["known_tokens"] == {"prompt_tokens": 8, "completion_tokens": 4}
    assert report["families"]["receipt"]["selected_originals"] == 3
    assert not report["operational_gate_passed"] and not report["human_release_measured"]
    assert not report["accuracy_measured"] and report["usd_cost"] is None
    assert before == {p.relative_to(campaign.output): freeze.digest_file(p) for p in campaign.output.rglob("*") if p.is_file()}
    external = campaign.output.parent / "report"
    verifier.write_report(external, report)
    assert "Accuracy, visual correctness" in (external / "report.md").read_text()
    assert "Total: 42" not in (external / "verification.json").read_text()
    assert str(campaign.rows[0]["source_path"]) not in (external / "verification.json").read_text()


@pytest.mark.parametrize("artifact", ["source", "outcome", "reply", "request", "result", "schema"])
@pytest.mark.parametrize("missing", [False, True])
def test_rejects_corrupt_or_missing_hash_chains(campaign, artifact, missing):
    doc_id = campaign.rows[0]["doc_id"]
    first = campaign.seal["attempts"][0]
    paths = {
        "source": Path(campaign.rows[0]["source_path"]),
        "outcome": campaign.output / f"outcomes/{doc_id}.json",
        "reply": campaign.output / "replies/000001.json",
        "request": campaign.output / f"requests/{doc_id}/{first['request_sha256']}.json",
        "result": campaign.output / f"product_runs/model2000_{doc_id}/docs/{doc_id}/result.json",
        "schema": campaign.output / "schemas/receipt.json",
    }
    if missing:
        paths[artifact].unlink()
    else:
        with paths[artifact].open("ab") as stream:
            stream.write(b"changed")
    with pytest.raises((ValueError, OSError)):
        verify(campaign)


@pytest.mark.parametrize("state", ["unstarted", "started"])
def test_incomplete_campaign_is_refused_before_any_prediction_or_source_access(campaign, monkeypatch, state):
    campaign.seal["sources"][0]["state"] = state
    rewrite_seal(campaign)
    original = verifier.digest_file
    def restricted(path):
        assert path.name in {"protocol.json", "1.json"}, "opened evidence before terminal gate"
        return original(path)
    monkeypatch.setattr(verifier, "digest_file", restricted)
    with pytest.raises(ValueError, match="not terminal"):
        verify(campaign)


def test_missing_final_seal_does_not_read_sources(campaign, monkeypatch):
    (campaign.output / "seals/1.json").unlink()
    monkeypatch.setattr(verifier, "_code_receipts", lambda _: pytest.fail("passed missing seal"))
    with pytest.raises((ValueError, OSError)):
        verify(campaign)


def test_summary_cannot_promote_an_uncertain_source(campaign):
    campaign.seal["summary"]["valid_full_coverage_originals"] = 2
    rewrite_seal(campaign)
    with pytest.raises(ValueError, match="summary differs"):
        verify(campaign)


@pytest.mark.parametrize("campaign", ["all_null"], indirect=True)
def test_valid_all_null_is_coverage_not_non_null_extraction(campaign):
    report = verify(campaign)
    assert report["counts"]["valid_full_coverage_originals"] == 1
    assert report["counts"]["valid_non_null_originals"] == 0
    assert report["counts"]["valid_all_null_originals"] == 1
    assert not report["accuracy_measured"] and not report["human_release_measured"]


def test_family_summary_cannot_hide_a_failed_original(campaign):
    campaign.seal["summary"]["families"]["receipt"]["selected_originals"] = 2
    rewrite_seal(campaign)
    with pytest.raises(ValueError, match="Family summary differs"):
        verify(campaign)


def test_unsealed_result_cannot_be_used_even_with_valid_internal_receipts(campaign):
    slot = campaign.seal["sources"][0]
    path = campaign.output / f"outcomes/{slot['doc_id']}.json"
    outcome = freeze.read_json(path)
    del outcome["output_files"][f"product_runs/model2000_{slot['doc_id']}/manifest.jsonl"]
    path.write_bytes(freeze.encoded(outcome))
    slot["receipt_sha256"] = freeze.digest_file(path)
    rewrite_seal(campaign)
    with pytest.raises(ValueError, match="Unsealed product result"):
        verify(campaign)


def test_reply_accounting_must_equal_snapshot(campaign):
    campaign.seal["attempts"][0]["prompt_tokens"] += 1
    rewrite_seal(campaign)
    with pytest.raises(ValueError, match="accounting differs"):
        verify(campaign)


def test_uncertain_without_reply_or_outcome_stays_in_denominator(campaign):
    attempt = campaign.seal["attempts"][-1]
    for key in ("reply_sha256", "prompt_tokens", "completion_tokens", "latency_ms", "finish_reason", "refusal", "error_category", "sdk_attempts"):
        attempt[key] = None
    slot = campaign.seal["sources"][-1]
    slot.update(receipt_sha256=None, reason="interrupted")
    # Independently reproduce what the original runner summary returns for an interrupted source.
    ledger = Ledger(campaign.output / "ledger.sqlite3")
    with ledger.transaction() as db:
        db.execute("UPDATE sources SET receipt_sha256=NULL, reason='interrupted' WHERE doc_id=?", (slot["doc_id"],))
        db.execute("UPDATE attempts SET reply_sha256=NULL, prompt_tokens=NULL, completion_tokens=NULL, latency_ms=NULL, "
                   "finish_reason=NULL, refusal=NULL, error_category=NULL, sdk_attempts=NULL WHERE attempt_id=?", (attempt["attempt_id"],))
    campaign.seal["summary"] = gate.summary(campaign.output, freeze.read_json(campaign.output / "protocol.json"))
    rewrite_seal(campaign)
    report = verify(campaign)
    assert report["counts"]["selected_originals"] == 3
    assert report["counts"]["known_sdk_attempts"] == 1
    assert report["counts"]["attempts_with_unknown_sdk_count"] == 1
    assert report["counts"]["outcome_receipt_originals"] == 2
    assert report["unreferenced_artifacts"]  # leftover reply/output cannot become success evidence


def test_cli_refuses_output_inside_campaign_without_overwriting(campaign, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["verify", "--run", str(campaign.output), "--protocol-sha256", campaign.protocol_sha,
                                    "--seal", "seals/1.json", "--seal-sha256", campaign.seal_sha,
                                    "--output", str(campaign.output / "new-report")])
    assert verifier.main() == 1
    assert not (campaign.output / "new-report").exists()
    assert json.loads(capsys.readouterr().out)["status"] == "refused"


def test_freeze_dependency_mutation_rejected_by_code_receipts(tmp_path, monkeypatch):
    name = "product_eval/final_gate_freeze.py"
    assert name in verifier.FROZEN_MODULES
    original = b"guard = True\n"
    path = tmp_path / name
    path.parent.mkdir()
    path.write_bytes(original)
    expected = freeze.digest_file(path)
    path.write_bytes(b"guard = False\n")
    monkeypatch.setattr(verifier, "ROOT", tmp_path)
    monkeypatch.setattr(verifier, "FROZEN_MODULES", (name,))
    monkeypatch.setattr(verifier.subprocess, "check_output", lambda *args, **kwargs: original)
    with pytest.raises(ValueError):
        verifier._code_receipts({"code": {"commit": "a" * 40, "python_source_sha256": {name: expected}}})
