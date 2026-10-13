from __future__ import annotations

import copy
import json
import sys

import pytest

from product_eval.contracts import ContractError
from product_eval.scoped_assessment import assess_records, main, pages_sha256
from product_eval.scorer import score_records


def _linked(gold_rows, candidate_rows, *, scope="target_fields", accepted=False):
    fields = sorted({field for row in gold_rows for field in row})
    candidate_fields = sorted({field for row in candidate_rows for field in row})
    gold = {"doc": {"contract_version": 1, "doc_id": "doc", "pages": [],
                    "gold_schema": [{"field_id": key, "type": "array[object]", "critical": False} for key in fields],
                    "gold_values": [{"field_id": key, "value": [{"row": i, "value": row[key]}
                                     for i, row in enumerate(gold_rows) if key in row]} for key in fields]}}
    candidate = {"doc": {"contract_version": 1, "doc_id": "doc", "document_status": "needs_review",
                         "proposed_schema": [{"field_id": key, "type": "array[object]"} for key in candidate_fields],
                         "extracted_values": [{"field_id": key, "value": [{"row": i, "value": row[key]}
                                               for i, row in enumerate(candidate_rows) if key in row],
                                               "status": "accepted" if accepted else "needs_review",
                                               "review_state": "none" if accepted else "pending"} for key in candidate_fields]}}
    context = {"doc": {"label_scope": scope, "gold_pages_sha256": pages_sha256([])}}
    return gold, candidate, context


def _scalar(*, scope="target_fields"):
    pages = [{"page": 1, "text": "Amount: 10"}]
    evidence = {"page": 1, "start": 8, "end": 10, "quote": "10"}
    gold = {"doc": {"contract_version": 1, "doc_id": "doc", "pages": pages,
                    "gold_schema": [{"field_id": "amount", "type": "string", "critical": True}],
                    "gold_values": [{"field_id": "amount", "value": "10", "evidence": evidence}]}}
    candidate = {"doc": {"contract_version": 1, "doc_id": "doc", "document_status": "processed",
                         "proposed_schema": [{"field_id": "amount", "type": "string"}],
                         "extracted_values": [{"field_id": "amount", "value": "10", "evidence": copy.deepcopy(evidence),
                                               "status": "accepted", "review_state": "none"}]}}
    context = {"doc": {"label_scope": scope, "gold_pages_sha256": pages_sha256(pages)}}
    return gold, candidate, context


def test_permuted_rows_match_once_without_changing_historical_ordinal_score():
    rows = [{"name": "A", "price": "10"}, {"name": "B", "price": "20"}]
    gold, candidates, contexts = _linked(rows, list(reversed(rows)))
    legacy = score_records(gold, candidates)
    report = assess_records(gold, candidates, contexts)
    assert legacy["linked_rows"]["proposed_complete_rows"]["tp"] == 0
    assert report["proposed_annotated_rows"]["matched"] == 2
    assert report["proposed_annotated_rows"]["precision"] == 1
    assert report["accepted_annotated_rows"]["matched"] == 0
    assert report["accepted_annotated_rows"]["missed_reference"] == 2
    assert score_records(gold, candidates) == legacy


@pytest.mark.parametrize("reference_count,predicted_count,expected", [(2, 1, 1), (1, 2, 1), (3, 3, 3)])
def test_duplicate_multiplicity_preserved(reference_count, predicted_count, expected):
    args = _linked([{"name": "A"}] * reference_count, [{"name": "A"}] * predicted_count)
    metric = assess_records(*args)["proposed_annotated_rows"]
    assert metric["matched"] == expected
    assert metric["false_positive"] == predicted_count - expected
    assert metric["missed_reference"] == reference_count - expected


def test_columns_from_different_rows_never_combine_into_a_match():
    args = _linked([{"name": "A", "price": "10"}, {"name": "B", "price": "20"}],
                   [{"name": "A", "price": "20"}, {"name": "B", "price": "10"}])
    assert assess_records(*args)["proposed_annotated_rows"]["matched"] == 0


def test_missing_candidate_kept_in_denominator():
    gold, _, contexts = _linked([{"name": "A"}, {"name": "B"}], [])
    report = assess_records(gold, {}, contexts)
    assert report["missing_candidates"] == 1
    assert report["proposed_annotated_rows"]["missed_reference"] == 2
    assert report["per_document"][0]["candidate_missing"] is True


def test_candidate_split_groups_do_not_join_into_a_reference_row():
    gold, candidates, contexts = _linked([{"name": "A", "price": "10"}], [{"name": "A", "price": "10"}])
    for field in candidates["doc"]["proposed_schema"]:
        field["group"] = field["field_id"]
    assert assess_records(gold, candidates, contexts)["proposed_annotated_rows"]["matched"] == 0


def test_group_names_can_differ_when_whole_field_relationships_are_identical():
    gold, candidates, contexts = _linked([{"name": "A", "price": "10"}], [{"name": "A", "price": "10"}])
    for field in gold["doc"]["gold_schema"]:
        field["group"] = "gold_items"
    for field in candidates["doc"]["proposed_schema"]:
        field["group"] = "candidate_lines"
    assert assess_records(gold, candidates, contexts)["proposed_annotated_rows"]["matched"] == 1


def test_partial_labels_use_maximum_matching_and_never_claim_precision():
    args = _linked([{"name": "A"}, {"name": "A", "price": "10"}],
                   [{"name": "A", "price": "10"}, {"name": "A"}, {"name": "extra"}], scope="positive_only")
    metric = assess_records(*args)["proposed_annotated_rows"]
    assert metric["matched"] == 2
    assert metric["unmatched_predictions"] == 1
    assert metric["false_positive"] is None
    assert metric["precision"] is None
    assert metric["f1"] is None
    assert metric["recall"] == 1


def test_partial_row_still_requires_all_annotated_cells():
    args = _linked([{"name": "A", "price": "10"}], [{"name": "A", "price": "11"}], scope="positive_only")
    assert assess_records(*args)["proposed_annotated_rows"]["matched"] == 0


def test_accepted_rows_require_parent_and_cell_acceptance():
    gold, candidates, contexts = _linked([{"name": "A", "price": "10"}],
                                        [{"name": "A", "price": "10"}], accepted=True)
    candidates["doc"]["extracted_values"][0]["value"][0]["status"] = "needs_review"
    report = assess_records(gold, candidates, contexts)
    assert report["proposed_annotated_rows"]["matched"] == 1
    assert report["accepted_annotated_rows"]["matched"] == 0


@pytest.mark.parametrize("scope,extra_fp", [("complete_document", 1), ("target_fields", 0), ("positive_only", None)])
def test_unlabelled_extras_are_unassessed_under_partial_document_scope(scope, extra_fp):
    gold, candidates, contexts = _scalar(scope=scope)
    candidates["doc"]["proposed_schema"].append({"field_id": "other", "type": "string"})
    candidates["doc"]["extracted_values"].append({"field_id": "other", "value": "unlabelled",
                                                 "status": "accepted", "review_state": "none"})
    report = assess_records(gold, candidates, contexts)
    assert report["accepted_scalar_values"]["false_positive"] == extra_fp
    assert report["unassessed"]["accepted_fields"] == (0 if scope == "complete_document" else 1)
    assert report["schema"]["false_positive"] == extra_fp
    assert report["per_document"][0]["unassessed_extra_field_ids"] == ([] if scope == "complete_document" else ["other"])


def test_unlabelled_row_column_does_not_invalidate_target_field_row():
    args = _linked([{"name": "A"}], [{"name": "A", "unlabelled": "detail"}])
    report = assess_records(*args)
    assert report["proposed_annotated_rows"]["matched"] == 1
    assert report["unassessed"]["schema_fields"] == 1


def test_correct_quote_in_different_ocr_coordinates_is_not_invalid_evidence():
    gold, candidates, contexts = _scalar()
    pages = {"doc": [{"page": 1, "text": "Amount:\n10"}]}
    contexts["doc"]["candidate_pages_sha256"] = pages_sha256(pages["doc"])
    report = assess_records(gold, candidates, contexts, pages)
    assert report["evidence"]["coordinates_incompatible"] == 1
    assert report["evidence"]["authentic_quotes"] == 1
    assert report["evidence"]["support_validity_rate"] is None
    assert report["per_document"][0]["evidence_fields"][0]["value_and_span_supported"] is None


def test_unknown_candidate_text_does_not_establish_coordinate_compatibility():
    report = assess_records(*_scalar())
    assert report["evidence"]["coordinates_unknown"] == 1
    assert report["evidence"]["quote_evaluable"] == 0
    assert report["evidence"]["support_validity_rate"] is None


def test_same_text_assesses_value_and_quote_and_span_together():
    gold, candidates, contexts = _scalar()
    pages = {"doc": gold["doc"]["pages"]}
    contexts["doc"]["candidate_pages_sha256"] = pages_sha256(pages["doc"])
    report = assess_records(gold, candidates, contexts, pages)
    assert report["evidence"]["support_validity_rate"] == 1
    candidates["doc"]["extracted_values"][0]["value"] = "wrong"
    report = assess_records(gold, candidates, contexts, pages)
    assert report["evidence"]["quote_authenticity_rate"] == 1
    assert report["evidence"]["support_validity_rate"] == 0


def test_forged_quote_is_counted_only_with_assessable_candidate_pages():
    gold, candidates, contexts = _scalar()
    pages = {"doc": gold["doc"]["pages"]}
    contexts["doc"]["candidate_pages_sha256"] = pages_sha256(pages["doc"])
    candidates["doc"]["extracted_values"][0]["evidence"]["quote"] = "99"
    report = assess_records(gold, candidates, contexts, pages)
    assert report["evidence"]["quote_authenticity_rate"] == 0
    assert report["evidence"]["support_validity_rate"] == 0


@pytest.mark.parametrize("key", ["gold_pages_sha256", "candidate_pages_sha256"])
def test_coordinate_hash_tamper_is_rejected(key):
    gold, candidates, contexts = _scalar()
    contexts["doc"][key] = "0" * 64
    with pytest.raises(ContractError, match="identity differs"):
        assess_records(gold, candidates, contexts)


def test_positive_only_null_rejected_and_complete_scope_can_assess_absence():
    gold, candidates, contexts = _scalar(scope="positive_only")
    gold["doc"]["gold_values"][0] = {"field_id": "amount", "value": None}
    with pytest.raises(ContractError, match="cannot assert absent"):
        assess_records(gold, candidates, contexts)
    contexts["doc"]["label_scope"] = "target_fields"
    assert assess_records(gold, candidates, contexts)["accepted_scalar_values"]["false_positive"] == 1


def test_wrong_array_shape_on_scalar_is_a_wrong_accepted_target_value():
    gold, candidates, contexts = _scalar()
    candidates["doc"]["extracted_values"][0]["value"] = [{"row": 0, "value": "10"}]
    assert assess_records(gold, candidates, contexts)["accepted_scalar_values"]["false_positive"] == 1


def test_manifest_requires_explicit_complete_document_coverage():
    gold, candidates, contexts = _scalar()
    with pytest.raises(ContractError, match="cover every"):
        assess_records(gold, candidates, {})
    contexts["doc"]["label_scope"] = "guessed"
    with pytest.raises(ContractError, match="explicit label_scope"):
        assess_records(gold, candidates, contexts)


def test_page_hash_ignores_only_serialization_and_list_order():
    pages = [{"page": 1, "text": "A"}, {"page": 2, "text": "B"}]
    assert pages_sha256(pages) == pages_sha256(list(reversed(pages)))
    assert pages_sha256(pages) != pages_sha256([{**pages[0], "text": "A "}, pages[1]])
    with pytest.raises(ContractError, match="unique positive"):
        pages_sha256([pages[0], pages[0]])


def test_cli_records_input_hashes_and_refuses_overwriting_report(tmp_path, monkeypatch):
    gold, candidates, contexts = _scalar()
    gold_path, candidate_path, context_path, report_path = [tmp_path / name for name in (
        "gold.jsonl", "candidate.jsonl", "contexts.json", "report.json")]
    gold_path.write_text(json.dumps(gold["doc"]) + "\n", encoding="utf-8")
    candidate_path.write_text(json.dumps(candidates["doc"]) + "\n", encoding="utf-8")
    context_path.write_text(json.dumps(contexts), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["scoped_assessment", "--gold", str(gold_path),
                                     "--candidate", str(candidate_path), "--contexts", str(context_path),
                                     "--report", str(report_path)])
    main()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert set(report["input_sha256"]) == {"gold", "candidate", "contexts"}
    before = report_path.read_bytes()
    with pytest.raises(SystemExit):
        main()
    assert report_path.read_bytes() == before


@pytest.mark.parametrize("invalid", ['{"doc":{},"doc":{}}', '{"doc":{"value":NaN}}', '[]'])
def test_cli_rejects_ambiguous_or_invalid_context_before_writing(tmp_path, monkeypatch, invalid):
    gold, candidates, _ = _scalar()
    gold_path, candidate_path, context_path, report_path = [tmp_path / name for name in (
        "gold.jsonl", "candidate.jsonl", "contexts.json", "report.json")]
    gold_path.write_text(json.dumps(gold["doc"]) + "\n", encoding="utf-8")
    candidate_path.write_text(json.dumps(candidates["doc"]) + "\n", encoding="utf-8")
    context_path.write_text(invalid, encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["scoped_assessment", "--gold", str(gold_path),
                                     "--candidate", str(candidate_path), "--contexts", str(context_path),
                                     "--report", str(report_path)])
    with pytest.raises(SystemExit):
        main()
    assert not report_path.exists()
