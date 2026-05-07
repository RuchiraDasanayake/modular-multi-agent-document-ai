from __future__ import annotations

from docai_core.metrics.aggregator import JobMetricsAggregator
from docai_core.metrics.evaluator import DocumentMetrics


def _dm(
    doc_id: str = "doc-1",
    field_total: int = 2,
    field_correct: int = 2,
    field_accuracy: float | None = 1.0,
    tp: int = 2,
    fp: int = 0,
    fn: int = 0,
    field_precision: float | None = 1.0,
    field_recall: float | None = 1.0,
    field_f1: float | None = 1.0,
    table_cell_total: int = 2,
    table_cell_correct: int = 2,
    table_cell_accuracy: float | None = 1.0,
    overall_accuracy: float | None = 1.0,
    corrected_field_count: int = 0,
    corrected_table_row_count: int = 0,
    missing_expected_field_count: int = 0,
    extra_extracted_field_count: int = 0,
) -> DocumentMetrics:
    return DocumentMetrics(
        document_id=doc_id,
        schema_id="schema-1",
        field_total=field_total,
        field_correct=field_correct,
        field_accuracy=field_accuracy,
        table_cell_total=table_cell_total,
        table_cell_correct=table_cell_correct,
        table_cell_accuracy=table_cell_accuracy,
        overall_accuracy=overall_accuracy,
        corrected_field_count=corrected_field_count,
        corrected_table_row_count=corrected_table_row_count,
        missing_expected_field_count=missing_expected_field_count,
        extra_extracted_field_count=extra_extracted_field_count,
        field_true_positive=tp,
        field_false_positive=fp,
        field_false_negative=fn,
        field_precision=field_precision,
        field_recall=field_recall,
        field_f1=field_f1,
    )


# ---------------------------------------------------------------------------
# Test 1: two perfect documents
# ---------------------------------------------------------------------------

def test_aggregate_two_perfect_documents() -> None:
    agg = JobMetricsAggregator()
    docs = [_dm("doc-1"), _dm("doc-2")]

    result = agg.aggregate_job("job-1", docs)

    assert result.document_count == 2
    assert result.reviewed_document_count == 2
    assert result.field_accuracy == 1.0
    assert result.table_cell_accuracy == 1.0
    assert result.overall_accuracy == 1.0
    assert result.metrics_status == "review_based"


# ---------------------------------------------------------------------------
# Test 2: mixed correct/incorrect — summed TP/FP/FN, precision/recall/F1
# ---------------------------------------------------------------------------

def test_aggregate_mixed_field_metrics() -> None:
    # doc-1: all correct — TP=2, FP=0, FN=0
    # doc-2: one wrong value — TP=1, FP=1, FN=1
    doc1 = _dm("doc-1", field_total=2, field_correct=2, tp=2, fp=0, fn=0,
               field_precision=1.0, field_recall=1.0, field_f1=1.0,
               table_cell_total=0, table_cell_correct=0,
               table_cell_accuracy=None, overall_accuracy=1.0)
    doc2 = _dm("doc-2", field_total=2, field_correct=1, tp=1, fp=1, fn=1,
               field_precision=0.5, field_recall=0.5, field_f1=0.5,
               table_cell_total=0, table_cell_correct=0,
               table_cell_accuracy=None, overall_accuracy=0.5)

    result = JobMetricsAggregator().aggregate_job("job-1", [doc1, doc2])

    assert result.field_total == 4
    assert result.field_correct == 3
    assert result.field_true_positive == 3
    assert result.field_false_positive == 1
    assert result.field_false_negative == 1
    # precision = 3/(3+1) = 0.75; recall = 3/(3+1) = 0.75; f1 = 0.75
    assert result.field_precision == 0.75
    assert result.field_recall == 0.75
    assert result.field_f1 == 0.75
    assert result.field_accuracy == 0.75


# ---------------------------------------------------------------------------
# Test 3: table cell aggregation
# ---------------------------------------------------------------------------

def test_aggregate_table_cell_metrics() -> None:
    doc1 = _dm("doc-1", field_total=0, field_correct=0, field_accuracy=None,
               tp=0, fp=0, fn=0, field_precision=None, field_recall=None, field_f1=None,
               table_cell_total=4, table_cell_correct=3, table_cell_accuracy=0.75,
               overall_accuracy=0.75)
    doc2 = _dm("doc-2", field_total=0, field_correct=0, field_accuracy=None,
               tp=0, fp=0, fn=0, field_precision=None, field_recall=None, field_f1=None,
               table_cell_total=2, table_cell_correct=2, table_cell_accuracy=1.0,
               overall_accuracy=1.0)

    result = JobMetricsAggregator().aggregate_job("job-1", [doc1, doc2])

    assert result.table_cell_total == 6
    assert result.table_cell_correct == 5
    assert result.table_cell_accuracy == round(5 / 6, 6)
    assert result.overall_accuracy == round(5 / 6, 6)


# ---------------------------------------------------------------------------
# Test 4: corrected / missing / extra counts
# ---------------------------------------------------------------------------

def test_aggregate_corrected_and_missing_extra_counts() -> None:
    doc1 = _dm("doc-1", corrected_field_count=1, corrected_table_row_count=2,
               missing_expected_field_count=1, extra_extracted_field_count=0)
    doc2 = _dm("doc-2", corrected_field_count=0, corrected_table_row_count=1,
               missing_expected_field_count=0, extra_extracted_field_count=2)

    result = JobMetricsAggregator().aggregate_job("job-1", [doc1, doc2])

    assert result.corrected_field_count == 1
    assert result.corrected_table_row_count == 3
    assert result.missing_expected_field_count == 1
    assert result.extra_extracted_field_count == 2


# ---------------------------------------------------------------------------
# Test 5: empty document list
# ---------------------------------------------------------------------------

def test_aggregate_empty_document_list() -> None:
    result = JobMetricsAggregator().aggregate_job("job-1", [])

    assert result.document_count == 0
    assert result.reviewed_document_count == 0
    assert result.field_accuracy is None
    assert result.field_precision is None
    assert result.field_recall is None
    assert result.field_f1 is None
    assert result.overall_accuracy is None
    assert result.metrics_status == "no_review_evidence"


# ---------------------------------------------------------------------------
# Test 6: aggregate_jobs with two job IDs
# ---------------------------------------------------------------------------

def test_aggregate_jobs_two_job_ids() -> None:
    result = JobMetricsAggregator().aggregate_jobs({
        "job-1": [_dm("doc-1"), _dm("doc-2")],
        "job-2": [_dm("doc-3")],
    })

    assert len(result) == 2
    job_ids = {jm.job_id for jm in result}
    assert job_ids == {"job-1", "job-2"}
    job1 = next(jm for jm in result if jm.job_id == "job-1")
    job2 = next(jm for jm in result if jm.job_id == "job-2")
    assert job1.document_count == 2
    assert job2.document_count == 1
