from datetime import datetime, timezone

from docai_core.contracts.domain import (
    Column,
    Document,
    DocumentProfile,
    ExtractionSchema,
    Field,
    SelectedPolicy,
    Table,
)
from docai_core.planning.run_plan_builder import RunPlanBuilder


def _build_schema() -> ExtractionSchema:
    return ExtractionSchema(
        schema_id="schema-1",
        project_id="proj-1",
        name="Invoice Schema",
        description="Invoice extraction schema",
        version="v1",
        fields=[
            Field(field_id="f1", name="invoice_number", description="Invoice number", type="string"),
            Field(field_id="f2", name="total_amount", description="Total amount", type="string"),
        ],
        tables=[
            Table(
                table_id="t1",
                name="line_items",
                description="Invoice rows",
                columns=[
                    Column(column_id="c1", name="description", description="Item description", type="string"),
                    Column(column_id="c2", name="line_total", description="Line total", type="string"),
                ],
            )
        ],
    )


def _build_policy() -> SelectedPolicy:
    return SelectedPolicy(
        policy_id="invoice_table_heavy_local_v1",
        policy_family="invoice_extraction",
        policy_version="v1",
        selected_by="deterministic_strategy_assigner",
    )


def test_run_plan_builder_normal_document_gets_normalize() -> None:
    now = datetime.now(timezone.utc)
    builder = RunPlanBuilder()
    schema = _build_schema()
    policy = _build_policy()
    document = Document(
        document_id="doc-1",
        job_id="job-1",
        original_filename="invoice_001.pdf",
        file_path="invoice_001.pdf",
        status="uploaded",
        uploaded_at=now,
        profile=DocumentProfile(document_id="doc-1"),
    )

    plan = builder.build_run_plan(schema, document, policy)

    assert plan.preprocessing_steps == ["normalize"]
    assert plan.fields_to_extract == ["invoice_number", "total_amount"]
    assert plan.tables_to_extract == ["line_items"]
    assert plan.policy_id == "invoice_table_heavy_local_v1"


def test_run_plan_builder_noisy_document_gets_denoise_and_deskew() -> None:
    now = datetime.now(timezone.utc)
    builder = RunPlanBuilder()
    schema = _build_schema()
    policy = _build_policy()
    document = Document(
        document_id="doc-2",
        job_id="job-1",
        original_filename="noisy_scan_001.png",
        file_path="noisy_scan_001.png",
        status="uploaded",
        uploaded_at=now,
        profile=DocumentProfile(document_id="doc-2"),
    )

    plan = builder.build_run_plan(schema, document, policy)

    assert plan.preprocessing_steps == ["denoise", "deskew"]
    assert plan.fields_to_extract == ["invoice_number", "total_amount"]
    assert plan.tables_to_extract == ["line_items"]
    assert plan.policy_id == "invoice_table_heavy_local_v1"
