from datetime import datetime, timezone

from docai_core.application.job_run_service import JobRunRequest, JobRunResult, JobRunService
from docai_core.artifacts.store import ArtifactStore
from docai_core.contracts.domain import Document, DocumentProfile, ExtractionSchema, Job, Project


def test_job_run_service_maps_orchestrator_summary(monkeypatch, tmp_path) -> None:
    now = datetime.now(timezone.utc)

    class FakeRuntimeOrchestrator:
        def __init__(self, artifact_store: ArtifactStore) -> None:
            self.artifact_store = artifact_store

        def run_job(self, project: Project, schema: ExtractionSchema, job: Job, documents: list[Document]) -> dict:
            assert project.project_id == "proj-1"
            assert schema.schema_id == "schema-1"
            assert job.job_id == "job-1"
            assert len(documents) == 1
            return {
                "job_id": "job-1",
                "document_count": 1,
                "completed_count": 1,
                "artifact_root": "runs/job-1",
                "policies_used": ["invoice_basic_local_v1"],
                "is_stub": True,
                "generated_by": "stub_runtime_orchestrator",
                "note": "Stub output for runtime spine validation only. Not real extraction.",
            }

    monkeypatch.setattr(
        "docai_core.application.job_run_service.RuntimeOrchestrator",
        FakeRuntimeOrchestrator,
    )

    request = JobRunRequest(
        project=Project(
            project_id="proj-1",
            name="Demo",
            description="Demo project",
            created_at=now,
            updated_at=now,
        ),
        schema=ExtractionSchema(
            schema_id="schema-1",
            project_id="proj-1",
            name="Schema",
            description="Schema",
            version="v1",
        ),
        job=Job(
            job_id="job-1",
            project_id="proj-1",
            schema_id="schema-1",
            name="Run",
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
            )
        ],
    )
    service = JobRunService(artifact_store=ArtifactStore(tmp_path))

    result = service.run_job(request)

    assert isinstance(result, JobRunResult)
    assert result.job_id == "job-1"
    assert result.document_count == 1
    assert result.completed_count == 1
    assert result.policies_used == ["invoice_basic_local_v1"]
    assert result.is_stub is True
    assert result.generated_by == "stub_runtime_orchestrator"
