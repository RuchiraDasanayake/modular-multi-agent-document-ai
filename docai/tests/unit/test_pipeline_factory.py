import pytest

from docai_core.extraction.kv_extraction_runner import KVOnlyExtractionRunner
from docai_core.extraction.model_centered_extraction_runner import ModelCenteredExtractionRunner
from docai_core.extraction.ocr_postprocessor import OCRPostProcessor
from docai_core.extraction.qwen_extraction_step import QwenExtractionStep
from docai_core.orchestration.pipeline_factory import (
    build_local_text_pipeline,
    build_model_pipeline,
    build_pipeline_for_policy,
    build_stub_pipeline,
)
from docai_core.plugins.models.stub_model_plugin import StubModelPlugin
from docai_core.text_acquisition.router import TextAcquisitionRouter
from docai_core.validation.grounding_validation_runner import GroundingValidationRunner


def test_build_stub_pipeline_produces_stub_document_processor() -> None:
    cfg = build_stub_pipeline()

    assert cfg.is_stub is True
    assert cfg.generated_by == "stub_runtime_orchestrator"
    assert "Stub output for runtime spine validation only." in cfg.note
    assert cfg.document_processor.text_acquisition_router is None
    assert cfg.document_processor.ocr_postprocessor is None
    assert cfg.document_processor.extraction_runner is None


def test_build_stub_pipeline_with_explicit_policy_dir(tmp_path) -> None:
    import shutil
    from pathlib import Path

    policy_dir = Path(__file__).resolve().parents[2] / "configs" / "policies"
    custom_dir = tmp_path / "policies"
    shutil.copytree(policy_dir, custom_dir)

    cfg = build_stub_pipeline(policy_dir=custom_dir)

    assert cfg.is_stub is True
    assert cfg.document_processor.text_acquisition_router is None


def test_build_local_text_pipeline_produces_real_document_processor() -> None:
    cfg = build_local_text_pipeline()

    assert cfg.is_stub is False
    assert cfg.generated_by == "local_text_pipeline_v1"
    assert "KVOnlyExtractionRunner" in cfg.note or "KV" in cfg.note or "No model inference" in cfg.note
    assert cfg.document_processor.text_acquisition_router is not None
    assert isinstance(cfg.document_processor.text_acquisition_router, TextAcquisitionRouter)
    assert cfg.document_processor.ocr_postprocessor is not None
    assert isinstance(cfg.document_processor.ocr_postprocessor, OCRPostProcessor)
    assert cfg.document_processor.extraction_runner is not None
    assert isinstance(cfg.document_processor.extraction_runner, KVOnlyExtractionRunner)


def test_build_local_text_pipeline_with_explicit_policy_dir(tmp_path) -> None:
    import shutil
    from pathlib import Path

    policy_dir = Path(__file__).resolve().parents[2] / "configs" / "policies"
    custom_dir = tmp_path / "policies"
    shutil.copytree(policy_dir, custom_dir)

    cfg = build_local_text_pipeline(policy_dir=custom_dir)

    assert cfg.is_stub is False
    assert cfg.document_processor.extraction_runner is not None


def test_stub_and_local_text_pipelines_are_independent() -> None:
    stub = build_stub_pipeline()
    real = build_local_text_pipeline()

    assert stub.document_processor is not real.document_processor
    assert stub.generated_by != real.generated_by
    assert stub.is_stub is True
    assert real.is_stub is False


def test_pipeline_config_fields_are_accessible() -> None:
    cfg = build_stub_pipeline()

    assert hasattr(cfg, "document_processor")
    assert hasattr(cfg, "generated_by")
    assert hasattr(cfg, "is_stub")
    assert hasattr(cfg, "note")


def test_build_model_pipeline_produces_model_centered_processor() -> None:
    step = QwenExtractionStep(model_plugin=StubModelPlugin())
    cfg = build_model_pipeline(model_step=step)

    assert cfg.is_stub is False
    assert cfg.generated_by == "model_centered_pipeline_v1"
    assert isinstance(cfg.document_processor.extraction_runner, ModelCenteredExtractionRunner)
    assert isinstance(cfg.document_processor.validation_runner, GroundingValidationRunner)
    assert cfg.document_processor.text_acquisition_router is not None


def test_build_model_pipeline_injects_model_step() -> None:
    step = QwenExtractionStep(model_plugin=StubModelPlugin())
    cfg = build_model_pipeline(model_step=step)

    runner = cfg.document_processor.extraction_runner
    assert isinstance(runner, ModelCenteredExtractionRunner)
    assert runner.model_step is step


# ---------------------------------------------------------------------------
# build_pipeline_for_policy
# ---------------------------------------------------------------------------

def test_build_pipeline_for_policy_invoice_basic_uses_local_text() -> None:
    cfg = build_pipeline_for_policy("invoice_basic_local_v1")

    assert cfg.generated_by == "local_text_pipeline_v1"
    assert cfg.is_stub is False
    assert isinstance(cfg.document_processor.extraction_runner, KVOnlyExtractionRunner)

    from docai_core.contracts.domain import AvailableTools
    from docai_core.contracts.domain import DocumentProfile, ExtractionSchema, Field
    schema = ExtractionSchema(schema_id="s1", project_id="p1", name="Test", description=None, version="v1", fields=[
        Field(field_id="f1", name="invoice_number", type="str", description=None),
    ])
    profile = DocumentProfile(document_id="d1")
    policy = cfg.document_processor.strategy_assigner.assign_strategy(schema, profile, AvailableTools())
    assert policy.policy_id == "invoice_basic_local_v1"
    assert policy.selected_by == "fixed_policy_assigner"


def test_build_pipeline_for_policy_noisy_scan_uses_model_pipeline() -> None:
    cfg = build_pipeline_for_policy("noisy_scan_rescue_v1")

    assert cfg.generated_by == "model_centered_pipeline_v1"
    assert cfg.is_stub is False
    assert isinstance(cfg.document_processor.extraction_runner, ModelCenteredExtractionRunner)

    from docai_core.contracts.domain import AvailableTools, DocumentProfile, ExtractionSchema, Field
    schema = ExtractionSchema(schema_id="s1", project_id="p1", name="Test", description=None, version="v1", fields=[
        Field(field_id="f1", name="total", type="str", description=None),
    ])
    profile = DocumentProfile(document_id="d1")
    policy = cfg.document_processor.strategy_assigner.assign_strategy(schema, profile, AvailableTools())
    assert policy.policy_id == "noisy_scan_rescue_v1"


def test_build_pipeline_for_unknown_policy_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown policy_id"):
        build_pipeline_for_policy("does_not_exist")
