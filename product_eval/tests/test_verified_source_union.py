"""Self-authored report fixtures only; no campaign, prediction or label access."""

import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from product_eval import verified_source_union as union


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, sort_keys=True).encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def row(doc_id, state="sealed", requests=1, valid=True, non_null=1):
    return {"doc_id": doc_id, "source_sha256": sha(doc_id), "family": "receipt", "state": state,
            "request_count": requests, "valid_strict_reply_attempts": requests if valid else 0,
            "valid_full_coverage": valid,
            "metrics": {"non_null_fields": non_null, "all_null": non_null == 0, "strict_parsed": valid}}


def op_counts(rows):
    return {"selected_originals": len(rows), "originals_with_request_begun": sum(x["request_count"] > 0 for x in rows),
            "valid_full_coverage_originals": sum(x["valid_full_coverage"] for x in rows),
            "valid_non_null_originals": sum(x["valid_full_coverage"] and x["metrics"]["non_null_fields"] > 0 for x in rows),
            "source_states": dict(union.Counter(x["state"] for x in rows)),
            "request_begun_attempts": sum(x["request_count"] for x in rows),
            "valid_strict_reply_attempts": sum(x["valid_strict_reply_attempts"] for x in rows),
            "known_sdk_attempts": 1, "attempts_with_unknown_sdk_count": 1,
            "uncertain_attempts": 1, "attempts_with_unknown_usage": 1}


@pytest.fixture
def evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(union, "EXPECTED_FAMILIES", {"operational": {"receipt": 3}, "quality_candidate": {"receipt": 4}})
    op_rows = [row("op1"), row("op2", "uncertain", valid=False, non_null=0),
               row("op3", requests=0, valid=False, non_null=0)]
    q_rows = [row("q1"), row("q2", non_null=0), row("q3", "uncertain", valid=False, non_null=0),
              row("q4", "unstarted", requests=0, valid=False, non_null=0)]
    schema = sha("schema")
    op_profile = {**union.INFERENCE_PROFILE, "workers": 4, "max_calls": 2500, "batch_size": 25}
    candidate_profile = {**union.INFERENCE_PROFILE, "workers": 1, "max_calls": 960, "batch_size": 25}
    op_protocol = {"mode": "model2000_original_operational", "sources": op_rows, "profile": op_profile}
    protocol = {"mode": "paired_quality240", "labels_opened": False, "sources": q_rows,
                "profiles": {"candidate": candidate_profile, "text": {**candidate_profile, "visual_document_profile": "disabled"}},
                "schemas": {"receipt": {"sha256": schema}}}
    counts = op_counts(op_rows)
    op = {"version": 1, "kind": "final_operational_verification", "status": "verified",
          "accuracy_measured": False, "human_release_measured": False, "profile": op_profile,
          "documents": op_rows, "counts": counts, "families": {"receipt": copy.deepcopy(counts)},
          "final_seal_sha256": sha("operational-seal"), "verified_artifact_hashes": {"schemas/receipt.json": schema}}
    pairs = []
    for item in q_rows:
        operational = {"state": item["state"], "request_kinds": ["text"] * item["request_count"],
                       "valid_strict_replies": item["valid_strict_reply_attempts"], "eligible_prediction": item["valid_full_coverage"],
                       "valid_full_coverage": item["valid_full_coverage"], "source_coverage": item["valid_full_coverage"], **item["metrics"]}
        pairs.append({"doc_id": item["doc_id"], "family": "receipt", "candidate": {"doc_id": item["doc_id"], "operational": operational},
                      "text": {"operational": {"valid_full_coverage": True, "non_null_fields": 24, "request_kinds": ["text"] * 4}}})
    usage = {"source_states": {"sealed": 2, "uncertain": 1, "unstarted": 1}, "originals_with_attempts": 3,
             "request_begun_attempts": 3, "valid_strict_replies": 2, "known_sdk_attempts": 2,
             "attempts_with_unknown_sdk_attempts": 1, "uncertain_attempts": 1,
             "attempts_with_unknown_prompt_tokens": 1, "attempts_with_unknown_completion_tokens": 1}
    quality = {"all_sources_retained": True, "human_release_measured": False, "whole_document_visual_truth_established": False,
               "paired_sources": pairs, "families": {"candidate": {"receipt": {"documents": 4, "operational_usage": usage}}}}
    fixture = SimpleNamespace(op=op, quality=quality, op_protocol=op_protocol, protocol=protocol,
                              op_dir=tmp_path / "op-report", q_dir=tmp_path / "q-report",
                              op_run=tmp_path / "op-run", q_run=tmp_path / "q-run")
    freeze(fixture)
    return fixture


def freeze(item):
    item.op["protocol_sha256"] = write(item.op_run / "protocol.json", item.op_protocol)
    protocol_sha = write(item.q_run / "protocol.json", item.protocol)
    seal_sha = write(item.q_run / "prediction-seal.json", {"all_slots_accounted": True, "labels_opened": False,
                     "files": {"protocol.json": protocol_sha, "seal-started.json": sha("permanent close")}})
    receipt = {"prediction_seal_sha256": seal_sha, "protocol_sha256": protocol_sha, "verified_originals": 4,
               "source_family_counts": {"receipt": 4}, "verified_request_attempts": 7,
               "labels_opened_before_verification": False}
    verified_sha = write(item.q_dir / "verified-before-labels.json", receipt)
    item.q_result_sha = write(item.q_dir / "quality-results.json", item.quality)
    item.q_receipt_sha = write(item.q_dir / "scoring-receipt.json", {**receipt, "no_inference_or_ocr": True,
                              "no_reference_repairs": True, "files": {"quality-results.json": item.q_result_sha,
                               "verified-before-labels.json": verified_sha}})
    item.op_report_sha = write(item.op_dir / "verification.json", item.op)
    item.op_receipt_sha = write(item.op_dir / "receipt.json", {"version": 1, "verification_sha256": item.op_report_sha})


def assemble(item):
    return union.assemble(item.op_dir, item.op_receipt_sha, item.op_report_sha, item.q_dir,
                          item.q_receipt_sha, item.q_result_sha, item.op_run, item.q_run)


def test_distinct_stage_counts_preserve_failures_and_exclude_baseline(evidence, monkeypatch):
    allowed = {evidence.op_dir / name for name in ("receipt.json", "verification.json")}
    allowed |= {evidence.q_dir / name for name in ("scoring-receipt.json", "verified-before-labels.json", "quality-results.json")}
    allowed |= {evidence.op_run / "protocol.json", evidence.q_run / "protocol.json", evidence.q_run / "prediction-seal.json"}
    read_bytes = Path.read_bytes
    def restricted(path):
        assert path in allowed, "must not open predictions, sources, labels or a ledger"
        return read_bytes(path)
    monkeypatch.setattr(Path, "read_bytes", restricted)
    report = assemble(evidence)
    assert report["distinct_union"] == {"selected": 7, "request_begun": 5, "valid_full_coverage": 3, "non_null_full_coverage": 2}
    assert report["source_disjoint"] and not report["baseline_arm_counted"]
    assert report["studies"]["operational"]["sealed_pre_model_rejections"] == 1
    assert report["studies"]["quality_candidate"]["source_states"] == {"sealed": 2, "uncertain": 1, "unstarted": 1}
    assert report["studies"]["quality_candidate"]["valid_all_null_originals"] == 1
    assert report["studies"]["operational"]["attempt_accounting"]["attempts_with_unknown_sdk_count"] == 1
    assert not report["accuracy_measured"] and not report["human_release_measured"]
    assert all(value is False for value in report["at_least_2000"].values())
    assert report["execution_profiles"]["operational"]["workers"] == 4
    assert report["execution_profiles"]["quality_candidate"]["max_calls"] == 960


def test_shared_bytes_are_counted_once_without_combining_partial_results(evidence):
    evidence.protocol["sources"][0]["source_sha256"] = evidence.op["documents"][0]["source_sha256"]
    evidence.protocol["sources"][2]["source_sha256"] = evidence.op["documents"][1]["source_sha256"]
    freeze(evidence)
    report = assemble(evidence)
    assert not report["source_disjoint"]
    assert report["shared_originals"] == {"selected": 2, "request_begun": 2, "valid_full_coverage": 1, "non_null_full_coverage": 1}
    assert report["distinct_union"] == {"selected": 5, "request_begun": 3, "valid_full_coverage": 2, "non_null_full_coverage": 1}


@pytest.mark.parametrize("filename", ["receipt.json", "verification.json"])
def test_missing_or_changed_operational_report_refuses(evidence, filename):
    (evidence.op_dir / filename).write_text("{}")
    with pytest.raises(ValueError, match="SHA differs"):
        assemble(evidence)


@pytest.mark.parametrize("location", ["quality-results.json", "verified-before-labels.json", "scoring-receipt.json"])
def test_missing_quality_evidence_refuses(evidence, location):
    (evidence.q_dir / location).unlink()
    with pytest.raises(OSError):
        assemble(evidence)


def test_nonverified_operational_report_refuses(evidence):
    evidence.op["status"] = "incomplete"
    freeze(evidence)
    with pytest.raises(ValueError, match="Completed operational verification"):
        assemble(evidence)


@pytest.mark.parametrize("defect", ["unstarted", "counter", "inventory", "unknown_count", "false_strict"])
def test_operational_accounting_cannot_silently_change(evidence, defect):
    if defect == "unstarted":
        evidence.op["documents"][2]["state"] = "unstarted"
    elif defect == "counter":
        evidence.op["counts"]["selected_originals"] -= 1
    elif defect == "inventory":
        evidence.op_protocol["sources"] = copy.deepcopy(evidence.op_protocol["sources"])
        evidence.op_protocol["sources"][0]["source_sha256"] = sha("different original")
    elif defect == "unknown_count":
        evidence.op["counts"]["attempts_with_unknown_usage"] = 20
    else:
        evidence.op["documents"][0]["metrics"]["strict_parsed"] = "false"
    freeze(evidence)
    with pytest.raises(ValueError):
        assemble(evidence)


@pytest.mark.parametrize("defect", ["omitted", "duplicate", "started", "counter", "false_full", "profile", "schema"])
def test_inconsistent_or_incomplete_candidate_evidence_refuses(evidence, defect):
    if defect == "omitted":
        evidence.quality["paired_sources"].pop()
    elif defect == "duplicate":
        evidence.protocol["sources"][1]["source_sha256"] = evidence.protocol["sources"][0]["source_sha256"]
    elif defect == "started":
        evidence.quality["paired_sources"][0]["candidate"]["operational"]["state"] = "started"
    elif defect == "counter":
        evidence.quality["families"]["candidate"]["receipt"]["operational_usage"]["request_begun_attempts"] += 1
    elif defect == "false_full":
        evidence.quality["paired_sources"][2]["candidate"]["operational"].update(
            valid_full_coverage=True, eligible_prediction=True, source_coverage=True)
    elif defect == "profile":
        evidence.protocol["profiles"]["candidate"]["visual_document_profile"] = "disabled"
    elif defect == "schema":
        evidence.protocol["schemas"]["receipt"]["sha256"] = sha("changed schema")
    freeze(evidence)
    with pytest.raises(ValueError):
        assemble(evidence)


def test_baseline_success_cannot_rescue_candidate_failure(evidence):
    before = assemble(evidence)["distinct_union"]
    for pair in evidence.quality["paired_sources"]:
        pair["text"] = {"all_assessed_positive_targets_match": True, "arbitrary": "ignored baseline"}
    freeze(evidence)
    assert assemble(evidence)["distinct_union"] == before


def test_unclosed_seal_refuses_before_quality_result_access(evidence, monkeypatch):
    seal_path = evidence.q_run / "prediction-seal.json"
    seal = json.loads(seal_path.read_bytes())
    seal["all_slots_accounted"] = False
    new_sha = write(seal_path, seal)
    receipt_path = evidence.q_dir / "scoring-receipt.json"
    receipt = json.loads(receipt_path.read_bytes())
    receipt["prediction_seal_sha256"] = new_sha
    verified_path = evidence.q_dir / "verified-before-labels.json"
    verified = json.loads(verified_path.read_bytes())
    verified["prediction_seal_sha256"] = new_sha
    receipt["files"]["verified-before-labels.json"] = write(verified_path, verified)
    evidence.q_receipt_sha = write(receipt_path, receipt)
    original = Path.read_bytes
    def restricted(path):
        assert path.name != "quality-results.json", "incomplete seal must close result access"
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", restricted)
    with pytest.raises(ValueError, match="complete pinned seal"):
        assemble(evidence)


def test_cli_writes_external_receipt_without_source_values(evidence, monkeypatch, capsys, tmp_path):
    output = tmp_path / "union-report"
    args = ["union", "--operational-dir", str(evidence.op_dir), "--operational-run", str(evidence.op_run),
            "--operational-receipt-sha256", evidence.op_receipt_sha, "--operational-report-sha256", evidence.op_report_sha,
            "--quality-dir", str(evidence.q_dir), "--quality-run", str(evidence.q_run),
            "--quality-receipt-sha256", evidence.q_receipt_sha, "--quality-result-sha256", evidence.q_result_sha,
            "--output", str(output)]
    monkeypatch.setattr("sys.argv", args)
    assert union.main() == 0
    receipt = json.loads(capsys.readouterr().out)
    assert hashlib.sha256((output / "union.json").read_bytes()).hexdigest() == receipt["union_sha256"]
    assert str(tmp_path) not in (output / "union.json").read_text()
    assert "semantic correctness" in (output / "report.md").read_text()
    assert union.main() == 1
    assert json.loads(capsys.readouterr().out)["status"] == "refused"


def test_cli_refuses_output_under_a_campaign_before_reading_inputs(evidence, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["union", "--operational-dir", str(evidence.op_dir),
        "--operational-run", str(evidence.op_run), "--operational-receipt-sha256", evidence.op_receipt_sha,
        "--operational-report-sha256", evidence.op_report_sha, "--quality-dir", str(evidence.q_dir),
        "--quality-run", str(evidence.q_run), "--quality-receipt-sha256", evidence.q_receipt_sha,
        "--quality-result-sha256", evidence.q_result_sha, "--output", str(evidence.q_run / "forbidden-output")])
    monkeypatch.setattr(union, "assemble", lambda *args: pytest.fail("output containment must precede evidence access"))
    assert union.main() == 1
    assert not (evidence.q_run / "forbidden-output").exists()
    assert json.loads(capsys.readouterr().out)["status"] == "refused"
