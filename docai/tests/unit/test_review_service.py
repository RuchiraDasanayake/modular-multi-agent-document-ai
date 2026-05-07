from __future__ import annotations

from docai_core.contracts.domain import (
    FieldOutput,
    FinalOutput,
    RecoveryReport,
    RowOutput,
    TableOutput,
    ValidationReport,
)
from docai_core.review.review_service import ReviewService


def _make_final_output() -> FinalOutput:
    return FinalOutput(
        document_id="doc-1",
        schema_id="schema-1",
        policy_id="invoice_table_heavy_local_v1",
        fields=[
            FieldOutput(
                field_name="invoice_number",
                value="INV-001",
                validation_status="valid",
            ),
            FieldOutput(
                field_name="total_amount",
                value="1250.00",
                validation_status="valid",
            ),
        ],
        tables=[
            TableOutput(
                table_name="line_items",
                rows=[
                    RowOutput(
                        row_index=0,
                        columns={"description": "Anvils", "line_total": "1000.00"},
                        validation_status="valid",
                    )
                ],
                validation_status="valid",
            )
        ],
        validation_report=ValidationReport(
            document_id="doc-1",
            pass_status=True,
            summary="stub validation passed",
        ),
        recovery_report=RecoveryReport(
            document_id="doc-1",
            attempted=False,
            summary="stub recovery not attempted",
        ),
    )


def test_build_expected_values_no_corrections() -> None:
    service = ReviewService()
    final_output = _make_final_output()

    ev = service.build_expected_values_from_final_output(final_output)

    assert ev.document_id == "doc-1"
    assert ev.schema_id == "schema-1"
    assert len(ev.fields) == 2
    assert len(ev.table_rows) == 1

    invoice_field = next(f for f in ev.fields if f.field_name == "invoice_number")
    assert invoice_field.expected_value == "INV-001"
    assert invoice_field.extracted_value == "INV-001"
    assert invoice_field.corrected is False

    amount_field = next(f for f in ev.fields if f.field_name == "total_amount")
    assert amount_field.expected_value == "1250.00"
    assert amount_field.corrected is False

    row = ev.table_rows[0]
    assert row.expected_columns == {"description": "Anvils", "line_total": "1000.00"}
    assert row.extracted_columns == {"description": "Anvils", "line_total": "1000.00"}
    assert row.corrected is False


def test_build_expected_values_with_field_correction() -> None:
    service = ReviewService()
    final_output = _make_final_output()

    ev = service.build_expected_values_from_final_output(
        final_output,
        field_corrections={"total_amount": "1300.00"},
    )

    corrected_field = next(f for f in ev.fields if f.field_name == "total_amount")
    assert corrected_field.expected_value == "1300.00"
    assert corrected_field.extracted_value == "1250.00"
    assert corrected_field.corrected is True

    unchanged_field = next(f for f in ev.fields if f.field_name == "invoice_number")
    assert unchanged_field.expected_value == "INV-001"
    assert unchanged_field.corrected is False


def test_build_expected_values_with_table_row_correction() -> None:
    service = ReviewService()
    final_output = _make_final_output()

    ev = service.build_expected_values_from_final_output(
        final_output,
        table_row_corrections={
            "line_items:0": {"description": "Anvils", "line_total": "1100.00"}
        },
    )

    row = ev.table_rows[0]
    assert row.expected_columns == {"description": "Anvils", "line_total": "1100.00"}
    assert row.extracted_columns == {"description": "Anvils", "line_total": "1000.00"}
    assert row.corrected is True


def test_create_review_record_approved() -> None:
    service = ReviewService()
    final_output = _make_final_output()
    ev = service.build_expected_values_from_final_output(final_output)

    record = service.create_review_record(
        job_id="job-1",
        run_type="training",
        final_output=final_output,
        expected_values=ev,
        approved_final_output=True,
    )

    assert record.review_status == "approved"
    assert record.approved_final_output is True
    assert record.document_id == "doc-1"
    assert record.job_id == "job-1"
    assert record.review_id == "job-1:doc-1:review"


def test_create_review_record_corrected_status() -> None:
    service = ReviewService()
    final_output = _make_final_output()
    ev = service.build_expected_values_from_final_output(
        final_output,
        field_corrections={"total_amount": "1300.00"},
    )

    record = service.create_review_record(
        job_id="job-1",
        run_type="training",
        final_output=final_output,
        expected_values=ev,
        approved_final_output=False,
    )

    assert record.review_status == "corrected"
    assert record.approved_final_output is False
