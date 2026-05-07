from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from docai_core.contracts.domain import Document, ExtractionSchema, Job, JobContext, Project, ProjectContext


@dataclass(slots=True)
class JobContextBuilder:
    def build_job_context(
        self,
        project: Project,
        schema: ExtractionSchema,
        job: Job,
        documents: list[Document],
        project_context: ProjectContext | None = None,
    ) -> JobContext:
        base_context = project_context or self._default_project_context(project, schema, job)
        snapshot = ProjectContext(**base_context.to_dict())

        return JobContext(
            job_id=job.job_id,
            project_id=project.project_id,
            schema_id=schema.schema_id,
            run_type=job.run_type,
            job_name=job.name,
            run_notes=None,
            selected_model_config={},
            selected_ocr_preference=snapshot.ocr_preference,
            strategy_mode="deterministic_policy",
            project_context_snapshot=snapshot,
            document_count=len(documents),
            queued_document_ids=[document.document_id for document in documents],
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )

    @staticmethod
    def _default_project_context(project: Project, schema: ExtractionSchema, job: Job) -> ProjectContext:
        updated_at = job.created_at or datetime.now(timezone.utc)
        return ProjectContext(
            project_id=project.project_id,
            domain="general",
            document_type="document",
            extraction_goal=f"Extract data for schema '{schema.name}'.",
            precision_preference="balanced",
            local_model="stub_local_model",
            ocr_preference="stub_ocr",
            field_hints=[field.name for field in schema.fields],
            table_hints=[table.name for table in schema.tables],
            known_edge_cases=[],
            approved_examples=[],
            validation_preferences={},
            recovery_preferences={},
            preferred_strategies=[],
            failed_strategies=[],
            review_lessons=[],
            learning_summary=None,
            version="v1",
            updated_at=updated_at,
        )
