"""Unit tests for AHMNAdvisoryService v1."""

from __future__ import annotations

from datetime import datetime, timezone

from docai_core.metrics.policy_performance import PolicyPerformanceRecord
from docai_core.application.ahmn_advisory_service import (
    AHMNAdvisoryRequest,
    AHMNAdvisoryResult,
    AHMNAdvisoryService,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _record(
    policy_id: str,
    document_type: str = "invoice",
    quality_bin: str = "clean",
    document_count: int = 20,
    field_f1: float | None = 0.88,
    field_accuracy: float | None = 0.90,
    missing_rate: float | None = 0.02,
    correction_rate: float | None = 0.01,
) -> PolicyPerformanceRecord:
    return PolicyPerformanceRecord(
        policy_id=policy_id,
        policy_version="v1",
        document_type=document_type,
        quality_bin=quality_bin,
        document_count=document_count,
        field_accuracy=field_accuracy,
        field_precision=field_accuracy,
        field_recall=field_accuracy,
        field_f1=field_f1,
        missing_rate=missing_rate,
        correction_rate=correction_rate,
        evaluated_at=_now(),
    )


# ---------------------------------------------------------------------------
# Test 1: service returns recommendation when eligible evidence exists
# ---------------------------------------------------------------------------

def test_service_returns_recommendation_when_evidence_exists() -> None:
    low = _record("policy_kv", field_f1=0.70)
    high = _record("policy_model", field_f1=0.95)

    svc = AHMNAdvisoryService()
    result = svc.recommend(
        AHMNAdvisoryRequest(
            records=[low, high],
            document_type="invoice",
            quality_bin="clean",
            min_document_count=10,
        )
    )

    assert isinstance(result, AHMNAdvisoryResult)
    assert result.status == "recommended"
    assert result.recommendation is not None
    assert result.recommendation.policy_id == "policy_model"


# ---------------------------------------------------------------------------
# Test 2: returns no_recommendation when records list is empty
# ---------------------------------------------------------------------------

def test_service_returns_no_recommendation_when_no_records() -> None:
    svc = AHMNAdvisoryService()
    result = svc.recommend(
        AHMNAdvisoryRequest(
            records=[],
            document_type="invoice",
            quality_bin="clean",
        )
    )

    assert result.status == "no_recommendation"
    assert result.recommendation is None
    assert result.reason


# ---------------------------------------------------------------------------
# Test 3: service respects min_document_count from the request
# ---------------------------------------------------------------------------

def test_service_respects_min_document_count() -> None:
    sparse = _record("sparse_policy", document_count=5, field_f1=0.99)

    svc = AHMNAdvisoryService()
    result = svc.recommend(
        AHMNAdvisoryRequest(
            records=[sparse],
            document_type="invoice",
            quality_bin="clean",
            min_document_count=10,
        )
    )

    assert result.status == "no_recommendation"
    assert result.recommendation is None


# ---------------------------------------------------------------------------
# Test 4: service does not mutate the input records list
# ---------------------------------------------------------------------------

def test_service_does_not_mutate_records() -> None:
    rec = _record("policy_a")
    original_count = rec.document_count
    original_f1 = rec.field_f1
    records = [rec]

    svc = AHMNAdvisoryService()
    svc.recommend(
        AHMNAdvisoryRequest(records=records, document_type="invoice", quality_bin="clean")
    )

    assert len(records) == 1
    assert records[0].document_count == original_count
    assert records[0].field_f1 == original_f1
    assert records[0].policy_id == "policy_a"


# ---------------------------------------------------------------------------
# Test 5: result reason is human-readable and mentions key context
# ---------------------------------------------------------------------------

def test_result_reason_is_human_readable() -> None:
    rec = _record("best_policy", field_f1=0.92)

    svc = AHMNAdvisoryService()

    result_with = svc.recommend(
        AHMNAdvisoryRequest(
            records=[rec],
            document_type="invoice",
            quality_bin="clean",
            min_document_count=10,
        )
    )
    assert result_with.status == "recommended"
    reason = result_with.reason
    assert len(reason) > 10
    assert any(word in reason.lower() for word in ("reviewed", "evidence", "selected", "f1", "accuracy"))

    result_without = svc.recommend(
        AHMNAdvisoryRequest(
            records=[],
            document_type="invoice",
            quality_bin="clean",
        )
    )
    assert result_without.status == "no_recommendation"
    no_reason = result_without.reason
    assert len(no_reason) > 10
    assert any(word in no_reason.lower() for word in ("no eligible", "evidence", "recommendation"))
