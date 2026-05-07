from __future__ import annotations

from docai_core.application.review_evaluation_service import (
    ReviewEvaluationAppRequest,
    ReviewEvaluationAppResult,
    ReviewEvaluationApplicationService,
)
from docai_core.artifacts.store import ArtifactStore


def test_request_dataclass_construction() -> None:
    req = ReviewEvaluationAppRequest(
        job_id="job-1",
        final_outputs=[],
        expected_values_by_document_id={},
    )
    assert req.job_id == "job-1"
    assert req.final_outputs == []
    assert req.expected_values_by_document_id == {}


def test_result_dataclass_construction() -> None:
    result = ReviewEvaluationAppResult(
        job_id="job-1",
        evaluated_document_count=2,
        skipped_document_ids=[],
        document_metrics_count=2,
        metrics_status="review_based",
        reviewed_metrics_artifact="/runs/job-1/reviewed_metrics_report.json",
        document_metrics_artifacts={
            "doc-1": "/runs/job-1/documents/doc-1/document_metrics.json",
            "doc-2": "/runs/job-1/documents/doc-2/document_metrics.json",
        },
    )
    assert result.job_id == "job-1"
    assert result.evaluated_document_count == 2
    assert result.metrics_status == "review_based"
    assert "doc-1" in result.document_metrics_artifacts
    assert "doc-2" in result.document_metrics_artifacts


def test_service_holds_artifact_store(tmp_path) -> None:
    store = ArtifactStore(tmp_path)
    svc = ReviewEvaluationApplicationService(artifact_store=store)
    assert svc.artifact_store is store
