from dataclasses import asdict
from datetime import datetime, timezone

from docai_core.artifacts.run_artifact_writer import RunArtifactWriter
from docai_core.artifacts.store import ArtifactStore
from docai_core.contracts.domain import (
    DocumentProfile,
    RecoveryReport,
    SelectedPolicy,
    ValidationReport,
)
from docai_core.metrics.aggregator import JobMetrics
from docai_core.metrics.evaluator import DocumentMetrics
from docai_core.metrics.stub_metrics_service import JobMetricsSummary
from docai_core.review.expected_values import (
    ExpectedFieldValue,
    ExpectedValues,
    ReviewRecord,
)


def test_run_artifact_writer_writes_stub_document_artifacts(tmp_path) -> None:
    store = ArtifactStore(tmp_path)
    writer = RunArtifactWriter(
        artifact_store=store,
        generated_by="stub_runtime_orchestrator",
        stub_note="Stub output for runtime spine validation only. Not real extraction.",
    )
    writer.create_job("job-1")
    writer.create_document("job-1", "doc-1")

    profile = DocumentProfile(document_id="doc-1", detected_type="document")
    policy = SelectedPolicy(
        policy_id="invoice_basic_local_v1",
        policy_family="invoice_extraction",
        policy_version="v1",
        selected_by="deterministic_strategy_assigner",
    )
    validation = ValidationReport(document_id="doc-1", pass_status=True, summary="stub validation passed")
    recovery = RecoveryReport(document_id="doc-1", attempted=False, summary="stub recovery not attempted")

    writer.write_document_profile("job-1", "doc-1", profile)
    writer.write_selected_policy("job-1", "doc-1", policy)
    writer.write_validation_report("job-1", "doc-1", validation)
    writer.write_recovery_report("job-1", "doc-1", recovery)

    profile_payload = store.read_json(store.document_artifact_path("job-1", "doc-1", "document_profile.json"))
    policy_payload = store.read_json(store.document_artifact_path("job-1", "doc-1", "selected_policy.json"))
    validation_payload = store.read_json(store.document_artifact_path("job-1", "doc-1", "validation_report.json"))
    recovery_payload = store.read_json(store.document_artifact_path("job-1", "doc-1", "recovery_report.json"))

    assert profile_payload["is_stub"] is True
    assert profile_payload["generated_by"] == "stub_runtime_orchestrator"
    assert policy_payload["is_stub"] is True
    assert validation_payload["is_stub"] is True
    assert recovery_payload["is_stub"] is True


def test_run_artifact_writer_writes_job_artifacts(tmp_path) -> None:
    now = datetime.now(timezone.utc)
    store = ArtifactStore(tmp_path)
    writer = RunArtifactWriter(
        artifact_store=store,
        generated_by="stub_runtime_orchestrator",
        stub_note="Stub output for runtime spine validation only. Not real extraction.",
    )
    writer.create_job("job-1")

    writer.write_job_context(
        "job-1",
        {
            "job_id": "job-1",
            "created_at": now,
            "is_stub": True,
            "generated_by": "stub_runtime_orchestrator",
        },
    )
    writer.write_document_queue("job-1", [{"document_id": "doc-1"}])
    writer.append_run_log("job-1", {"event": "job_started", "job_id": "job-1"})
    metrics_summary = JobMetricsSummary(
        job_id="job-1",
        document_count=1,
        validation_pass_count=1,
        validation_pass_rate=1.0,
        recovery_attempted_count=0,
        recovery_success_count=0,
        recovery_success_rate=None,
    )
    writer.write_metrics_report("job-1", asdict(metrics_summary))
    writer.write_extracted_data_export("job-1", {"job_id": "job-1", "document_count": 1, "documents": []})

    queue_payload = store.read_json(store.job_artifact_path("job-1", "document_queue.json"))
    metrics_payload = store.read_json(store.job_artifact_path("job-1", "metrics_report.json"))
    export_payload = store.read_json(store.job_artifact_path("job-1", "extracted_data_export.json"))
    run_log = store.read_text(store.job_artifact_path("job-1", "run_log.jsonl"))

    assert queue_payload["is_stub"] is True
    assert metrics_payload["is_stub"] is True
    assert metrics_payload["metrics_status"] == "partial_stub"
    assert metrics_payload["validation_pass_rate"] == 1.0
    assert export_payload["is_stub"] is True
    assert "job_started" in run_log


def test_run_artifact_writer_writes_review_artifacts(tmp_path) -> None:
    store = ArtifactStore(tmp_path)
    writer = RunArtifactWriter(
        artifact_store=store,
        generated_by="stub_runtime_orchestrator",
        stub_note="Stub output for runtime spine validation only. Not real extraction.",
    )
    writer.create_job("job-1")
    writer.create_document("job-1", "doc-1")

    ev = ExpectedValues(
        document_id="doc-1",
        schema_id="schema-1",
        fields=[
            ExpectedFieldValue(
                field_name="invoice_number",
                expected_value="INV-001",
                extracted_value="INV-001",
            )
        ],
    )
    record = ReviewRecord(
        review_id="job-1:doc-1:review",
        job_id="job-1",
        document_id="doc-1",
        schema_id="schema-1",
        run_type="training",
        expected_values=ev,
        review_status="approved",
        approved_final_output=True,
    )

    writer.write_expected_values("job-1", "doc-1", ev)
    writer.write_review_record("job-1", "doc-1", record)

    ev_payload = store.read_json(store.document_artifact_path("job-1", "doc-1", "expected_values.json"))
    rr_payload = store.read_json(store.document_artifact_path("job-1", "doc-1", "review_record.json"))

    assert ev_payload["is_stub"] is True
    assert ev_payload["generated_by"] == "stub_runtime_orchestrator"
    assert ev_payload["note"] == "Stub output for runtime spine validation only. Not real extraction."
    assert ev_payload["document_id"] == "doc-1"

    assert rr_payload["is_stub"] is True
    assert rr_payload["generated_by"] == "stub_runtime_orchestrator"
    assert rr_payload["review_id"] == "job-1:doc-1:review"
    assert rr_payload["review_status"] == "approved"


def test_run_artifact_writer_writes_reviewed_metrics_artifacts(tmp_path) -> None:
    store = ArtifactStore(tmp_path)
    writer = RunArtifactWriter(
        artifact_store=store,
        generated_by="stub_runtime_orchestrator",
        stub_note="Stub output for runtime spine validation only. Not real extraction.",
    )
    writer.create_job("job-1")
    writer.create_document("job-1", "doc-1")

    doc_metrics = DocumentMetrics(
        document_id="doc-1",
        schema_id="schema-1",
        field_total=2,
        field_correct=2,
        field_accuracy=1.0,
        table_cell_total=0,
        table_cell_correct=0,
        table_cell_accuracy=None,
        overall_accuracy=1.0,
        corrected_field_count=0,
        corrected_table_row_count=0,
        missing_expected_field_count=0,
        extra_extracted_field_count=0,
        field_true_positive=2,
        field_false_positive=0,
        field_false_negative=0,
        field_precision=1.0,
        field_recall=1.0,
        field_f1=1.0,
    )
    job_metrics = JobMetrics(
        job_id="job-1",
        document_count=1,
        reviewed_document_count=1,
        field_total=2,
        field_correct=2,
        field_accuracy=1.0,
        field_true_positive=2,
        field_false_positive=0,
        field_false_negative=0,
        field_precision=1.0,
        field_recall=1.0,
        field_f1=1.0,
        table_cell_total=0,
        table_cell_correct=0,
        table_cell_accuracy=None,
        overall_accuracy=1.0,
        corrected_field_count=0,
        corrected_table_row_count=0,
        missing_expected_field_count=0,
        extra_extracted_field_count=0,
        metrics_status="review_based",
    )

    writer.write_document_metrics("job-1", "doc-1", doc_metrics)
    writer.write_reviewed_metrics_report("job-1", job_metrics)

    dm_payload = store.read_json(store.document_artifact_path("job-1", "doc-1", "document_metrics.json"))
    rmr_payload = store.read_json(store.job_artifact_path("job-1", "reviewed_metrics_report.json"))

    assert dm_payload["is_stub"] is True
    assert dm_payload["generated_by"] == "stub_runtime_orchestrator"
    assert dm_payload["note"] == "Stub output for runtime spine validation only. Not real extraction."
    assert dm_payload["document_id"] == "doc-1"
    assert dm_payload["schema_id"] == "schema-1"
    assert dm_payload["field_accuracy"] == 1.0
    assert dm_payload["field_f1"] == 1.0

    assert rmr_payload["is_stub"] is True
    assert rmr_payload["generated_by"] == "stub_runtime_orchestrator"
    assert rmr_payload["job_id"] == "job-1"
    assert rmr_payload["metrics_status"] == "review_based"
    assert rmr_payload["field_accuracy"] == 1.0
    assert rmr_payload["field_f1"] == 1.0


def test_writer_defaults_to_stub_metadata(tmp_path) -> None:
    store = ArtifactStore(tmp_path)
    writer = RunArtifactWriter(
        artifact_store=store,
        generated_by="stub_runtime_orchestrator",
        stub_note="Stub output for runtime spine validation only. Not real extraction.",
    )
    writer.create_job("job-1")
    writer.create_document("job-1", "doc-1")

    profile = DocumentProfile(document_id="doc-1", detected_type="document")
    writer.write_document_profile("job-1", "doc-1", profile)

    payload = store.read_json(store.document_artifact_path("job-1", "doc-1", "document_profile.json"))
    assert payload["is_stub"] is True
    assert payload["generated_by"] == "stub_runtime_orchestrator"


def test_writer_can_write_non_stub_metadata(tmp_path) -> None:
    store = ArtifactStore(tmp_path)
    writer = RunArtifactWriter(
        artifact_store=store,
        generated_by="local_text_pipeline_v1",
        stub_note="Real text acquisition via KVOnlyExtractionRunner. No model inference.",
        is_stub=False,
    )
    writer.create_job("job-1")
    writer.create_document("job-1", "doc-1")

    profile = DocumentProfile(document_id="doc-1", detected_type="document")
    writer.write_document_profile("job-1", "doc-1", profile)

    payload = store.read_json(store.document_artifact_path("job-1", "doc-1", "document_profile.json"))
    assert payload["is_stub"] is False
    assert payload["generated_by"] == "local_text_pipeline_v1"

    writer.write_document_queue("job-1", [{"document_id": "doc-1"}])
    queue_payload = store.read_json(store.job_artifact_path("job-1", "document_queue.json"))
    assert queue_payload["is_stub"] is False

    writer.write_extracted_data_export("job-1", {"job_id": "job-1", "document_count": 1, "documents": []})
    export_payload = store.read_json(store.job_artifact_path("job-1", "extracted_data_export.json"))
    assert export_payload["is_stub"] is False
