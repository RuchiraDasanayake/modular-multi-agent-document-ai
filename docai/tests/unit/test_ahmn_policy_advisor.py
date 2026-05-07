"""Unit tests for AHMNPolicyAdvisor v1 — read-only recommendation layer."""

from __future__ import annotations

from datetime import datetime, timezone

from docai_core.metrics.policy_performance import PolicyPerformanceRecord
from docai_core.policies.ahmn_policy_advisor import AHMNPolicyAdvisor, AHMNPolicyRecommendation


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _record(
    policy_id: str,
    document_type: str = "invoice",
    quality_bin: str = "clean",
    document_count: int = 20,
    field_f1: float | None = 0.90,
    field_accuracy: float | None = 0.92,
    field_precision: float | None = 0.91,
    field_recall: float | None = 0.89,
    missing_rate: float | None = 0.05,
    correction_rate: float | None = 0.03,
    policy_version: str = "v1",
) -> PolicyPerformanceRecord:
    return PolicyPerformanceRecord(
        policy_id=policy_id,
        policy_version=policy_version,
        document_type=document_type,
        quality_bin=quality_bin,
        document_count=document_count,
        field_accuracy=field_accuracy,
        field_precision=field_precision,
        field_recall=field_recall,
        field_f1=field_f1,
        missing_rate=missing_rate,
        correction_rate=correction_rate,
        evaluated_at=_now(),
    )


# ---------------------------------------------------------------------------
# Test 1: recommends highest F1 among matching profile records
# ---------------------------------------------------------------------------

def test_recommends_highest_f1_matching_profile() -> None:
    low = _record("policy_kv", field_f1=0.70, missing_rate=0.05, correction_rate=0.02)
    high = _record("policy_model", field_f1=0.95, missing_rate=0.01, correction_rate=0.01)

    advisor = AHMNPolicyAdvisor(min_document_count=10)
    rec = advisor.recommend([low, high], document_type="invoice", quality_bin="clean")

    assert rec is not None
    assert isinstance(rec, AHMNPolicyRecommendation)
    assert rec.policy_id == "policy_model"
    assert rec.field_f1 == 0.95
    assert rec.evidence_document_count == 20


# ---------------------------------------------------------------------------
# Test 2: filters by document_type — receipt record not used for invoice
# ---------------------------------------------------------------------------

def test_filters_by_document_type() -> None:
    receipt_rec = _record("receipt_policy", document_type="receipt", quality_bin="clean")
    invoice_rec = _record("invoice_policy", document_type="invoice", quality_bin="clean", field_f1=0.80)

    advisor = AHMNPolicyAdvisor(min_document_count=10)
    rec = advisor.recommend(
        [receipt_rec, invoice_rec], document_type="invoice", quality_bin="clean"
    )

    assert rec is not None
    assert rec.policy_id == "invoice_policy"
    assert rec.document_type == "invoice"


# ---------------------------------------------------------------------------
# Test 3: filters by quality_bin — low-quality record not used for high
# ---------------------------------------------------------------------------

def test_filters_by_quality_bin() -> None:
    low_rec = _record("policy_a", quality_bin="low", field_f1=0.99)
    high_rec = _record("policy_b", quality_bin="high", field_f1=0.75)

    advisor = AHMNPolicyAdvisor(min_document_count=10)
    rec = advisor.recommend([low_rec, high_rec], document_type="invoice", quality_bin="high")

    assert rec is not None
    assert rec.policy_id == "policy_b"
    assert rec.quality_bin == "high"


# ---------------------------------------------------------------------------
# Test 4: respects min_document_count — below threshold is excluded
# ---------------------------------------------------------------------------

def test_respects_min_document_count() -> None:
    sparse = _record("sparse_policy", document_count=5, field_f1=0.99)
    sufficient = _record("sufficient_policy", document_count=15, field_f1=0.80)

    advisor = AHMNPolicyAdvisor(min_document_count=10)
    rec = advisor.recommend([sparse, sufficient], document_type="invoice", quality_bin="clean")

    assert rec is not None
    assert rec.policy_id == "sufficient_policy"


# ---------------------------------------------------------------------------
# Test 5: uses accuracy when F1 is None
# ---------------------------------------------------------------------------

def test_uses_accuracy_when_f1_missing() -> None:
    rec_no_f1 = _record(
        "policy_no_f1",
        field_f1=None,
        field_accuracy=0.88,
        missing_rate=0.0,
        correction_rate=0.0,
    )

    advisor = AHMNPolicyAdvisor(min_document_count=10)
    rec = advisor.recommend([rec_no_f1], document_type="invoice", quality_bin="clean")

    assert rec is not None
    assert rec.policy_id == "policy_no_f1"
    assert rec.field_f1 is None
    assert rec.field_accuracy == 0.88
    assert rec.score is not None
    assert rec.score > 0.0
    assert "accuracy" in rec.reason.lower()


# ---------------------------------------------------------------------------
# Test 6: penalizes high missing/correction rates between equal-F1 records
# ---------------------------------------------------------------------------

def test_penalizes_missing_and_correction_rate() -> None:
    messy = _record(
        "messy_policy",
        field_f1=0.90,
        missing_rate=0.40,
        correction_rate=0.30,
    )
    clean = _record(
        "clean_policy",
        field_f1=0.90,
        missing_rate=0.02,
        correction_rate=0.01,
    )

    advisor = AHMNPolicyAdvisor(min_document_count=10)
    rec = advisor.recommend([messy, clean], document_type="invoice", quality_bin="clean")

    assert rec is not None
    assert rec.policy_id == "clean_policy"


# ---------------------------------------------------------------------------
# Test 7: returns None when no eligible records
# ---------------------------------------------------------------------------

def test_returns_none_when_no_eligible_records() -> None:
    too_few = _record("policy_a", document_count=3, field_f1=0.99)
    wrong_type = _record("policy_b", document_type="receipt", quality_bin="clean")
    wrong_bin = _record("policy_c", document_type="invoice", quality_bin="low")

    advisor = AHMNPolicyAdvisor(min_document_count=10)
    rec = advisor.recommend(
        [too_few, wrong_type, wrong_bin], document_type="invoice", quality_bin="clean"
    )

    assert rec is None


# ---------------------------------------------------------------------------
# Test 8: public export from docai_core.policies
# ---------------------------------------------------------------------------

def test_public_export_available() -> None:
    from docai_core.policies import AHMNPolicyAdvisor as Advisor
    from docai_core.policies import AHMNPolicyRecommendation as Rec

    assert Advisor is AHMNPolicyAdvisor
    assert Rec is AHMNPolicyRecommendation
