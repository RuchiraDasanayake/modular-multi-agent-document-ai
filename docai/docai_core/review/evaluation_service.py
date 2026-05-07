from __future__ import annotations

from dataclasses import dataclass, field as dc_field

from docai_core.artifacts.run_artifact_writer import RunArtifactWriter
from docai_core.artifacts.store import ArtifactStore
from docai_core.contracts.domain import FinalOutput
from docai_core.metrics.aggregator import JobMetrics, JobMetricsAggregator
from docai_core.metrics.evaluator import DocumentMetrics, MetricsEvaluator
from docai_core.review.expected_values import ExpectedValues


@dataclass(slots=True)
class ReviewEvaluationRequest:
    job_id: str
    final_outputs: list[FinalOutput]
    expected_values_by_document_id: dict[str, ExpectedValues]


@dataclass(slots=True)
class ReviewEvaluationResult:
    job_id: str
    document_metrics: list[DocumentMetrics]
    job_metrics: JobMetrics
    evaluated_document_count: int
    skipped_document_ids: list[str]


@dataclass(slots=True)
class ReviewEvaluationService:
    """Coordinates post-review metrics evaluation and artifact writing.

    For each FinalOutput that has a matching ExpectedValues entry, computes
    DocumentMetrics, writes document_metrics.json, then aggregates to
    JobMetrics and writes reviewed_metrics_report.json.

    Does not perform extraction, run planning, strategy assignment, or learning.
    Does not evaluate documents that lack ExpectedValues.
    """

    artifact_store: ArtifactStore
    generated_by: str = "review_evaluation_service"
    note: str = "Review-based metrics computed from FinalOutput and ExpectedValues."

    def evaluate(self, request: ReviewEvaluationRequest) -> ReviewEvaluationResult:
        writer = RunArtifactWriter(
            artifact_store=self.artifact_store,
            generated_by=self.generated_by,
            stub_note=self.note,
        )
        evaluator = MetricsEvaluator()
        document_metrics: list[DocumentMetrics] = []
        skipped: list[str] = []

        for final_output in request.final_outputs:
            ev = request.expected_values_by_document_id.get(final_output.document_id)
            if ev is None:
                skipped.append(final_output.document_id)
                continue
            doc_metrics = evaluator.evaluate_document(final_output, ev)
            writer.write_document_metrics(request.job_id, final_output.document_id, doc_metrics)
            document_metrics.append(doc_metrics)

        job_metrics = JobMetricsAggregator().aggregate_job(request.job_id, document_metrics)
        writer.write_reviewed_metrics_report(request.job_id, job_metrics)

        return ReviewEvaluationResult(
            job_id=request.job_id,
            document_metrics=document_metrics,
            job_metrics=job_metrics,
            evaluated_document_count=len(document_metrics),
            skipped_document_ids=skipped,
        )
