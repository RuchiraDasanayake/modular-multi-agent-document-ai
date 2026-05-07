from __future__ import annotations

from dataclasses import dataclass

from docai_core.artifacts.store import ArtifactStore
from docai_core.contracts.domain import Document, ExtractionSchema, Job, Project
from docai_core.orchestration.pipeline_config import RuntimePipelineConfig
from docai_core.orchestration.runtime_orchestrator import RuntimeOrchestrator


@dataclass(slots=True)
class JobRunRequest:
    project: Project
    schema: ExtractionSchema
    job: Job
    documents: list[Document]


@dataclass(slots=True)
class JobRunResult:
    job_id: str
    document_count: int
    completed_count: int
    artifact_root: str
    policies_used: list[str]
    is_stub: bool
    generated_by: str
    note: str | None = None


@dataclass(slots=True)
class JobRunService:
    artifact_store: ArtifactStore
    pipeline_config: RuntimePipelineConfig | None = None

    def run_job(self, request: JobRunRequest) -> JobRunResult:
        extra = {"pipeline_config": self.pipeline_config} if self.pipeline_config is not None else {}
        orchestrator = RuntimeOrchestrator(artifact_store=self.artifact_store, **extra)
        summary = orchestrator.run_job(
            project=request.project,
            schema=request.schema,
            job=request.job,
            documents=request.documents,
        )
        return JobRunResult(
            job_id=summary["job_id"],
            document_count=summary["document_count"],
            completed_count=summary["completed_count"],
            artifact_root=summary["artifact_root"],
            policies_used=summary["policies_used"],
            is_stub=summary["is_stub"],
            generated_by=summary["generated_by"],
            note=summary.get("note"),
        )
