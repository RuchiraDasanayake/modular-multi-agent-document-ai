from __future__ import annotations

from dataclasses import dataclass

from docai_core.artifacts.store import ArtifactStore
from docai_core.contracts.domain import FinalOutput
from docai_core.review.evaluation_service import ReviewEvaluationRequest, ReviewEvaluationService
from docai_core.review.expected_values import ExpectedValues


@dataclass(slots=True)
class ReviewEvaluationAppRequest:
    job_id: str
    final_outputs: list[FinalOutput]
    expected_values_by_document_id: dict[str, ExpectedValues]


@dataclass(slots=True)
class ReviewEvaluationAppResult:
    job_id: str
    evaluated_document_count: int
    skipped_document_ids: list[str]
    document_metrics_count: int
    metrics_status: str
    reviewed_metrics_artifact: str
    document_metrics_artifacts: dict[str, str]


@dataclass(slots=True)
class ReviewEvaluationApplicationService:
    """Application-layer entry point for post-review metrics evaluation.

    Delegates to ReviewEvaluationService and returns a stable result with
    artifact path strings. Does not perform extraction, run planning,
    strategy assignment, or learning.
    """

    artifact_store: ArtifactStore

    def evaluate_reviewed_outputs(
        self,
        request: ReviewEvaluationAppRequest,
    ) -> ReviewEvaluationAppResult:
        inner = ReviewEvaluationService(artifact_store=self.artifact_store)
        result = inner.evaluate(
            ReviewEvaluationRequest(
                job_id=request.job_id,
                final_outputs=request.final_outputs,
                expected_values_by_document_id=request.expected_values_by_document_id,
            )
        )

        reviewed_metrics_artifact = str(
            self.artifact_store.job_artifact_path(request.job_id, "reviewed_metrics_report.json")
        )
        document_metrics_artifacts = {
            dm.document_id: str(
                self.artifact_store.document_artifact_path(
                    request.job_id, dm.document_id, "document_metrics.json"
                )
            )
            for dm in result.document_metrics
        }

        return ReviewEvaluationAppResult(
            job_id=result.job_id,
            evaluated_document_count=result.evaluated_document_count,
            skipped_document_ids=result.skipped_document_ids,
            document_metrics_count=len(result.document_metrics),
            metrics_status=result.job_metrics.metrics_status,
            reviewed_metrics_artifact=reviewed_metrics_artifact,
            document_metrics_artifacts=document_metrics_artifacts,
        )
