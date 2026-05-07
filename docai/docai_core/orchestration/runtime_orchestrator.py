from __future__ import annotations

from dataclasses import asdict, dataclass, field as dc_field
from pathlib import Path

from docai_core.artifacts.run_artifact_writer import RunArtifactWriter
from docai_core.artifacts.store import ArtifactStore
from docai_core.capabilities.registry import CapabilityRegistry
from docai_core.contracts.domain import (
    AvailableTool,
    Document,
    ExtractionSchema,
    FinalOutput,
    Job,
    Project,
)
from docai_core.metrics.stub_metrics_service import StubMetricsService
from docai_core.extraction.stub_extraction_runner import StubExtractionRunner
from docai_core.orchestration.document_processor import DocumentProcessor
from docai_core.orchestration.document_queue import DocumentQueueBuilder
from docai_core.orchestration.job_context import JobContextBuilder
from docai_core.orchestration.pipeline_config import RuntimePipelineConfig
from docai_core.orchestration.pipeline_factory import build_stub_pipeline
from docai_core.planning.run_plan_builder import RunPlanBuilder
from docai_core.policies.assigner import StrategyAssigner
from docai_core.policies.registry import PolicyRegistry
from docai_core.recovery.stub_recovery_runner import StubRecoveryRunner
from docai_core.validation.stub_validation_runner import StubValidationRunner


@dataclass(slots=True)
class RuntimeOrchestrator:
    """Coordinates job-level runtime flow: context, queue, per-document processing, and artifact writing.
    Per-document processing is delegated to DocumentProcessor. Do not add real OCR, LLM, learning,
    API, or production infrastructure logic directly here."""

    artifact_store: ArtifactStore
    strategy_assigner: StrategyAssigner | None = None
    capability_registry: CapabilityRegistry = dc_field(default_factory=CapabilityRegistry)
    job_context_builder: JobContextBuilder = dc_field(default_factory=JobContextBuilder)
    document_queue_builder: DocumentQueueBuilder = dc_field(default_factory=DocumentQueueBuilder)
    run_plan_builder: RunPlanBuilder = dc_field(default_factory=RunPlanBuilder)
    stub_extraction_runner: StubExtractionRunner = dc_field(default_factory=StubExtractionRunner)
    stub_validation_runner: StubValidationRunner = dc_field(default_factory=StubValidationRunner)
    stub_recovery_runner: StubRecoveryRunner = dc_field(default_factory=StubRecoveryRunner)
    pipeline_config: RuntimePipelineConfig | None = None

    def run_job(
        self,
        project: Project,
        schema: ExtractionSchema,
        job: Job,
        documents: list[Document],
    ) -> dict:
        cfg = self.pipeline_config or build_stub_pipeline()
        self._ensure_stub_capabilities_registered()
        available_tools = self.capability_registry.snapshot()

        writer = RunArtifactWriter(
            artifact_store=self.artifact_store,
            generated_by=cfg.generated_by,
            stub_note=cfg.note,
            is_stub=cfg.is_stub,
        )
        document_processor = cfg.document_processor

        writer.create_job(job.job_id)
        job_context = self.job_context_builder.build_job_context(project, schema, job, documents)
        document_queue = self.document_queue_builder.build_queue(job, documents)

        job_context.is_stub = cfg.is_stub
        job_context.generated_by = cfg.generated_by
        job_context.note = cfg.note

        writer.write_job_context(job.job_id, job_context)
        writer.write_document_queue(job.job_id, document_queue)
        writer.append_run_log(job.job_id, {"event": "job_started", "job_id": job.job_id})

        policies_used: list[str] = []
        final_outputs: list[dict] = []
        final_output_objects: list[FinalOutput] = []

        for document in documents:
            writer.create_document(job.job_id, document.document_id)
            result = document_processor.process_document(schema, document, available_tools)

            ocr_path = writer.document_artifact_path(job.job_id, document.document_id, "ocr_output.json")
            extracted_path = writer.document_artifact_path(job.job_id, document.document_id, "extracted_output.json")
            validation_path = writer.document_artifact_path(job.job_id, document.document_id, "validation_report.json")
            recovery_path = writer.document_artifact_path(job.job_id, document.document_id, "recovery_report.json")
            final_path = writer.document_artifact_path(job.job_id, document.document_id, "final_output.json")

            result.ocr_output.artifact_paths = [str(ocr_path)]
            result.extracted_output.artifact_paths = [str(extracted_path)]
            result.validation_report.artifact_paths = [str(validation_path)]
            result.recovery_report.artifact_paths = [str(recovery_path)]
            result.final_output.artifact_paths = [str(final_path)]

            writer.write_document_profile(job.job_id, document.document_id, result.document_profile)
            writer.write_selected_policy(job.job_id, document.document_id, result.selected_policy)
            writer.write_run_plan(job.job_id, document.document_id, result.run_plan)
            writer.write_ocr_output(job.job_id, document.document_id, result.ocr_output)
            writer.write_extracted_output(job.job_id, document.document_id, result.extracted_output)
            writer.write_validation_report(job.job_id, document.document_id, result.validation_report)
            writer.write_recovery_report(job.job_id, document.document_id, result.recovery_report)
            writer.write_final_output(job.job_id, document.document_id, result.final_output)

            policies_used.append(result.selected_policy.policy_id)
            final_output_objects.append(result.final_output)
            final_outputs.append(result.final_output.to_dict())
            writer.append_run_log(
                job.job_id,
                {
                    "event": "document_completed",
                    "job_id": job.job_id,
                    "document_id": document.document_id,
                    "policy_id": result.selected_policy.policy_id,
                },
            )

        metrics_summary = StubMetricsService().compute_job_metrics(job.job_id, final_output_objects)
        writer.write_metrics_report(job.job_id, asdict(metrics_summary))
        writer.write_extracted_data_export(
            job.job_id,
            {
                "job_id": job.job_id,
                "document_count": len(documents),
                "documents": final_outputs,
            },
        )
        writer.append_run_log(
            job.job_id,
            {"event": "job_completed", "job_id": job.job_id, "completed_count": len(documents)},
        )

        return {
            "job_id": job.job_id,
            "document_count": len(documents),
            "completed_count": len(documents),
            "artifact_root": str(self.artifact_store.job_dir(job.job_id)),
            "policies_used": sorted(set(policies_used)),
            "is_stub": cfg.is_stub,
            "generated_by": cfg.generated_by,
            "note": cfg.note,
        }

    def _default_strategy_assigner(self) -> StrategyAssigner:
        policy_dir = Path(__file__).resolve().parents[2] / "configs" / "policies"
        return StrategyAssigner(registry=PolicyRegistry(policy_dir))

    def _ensure_stub_capabilities_registered(self) -> None:
        # Stub-only runtime spine fallback. Do not add real tool integration here.
        if (
            self.capability_registry.available_tools.available_ocr_engines
            or self.capability_registry.available_tools.available_parsers
            or self.capability_registry.available_tools.available_models
            or self.capability_registry.available_tools.available_validators
            or self.capability_registry.available_tools.available_recovery_strategies
        ):
            return

        tool = AvailableTool(
            tool_id="stub_ocr_parser_model",
            tool_type="ocr_parser_model",
            capabilities=[
                "text_output",
                "bbox_output",
                "table_detection",
                "json_output",
            ],
            enabled=True,
        )
        self.capability_registry.register_ocr_engine(tool)
        self.capability_registry.register_parser(tool)
        self.capability_registry.register_model(tool)
