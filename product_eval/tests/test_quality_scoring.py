"""Self-authored sealed campaigns only; never opens the reserved cohort."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest

from idpo.product_auto.provider import ModelReply
from product_eval import quality_comparison as quality
from product_eval import quality_scoring as scoring
from product_eval import quality_scoring_verification as verify
from product_eval.final_gate_freeze import digest_file, encoded, read_json, write_new
from product_eval.final_gate_ledger import Ledger
from product_eval.tests.test_quality_comparison import (  # noqa: F401 - shared fixture
    execute,
    frozen,
    install_mocks,
)
from product_eval.tests.test_vrdu import _annotation, _row, _write_family


def test_newline_conversion_requires_registered_git_content():
    blob = b"value = 1\n# unchanged\n"
    sha = hashlib.sha256(blob).hexdigest()
    assert verify._newline_receipt(blob.replace(b"\n", b"\r\n"), sha, blob)["canonical_source_sha256"] == sha
    for changed in (blob.replace(b"1", b"2"), blob.replace(b" = ", b"="), blob + b"\n", blob.replace(b"\n", b"\r")):
        with pytest.raises(ValueError, match="implementation changed"):
            verify._newline_receipt(changed, sha, blob)
    with pytest.raises(ValueError, match="implementation changed"):
        verify._newline_receipt(blob, sha, b"value = 2\n")


@pytest.fixture
def campaign(frozen, monkeypatch):  # noqa: F811 - pytest resolves imported shared fixture
    protocol = read_json(frozen.output / "protocol.json")
    code_root = Path(verify.__file__).resolve().parents[1]
    protocol["code"]["python_source_sha256"] = {name: digest_file(code_root / name) for name in verify.FROZEN_MODULES}
    (frozen.output / "protocol.json").write_bytes(encoded(protocol))
    frozen.sha = digest_file(frozen.output / "protocol.json")
    monkeypatch.setattr(quality.freeze_helpers, "code_receipt", lambda: protocol["code"])
    for arm in quality.ARMS:
        with Ledger(frozen.output / "arms" / arm / "ledger.sqlite3").transaction() as db:
            db.execute("UPDATE settings SET value=? WHERE key='protocol_sha256'", (frozen.sha,))
    plan_sha = write_new(frozen.output / "analysis-plan.json", {"frozen_execution_protocol_sha256": frozen.sha})
    prereg_sha = write_new(frozen.output / "analysis-preregistration.json", {
        "protocol_sha256": frozen.sha, "analysis_plan_sha256": plan_sha, "arm_model_attempts": {arm: 0 for arm in quality.ARMS}})
    monkeypatch.setattr(verify, "PROTOCOL_SHA256", frozen.sha)
    monkeypatch.setattr(verify, "ANALYSIS_SHA256", plan_sha)
    monkeypatch.setattr(verify, "PREREGISTRATION_SHA256", prereg_sha)
    return frozen


def _seal(campaign):
    return digest_file(campaign.output / "prediction-seal.json")


def _gold(bundle):
    gold = {}
    for key, source in bundle["sources"].items():
        schema = [{"field_id": "total", "type": "integer", "critical": False}]
        values = [{"field_id": "total", "value": 42}]
        if source["family"] != "registration-form":
            schema.append({"field_id": "item", "type": "array[object]", "critical": False})
            values.append({"field_id": "item", "value": [{"row": 0, "value": "Widget"}]})
        gold[key] = {"contract_version": 1, "doc_id": key, "pages": [{"page": 1, "text": "Widget Total: 42"}],
                     "gold_schema": schema, "gold_values": values}
    return gold


def test_sealed_actual_workflow_candidates_verify_and_bootstrap(campaign, monkeypatch):
    install_mocks(monkeypatch, campaign)
    execute(campaign)
    bundle = verify.verify_campaign(campaign.output, _seal(campaign))
    assert bundle["receipt"]["verified_product_results"] == 12
    assert bundle["receipt"]["verified_request_attempts"] == 12
    result = scoring.assemble_scores(bundle, _gold(bundle))
    assert len(result["paired_sources"]) == 6
    for arm in quality.ARMS:
        for family in quality.FAMILIES:
            report = result["families"][arm][family]
            assert report["documents"] == 2
            assert report["proposed_scalar_positive"] == {"matched": 2, "reference": 2, "recall": 1.0}
            assert report["operational_usage"]["known_prompt_tokens"] == 20
            assert report["operational_usage"]["attempts_with_unknown_prompt_tokens"] == 0
        assert result["families"][arm]["receipt"]["proposed_annotated_rows"]["false_positive"] is None
    assert result["paired_uncertainty"]["proposed_scalar_positive"]["replicates"] == 10000
    assert result["paired_uncertainty"]["proposed_annotated_rows"]["macro"]["families"] == ["ad-buy-form", "receipt"]
    assert result["paired_uncertainty"]["valid_full_coverage"]["discordance"] == {"both": 6}
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("damage", ["missing_seal", "changed_artifact", "unsealed_artifact", "changed_source", "changed_plan", "changed_module"])
def test_integrity_failure_never_opens_references(campaign, monkeypatch, tmp_path, damage):
    install_mocks(monkeypatch, campaign)
    execute(campaign)
    seal = _seal(campaign)
    if damage == "missing_seal":
        (campaign.output / "prediction-seal.json").unlink()
    elif damage == "changed_artifact":
        (campaign.output / "arms/text/candidates.jsonl").write_text("{}\n")
    elif damage == "unsealed_artifact":
        (campaign.output / "extra.json").write_text("{}")
    elif damage == "changed_source":
        Path(campaign.sources[0]["source_path"]).write_bytes(b"changed")
    elif damage == "changed_plan":
        (campaign.output / "analysis-plan.json").write_text("{}")
    else:
        monkeypatch.setattr(verify, "FROZEN_MODULES", (*verify.FROZEN_MODULES, "product_eval/quality_scoring.py"))
    monkeypatch.setattr(scoring, "load_references", lambda *a, **kw: pytest.fail("Labels opened before verification"))
    with pytest.raises((ValueError, OSError)):
        scoring.run_analysis(campaign.output, seal, tmp_path / "derived", vrdu_root=tmp_path / "never-read", cord_gold=tmp_path / "never-read.jsonl")
    assert not (tmp_path / "derived").exists()


def test_failed_uncertain_and_unattempted_slots_retain_reference_denominators(campaign, monkeypatch):
    failure = ModelReply("", 1, error="safe", error_category="transport_timeout", sdk_attempts=1)
    install_mocks(monkeypatch, campaign, first_reply=failure)
    execute(campaign)
    quality._seal(campaign.output, read_json(campaign.output / "protocol.json"), include_unattempted=True)
    bundle = verify.verify_campaign(campaign.output, _seal(campaign))
    result = scoring.assemble_scores(bundle, _gold(bundle))
    for arm in quality.ARMS:
        assert sum(row["proposed_scalar_positive"]["reference"] for row in result["families"][arm].values()) == 6
        assert sum(row["proposed_scalar_positive"]["matched"] for row in result["families"][arm].values()) == 0
    usage = result["families"]["text"]["registration-form"]["operational_usage"]
    assert usage["uncertain_attempts"] == 1
    assert usage["attempts_with_unknown_prompt_tokens"] == 1
    assert result["paired_uncertainty"]["valid_full_coverage"]["discordance"] == {"neither": 6}


def test_lists_nulls_rows_and_partial_extra_cells_keep_separate_semantics(campaign, monkeypatch):
    install_mocks(monkeypatch, campaign)
    execute(campaign)
    bundle = verify.verify_campaign(campaign.output, _seal(campaign))
    gold = _gold(bundle)
    reg = next(key for key, row in bundle["sources"].items() if row["family"] == "registration-form")
    gold[reg]["gold_schema"][0]["type"] = "array[string]"
    gold[reg]["gold_values"][0]["value"] = ["42", "forty-two"]
    other = next(key for key, row in bundle["sources"].items() if row["family"] == "registration-form" and key != reg)
    gold[other]["gold_values"][0]["value"] = None
    receipt = next(key for key, row in bundle["sources"].items() if row["family"] == "receipt")
    gold[receipt]["gold_values"][1]["value"] = [{"row": 0, "value": "Widget"}, {"row": 1, "value": "Widget"}]
    # One prediction cannot satisfy both equal reference rows.
    result = scoring.assemble_scores(bundle, gold)
    for arm in quality.ARMS:
        family = result["families"][arm]["registration-form"]
        assert family["historical_ordered_lists"]["reference"] == 1
        assert family["historical_ordered_lists"]["matched"] == 0
        assert family["ordered_list_schema_incompatibilities"] == 1
        assert family["null_scalar_reference_targets"] == 1
        assert family["proposed_scalar_positive"]["reference"] == 1
        rows = result["families"][arm]["receipt"]["proposed_annotated_rows"]
        assert (rows["matched"], rows["reference"]) == (2, 3)
        assert rows["precision"] is rows["f1"] is rows["false_positive"] is None


def test_reference_assembly_uses_unchanged_creator_conversion_only_after_receipt(campaign, monkeypatch, tmp_path):
    install_mocks(monkeypatch, campaign)
    execute(campaign)
    bundle = verify.verify_campaign(campaign.output, _seal(campaign))
    creator = tmp_path / "creator"
    text = "Widget Total: 42"
    for family in ("registration-form", "ad-buy-form"):
        annotations = [["total", [_annotation("42", text)]]]
        matchers = {"total": "GeneralStringMatch"}
        if family == "ad-buy-form":
            annotations += [[["item"], [[_annotation("Widget", text)]]]]
            matchers["item"] = "GeneralStringMatch"
        rows = [_row(Path(row["source_path"]).name, text, annotations) for row in bundle["sources"].values() if row["family"] == family]
        _write_family(creator, family, rows, matchers, {"item"} if family == "ad-buy-form" else set())
    gold = _gold(bundle)
    cord = tmp_path / "gold_reserved.jsonl"
    cord.write_text("\n".join(json.dumps(gold[key]) for key, row in bundle["sources"].items() if row["family"] == "receipt"))
    output = tmp_path / "derived"
    result = scoring.run_analysis(campaign.output, _seal(campaign), output, vrdu_root=creator, cord_gold=cord)
    assert len(result["scoring_receipt_sha256"]) == 64
    assert read_json(output / "reference-conversion.json")["documents"] == 6
    report = read_json(output / "quality-results.json")
    # VRDU values remain strings: importing them must not coerce to model integers.
    assert report["families"]["text"]["registration-form"]["proposed_scalar_positive"]["matched"] == 0
    assert report["families"]["text"]["receipt"]["proposed_scalar_positive"]["matched"] == 2
    assert read_json(output / "verified-before-labels.json")["labels_opened_before_verification"] is False


def test_failed_status_cannot_earn_matches_even_with_leftover_values(campaign, monkeypatch):
    install_mocks(monkeypatch, campaign)
    execute(campaign)
    bundle = verify.verify_campaign(campaign.output, _seal(campaign))
    changed = deepcopy(bundle)
    key = next(iter(changed["sources"]))
    changed["arms"]["text"][key]["eligible"] = False
    changed["arms"]["text"][key]["candidate"]["document_status"] = "failed"
    report = scoring.assemble_scores(changed, _gold(bundle))
    pair = next(row for row in report["paired_sources"] if row["doc_id"] == key)
    assert pair["text"]["proposed_scalar_positive"] == {"matched": 0, "reference": 1, "recall": 0.0}
    assert pair["candidate"]["proposed_scalar_positive"]["matched"] == 1


@pytest.mark.parametrize("damage", ["document_drop", "ledger_usage", "schema", "result_receipt"])
def test_nested_contract_verification_rejects_even_when_outer_hashes_are_recomputed(campaign, monkeypatch, tmp_path, damage):
    install_mocks(monkeypatch, campaign)
    execute(campaign)
    directory = campaign.output / "arms/text"
    if damage == "document_drop":
        path = directory / "documents.json"
        path.write_bytes(encoded(read_json(path)[:-1]))
    elif damage == "ledger_usage":
        path = directory / "ledger-snapshot.json"
        state = read_json(path)
        state["attempts"][0]["prompt_tokens"] += 1
        path.write_bytes(encoded(state))
    elif damage == "schema":
        path = directory / "schemas/receipt.json"
        schema = read_json(path)
        schema["fields"][0]["description"] = "Changed task meaning"
        path.write_bytes(encoded(schema))
    else:
        path = next((directory / "product_runs").glob("*/docs/*/result.json"))
        result = read_json(path)
        result["reason"] = "tampered"
        path.write_bytes(encoded(result))
    seal = read_json(campaign.output / "prediction-seal.json")
    seal["files"] = {name: digest_file(campaign.output / name) for name in seal["files"]}
    (campaign.output / "prediction-seal.json").write_bytes(encoded(seal))
    monkeypatch.setattr(scoring, "load_references", lambda *a, **kw: pytest.fail("Labels opened on invalid nested receipt"))
    with pytest.raises(ValueError):
        scoring.run_analysis(campaign.output, _seal(campaign), tmp_path / "derived", vrdu_root=tmp_path / "never", cord_gold=tmp_path / "never.jsonl")
