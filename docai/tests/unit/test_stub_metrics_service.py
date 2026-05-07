from __future__ import annotations

from docai_core.contracts.domain import (
    FieldOutput,
    FinalOutput,
    RecoveryReport,
    TableOutput,
    ValidationReport,
)
from docai_core.metrics.stub_metrics_service import StubMetricsService


def _make_final_output(
    doc_id: str,
    validation_pass: bool,
    recovery_attempted: bool,
    recovery_status: str = "not_attempted",
) -> FinalOutput:
    return FinalOutput(
        document_id=doc_id,
        schema_id="schema-1",
        policy_id="invoice_table_heavy_local_v1",
        fields=[FieldOutput(field_name="invoice_number", value="INV-001", validation_status="valid")],
        tables=[],
        validation_report=ValidationReport(
            document_id=doc_id,
            pass_status=validation_pass,
            summary="stub",
        ),
        recovery_report=RecoveryReport(
            document_id=doc_id,
            attempted=recovery_attempted,
            status=recovery_status,
            summary="stub",
        ),
    )


def test_compute_job_metrics_all_passing() -> None:
    service = StubMetricsService()
    outputs = [
        _make_final_output("doc-1", validation_pass=True, recovery_attempted=False),
        _make_final_output("doc-2", validation_pass=True, recovery_attempted=False),
    ]

    summary = service.compute_job_metrics("job-1", outputs)

    assert summary.job_id == "job-1"
    assert summary.document_count == 2
    assert summary.validation_pass_count == 2
    assert summary.validation_pass_rate == 1.0
    assert summary.recovery_attempted_count == 0
    assert summary.recovery_success_rate is None
    assert summary.metrics_status == "partial_stub"
    # Review-dependent metrics must remain None
    assert summary.precision is None
    assert summary.recall is None
    assert summary.f1 is None
    assert summary.field_accuracy is None
    assert summary.table_accuracy is None


def test_compute_job_metrics_partial_pass() -> None:
    service = StubMetricsService()
    outputs = [
        _make_final_output("doc-1", validation_pass=True, recovery_attempted=False),
        _make_final_output("doc-2", validation_pass=False, recovery_attempted=True, recovery_status="recovered"),
        _make_final_output("doc-3", validation_pass=False, recovery_attempted=True, recovery_status="failed"),
    ]

    summary = service.compute_job_metrics("job-1", outputs)

    assert summary.document_count == 3
    assert summary.validation_pass_count == 1
    assert summary.validation_pass_rate == round(1 / 3, 4)
    assert summary.recovery_attempted_count == 2
    assert summary.recovery_success_count == 1
    assert summary.recovery_success_rate == 0.5


def test_compute_job_metrics_empty_outputs() -> None:
    service = StubMetricsService()
    summary = service.compute_job_metrics("job-1", [])

    assert summary.document_count == 0
    assert summary.validation_pass_rate is None
    assert summary.recovery_success_rate is None
