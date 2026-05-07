"""Unit tests for PolicyPerformanceAggregator."""

from __future__ import annotations

from docai_core.metrics.evaluator import DocumentMetrics
from docai_core.metrics.policy_performance import (
    DocumentPolicyProfile,
    PolicyPerformanceAggregator,
    PolicyPerformanceRecord,
)


def _dm(
    document_id: str,
    *,
    field_total: int = 4,
    field_correct: int = 4,
    field_true_positive: int = 4,
    field_false_positive: int = 0,
    field_false_negative: int = 0,
    missing_expected_field_count: int = 0,
    corrected_field_count: int = 0,
    extra_extracted_field_count: int = 0,
    field_accuracy: float | None = 1.0,
    field_precision: float | None = 1.0,
    field_recall: float | None = 1.0,
    field_f1: float | None = 1.0,
) -> DocumentMetrics:
    return DocumentMetrics(
        document_id=document_id,
        schema_id="invoice_basic",
        field_total=field_total,
        field_correct=field_correct,
        field_accuracy=field_accuracy,
        table_cell_total=0,
        table_cell_correct=0,
        table_cell_accuracy=None,
        overall_accuracy=field_accuracy,
        corrected_field_count=corrected_field_count,
        corrected_table_row_count=0,
        missing_expected_field_count=missing_expected_field_count,
        extra_extracted_field_count=extra_extracted_field_count,
        field_true_positive=field_true_positive,
        field_false_positive=field_false_positive,
        field_false_negative=field_false_negative,
        field_precision=field_precision,
        field_recall=field_recall,
        field_f1=field_f1,
    )


def _profile(
    doc_id: str,
    policy_id: str = "invoice_basic_local_v1",
    policy_version: str = "v1",
    document_type: str = "invoice",
    quality_bin: str = "clean",
) -> tuple[str, DocumentPolicyProfile]:
    return doc_id, DocumentPolicyProfile(
        policy_id=policy_id,
        policy_version=policy_version,
        document_type=document_type,
        quality_bin=quality_bin,
    )


# ---------------------------------------------------------------------------
# Test 1: empty input produces empty output
# ---------------------------------------------------------------------------

def test_aggregate_empty_input_returns_empty_list() -> None:
    agg = PolicyPerformanceAggregator()
    result = agg.aggregate([], {})
    assert result == []


# ---------------------------------------------------------------------------
# Test 2: single document produces single record
# ---------------------------------------------------------------------------

def test_aggregate_single_document_produces_one_record() -> None:
    dm = _dm("doc-0")
    _, profile = _profile("doc-0")
    agg = PolicyPerformanceAggregator()
    records = agg.aggregate([dm], {"doc-0": profile})

    assert len(records) == 1
    rec = records[0]
    assert rec.policy_id == "invoice_basic_local_v1"
    assert rec.policy_version == "v1"
    assert rec.document_type == "invoice"
    assert rec.quality_bin == "clean"
    assert rec.document_count == 1
    assert rec.field_accuracy == 1.0
    assert rec.field_recall == 1.0
    assert rec.missing_rate == 0.0
    assert rec.correction_rate == 0.0


# ---------------------------------------------------------------------------
# Test 3: two documents in the same group are merged
# ---------------------------------------------------------------------------

def test_aggregate_two_docs_same_group_produces_one_record() -> None:
    dm0 = _dm("doc-0", field_accuracy=1.0, field_recall=1.0, field_f1=1.0)
    dm1 = _dm("doc-1", field_accuracy=0.5, field_recall=0.5, field_f1=0.5)
    profile_map = dict([_profile("doc-0"), _profile("doc-1")])
    agg = PolicyPerformanceAggregator()
    records = agg.aggregate([dm0, dm1], profile_map)

    assert len(records) == 1
    rec = records[0]
    assert rec.document_count == 2
    assert rec.field_accuracy == 0.75
    assert rec.field_recall == 0.75


# ---------------------------------------------------------------------------
# Test 4: two different policies produce two records
# ---------------------------------------------------------------------------

def test_aggregate_two_policies_produce_two_records() -> None:
    dm0 = _dm("doc-0")
    dm1 = _dm("doc-1", field_accuracy=0.5, field_recall=0.5, field_f1=0.666667, field_precision=1.0)
    profile_map = {
        "doc-0": DocumentPolicyProfile(policy_id="policy_a", policy_version="v1",
                                        document_type="invoice", quality_bin="clean"),
        "doc-1": DocumentPolicyProfile(policy_id="policy_b", policy_version="v1",
                                        document_type="invoice", quality_bin="clean"),
    }
    agg = PolicyPerformanceAggregator()
    records = agg.aggregate([dm0, dm1], profile_map)

    assert len(records) == 2
    by_policy = {r.policy_id: r for r in records}
    assert "policy_a" in by_policy
    assert "policy_b" in by_policy
    assert by_policy["policy_a"].document_count == 1
    assert by_policy["policy_b"].document_count == 1


# ---------------------------------------------------------------------------
# Test 5: missing profile falls back to "unknown" group
# ---------------------------------------------------------------------------

def test_aggregate_missing_profile_uses_unknown_group() -> None:
    dm = _dm("doc-orphan")
    agg = PolicyPerformanceAggregator()
    records = agg.aggregate([dm], {})

    assert len(records) == 1
    rec = records[0]
    assert rec.policy_id == "unknown"
    assert rec.document_type == "unknown"
    assert rec.quality_bin == "unknown"


# ---------------------------------------------------------------------------
# Test 6: missing_rate and correction_rate computed correctly
# ---------------------------------------------------------------------------

def test_aggregate_missing_and_correction_rates() -> None:
    dm = _dm(
        "doc-0",
        field_total=4,
        missing_expected_field_count=1,
        corrected_field_count=2,
    )
    _, profile = _profile("doc-0")
    agg = PolicyPerformanceAggregator()
    records = agg.aggregate([dm], {"doc-0": profile})

    rec = records[0]
    assert rec.missing_rate == round(1 / 4, 6)
    assert rec.correction_rate == round(2 / 4, 6)


# ---------------------------------------------------------------------------
# Test 7: zero field_total produces None rates
# ---------------------------------------------------------------------------

def test_aggregate_zero_field_total_yields_none_rates() -> None:
    dm = _dm(
        "doc-0",
        field_total=0,
        field_correct=0,
        field_accuracy=None,
        field_precision=None,
        field_recall=None,
        field_f1=None,
        missing_expected_field_count=0,
        corrected_field_count=0,
    )
    _, profile = _profile("doc-0")
    agg = PolicyPerformanceAggregator()
    records = agg.aggregate([dm], {"doc-0": profile})

    rec = records[0]
    assert rec.missing_rate is None
    assert rec.correction_rate is None
    assert rec.field_accuracy is None
