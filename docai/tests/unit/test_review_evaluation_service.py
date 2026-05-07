from __future__ import annotations

from docai_core.artifacts.store import ArtifactStore
from docai_core.contracts.domain import (
    FieldOutput,
    FinalOutput,
    RecoveryReport,
    RowOutput,
    TableOutput,
    ValidationReport,
)
from docai_core.review.evaluation_service import ReviewEvaluationRequest, ReviewEvaluationService
from docai_core.review.expected_values import ExpectedFieldValue, ExpectedValues

_JOB_ID = "job-1"
_SCHEMA_ID = "schema-1"
_POLICY_ID = "invoice_table_heavy_local_v1"


def _fo(doc_id: str, field_value: str = "INV-001") -> FinalOutput:
    return FinalOutput(
        document_id=doc_id,
        schema_id=_SCHEMA_ID,
        policy_id=_POLICY_ID,
        fields=[FieldOutput(field_name="invoice_number", value=field_value, validation_status="valid")],
        tables=[],
        validation_report=ValidationReport(document_id=doc_id, pass_status=True, summary="stub"),
        recovery_report=RecoveryReport(document_id=doc_id, attempted=False, summary="stub"),
    )


def _ev(doc_id: str, expected: str = "INV-001") -> ExpectedValues:
    return ExpectedValues(
        document_id=doc_id,
        schema_id=_SCHEMA_ID,
        fields=[ExpectedFieldValue(field_name="invoice_number", expected_value=expected)],
    )


def _service(tmp_path) -> ReviewEvaluationService:
    return ReviewEvaluationService(artifact_store=ArtifactStore(tmp_path))


# ---------------------------------------------------------------------------
# Test 1: all documents have ExpectedValues
# ---------------------------------------------------------------------------

def test_evaluate_all_documents_reviewed(tmp_path) -> None:
    service = _service(tmp_path)
    store = service.artifact_store
    store.create_job(_JOB_ID)
    store.create_document(_JOB_ID, "doc-1")
    store.create_document(_JOB_ID, "doc-2")

    request = ReviewEvaluationRequest(
        job_id=_JOB_ID,
        final_outputs=[_fo("doc-1"), _fo("doc-2")],
        expected_values_by_document_id={"doc-1": _ev("doc-1"), "doc-2": _ev("doc-2")},
    )
    result = service.evaluate(request)

    assert result.evaluated_document_count == 2
    assert result.skipped_document_ids == []
    assert len(result.document_metrics) == 2
    assert result.job_metrics.metrics_status == "review_based"

    assert store.document_artifact_path(_JOB_ID, "doc-1", "document_metrics.json").exists()
    assert store.document_artifact_path(_JOB_ID, "doc-2", "document_metrics.json").exists()
    assert store.job_artifact_path(_JOB_ID, "reviewed_metrics_report.json").exists()

    rmr = store.read_json(store.job_artifact_path(_JOB_ID, "reviewed_metrics_report.json"))
    assert rmr["job_id"] == _JOB_ID
    assert rmr["metrics_status"] == "review_based"


# ---------------------------------------------------------------------------
# Test 2: one document missing ExpectedValues — skipped
# ---------------------------------------------------------------------------

def test_evaluate_one_document_skipped(tmp_path) -> None:
    service = _service(tmp_path)
    store = service.artifact_store
    store.create_job(_JOB_ID)
    store.create_document(_JOB_ID, "doc-1")
    store.create_document(_JOB_ID, "doc-2")

    request = ReviewEvaluationRequest(
        job_id=_JOB_ID,
        final_outputs=[_fo("doc-1"), _fo("doc-2")],
        expected_values_by_document_id={"doc-1": _ev("doc-1")},
    )
    result = service.evaluate(request)

    assert result.evaluated_document_count == 1
    assert "doc-2" in result.skipped_document_ids
    assert len(result.document_metrics) == 1
    assert result.job_metrics.document_count == 1

    assert store.document_artifact_path(_JOB_ID, "doc-1", "document_metrics.json").exists()
    assert not store.document_artifact_path(_JOB_ID, "doc-2", "document_metrics.json").exists()
    assert store.job_artifact_path(_JOB_ID, "reviewed_metrics_report.json").exists()


# ---------------------------------------------------------------------------
# Test 3: no documents have ExpectedValues
# ---------------------------------------------------------------------------

def test_evaluate_no_expected_values(tmp_path) -> None:
    service = _service(tmp_path)
    store = service.artifact_store
    store.create_job(_JOB_ID)
    store.create_document(_JOB_ID, "doc-1")
    store.create_document(_JOB_ID, "doc-2")

    request = ReviewEvaluationRequest(
        job_id=_JOB_ID,
        final_outputs=[_fo("doc-1"), _fo("doc-2")],
        expected_values_by_document_id={},
    )
    result = service.evaluate(request)

    assert result.evaluated_document_count == 0
    assert set(result.skipped_document_ids) == {"doc-1", "doc-2"}
    assert result.job_metrics.metrics_status == "no_review_evidence"

    assert store.job_artifact_path(_JOB_ID, "reviewed_metrics_report.json").exists()
    assert not store.document_artifact_path(_JOB_ID, "doc-1", "document_metrics.json").exists()
    assert not store.document_artifact_path(_JOB_ID, "doc-2", "document_metrics.json").exists()
