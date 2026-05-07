from __future__ import annotations

from dataclasses import dataclass

from docai_core.contracts.domain import (
    AvailableTools,
    Document,
    DocumentProfile,
    ExtractionSchema,
    ExtractedOutput,
    FinalOutput,
    OCROutput,
    RecoveryReport,
    RunPlan,
    SelectedPolicy,
    ValidationReport,
)
from docai_core.extraction.base import ExtractionRunnerProtocol
from docai_core.extraction.ocr_postprocessor import OCRPostProcessor
from docai_core.extraction.stub_extraction_runner import StubExtractionRunner
from docai_core.planning.run_plan_builder import RunPlanBuilder
from docai_core.policies.assigner import StrategyAssigner
from docai_core.recovery.stub_recovery_runner import StubRecoveryRunner
from docai_core.text_acquisition.router import TextAcquisitionRouter
from docai_core.validation.base import ValidationRunnerProtocol
from docai_core.validation.stub_validation_runner import StubValidationRunner


@dataclass(slots=True)
class DocumentProcessingResult:
    """Holds all per-document artifacts produced by one call to DocumentProcessor.process_document.
    artifact_paths are not set here — RuntimeOrchestrator sets them before writing."""

    document_profile: DocumentProfile
    selected_policy: SelectedPolicy
    run_plan: RunPlan
    ocr_output: OCROutput
    extracted_output: ExtractedOutput
    validation_report: ValidationReport
    recovery_report: RecoveryReport
    final_output: FinalOutput


@dataclass(slots=True)
class DocumentProcessor:
    """Processes exactly one document through the current runtime spine.

    Responsibilities:
    - Profile building
    - Strategy assignment
    - Run plan construction
    - OCR acquisition (real or stub)
    - Extraction (real or stub)
    - Stub validation and recovery
    - FinalOutput assembly

    Real acquisition path: inject text_acquisition_router, ocr_postprocessor,
    and extraction_runner. All three default to None; when absent the stub path
    is used, preserving existing behavior unchanged.

    Does NOT write artifacts, set artifact_paths, or mutate job-level state.
    """

    strategy_assigner: StrategyAssigner
    run_plan_builder: RunPlanBuilder
    stub_extraction_runner: StubExtractionRunner
    stub_validation_runner: StubValidationRunner
    stub_recovery_runner: StubRecoveryRunner
    stub_note: str
    text_acquisition_router: TextAcquisitionRouter | None = None
    ocr_postprocessor: OCRPostProcessor | None = None
    extraction_runner: ExtractionRunnerProtocol | None = None
    validation_runner: ValidationRunnerProtocol | None = None

    def process_document(
        self,
        schema: ExtractionSchema,
        document: Document,
        available_tools: AvailableTools,
    ) -> DocumentProcessingResult:
        profile = self._build_profile(schema, document)
        policy = self.strategy_assigner.assign_strategy(schema, profile, available_tools)
        run_plan = self.run_plan_builder.build_run_plan(schema, document, policy)

        if self.text_acquisition_router is not None:
            raw_ocr = self.text_acquisition_router.extract(document)
            ocr_output = (
                self.ocr_postprocessor.process(raw_ocr)
                if self.ocr_postprocessor is not None
                else raw_ocr
            )
        else:
            ocr_output = self.stub_extraction_runner.build_ocr_output(document)

        runner: ExtractionRunnerProtocol = self.extraction_runner or self.stub_extraction_runner
        extracted_output = runner.build_extracted_output(schema, document, policy, ocr_output)

        validator = self.validation_runner or self.stub_validation_runner
        validation_report = validator.build_validation_report(extracted_output, ocr_output, schema)
        recovery_report = self.stub_recovery_runner.build_recovery_report(document)
        final_output = FinalOutput(
            document_id=document.document_id,
            schema_id=schema.schema_id,
            policy_id=policy.policy_id,
            fields=extracted_output.fields,
            tables=extracted_output.tables,
            validation_report=validation_report,
            recovery_report=recovery_report,
            quality_summary=self.stub_note,
        )
        return DocumentProcessingResult(
            document_profile=profile,
            selected_policy=policy,
            run_plan=run_plan,
            ocr_output=ocr_output,
            extracted_output=extracted_output,
            validation_report=validation_report,
            recovery_report=recovery_report,
            final_output=final_output,
        )

    def _build_profile(self, schema: ExtractionSchema, document: Document) -> DocumentProfile:
        name = document.original_filename.lower()
        quality_bin = "low" if ("scan" in name or "noisy" in name) else "good"
        layout_type = "table_heavy" if len(schema.tables) > 0 else "simple"
        detected_type = "receipt" if "receipt" in name else "document"
        return DocumentProfile(
            document_id=document.document_id,
            detected_type=detected_type,
            layout_type=layout_type,
            quality_bin=quality_bin,
            language="en",
            content_profile="general",
        )
