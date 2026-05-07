from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from docai_core.contracts.domain import (
    AvailableTool,
    AvailableTools,
    Column,
    Document,
    DocumentProfile,
    ExtractionSchema,
    Field,
    Table,
)
from docai_core.extraction.stub_extraction_runner import StubExtractionRunner
from docai_core.orchestration.document_processor import DocumentProcessor
from docai_core.planning.run_plan_builder import RunPlanBuilder
from docai_core.policies.assigner import StrategyAssigner
from docai_core.policies.registry import PolicyRegistry
from docai_core.recovery.stub_recovery_runner import StubRecoveryRunner
from docai_core.validation.stub_validation_runner import StubValidationRunner

_POLICY_DIR = Path(__file__).resolve().parents[2] / "configs" / "policies"
_STUB_NOTE = "Stub output for unit test only."


def _available_tools() -> AvailableTools:
    tool = AvailableTool(
        tool_id="stub_tool",
        tool_type="ocr_parser_model",
        capabilities=["text_output", "bbox_output", "table_detection", "json_output"],
        enabled=True,
    )
    return AvailableTools(
        available_ocr_engines=[tool],
        available_parsers=[tool],
        available_models=[tool],
    )


def _make_processor() -> DocumentProcessor:
    return DocumentProcessor(
        strategy_assigner=StrategyAssigner(registry=PolicyRegistry(_POLICY_DIR)),
        run_plan_builder=RunPlanBuilder(),
        stub_extraction_runner=StubExtractionRunner(),
        stub_validation_runner=StubValidationRunner(),
        stub_recovery_runner=StubRecoveryRunner(),
        stub_note=_STUB_NOTE,
    )


def _make_schema() -> ExtractionSchema:
    now = datetime.now(timezone.utc)
    return ExtractionSchema(
        schema_id="schema-1",
        project_id="proj-1",
        name="Invoice Schema",
        description="Test invoice schema",
        version="v1",
        fields=[
            Field(field_id="f-1", name="invoice_number", description="", type="string", required=True),
            Field(field_id="f-2", name="total_amount", description="", type="string", required=True),
        ],
        tables=[
            Table(
                table_id="t-1",
                name="line_items",
                description="",
                columns=[
                    Column(column_id="c-1", name="description", description="", type="string", required=True),
                    Column(column_id="c-2", name="line_total", description="", type="string", required=True),
                ],
            )
        ],
        created_at=now,
        updated_at=now,
    )


def _make_document(doc_id: str, filename: str) -> Document:
    return Document(
        document_id=doc_id,
        job_id="job-1",
        original_filename=filename,
        file_path=filename,
        status="uploaded",
        uploaded_at=datetime.now(timezone.utc),
        profile=DocumentProfile(document_id=doc_id),
    )


def test_process_normal_invoice_document() -> None:
    processor = _make_processor()
    schema = _make_schema()
    document = _make_document("doc-1", "invoice_001.pdf")
    tools = _available_tools()

    result = processor.process_document(schema, document, tools)

    assert result.selected_policy.policy_id == "invoice_table_heavy_local_v1"
    assert result.run_plan.document_id == "doc-1"
    assert result.run_plan.policy_id == "invoice_table_heavy_local_v1"
    assert "invoice_001.pdf" in result.ocr_output.text
    assert len(result.extracted_output.fields) > 0
    assert result.validation_report.pass_status is True
    assert result.recovery_report.attempted is False
    assert result.final_output.document_id == "doc-1"


def test_process_noisy_scan_document() -> None:
    processor = _make_processor()
    schema = _make_schema()
    document = _make_document("doc-2", "noisy_scan_001.png")
    tools = _available_tools()

    result = processor.process_document(schema, document, tools)

    assert result.selected_policy.policy_id == "noisy_scan_rescue_v1"
    assert result.document_profile.quality_bin == "low"
    assert "denoise" in result.run_plan.preprocessing_steps
    assert "deskew" in result.run_plan.preprocessing_steps
