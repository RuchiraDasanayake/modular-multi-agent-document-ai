"""Authored synthetic labels only; no research corpus or provider access."""
import copy
import json

import pytest

from product_eval import operational_recall as scoring
from product_eval.final_gate_freeze import digest_file
from product_eval.tests.test_scoped_assessment import _linked


def scalar_records():
    gold, predictions = {}, {}
    for key in ("good", "failed", "uncertain"):
        gold[key] = {"contract_version": 1, "doc_id": key, "pages": [],
                     "gold_schema": [{"field_id": "total", "type": "string", "critical": False}],
                     "gold_values": [{"field_id": "total", "value": "42"}]}
        predictions[key] = {"contract_version": 1, "doc_id": key, "document_status": "needs_review",
                            "proposed_schema": [{"field_id": "total", "type": "string"}],
                            "extracted_values": [{"field_id": "total", "value": "42",
                                                  "status": "needs_review", "review_state": "pending"}]}
    return gold, predictions


def test_failed_and_uncertain_correct_looking_values_never_earn_credit():
    gold, predictions = scalar_records()
    sources = {key: {"family": "receipt"} for key in gold}
    result = scoring.score_records(sources, gold, predictions, {}, {"good"})
    family = result["families"]["receipt"]
    assert family["positive_scalar_targets"] == {"matched": 1, "reference": 3, "recall": 1 / 3}
    assert family["documents"] == 3 and family["eligible_documents"] == 1
    assert result["precision"] is result["f1"] is None
    assert result["scalar_equal_family_macro_recall"] is None  # Missing families cannot be silently dropped.


def test_positive_rows_keep_duplicate_multiplicity_and_do_not_require_extra_cells():
    gold, predictions, _ = _linked([{"name": "A"}, {"name": "A"}],
                                   [{"name": "A", "price": "99"}], scope="positive_only")
    report = scoring.score_records({"doc": {"family": "receipt"}}, gold, predictions, {}, {"doc"})
    assert report["families"]["receipt"]["annotated_rows"] == {"matched": 1, "reference": 2, "recall": .5}
    failed = scoring.score_records({"doc": {"family": "receipt"}}, gold, predictions, {}, set())
    assert failed["families"]["receipt"]["annotated_rows"]["matched"] == 0


def test_reference_missing_any_original_is_an_error():
    gold, predictions = scalar_records()
    with pytest.raises(ValueError, match="Every selected"):
        scoring.score_records({key: {"family": "receipt"} for key in gold},
                              {"good": gold["good"]}, predictions, {}, {"good"})


def test_plan_hashes_code_and_inventory_without_opening_references(tmp_path):
    cohort = tmp_path / "cohort.jsonl"
    cohort.write_text('{"doc_id":"synthetic"}\n')
    plan = scoring.make_plan(cohort)
    scoring.validate_plan(plan, digest_file(cohort))
    assert plan["labels_opened"] is False
    changed = copy.deepcopy(plan)
    changed["failure_policy"] = "Drop failures"
    with pytest.raises(ValueError, match="Preregistered"):
        scoring.validate_plan(changed, digest_file(cohort))
    with pytest.raises(ValueError, match="Preregistered"):
        scoring.validate_plan(plan, "0" * 64)


def test_labels_are_never_opened_if_final_seal_verification_fails(tmp_path, monkeypatch):
    run = tmp_path / "run"
    run.mkdir()
    cohort = tmp_path / "cohort.jsonl"
    cohort.write_text("[]")
    (run / "protocol.json").write_text(json.dumps({"analysis_plan": scoring.make_plan(cohort),
                                                 "cohort_sha256": digest_file(cohort)}))
    def reject(*_):
        raise ValueError("bad seal")
    monkeypatch.setattr(scoring, "verify_completed", reject)
    monkeypatch.setattr(scoring, "load_references", lambda *_: pytest.fail("labels opened before verification"))
    with pytest.raises(ValueError, match="bad seal"):
        scoring.run_analysis(run, digest_file(run / "protocol.json"), "seals/1.json", "b" * 64,
                             tmp_path / "results", tmp_path / "vrdu", tmp_path / "cord.jsonl")
    assert not (tmp_path / "results").exists()


def test_verified_receipt_is_durable_before_reference_loader_and_failures_remain(tmp_path, monkeypatch):
    gold, predictions = scalar_records()
    run = tmp_path / "run"
    run.mkdir()
    cohort = tmp_path / "cohort.jsonl"
    cohort.write_text("[]")
    sources = [{"doc_id": key, "source_sha256": "c" * 64, "family": "receipt"} for key in gold]
    (run / "protocol.json").write_text(json.dumps({"analysis_plan": scoring.make_plan(cohort),
        "cohort_sha256": digest_file(cohort), "sources": sources}))
    relative = "product_runs/model2000_good/docs/good/result.json"
    path = run / relative
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"candidate": predictions["good"], "pages": []}))
    verified = {"documents": [dict(row, valid_full_coverage=row["doc_id"] == "good") for row in sources],
                "verified_artifact_hashes": {relative: digest_file(path),
                                             "protocol.json": digest_file(run / "protocol.json")}}
    monkeypatch.setattr(scoring, "verify_completed", lambda *_: verified)
    monkeypatch.setattr(scoring, "verify_reference_bytes", lambda *_: None)  # Authored in-memory references only.
    def references(sources, vrdu, cord, output):
        assert json.loads((output / "verified-before-labels.json").read_text()) == verified
        return gold, {"synthetic": True}
    monkeypatch.setattr(scoring, "load_references", references)
    output = tmp_path / "results"
    scoring.run_analysis(run, digest_file(run / "protocol.json"), "seals/1.json", "b" * 64, output,
                         tmp_path / "vrdu", tmp_path / "cord.jsonl")
    result = json.loads((output / "positive-recall.json").read_text())
    assert result["selected_originals"] == 3
    assert result["families"]["receipt"]["positive_scalar_targets"]["reference"] == 3


def test_changed_reference_bytes_are_rejected(tmp_path):
    cord = tmp_path / "gold.jsonl"
    cord.write_text("changed annotations")
    with pytest.raises(ValueError, match="reference bytes differ"):
        scoring.verify_reference_bytes(tmp_path, cord)


def test_freeze_dependency_mutation_invalidates_plan(tmp_path, monkeypatch):
    cohort = tmp_path / "cohort"
    cohort.write_text("[]")
    plan = scoring.make_plan(cohort)
    real_digest = scoring.digest_file
    dependency = scoring.ROOT / "product_eval/final_gate_freeze.py"
    assert str(dependency.relative_to(scoring.ROOT)).replace("\\", "/") in plan["scorer_sha256"]
    monkeypatch.setattr(scoring, "digest_file", lambda path: "0" * 64 if path == dependency else real_digest(path))
    with pytest.raises(ValueError, match="Preregistered"):
        scoring.validate_plan(plan, real_digest(cohort))


@pytest.mark.parametrize("mutation", ["initial_bytes", "receipt", "inventory"])
def test_protocol_identity_rejected_before_labels(tmp_path, monkeypatch, mutation):
    run = tmp_path / "run"
    run.mkdir()
    cohort = tmp_path / "cohort"
    cohort.write_text("[]")
    sources = [{"doc_id": "one", "source_sha256": "c" * 64, "family": "receipt"}]
    path = run / "protocol.json"
    path.write_text(json.dumps({"analysis_plan": scoring.make_plan(cohort),
                               "cohort_sha256": digest_file(cohort), "sources": sources}))
    sha = digest_file(path)
    verified = {"documents": copy.deepcopy(sources), "verified_artifact_hashes": {"protocol.json": sha}}
    if mutation == "initial_bytes":
        path.write_text(path.read_text() + " ")
    elif mutation == "receipt":
        verified["verified_artifact_hashes"]["protocol.json"] = "0" * 64
    else:
        verified["documents"][0]["source_sha256"] = "0" * 64
    monkeypatch.setattr(scoring, "verify_completed", lambda *_: verified)
    monkeypatch.setattr(scoring, "load_references", lambda *_: pytest.fail("labels opened"))
    with pytest.raises(ValueError, match="[Pp]rotocol|inventory"):
        scoring.run_analysis(run, sha, "seals/1.json", "b" * 64, tmp_path / "output",
                             tmp_path / "vrdu", tmp_path / "cord")
    assert not (tmp_path / "output").exists()
