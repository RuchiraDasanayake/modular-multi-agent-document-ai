from __future__ import annotations

from dataclasses import dataclass

from docai_core.metrics.evaluator import DocumentMetrics


@dataclass(slots=True)
class JobMetrics:
    job_id: str
    document_count: int
    reviewed_document_count: int
    field_total: int
    field_correct: int
    field_accuracy: float | None
    field_true_positive: int
    field_false_positive: int
    field_false_negative: int
    field_precision: float | None
    field_recall: float | None
    field_f1: float | None
    table_cell_total: int
    table_cell_correct: int
    table_cell_accuracy: float | None
    overall_accuracy: float | None
    corrected_field_count: int
    corrected_table_row_count: int
    missing_expected_field_count: int
    extra_extracted_field_count: int
    metrics_status: str


@dataclass(slots=True)
class JobMetricsAggregator:
    """Aggregates document-level DocumentMetrics into job-level JobMetrics.

    Does not recompute field/table comparisons, inspect FinalOutput or
    ExpectedValues, write artifacts, or mutate any policy or strategy.
    """

    def aggregate_job(
        self,
        job_id: str,
        document_metrics: list[DocumentMetrics],
    ) -> JobMetrics:
        doc_count = len(document_metrics)

        if doc_count == 0:
            return JobMetrics(
                job_id=job_id,
                document_count=0,
                reviewed_document_count=0,
                field_total=0,
                field_correct=0,
                field_accuracy=None,
                field_true_positive=0,
                field_false_positive=0,
                field_false_negative=0,
                field_precision=None,
                field_recall=None,
                field_f1=None,
                table_cell_total=0,
                table_cell_correct=0,
                table_cell_accuracy=None,
                overall_accuracy=None,
                corrected_field_count=0,
                corrected_table_row_count=0,
                missing_expected_field_count=0,
                extra_extracted_field_count=0,
                metrics_status="no_review_evidence",
            )

        field_total = sum(d.field_total for d in document_metrics)
        field_correct = sum(d.field_correct for d in document_metrics)
        tp = sum(d.field_true_positive for d in document_metrics)
        fp = sum(d.field_false_positive for d in document_metrics)
        fn = sum(d.field_false_negative for d in document_metrics)
        table_cell_total = sum(d.table_cell_total for d in document_metrics)
        table_cell_correct = sum(d.table_cell_correct for d in document_metrics)

        field_accuracy = round(field_correct / field_total, 6) if field_total > 0 else None
        field_precision = round(tp / (tp + fp), 6) if (tp + fp) > 0 else None
        field_recall = round(tp / (tp + fn), 6) if (tp + fn) > 0 else None
        if (
            field_precision is not None
            and field_recall is not None
            and (field_precision + field_recall) > 0
        ):
            field_f1: float | None = round(
                2 * field_precision * field_recall / (field_precision + field_recall), 6
            )
        else:
            field_f1 = None

        table_cell_accuracy = (
            round(table_cell_correct / table_cell_total, 6) if table_cell_total > 0 else None
        )
        combined_total = field_total + table_cell_total
        overall_accuracy = (
            round((field_correct + table_cell_correct) / combined_total, 6)
            if combined_total > 0
            else None
        )

        return JobMetrics(
            job_id=job_id,
            document_count=doc_count,
            reviewed_document_count=doc_count,
            field_total=field_total,
            field_correct=field_correct,
            field_accuracy=field_accuracy,
            field_true_positive=tp,
            field_false_positive=fp,
            field_false_negative=fn,
            field_precision=field_precision,
            field_recall=field_recall,
            field_f1=field_f1,
            table_cell_total=table_cell_total,
            table_cell_correct=table_cell_correct,
            table_cell_accuracy=table_cell_accuracy,
            overall_accuracy=overall_accuracy,
            corrected_field_count=sum(d.corrected_field_count for d in document_metrics),
            corrected_table_row_count=sum(d.corrected_table_row_count for d in document_metrics),
            missing_expected_field_count=sum(d.missing_expected_field_count for d in document_metrics),
            extra_extracted_field_count=sum(d.extra_extracted_field_count for d in document_metrics),
            metrics_status="review_based",
        )

    def aggregate_jobs(
        self,
        job_metrics_by_job_id: dict[str, list[DocumentMetrics]],
    ) -> list[JobMetrics]:
        return [
            self.aggregate_job(job_id, doc_metrics)
            for job_id, doc_metrics in job_metrics_by_job_id.items()
        ]
