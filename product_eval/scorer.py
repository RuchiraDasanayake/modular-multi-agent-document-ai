"""Deterministic pre-review scoring for product extraction candidates."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from product_eval.contracts import ContractError, validate_record


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _prf(tp: int, fp: int, fn: int) -> dict[str, int | float | None]:
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": _rate(tp, tp + fp),
        "recall": _rate(tp, tp + fn),
        "f1": _rate(2 * tp, 2 * tp + fp + fn),
    }


def _typed_equal(left: Any, right: Any) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_typed_equal(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_typed_equal(a, b) for a, b in zip(left, right))
    return left == right


def _numeric_zero(value: Any) -> bool:
    return type(value) in {int, float} and value == 0


def _has_complete_evidence(evidence: Any) -> bool:
    return (
        isinstance(evidence, dict)
        and type(evidence.get("page")) is int
        and type(evidence.get("start")) is int
        and type(evidence.get("end")) is int
        and isinstance(evidence.get("quote"), str)
        and bool(evidence["quote"])
        and 0 <= evidence["start"] < evidence["end"]
    )


def _valid_evidence(
    candidate_evidence: Any,
    gold_evidence: dict[str, Any],
    pages: dict[int, str],
    *,
    value_matches: bool,
) -> bool:
    if not value_matches or not _has_complete_evidence(candidate_evidence):
        return False
    page = candidate_evidence["page"]
    if page != gold_evidence["page"] or page not in pages:
        return False
    start, end = candidate_evidence["start"], candidate_evidence["end"]
    if end > len(pages[page]) or candidate_evidence["quote"] != pages[page][start:end]:
        return False
    return start <= gold_evidence["start"] and end >= gold_evidence["end"]


def score_records(
    gold_records: Mapping[str, dict[str, Any]],
    candidate_records: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    """Score candidate outputs joined to adjudicated gold by exact document/field IDs.

    Missing candidate documents are failures, not silently dropped. The reported value
    score uses raw machine output before any human correction. Undefined ratios are null.
    """
    if not gold_records:
        raise ContractError("gold records must not be empty")
    unknown_docs = set(candidate_records) - set(gold_records)
    if unknown_docs:
        raise ContractError(f"candidate contains unknown doc_id(s): {sorted(unknown_docs)}")
    for doc_id, record in gold_records.items():
        validate_record(record, kind="gold", label=f"gold[{doc_id!r}]")
        if record["doc_id"] != doc_id:
            raise ContractError(f"gold mapping key {doc_id!r} disagrees with record doc_id")
    for doc_id, record in candidate_records.items():
        validate_record(record, kind="candidate", label=f"candidate[{doc_id!r}]")
        if record["doc_id"] != doc_id:
            raise ContractError(f"candidate mapping key {doc_id!r} disagrees with record doc_id")

    schema = Counter()
    values = Counter()
    evidence = Counter()
    operations = Counter()
    measurement_counts = Counter()
    observed_measurements = Counter()
    per_field: list[dict[str, Any]] = []
    per_document: list[dict[str, Any]] = []

    for doc_id in sorted(gold_records):
        gold = gold_records[doc_id]
        candidate = candidate_records.get(doc_id)
        if candidate is None:
            operations["missing_candidate_docs"] += 1
        document_status = candidate["document_status"] if candidate else "no_output"
        gold_schema = {item["field_id"]: item for item in gold["gold_schema"]}
        gold_values = {item["field_id"]: item for item in gold["gold_values"]}
        proposed_schema = {item["field_id"]: item for item in candidate["proposed_schema"]} if candidate else {}
        extracted_values = {item["field_id"]: item for item in candidate["extracted_values"]} if candidate else {}
        pages = {item["page"]: item["text"] for item in gold["pages"]}

        operations["gold_field_count"] += len(gold_schema)
        operations["orphan_extracted_values"] += len(set(extracted_values) - set(proposed_schema))
        if document_status == "processed":
            operations["processed_docs"] += 1
        if document_status == "unsupported":
            operations["unsupported_docs"] += 1
        if document_status == "failed":
            operations["failed_docs"] += 1

        review_required = document_status == "needs_review" or any(
            item["status"] == "needs_review" or item["review_state"] != "none"
            for item in extracted_values.values()
        )
        if review_required:
            operations["docs_requiring_or_receiving_review"] += 1
        if document_status == "processed" and not review_required:
            operations["auto_processed_docs"] += 1

        doc_false_accepted = 0
        doc_critical_evidence_valid = True
        for field_id in sorted(set(gold_schema) | set(proposed_schema) | set(extracted_values)):
            expected_schema = gold_schema.get(field_id)
            proposed = proposed_schema.get(field_id)
            gold_value_record = gold_values.get(field_id)
            predicted = extracted_values.get(field_id)
            expected_value = gold_value_record["value"] if gold_value_record else None
            predicted_value = predicted["value"] if predicted else None
            predicted_status = predicted["status"] if predicted else "no_output"
            review_state = predicted["review_state"] if predicted else "none"
            gold_positive = gold_value_record is not None and expected_value is not None
            accepted = predicted_status == "accepted"
            value_matches = accepted and gold_positive and _typed_equal(expected_value, predicted_value)

            type_match: bool | None = None
            group_match: bool | None = None
            if expected_schema and proposed:
                schema["tp"] += 1
                schema_outcome = "matched"
                schema["type_evaluated"] += 1
                type_match = proposed["type"] == expected_schema["type"]
                if type_match:
                    schema["type_correct"] += 1
                if expected_schema.get("group") is not None:
                    schema["group_evaluated"] += 1
                    group_match = proposed.get("group") == expected_schema["group"]
                    if group_match:
                        schema["group_correct"] += 1
            elif expected_schema:
                schema["fn"] += 1
                schema_outcome = "missed"
            else:
                if proposed:
                    schema["fp"] += 1
                schema_outcome = "spurious" if proposed else "not_proposed"

            if value_matches:
                values["tp"] += 1
                value_outcome = "correct_accepted"
            elif accepted:
                values["fp"] += 1
                values["false_accepted"] += 1
                doc_false_accepted += 1
                if expected_schema and expected_schema["critical"]:
                    values["critical_false_accepted"] += 1
                if gold_positive:
                    values["fn"] += 1
                    value_outcome = "wrong_accepted"
                else:
                    value_outcome = "false_accepted_absent_or_unknown"
            elif gold_positive:
                values["fn"] += 1
                value_outcome = "abstained" if predicted_status in {"needs_review", "rejected"} else "missing"
            elif gold_value_record is not None:
                value_outcome = "correct_missing" if predicted_status == "missing" else "unresolved_missing"
            else:
                value_outcome = "no_accepted_value"

            missing_zero_error: str | None = None
            if gold_value_record is not None and _numeric_zero(expected_value) and predicted_status in {"missing", "no_output"}:
                values["gold_zero_predicted_missing"] += 1
                missing_zero_error = "zero_as_missing"
            if gold_value_record is not None and expected_value is None and accepted and _numeric_zero(predicted_value):
                values["gold_missing_predicted_zero"] += 1
                missing_zero_error = "missing_as_zero"

            if expected_schema and accepted and review_state == "none":
                operations["auto_accepted_gold_fields"] += 1
            if expected_schema and (review_state != "none" or predicted_status == "needs_review"):
                operations["reviewed_or_pending_gold_fields"] += 1

            evidence_outcome = "not_evaluable"
            gold_evidence = gold_value_record.get("evidence") if gold_value_record else None
            if accepted and gold_evidence is not None:
                evidence["evaluable_accepted_values"] += 1
                candidate_evidence = predicted.get("evidence") if predicted else None
                if _has_complete_evidence(candidate_evidence):
                    evidence["present"] += 1
                    if _valid_evidence(candidate_evidence, gold_evidence, pages, value_matches=value_matches):
                        evidence["valid"] += 1
                        evidence_outcome = "valid"
                    else:
                        evidence_outcome = "invalid"
                else:
                    evidence_outcome = "absent_or_incomplete"
                if expected_schema and expected_schema["critical"] and evidence_outcome != "valid":
                    doc_critical_evidence_valid = False

            per_field.append(
                {
                    "doc_id": doc_id,
                    "field_id": field_id,
                    "critical": expected_schema["critical"] if expected_schema else None,
                    "schema_outcome": schema_outcome,
                    "type_match": type_match,
                    "group_match": group_match,
                    "value_outcome": value_outcome,
                    "missing_zero_error": missing_zero_error,
                    "candidate_status": predicted_status,
                    "review_state": review_state,
                    "evidence_outcome": evidence_outcome,
                }
            )

        critical_ids = [field_id for field_id, item in gold_schema.items() if item["critical"]]
        if critical_ids:
            operations["critical_evaluable_docs"] += 1
        critical_correct = all(
            (
                extracted_values.get(field_id, {}).get("status") == "missing"
                if gold_values[field_id]["value"] is None
                else extracted_values.get(field_id, {}).get("status") == "accepted"
                and _typed_equal(extracted_values[field_id]["value"], gold_values[field_id]["value"])
            )
            for field_id in critical_ids
        )
        correct_auto_release = (
            bool(critical_ids)
            and document_status == "processed"
            and not review_required
            and critical_correct
            and doc_critical_evidence_valid
            and not doc_false_accepted
        )
        if correct_auto_release:
            operations["correctly_auto_released_docs"] += 1

        measurements = candidate.get("measurements", {}) if candidate else {}
        per_document.append(
            {
                "doc_id": doc_id,
                "document_status": document_status,
                "review_required": review_required,
                "critical_fields": len(critical_ids),
                "false_accepted": doc_false_accepted,
                "critical_evidence_valid": doc_critical_evidence_valid,
                "correct_auto_release": correct_auto_release,
                "total_cost_reported": "total_cost_usd" in measurements,
            }
        )
        for name in ("latency_ms", "api_cost_usd", "compute_cost_usd", "total_cost_usd", "review_minutes"):
            if name in measurements:
                measurement_counts[name] += 1
                observed_measurements[name] += measurements[name]

    doc_count = len(gold_records)
    gold_field_count = operations["gold_field_count"]
    all_costs_reported = measurement_counts["total_cost_usd"] == doc_count
    correct_release_count = operations["correctly_auto_released_docs"]
    return {
        "contract_version": 1,
        "documents": {
            "gold": doc_count,
            "candidate": len(candidate_records),
            "missing_candidate": operations["missing_candidate_docs"],
            "unsupported": operations["unsupported_docs"],
            "failed": operations["failed_docs"],
        },
        "schema": {
            **_prf(schema["tp"], schema["fp"], schema["fn"]),
            "type_correct": schema["type_correct"],
            "type_evaluated": schema["type_evaluated"],
            "type_accuracy": _rate(schema["type_correct"], schema["type_evaluated"]),
            "group_correct": schema["group_correct"],
            "group_evaluated": schema["group_evaluated"],
            "group_accuracy": _rate(schema["group_correct"], schema["group_evaluated"]),
        },
        "values": {
            **_prf(values["tp"], values["fp"], values["fn"]),
            "false_accepted": values["false_accepted"],
            "critical_false_accepted": values["critical_false_accepted"],
            "gold_zero_predicted_missing": values["gold_zero_predicted_missing"],
            "gold_missing_predicted_zero": values["gold_missing_predicted_zero"],
        },
        "evidence": {
            "evaluable_accepted_values": evidence["evaluable_accepted_values"],
            "present": evidence["present"],
            "valid": evidence["valid"],
            "presence_rate": _rate(evidence["present"], evidence["evaluable_accepted_values"]),
            "validity_rate": _rate(evidence["valid"], evidence["evaluable_accepted_values"]),
        },
        "operations": {
            "gold_fields": gold_field_count,
            "orphan_extracted_values": operations["orphan_extracted_values"],
            "auto_accepted_gold_fields": operations["auto_accepted_gold_fields"],
            "field_automation_rate": _rate(operations["auto_accepted_gold_fields"], gold_field_count),
            "reviewed_or_pending_gold_fields": operations["reviewed_or_pending_gold_fields"],
            "field_review_rate": _rate(operations["reviewed_or_pending_gold_fields"], gold_field_count),
            "docs_requiring_or_receiving_review": operations["docs_requiring_or_receiving_review"],
            "doc_review_rate": _rate(operations["docs_requiring_or_receiving_review"], doc_count),
            "auto_processed_docs": operations["auto_processed_docs"],
            "doc_automation_rate": _rate(operations["auto_processed_docs"], doc_count),
            "critical_evaluable_docs": operations["critical_evaluable_docs"],
            "correctly_auto_released_docs": correct_release_count,
            "correct_auto_release_rate": _rate(correct_release_count, operations["critical_evaluable_docs"]),
        },
        "measurements": {
            name: {
                "reported_docs": measurement_counts[name],
                "observed_sum": observed_measurements[name],
            }
            for name in sorted(("latency_ms", "api_cost_usd", "compute_cost_usd", "total_cost_usd", "review_minutes"))
        }
        | {
            "all_docs_report_total_cost": all_costs_reported,
            "cost_per_correctly_auto_released_doc_usd": (
                observed_measurements["total_cost_usd"] / correct_release_count
                if all_costs_reported and correct_release_count
                else None
            ),
        },
        "per_document": per_document,
        "per_field": per_field,
    }
