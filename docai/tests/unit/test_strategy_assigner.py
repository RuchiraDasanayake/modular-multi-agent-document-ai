from datetime import datetime, timezone
from pathlib import Path

from docai_core.contracts.domain import (
    AvailableTool,
    AvailableTools,
    Column,
    DocumentProfile,
    ExtractionSchema,
    Field,
    Table,
)
from docai_core.policies.assigner import StrategyAssigner
from docai_core.policies.registry import PolicyRegistry


def _registry() -> PolicyRegistry:
    repo_root = Path(__file__).resolve().parents[2]
    return PolicyRegistry(repo_root / "configs" / "policies")


def _available_tools(capabilities: list[str]) -> AvailableTools:
    tool = AvailableTool(
        tool_id="tool-1",
        tool_type="ocr",
        capabilities=capabilities,
        enabled=True,
    )
    return AvailableTools(
        available_ocr_engines=[tool],
        available_parsers=[],
        available_models=[],
        available_validators=[],
        available_recovery_strategies=[],
    )


def _schema(with_table: bool) -> ExtractionSchema:
    now = datetime.now(timezone.utc)
    tables = []
    if with_table:
        tables = [
            Table(
                table_id="line_items",
                name="line_items",
                description="Line item table",
                columns=[
                    Column(
                        column_id="description",
                        name="description",
                        description="Item description",
                        type="string",
                        required=True,
                    )
                ],
            )
        ]
    return ExtractionSchema(
        schema_id="schema-1",
        project_id="project-1",
        name="Schema",
        description="Schema",
        version="v1",
        fields=[
            Field(
                field_id="invoice_id",
                name="invoice_id",
                description="Invoice id",
                type="string",
                required=True,
            )
        ],
        tables=tables,
        created_at=now,
        updated_at=now,
    )


def test_low_quality_document_gets_noisy_scan_rescue() -> None:
    assigner = StrategyAssigner(registry=_registry())
    profile = DocumentProfile(document_id="doc-1", quality_bin="low", layout_type="simple", detected_type="document")
    selected = assigner.assign_strategy(_schema(with_table=False), profile, _available_tools(["text_output"]))
    assert selected.policy_id == "noisy_scan_rescue_v1"


def test_table_heavy_schema_and_document_get_invoice_table_heavy() -> None:
    assigner = StrategyAssigner(registry=_registry())
    profile = DocumentProfile(
        document_id="doc-1",
        quality_bin="good",
        layout_type="table_heavy",
        detected_type="document",
    )
    selected = assigner.assign_strategy(
        _schema(with_table=True), profile, _available_tools(["text_output", "bbox_output"])
    )
    assert selected.policy_id == "invoice_table_heavy_local_v1"


def test_receipt_document_gets_receipt_basic() -> None:
    assigner = StrategyAssigner(registry=_registry())
    profile = DocumentProfile(document_id="doc-1", quality_bin="good", layout_type="simple", detected_type="receipt")
    selected = assigner.assign_strategy(_schema(with_table=False), profile, _available_tools(["text_output"]))
    assert selected.policy_id == "receipt_basic_local_v1"


def test_default_document_gets_invoice_basic() -> None:
    assigner = StrategyAssigner(registry=_registry())
    profile = DocumentProfile(document_id="doc-1", quality_bin="good", layout_type="simple", detected_type="document")
    selected = assigner.assign_strategy(_schema(with_table=False), profile, _available_tools(["text_output"]))
    assert selected.policy_id == "invoice_basic_local_v1"


def test_selected_policy_includes_human_readable_reasons() -> None:
    assigner = StrategyAssigner(registry=_registry())
    profile = DocumentProfile(document_id="doc-1", quality_bin="low", layout_type="simple", detected_type="document")
    selected = assigner.assign_strategy(_schema(with_table=False), profile, _available_tools(["text_output"]))
    assert len(selected.reasons) > 0
    assert "Document quality is low" in selected.reasons[0]


def test_incompatible_policy_requirements_are_listed_in_disabled_candidates() -> None:
    assigner = StrategyAssigner(registry=_registry())
    profile = DocumentProfile(
        document_id="doc-1",
        quality_bin="good",
        layout_type="table_heavy",
        detected_type="document",
    )
    selected = assigner.assign_strategy(_schema(with_table=True), profile, _available_tools(["text_output"]))
    assert selected.policy_id == "invoice_basic_local_v1"
    disabled = selected.disabled_candidates
    assert isinstance(disabled, list)
    assert len(disabled) > 0
    assert disabled[0].policy_id
    assert disabled[0].reason_disabled
    assert any(
        item.policy_id == "invoice_table_heavy_local_v1"
        and "Requires table_detection or bbox_output" in item.reason_disabled
        for item in disabled
    )
