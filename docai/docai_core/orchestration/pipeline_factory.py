from __future__ import annotations

import dataclasses
from pathlib import Path

from docai_core.contracts.domain import AvailableTools, DocumentProfile, ExtractionSchema, SelectedPolicy
from docai_core.extraction.kv_extraction_runner import KVOnlyExtractionRunner
from docai_core.extraction.model_centered_extraction_runner import ModelCenteredExtractionRunner
from docai_core.extraction.ocr_postprocessor import OCRPostProcessor
from docai_core.extraction.qwen_extraction_step import QwenExtractionStep
from docai_core.extraction.stub_extraction_runner import StubExtractionRunner
from docai_core.orchestration.document_processor import DocumentProcessor
from docai_core.orchestration.pipeline_config import RuntimePipelineConfig
from docai_core.planning.run_plan_builder import RunPlanBuilder
from docai_core.policies.assigner import StrategyAssigner
from docai_core.policies.registry import PolicyRegistry
from docai_core.plugins.models.stub_model_plugin import StubModelPlugin
from docai_core.recovery.stub_recovery_runner import StubRecoveryRunner
from docai_core.text_acquisition.router import TextAcquisitionRouter
from docai_core.validation.grounding_validation_runner import GroundingValidationRunner
from docai_core.validation.stub_validation_runner import StubValidationRunner


class _FixedPolicyAssigner:
    """Returns a pre-built SelectedPolicy for every document — bypasses auto-selection."""

    def __init__(self, policy: SelectedPolicy) -> None:
        self._policy = policy

    def assign_strategy(
        self,
        schema: ExtractionSchema,
        document_profile: DocumentProfile,
        available_tools: AvailableTools,
    ) -> SelectedPolicy:
        return self._policy


def _find_variant(registry: PolicyRegistry, policy_id: str) -> tuple[dict, str]:
    """Return (variant_dict, family_id) for the first variant matching policy_id.

    Raises ValueError if not found.
    """
    for family_id in registry.list_policy_families():
        for variant in registry.load_family(family_id).get("variants", []):
            if variant.get("policy_id") == policy_id:
                return variant, family_id
    raise ValueError(f"Unknown policy_id {policy_id!r}.")

_DEFAULT_POLICY_DIR = Path(__file__).resolve().parents[2] / "configs" / "policies"

_STUB_GENERATED_BY = "stub_runtime_orchestrator"
_STUB_NOTE = "Stub output for runtime spine validation only. Not real extraction."

_LOCAL_TEXT_GENERATED_BY = "local_text_pipeline_v1"
_LOCAL_TEXT_NOTE = "Real text acquisition via KVOnlyExtractionRunner. No model inference."

_MODEL_GENERATED_BY = "model_centered_pipeline_v1"
_MODEL_NOTE = "Model-centered extraction via KV+Qwen merge. Grounding validated."


def _strategy_assigner(policy_dir: Path) -> StrategyAssigner:
    return StrategyAssigner(registry=PolicyRegistry(policy_dir))


def build_stub_pipeline(policy_dir: Path | None = None) -> RuntimePipelineConfig:
    """Build the default stub pipeline — identical to the previous inline construction
    inside RuntimeOrchestrator. All extraction output is synthetic; is_stub=True."""
    resolved = policy_dir or _DEFAULT_POLICY_DIR
    processor = DocumentProcessor(
        strategy_assigner=_strategy_assigner(resolved),
        run_plan_builder=RunPlanBuilder(),
        stub_extraction_runner=StubExtractionRunner(),
        stub_validation_runner=StubValidationRunner(),
        stub_recovery_runner=StubRecoveryRunner(),
        stub_note=_STUB_NOTE,
    )
    return RuntimePipelineConfig(
        document_processor=processor,
        generated_by=_STUB_GENERATED_BY,
        is_stub=True,
        note=_STUB_NOTE,
    )


def build_local_text_pipeline(policy_dir: Path | None = None) -> RuntimePipelineConfig:
    """Build the local-text pipeline: real file acquisition + KV extraction, no model calls.

    Supports .txt, native-text .pdf, and image files (routes to ImageOCRExtractor;
    Tesseract must be available for real image documents). Validation and recovery
    remain stub. is_stub=False.
    """
    resolved = policy_dir or _DEFAULT_POLICY_DIR
    processor = DocumentProcessor(
        strategy_assigner=_strategy_assigner(resolved),
        run_plan_builder=RunPlanBuilder(),
        stub_extraction_runner=StubExtractionRunner(),
        stub_validation_runner=StubValidationRunner(),
        stub_recovery_runner=StubRecoveryRunner(),
        stub_note=_LOCAL_TEXT_NOTE,
        text_acquisition_router=TextAcquisitionRouter(),
        ocr_postprocessor=OCRPostProcessor(),
        extraction_runner=KVOnlyExtractionRunner(),
        validation_runner=GroundingValidationRunner(),
    )
    return RuntimePipelineConfig(
        document_processor=processor,
        generated_by=_LOCAL_TEXT_GENERATED_BY,
        is_stub=False,
        note=_LOCAL_TEXT_NOTE,
    )


def build_model_pipeline(
    model_step: QwenExtractionStep,
    policy_dir: Path | None = None,
) -> RuntimePipelineConfig:
    """Build the model-centered pipeline: real acquisition + KV+model merge.

    Caller must supply a model_step (QwenExtractionStep with real or fake plugin).
    Supports same file formats as build_local_text_pipeline.
    is_stub=False.
    """
    resolved = policy_dir or _DEFAULT_POLICY_DIR
    processor = DocumentProcessor(
        strategy_assigner=_strategy_assigner(resolved),
        run_plan_builder=RunPlanBuilder(),
        stub_extraction_runner=StubExtractionRunner(),
        stub_validation_runner=StubValidationRunner(),
        stub_recovery_runner=StubRecoveryRunner(),
        stub_note=_MODEL_NOTE,
        text_acquisition_router=TextAcquisitionRouter(),
        ocr_postprocessor=OCRPostProcessor(),
        extraction_runner=ModelCenteredExtractionRunner(model_step=model_step),
        validation_runner=GroundingValidationRunner(),
    )
    return RuntimePipelineConfig(
        document_processor=processor,
        generated_by=_MODEL_GENERATED_BY,
        is_stub=False,
        note=_MODEL_NOTE,
    )


def build_pipeline_for_policy(
    policy_id: str,
    policy_dir: Path | None = None,
    model_step: QwenExtractionStep | None = None,
) -> RuntimePipelineConfig:
    """Build a pipeline where DocumentProcessor always uses policy_id as SelectedPolicy.

    Reads variant["runtime"]["pipeline_mode"] to choose build_local_text_pipeline()
    or build_model_pipeline(). The _FixedPolicyAssigner replaces StrategyAssigner so
    every document in the job receives the same forced policy regardless of profile.
    Raises ValueError for unknown policy_id.
    """
    resolved = policy_dir or _DEFAULT_POLICY_DIR
    registry = PolicyRegistry(resolved)
    variant, family_id = _find_variant(registry, policy_id)

    fixed_policy = SelectedPolicy(
        policy_id=policy_id,
        policy_family=family_id,
        policy_version=str(variant.get("version", "v1")),
        selected_by="fixed_policy_assigner",
        confidence=1.0,
        reasons=[f"Policy forced: {policy_id}"],
    )
    fixed_assigner = _FixedPolicyAssigner(policy=fixed_policy)

    pipeline_mode = variant.get("runtime", {}).get("pipeline_mode", "local_text")
    if pipeline_mode == "local_text_model":
        step = model_step or QwenExtractionStep(model_plugin=StubModelPlugin())
        config = build_model_pipeline(model_step=step, policy_dir=resolved)
    else:
        config = build_local_text_pipeline(policy_dir=resolved)

    new_processor = dataclasses.replace(config.document_processor, strategy_assigner=fixed_assigner)
    return dataclasses.replace(config, document_processor=new_processor)
