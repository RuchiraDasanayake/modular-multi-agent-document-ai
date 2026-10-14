"""Synthetic post-score timing reports; never reads a real campaign or labels."""
from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/quality240_timing_usage.py"
spec = importlib.util.spec_from_file_location("quality_timing_test_target", SCRIPT)
timing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(timing)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return timing.digest(path)


@pytest.fixture
def metadata():
    families = ["registration-form"] * 100 + ["ad-buy-form"] * 100 + ["receipt"] * 40
    sources = [{"doc_id": f"{index:032x}", "family": family} for index, family in enumerate(families)]
    snapshots, documents, scored = {}, {}, {"all_sources_retained": True, "families": {}}
    for arm in timing.ARMS:
        slots = [{"doc_id": row["doc_id"], "state": "unstarted", "updated": 990.0} for row in sources]
        docs = [{**row, "state": "unstarted", "reason": "unstarted", "outcome": None} for row in sources]
        attempts = []
        if arm == "text":
            for index, state, duration, close in ((0, "sealed", 100.0, 1001.0), (1, "uncertain", None, 1010.0),
                                                  (2, "sealed", 50.0, 1003.0)):
                slots[index].update(state=state, updated=close)
                docs[index].update(state=state, reason="pre_model_failure" if index == 2 else state,
                                   outcome={"duration_ms": duration} if duration is not None else None)
            for index, state, latency, prompt, completion, category in (
                (0, "replied", 10.0, 5, 2, None), (1, "uncertain", 90.0, None, None, "provider_server")
            ):
                attempts.append({"attempt_id": index + 1, "doc_id": sources[index]["doc_id"], "state": state,
                                 "latency_ms": latency, "prompt_tokens": prompt, "completion_tokens": completion,
                                 "sdk_attempts": 1, "error_category": category})
        snapshots[arm] = {"sources": slots, "attempts": attempts}
        documents[arm] = docs
        scored["families"][arm] = {}
        for family in set(families):
            rows = [{"state": slot["state"], "reason": doc["reason"], "duration_ms": doc["outcome"]["duration_ms"] if doc["outcome"] else None,
                     "attempts": [attempt for attempt in attempts if attempt["doc_id"] == slot["doc_id"]]}
                    for slot, doc in zip(slots, docs, strict=True) if doc["family"] == family]
            usage = timing.summarize(rows)
            usage.update(known_latency_ms=usage["request_latency_ms"]["known_sum_ms"],
                         attempts_with_unknown_latency_ms=usage["request_latency_ms"]["missing_latency_requests"],
                         known_product_duration_ms=usage["source_execution_duration_ms"]["known_sum_ms"],
                         originals_without_duration=len(rows) - usage["source_execution_duration_ms"]["measured_count"])
            scored["families"][arm][family] = {"documents": len(rows), "operational_usage": usage}
    return {"protocol": {"sources": sources}, "snapshots": snapshots, "documents": documents,
            "events": [{"event": "start", "time_ns": 1_000_000_000_000},
                       {"event": "stop", "time_ns": 1_002_000_000_000},
                       {"event": "acknowledge_stop", "time_ns": 1_009_000_000_000}], "scored": scored}


def test_failed_requests_missing_durations_and_full_source_denominators(metadata):
    result = timing.assemble(**metadata)
    report = result["arms"]["text"]["overall"]
    assert report["selected_sources"] == 240
    assert report["started_sources"] == 3 and report["originals_with_attempts"] == 2
    assert report["source_states"] == {"sealed": 2, "uncertain": 1, "unstarted": 237}
    assert report["source_reason_counts"]["pre_model_failure"] == 1
    assert report["request_latency_ms"] == {"measured_count": 2, "known_sum_ms": 100.0, "p50_ms": 50.0,
        "p95_ms": 86.0, "attempted_requests": 2, "missing_latency_requests": 0,
        "measured_attempt_states": {"replied": 1, "uncertain": 1}}
    assert report["source_execution_duration_ms"]["p50_ms"] == 75.0
    assert report["source_execution_duration_ms"]["p95_ms"] == 97.5
    assert report["source_execution_duration_ms"]["missing_duration_started_sources"] == 1
    assert report["model_attempted_source_duration_ms"]["measured_count"] == 1
    assert report["model_attempted_source_duration_ms"]["missing_duration_model_attempted_sources"] == 1
    assert report["known_prompt_tokens"] == 5 and report["known_completion_tokens"] == 2
    assert report["attempts_with_any_unknown_tokens"] == 1 and report["usd_cost"] is None
    empty = result["arms"]["candidate"]["overall"]
    assert empty["selected_sources"] == 240 and empty["request_latency_ms"]["p50_ms"] is None
    assert empty["source_execution_duration_ms"]["measured_count"] == 0
    assert result["overall_source_arm_slots"]["selected_sources"] == 480
    span = result["campaign_execution_span"]
    assert span["elapsed_ms"] == 10000.0 and span["started_source_arm_slots"] == 3
    assert span["includes_provider_and_operator_pauses"] is True
    assert span["excludes_sealing_and_analysis"] is True and span["process_active_campaign_duration_ms"] is None
    json.dumps(result, allow_nan=False)


def test_missing_failed_request_latency_does_not_become_zero(metadata):
    metadata["snapshots"]["text"]["attempts"][1]["latency_ms"] = None
    usage = metadata["scored"]["families"]["text"]["registration-form"]["operational_usage"]
    usage.update(known_latency_ms=10.0, attempts_with_unknown_latency_ms=1)
    report = timing.assemble(**metadata)["arms"]["text"]["overall"]["request_latency_ms"]
    assert report["measured_count"] == 1 and report["missing_latency_requests"] == 1
    assert report["p50_ms"] == report["p95_ms"] == 10.0


@pytest.mark.parametrize("values", [[-1], [float("nan")], [float("inf")], [True], ["2"]])
def test_invalid_timing_cannot_enter_report(values):
    with pytest.raises(ValueError, match="Invalid timing"):
        timing.distribution(values)


@pytest.fixture
def receipts(tmp_path, metadata, monkeypatch):
    run, scored_root = tmp_path / "run", tmp_path / "scored"
    pins = {}
    pins["protocol.json"] = write(run / "protocol.json", metadata["protocol"])
    pins["analysis-plan.json"] = write(run / "analysis-plan.json", {"status": "synthetic"})
    pins["analysis-preregistration.json"] = write(run / "analysis-preregistration.json", {"synthetic": True})
    pins["seal-started.json"] = write(run / "seal-started.json", {"include_unattempted": True})
    for name, value in (("PROTOCOL_SHA256", pins["protocol.json"]), ("PLAN_SHA256", pins["analysis-plan.json"]),
                        ("PREREGISTRATION_SHA256", pins["analysis-preregistration.json"])):
        monkeypatch.setattr(timing, name, value)
    for arm in timing.ARMS:
        for filename, value in (("ledger-snapshot.json", metadata["snapshots"][arm]),
                                ("documents.json", metadata["documents"][arm])):
            relative = f"arms/{arm}/{filename}"
            pins[relative] = write(run / relative, value)
    for index, value in enumerate(metadata["events"], 1):
        relative = f"controls/{index:06d}.json"
        pins[relative] = write(run / relative, value)
    seal_sha = write(run / "prediction-seal.json", {"files": pins, "all_slots_accounted": True, "labels_opened": False})
    verified = {"prediction_seal_sha256": seal_sha, "protocol_sha256": pins["protocol.json"],
                "analysis_plan_sha256": pins["analysis-plan.json"], "preregistration_sha256": pins["analysis-preregistration.json"],
                "labels_opened_before_verification": False}
    independent = {"version": 1, "type": "quality240_independent_prediction_verification", "labels_opened": False,
                   "context": {"prediction_seal_sha256": seal_sha}, "verification": verified}
    independent_path = tmp_path / "independent.json"
    verification_sha = write(independent_path, independent)
    files = {"verified-before-labels.json": write(scored_root / "verified-before-labels.json", verified),
             "quality-results.json": write(scored_root / "quality-results.json", metadata["scored"])}
    scoring = {**verified, "files": files, "no_inference_or_ocr": True, "no_reference_repairs": True}
    scoring_sha = write(scored_root / "scoring-receipt.json", scoring)
    return {"run": run, "seal_sha": seal_sha, "verification_receipt": independent_path,
            "verification_sha": verification_sha, "scored_output": scored_root, "scoring_sha": scoring_sha,
            "output": tmp_path / "report.json"}


def test_report_requires_pinned_full_verification_and_scores_without_labels(receipts):
    result = timing.run_report(**receipts)
    assert result["reference_files_opened_by_helper"] is False and result["model_calls"] == 0
    report = json.loads(receipts["output"].read_text())
    assert report["inputs_sha256"]["prediction_seal"] == receipts["seal_sha"]
    assert report["inputs_sha256"]["helper"] == timing.digest(SCRIPT)
    assert report["arms"]["text"]["overall"]["selected_sources"] == 240
    with pytest.raises(ValueError, match="New external output"):
        timing.run_report(**receipts)


@pytest.mark.parametrize("damage", ["seal", "verification", "scoring", "result", "snapshot", "document", "event"])
def test_tampering_fails_before_report_output(receipts, damage):
    paths = {"seal": receipts["run"] / "prediction-seal.json", "verification": receipts["verification_receipt"],
             "scoring": receipts["scored_output"] / "scoring-receipt.json", "result": receipts["scored_output"] / "quality-results.json",
             "snapshot": receipts["run"] / "arms/text/ledger-snapshot.json", "document": receipts["run"] / "arms/text/documents.json",
             "event": receipts["run"] / "controls/000001.json"}
    with paths[damage].open("ab") as handle:
        handle.write(b" ")
    with pytest.raises(ValueError, match="hash differs"):
        timing.run_report(**receipts)
    assert not receipts["output"].exists()


def test_receipt_for_another_campaign_cannot_be_rebound(receipts):
    independent = json.loads(receipts["verification_receipt"].read_text())
    independent["verification"]["prediction_seal_sha256"] = "0" * 64
    receipts["verification_sha"] = write(receipts["verification_receipt"], independent)
    with pytest.raises(ValueError, match="registration differs"):
        timing.run_report(**receipts)
    assert not receipts["output"].exists()


def test_usage_must_match_already_scored_accounting(metadata):
    changed = deepcopy(metadata)
    changed["scored"]["families"]["text"]["registration-form"]["operational_usage"]["known_prompt_tokens"] += 1
    with pytest.raises(ValueError, match="usage accounting differs"):
        timing.assemble(**changed)


def test_timing_must_match_already_scored_accounting(metadata):
    metadata["scored"]["families"]["text"]["registration-form"]["operational_usage"]["known_latency_ms"] += 1
    with pytest.raises(ValueError, match="timing accounting differs"):
        timing.assemble(**metadata)


def test_extra_unsealed_campaign_file_is_rejected(receipts):
    write(receipts["run"] / "unexpected.json", {})
    with pytest.raises(ValueError, match="Unsealed or missing"):
        timing.run_report(**receipts)


@pytest.mark.parametrize("damage", ["dropped", "unclosed", "unstarted_work", "missing_start"])
def test_invalid_denominators_and_missing_campaign_clock_rejected(metadata, damage):
    if damage == "dropped":
        metadata["snapshots"]["text"]["sources"].pop()
    elif damage == "unclosed":
        metadata["snapshots"]["text"]["sources"][0]["state"] = "started"
    elif damage == "unstarted_work":
        metadata["snapshots"]["text"]["sources"][0]["state"] = "unstarted"
        metadata["documents"]["text"][0]["state"] = "unstarted"
    else:
        metadata["events"] = []
    with pytest.raises(ValueError):
        timing.assemble(**metadata)
