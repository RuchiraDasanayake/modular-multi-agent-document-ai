from datetime import datetime, timezone

from docai_core.application.job_run_service import JobRunRequest, JobRunService
from docai_core.artifacts.store import ArtifactStore
from docai_core.contracts.domain import (
    Column,
    Document,
    DocumentProfile,
    ExtractionSchema,
    Field,
    Job,
    Project,
    Table,
)


def test_job_run_service_executes_runtime_orchestrator(tmp_path) -> None:
    now = datetime.now(timezone.utc)
    service = JobRunService(artifact_store=ArtifactStore(tmp_path))

    request = JobRunRequest(
        project=Project(
            project_id="proj-1",
            name="Demo Project",
            description="Demo",
            created_at=now,
            updated_at=now,
        ),
        schema=ExtractionSchema(
            schema_id="schema-1",
            project_id="proj-1",
            name="Invoice Schema",
            description="Invoice extraction schema",
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
                    name="total_amount",
                    description="Total amount",
                    type="string",
                    required=True,
                ),
            ],
            tables=[
                Table(
                    table_id="t-1",
                    name="line_items",
                    description="Invoice rows",
                    columns=[
                        Column(
                            column_id="c-1",
                            name="description",
                            description="Item description",
                            type="string",
                            required=True,
                        ),
                        Column(
                            column_id="c-2",
                            name="line_total",
                            description="Line total",
                            type="string",
                            required=True,
                        ),
                    ],
                )
            ],
            created_at=now,
            updated_at=now,
        ),
        job=Job(
            job_id="job-1",
            project_id="proj-1",
            schema_id="schema-1",
            name="Run 1",
            run_type="training",
            status="queued",
            created_at=now,
        ),
        documents=[
            Document(
                document_id="doc-1",
                job_id="job-1",
                original_filename="invoice_001.pdf",
                file_path="invoice_001.pdf",
                status="uploaded",
                uploaded_at=now,
                profile=DocumentProfile(document_id="doc-1"),
            ),
            Document(
                document_id="doc-2",
                job_id="job-1",
                original_filename="noisy_scan_001.png",
                file_path="noisy_scan_001.png",
                status="uploaded",
                uploaded_at=now,
                profile=DocumentProfile(document_id="doc-2"),
            ),
        ],
    )

    result = service.run_job(request)

    assert result.job_id == "job-1"
    assert result.document_count == 2
    assert result.completed_count == 2
    assert result.is_stub is True
    assert result.generated_by == "stub_runtime_orchestrator"

    store = service.artifact_store
    assert store.job_artifact_path("job-1", "job_context.json").exists()
    assert store.job_artifact_path("job-1", "document_queue.json").exists()
    assert store.job_artifact_path("job-1", "metrics_report.json").exists()
    assert store.job_artifact_path("job-1", "extracted_data_export.json").exists()
    assert store.job_artifact_path("job-1", "run_log.jsonl").exists()
    assert store.document_artifact_path("job-1", "doc-1", "final_output.json").exists()
    assert store.document_artifact_path("job-1", "doc-2", "final_output.json").exists()
