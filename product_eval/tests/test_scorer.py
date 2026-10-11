from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

from product_eval.contracts import ContractError, load_jsonl
from product_eval.scorer import score_records

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _records() -> tuple[dict, dict]:
    return (
        load_jsonl(FIXTURES / "gold.jsonl", kind="gold"),
        load_jsonl(FIXTURES / "candidate.jsonl", kind="candidate"),
    )


def test_synthetic_fixture_reports_separate_schema_value_and_review_metrics() -> None:
    gold, candidate = _records()
    report = score_records(gold, candidate)

    assert report["schema"]["tp"] == 6
    assert report["schema"]["fp"] == 1
    assert report["schema"]["fn"] == 0
    assert report["schema"]["type_correct"] == 5
    assert report["schema"]["group_correct"] == 5
    assert report["values"]["tp"] == 3
    assert report["values"]["fp"] == 2
    assert report["values"]["fn"] == 1
    assert report["values"]["false_accepted"] == 2
    assert report["values"]["critical_false_accepted"] == 0
    assert report["values"]["gold_zero_predicted_missing"] == 1
    assert report["values"]["gold_missing_predicted_zero"] == 1
    assert report["evidence"]["evaluable_accepted_values"] == 3
    assert report["evidence"]["present"] == 2
    assert report["evidence"]["valid"] == 2
    assert report["operations"]["auto_accepted_gold_fields"] == 4
    assert report["operations"]["reviewed_or_pending_gold_fields"] == 1
    assert report["operations"]["docs_requiring_or_receiving_review"] == 1
    assert report["operations"]["correctly_auto_released_docs"] == 1
    assert report["measurements"]["total_cost_usd"]["reported_docs"] == 1
    assert report["measurements"]["cost_per_correctly_auto_released_doc_usd"] is None
    assert len(report["per_field"]) == 7


def test_full_cost_coverage_enables_cost_per_correct_release() -> None:
    gold, candidate = _records()
    candidate["synthetic-request-1"]["measurements"]["total_cost_usd"] = 0.02

    report = score_records(gold, candidate)

    assert report["measurements"]["all_docs_report_total_cost"] is True
    assert report["measurements"]["cost_per_correctly_auto_released_doc_usd"] == pytest.approx(0.03)


def test_missing_candidate_document_counts_as_failure_not_dropped() -> None:
    gold, candidate = _records()
    del candidate["synthetic-request-1"]

    report = score_records(gold, candidate)

    assert report["documents"]["gold"] == 2
    assert report["documents"]["candidate"] == 1
    assert report["documents"]["missing_candidate"] == 1
    assert report["schema"]["fn"] == 3
    assert report["values"]["fn"] == 2
    assert report["operations"]["doc_automation_rate"] == 0.5
    assert report["measurements"]["all_docs_report_total_cost"] is False


def test_wrong_critical_acceptance_invalidates_release_and_evidence() -> None:
    gold, candidate = _records()
    invoice = candidate["synthetic-invoice-1"]["extracted_values"][0]
    invoice["value"] = "INV-8"

    report = score_records(gold, candidate)

    assert report["values"]["critical_false_accepted"] == 1
    assert report["operations"]["correctly_auto_released_docs"] == 0
    assert report["evidence"]["present"] == 2
    assert report["evidence"]["valid"] == 1


def test_missing_critical_evidence_invalidates_correct_auto_release() -> None:
    gold, candidate = _records()
    candidate["synthetic-invoice-1"]["extracted_values"][0]["evidence"] = {"page": 1}

    report = score_records(gold, candidate)

    assert report["values"]["false_accepted"] == 2
    assert report["per_document"][0]["critical_evidence_valid"] is False
    assert report["operations"]["correctly_auto_released_docs"] == 0


def test_page_only_and_wrong_quote_do_not_count_as_valid_grounding() -> None:
    gold, candidate = _records()
    account = candidate["synthetic-request-1"]["extracted_values"][0]
    report = score_records(gold, candidate)
    assert report["evidence"]["present"] == 2

    account["evidence"] = {"page": 1, "start": 24, "end": 27, "quote": "wrong"}
    report = score_records(gold, candidate)
    assert report["evidence"]["present"] == 3
    assert report["evidence"]["valid"] == 2

    account["evidence"]["quote"] = "A-9"
    report = score_records(gold, candidate)
    assert report["evidence"]["valid"] == 3


def test_zero_is_not_false_or_absent() -> None:
    gold, candidate = _records()
    request = candidate["synthetic-request-1"]["extracted_values"]
    request[2]["value"] = False  # Gold optional_reference is null, not numeric zero.
    invoice = candidate["synthetic-invoice-1"]["extracted_values"]
    invoice[1]["value"] = 0  # Gold discount is JSON float 0.0, not JSON integer 0.

    report = score_records(gold, candidate)

    assert report["values"]["gold_missing_predicted_zero"] == 0
    assert report["values"]["false_accepted"] == 3
    assert report["values"]["fn"] == 2


def test_invalid_gold_or_extra_candidate_doc_is_rejected() -> None:
    gold, candidate = _records()
    invalid = copy.deepcopy(gold)
    invalid["synthetic-invoice-1"]["gold_values"][0]["evidence"]["quote"] = "not in source"
    with pytest.raises(ContractError, match="quote must equal"):
        score_records(invalid, candidate)

    candidate["unknown-doc"] = {**candidate["synthetic-invoice-1"], "doc_id": "unknown-doc"}
    with pytest.raises(ContractError, match="unknown doc_id"):
        score_records(gold, candidate)


def test_duplicate_document_and_field_ids_are_rejected(tmp_path: Path) -> None:
    gold_path = tmp_path / "gold.jsonl"
    original = (FIXTURES / "gold.jsonl").read_text(encoding="utf-8").splitlines()[0]
    gold_path.write_text(original + "\n" + original + "\n", encoding="utf-8")
    with pytest.raises(ContractError, match="duplicate doc_id"):
        load_jsonl(gold_path, kind="gold")

    gold, candidate = _records()
    candidate["synthetic-invoice-1"]["proposed_schema"].append(
        copy.deepcopy(candidate["synthetic-invoice-1"]["proposed_schema"][0])
    )
    with pytest.raises(ContractError, match="duplicate field_id"):
        score_records(gold, candidate)


def test_cli_min_documents_guard(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from product_eval.cli import main

    report_path = tmp_path / "report.json"
    arguments = [
        "product_eval.cli", "--gold", str(FIXTURES / "gold.jsonl"),
        "--candidate", str(FIXTURES / "candidate.jsonl"), "--report", str(report_path),
    ]
    monkeypatch.setattr(sys, "argv", arguments + ["--min-documents", "3"])
    with pytest.raises(SystemExit, match="2"):
        main()
    assert "got gold=2, candidate=2" in capsys.readouterr().err
    assert not report_path.exists()

    monkeypatch.setattr(sys, "argv", arguments + ["--min-documents", "2"])
    main()
    assert json.loads(report_path.read_text(encoding="utf-8"))["documents"]["gold"] == 2
