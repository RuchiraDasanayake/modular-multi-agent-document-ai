import json
from datetime import datetime, timezone

from docai_core.contracts.domain import (
    Column,
    DisabledCandidate,
    Document,
    DocumentProfile,
    ExpectedOutput,
    ExtractionSchema,
    Field,
    FieldOutput,
    FinalOutput,
    Job,
    LearningRecord,
    MetricsReport,
    Project,
    RecoveryReport,
    RowOutput,
    Table,
    TableOutput,
    ValidationReport,
)


def test_project_can_be_created_and_serialized() -> None:
    now = datetime.now(timezone.utc)
    project = Project(
        project_id="proj-1",
        name="Invoice Project",
        description="Test",
        created_at=now,
        updated_at=now,
    )

    payload = project.to_dict()
    assert payload["project_id"] == "proj-1"
    assert "Invoice Project" in project.to_json()


def test_extraction_schema_supports_fields_and_tables() -> None:
    schema = ExtractionSchema(
        schema_id="schema-1",
        project_id="proj-1",
        name="Invoice Schema",
        description="Schema for invoices",
        version="v1",
        fields=[
            Field(
                field_id="f1",
                name="invoice_number",
                description="Invoice number",
                type="string",
                required=True,
            )
        ],
        tables=[
            Table(
                table_id="t1",
                name="line_items",
                description="Invoice rows",
                columns=[
                    Column(
                        column_id="c1",
                        name="description",
                        description="Item description",
                        type="string",
                        required=True,
                    )
                ],
                required=False,
            )
        ],
    )

    assert schema.fields[0].name == "invoice_number"
    assert schema.tables[0].columns[0].name == "description"


def test_job_supports_training_and_production_run_types() -> None:
    now = datetime.now(timezone.utc)
    training_job = Job(
        job_id="job-1",
        project_id="proj-1",
        schema_id="schema-1",
        name="Training batch",
        run_type="training",
        status="queued",
        created_at=now,
    )
    production_job = Job(
        job_id="job-2",
        project_id="proj-1",
        schema_id="schema-1",
        name="Production batch",
        run_type="production",
        status="queued",
        created_at=now,
    )

    assert training_job.run_type == "training"
    assert production_job.run_type == "production"


def test_document_supports_document_profile() -> None:
    now = datetime.now(timezone.utc)
    profile = DocumentProfile(
        document_id="doc-1",
        detected_type="invoice",
        layout_type="table-heavy",
        quality_bin="low",
    )
    document = Document(
        document_id="doc-1",
        job_id="job-1",
        original_filename="invoice.pdf",
        file_path="artifacts/doc-1.pdf",
        status="uploaded",
        uploaded_at=now,
        profile=profile,
    )

    assert document.profile.detected_type == "invoice"
    assert json.loads(document.to_json())["profile"]["layout_type"] == "table-heavy"


def test_field_output_supports_evidence_and_validation_status() -> None:
    field_output = FieldOutput(
        field_name="total_amount",
        value="100.00",
        normalized_value=100.0,
        confidence=0.97,
        evidence_text="Total Amount: 100.00",
        evidence_location="page:1,line:20",
        extraction_method="llm_field_extraction",
        validation_status="valid",
        issues=[],
    )

    assert field_output.evidence_text == "Total Amount: 100.00"
    assert field_output.validation_status == "valid"


def test_table_output_preserves_row_output_column_relationships() -> None:
    row = RowOutput(
        row_index=0,
        columns={"cpt_code": "99213", "units": 2, "charge_amount": "150.00"},
        validation_status="valid",
    )
    table = TableOutput(
        table_name="service_lines",
        rows=[row],
        validation_status="valid",
    )

    assert table.rows[0].columns["cpt_code"] == "99213"
    assert table.rows[0].columns["units"] == 2
    assert table.rows[0].columns["charge_amount"] == "150.00"


def test_final_output_includes_fields_tables_validation_recovery_and_artifacts() -> None:
    field_output = FieldOutput(
        field_name="invoice_number",
        value="INV-001",
        validation_status="valid",
    )
    row = RowOutput(
        row_index=0,
        columns={"description": "Service", "line_total": "100.00"},
        validation_status="valid",
    )
    table = TableOutput(
        table_name="line_items",
        rows=[row],
        validation_status="valid",
    )
    validation = ValidationReport(
        document_id="doc-1",
        pass_status=True,
        artifact_paths=["artifacts/doc-1/validation_report.json"],
    )
    recovery = RecoveryReport(
        document_id="doc-1",
        status="not_attempted",
        attempted=False,
        artifact_paths=["artifacts/doc-1/recovery_report.json"],
    )
    final_output = FinalOutput(
        document_id="doc-1",
        schema_id="schema-1",
        policy_id="invoice_basic_local_v1",
        fields=[field_output],
        tables=[table],
        validation_report=validation,
        recovery_report=recovery,
        artifact_paths=["artifacts/doc-1/final_output.json"],
    )

    payload = final_output.to_dict()
    assert payload["validation_report"]["pass_status"] is True
    assert payload["recovery_report"]["status"] == "not_attempted"
    assert payload["artifact_paths"] == ["artifacts/doc-1/final_output.json"]


def test_learning_record_stores_metrics_and_human_correction_summary() -> None:
    now = datetime.now(timezone.utc)
    metrics = MetricsReport(
        job_id="job-1",
        document_id="doc-1",
        precision=0.9,
        recall=0.8,
        f1=0.85,
        policy_id="invoice_basic_local_v1",
    )
    learning_record = LearningRecord(
        learning_record_id="lr-1",
        document_id="doc-1",
        schema_id="schema-1",
        policy_id="invoice_basic_local_v1",
        metrics=metrics,
        human_correction_summary="Corrected total_amount from 10.00 to 100.00",
        created_at=now,
    )

    payload = learning_record.to_dict()
    assert payload["metrics"]["f1"] == 0.85
    assert "Corrected total_amount" in payload["human_correction_summary"]


def test_selected_policy_supports_structured_disabled_candidates() -> None:
    from docai_core.contracts.domain import SelectedPolicy

    selected = SelectedPolicy(
        policy_id="invoice_basic_local_v1",
        policy_family="invoice_extraction",
        policy_version="v1",
        selected_by="deterministic_strategy_assigner",
        reasons=["Fallback selected."],
        disabled_candidates=[
            DisabledCandidate(
                policy_id="invoice_table_heavy_local_v1",
                reason_disabled="Requires table_detection or bbox_output, but only text_output is available.",
            )
        ],
    )

    payload = selected.to_dict()
    assert payload["disabled_candidates"][0]["policy_id"] == "invoice_table_heavy_local_v1"
    assert "Requires table_detection or bbox_output" in payload["disabled_candidates"][0]["reason_disabled"]
