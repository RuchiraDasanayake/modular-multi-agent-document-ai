"""End-to-end integration test: runtime execution path followed by post-review evaluation path.

Demonstrates that both paths coexist in the same artifact store without conflicts:
  JobRunService → runtime artifacts (metrics_report.json, final_output.json, ...)
  ReviewEvaluationApplicationService → reviewed artifacts (document_metrics.json, reviewed_metrics_report.json)
"""

from __future__ import annotations

from datetime import datetime, timezone

from docai_core.application.job_run_service import JobRunRequest, JobRunService
from docai_core.application.review_evaluation_service import (
    ReviewEvaluationAppRequest,
    ReviewEvaluationApplicationService,
)
from docai_core.artifacts.store import ArtifactStore
from docai_core.contracts.domain import (
    Document,
    DocumentProfile,
    ExtractionSchema,
    Field,
    FieldOutput,
    FinalOutput,
    Job,
    Project,
    RecoveryReport,
    ValidationReport,
)
from docai_core.review.review_service import ReviewService

_NOW = datetime.now(timezone.utc)
_JOB_ID = "job-e2e"
_SCHEMA_ID = "schema-e2e"


def _project() -> Project:
    return Project(
        project_id="proj-e2e",
        name="E2E Demo Project",
        description="End-to-end demo",
        created_at=_NOW,
        updated_at=_NOW,
    )


def _schema() -> ExtractionSchema:
    return ExtractionSchema(
        schema_id=_SCHEMA_ID,
        project_id="proj-e2e",
        name="Invoice Schema",
        description="Simple invoice schema for e2e demo",
        version="v1",
        fields=[
            Field(
                field_id="f-1",
                name="invoice_number",
                description="Invoice number",
                type="string",
                required=True,
            ),
            Field(
                field_id="f-2",
                name="vendor_name",
                description="Vendor name",
                type="string",
                required=True,
            ),
        ],
        tables=[],
        created_at=_NOW,
        updated_at=_NOW,
    )


def _job() -> Job:
    return Job(
        job_id=_JOB_ID,
        project_id="proj-e2e",
        schema_id=_SCHEMA_ID,
        name="E2E Demo Run",
        run_type="training",
        status="queued",
        created_at=_NOW,
    )


def _documents() -> list[Document]:
    return [
        Document(
            document_id="doc-1",
            job_id=_JOB_ID,
            original_filename="invoice_001.pdf",
            file_path="invoice_001.pdf",
            status="uploaded",
            uploaded_at=_NOW,
            profile=DocumentProfile(document_id="doc-1"),
        ),
        Document(
            document_id="doc-2",
            job_id=_JOB_ID,
            original_filename="invoice_002.pdf",
            file_path="invoice_002.pdf",
            status="uploaded",
            uploaded_at=_NOW,
            profile=DocumentProfile(document_id="doc-2"),
        ),
    ]


def _final_output(doc_id: str, invoice_number: str, vendor_name: str) -> FinalOutput:
    return FinalOutput(
        document_id=doc_id,
        schema_id=_SCHEMA_ID,
        policy_id="invoice_basic_local_v1",
        fields=[
            FieldOutput(field_name="invoice_number", value=invoice_number, validation_status="valid"),
            FieldOutput(field_name="vendor_name", value=vendor_name, validation_status="valid"),
        ],
        tables=[],
        validation_report=ValidationReport(document_id=doc_id, pass_status=True, summary="stub"),
        recovery_report=RecoveryReport(document_id=doc_id, attempted=False, summary="stub"),
    )


def test_runtime_then_review_paths_share_artifact_store(tmp_path) -> None:
    store = ArtifactStore(tmp_path)

    # --- Path 1: runtime extraction ---
    run_result = JobRunService(artifact_store=store).run_job(
        JobRunRequest(
            project=_project(),
            schema=_schema(),
            job=_job(),
            documents=_documents(),
        )
    )
    assert run_result.job_id == _JOB_ID
    assert run_result.completed_count == 2

    # Runtime artifacts exist
    assert store.job_artifact_path(_JOB_ID, "metrics_report.json").exists()
    assert store.document_artifact_path(_JOB_ID, "doc-1", "final_output.json").exists()
    assert store.document_artifact_path(_JOB_ID, "doc-2", "final_output.json").exists()

    # Reviewed artifacts not yet present
    assert not store.job_artifact_path(_JOB_ID, "reviewed_metrics_report.json").exists()

    # --- Path 2: post-review evaluation ---
    # doc-1: reviewer accepts extracted values as-is → 100% accuracy
    # doc-2: reviewer corrects invoice_number → that field scores 0%
    fo_doc1 = _final_output("doc-1", invoice_number="INV-001", vendor_name="Acme Corp")
    fo_doc2 = _final_output("doc-2", invoice_number="INV-002", vendor_name="Beta Ltd")

    review_svc = ReviewService()
    ev_doc1 = review_svc.build_expected_values_from_final_output(fo_doc1)
    ev_doc2 = review_svc.build_expected_values_from_final_output(
        fo_doc2,
        field_corrections={"invoice_number": "INV-CORRECTED"},
    )

    eval_result = ReviewEvaluationApplicationService(artifact_store=store).evaluate_reviewed_outputs(
        ReviewEvaluationAppRequest(
            job_id=_JOB_ID,
            final_outputs=[fo_doc1, fo_doc2],
            expected_values_by_document_id={"doc-1": ev_doc1, "doc-2": ev_doc2},
        )
    )

    assert eval_result.job_id == _JOB_ID
    assert eval_result.evaluated_document_count == 2
    assert eval_result.skipped_document_ids == []
    assert eval_result.metrics_status == "review_based"

    # Reviewed artifacts written without overwriting runtime artifacts
    assert store.job_artifact_path(_JOB_ID, "reviewed_metrics_report.json").exists()
    assert store.document_artifact_path(_JOB_ID, "doc-1", "document_metrics.json").exists()
    assert store.document_artifact_path(_JOB_ID, "doc-2", "document_metrics.json").exists()

    # Runtime artifacts still intact
    assert store.job_artifact_path(_JOB_ID, "metrics_report.json").exists()
    assert store.document_artifact_path(_JOB_ID, "doc-1", "final_output.json").exists()
    assert store.document_artifact_path(_JOB_ID, "doc-2", "final_output.json").exists()

    # Job-level reviewed metrics reflect mixed review outcome
    report = store.read_json(store.job_artifact_path(_JOB_ID, "reviewed_metrics_report.json"))
    assert report["metrics_status"] == "review_based"
    assert report["document_count"] == 2

    # doc-1 was accepted as-is: both fields correct
    doc1_metrics = store.read_json(
        store.document_artifact_path(_JOB_ID, "doc-1", "document_metrics.json")
    )
    assert doc1_metrics["field_accuracy"] == 1.0

    # doc-2 had invoice_number corrected: one of two fields wrong
    doc2_metrics = store.read_json(
        store.document_artifact_path(_JOB_ID, "doc-2", "document_metrics.json")
    )
    assert doc2_metrics["field_accuracy"] == 0.5
