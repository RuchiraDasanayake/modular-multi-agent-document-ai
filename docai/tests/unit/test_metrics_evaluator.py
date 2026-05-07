from __future__ import annotations

from docai_core.contracts.domain import (
    FieldOutput,
    FinalOutput,
    RecoveryReport,
    RowOutput,
    TableOutput,
    ValidationReport,
)
from docai_core.metrics.evaluator import MetricsEvaluator
from docai_core.review.expected_values import (
    ExpectedFieldValue,
    ExpectedTableRowValue,
    ExpectedValues,
)

_DOC_ID = "doc-1"
_SCHEMA_ID = "schema-1"
_POLICY_ID = "invoice_table_heavy_local_v1"


def _validation() -> ValidationReport:
    return ValidationReport(document_id=_DOC_ID, pass_status=True, summary="stub")


def _recovery() -> RecoveryReport:
    return RecoveryReport(document_id=_DOC_ID, attempted=False, summary="stub")


def _final_output(
    fields: list[FieldOutput],
    tables: list[TableOutput] | None = None,
) -> FinalOutput:
    return FinalOutput(
        document_id=_DOC_ID,
        schema_id=_SCHEMA_ID,
        policy_id=_POLICY_ID,
        fields=fields,
        tables=tables or [],
        validation_report=_validation(),
        recovery_report=_recovery(),
    )


def _expected_values(
    fields: list[ExpectedFieldValue],
    table_rows: list[ExpectedTableRowValue] | None = None,
) -> ExpectedValues:
    return ExpectedValues(
        document_id=_DOC_ID,
        schema_id=_SCHEMA_ID,
        fields=fields,
        table_rows=table_rows or [],
    )


# ---------------------------------------------------------------------------
# Test 1: exact match
# ---------------------------------------------------------------------------

def test_exact_match_all_correct() -> None:
    fo = _final_output(
        fields=[
            FieldOutput(field_name="invoice_number", value="INV-001", validation_status="valid"),
            FieldOutput(field_name="total_amount", value="500.00", validation_status="valid"),
        ],
        tables=[
            TableOutput(
                table_name="line_items",
                rows=[RowOutput(row_index=0, columns={"description": "Anvils", "qty": "2"})],
            )
        ],
    )
    ev = _expected_values(
        fields=[
            ExpectedFieldValue(field_name="invoice_number", expected_value="INV-001"),
            ExpectedFieldValue(field_name="total_amount", expected_value="500.00"),
        ],
        table_rows=[
            ExpectedTableRowValue(
                table_name="line_items",
                row_index=0,
                expected_columns={"description": "Anvils", "qty": "2"},
            )
        ],
    )
    result = MetricsEvaluator().evaluate_document(fo, ev)

    assert result.field_accuracy == 1.0
    assert result.table_cell_accuracy == 1.0
    assert result.overall_accuracy == 1.0


# ---------------------------------------------------------------------------
# Test 2: one field differs
# ---------------------------------------------------------------------------

def test_one_field_differs() -> None:
    fo = _final_output(
        fields=[
            FieldOutput(field_name="invoice_number", value="INV-001", validation_status="valid"),
            FieldOutput(field_name="total_amount", value="999.00", validation_status="valid"),
        ],
    )
    ev = _expected_values(
        fields=[
            ExpectedFieldValue(field_name="invoice_number", expected_value="INV-001"),
            ExpectedFieldValue(field_name="total_amount", expected_value="500.00"),
        ],
    )
    result = MetricsEvaluator().evaluate_document(fo, ev)

    assert result.field_total == 2
    assert result.field_correct == 1
    assert result.field_accuracy == 0.5


# ---------------------------------------------------------------------------
# Test 3: one expected field missing from FinalOutput
# ---------------------------------------------------------------------------

def test_missing_expected_field() -> None:
    fo = _final_output(
        fields=[
            FieldOutput(field_name="invoice_number", value="INV-001", validation_status="valid"),
            # total_amount deliberately absent
        ],
    )
    ev = _expected_values(
        fields=[
            ExpectedFieldValue(field_name="invoice_number", expected_value="INV-001"),
            ExpectedFieldValue(field_name="total_amount", expected_value="500.00"),
        ],
    )
    result = MetricsEvaluator().evaluate_document(fo, ev)

    assert result.missing_expected_field_count == 1
    assert result.field_total == 2
    assert result.field_correct == 1
    assert result.field_accuracy == 0.5


# ---------------------------------------------------------------------------
# Test 4: extra extracted field not in expected
# ---------------------------------------------------------------------------

def test_extra_extracted_field() -> None:
    fo = _final_output(
        fields=[
            FieldOutput(field_name="invoice_number", value="INV-001", validation_status="valid"),
            FieldOutput(field_name="unexpected_field", value="surprise", validation_status="valid"),
        ],
    )
    ev = _expected_values(
        fields=[
            ExpectedFieldValue(field_name="invoice_number", expected_value="INV-001"),
        ],
    )
    result = MetricsEvaluator().evaluate_document(fo, ev)

    assert result.extra_extracted_field_count == 1
    assert result.field_total == 1  # extra does not inflate total
    assert result.field_correct == 1
    assert result.field_accuracy == 1.0


# ---------------------------------------------------------------------------
# Test 5: one table cell differs
# ---------------------------------------------------------------------------

def test_one_table_cell_differs() -> None:
    fo = _final_output(
        fields=[],
        tables=[
            TableOutput(
                table_name="line_items",
                rows=[RowOutput(row_index=0, columns={"description": "Anvils", "qty": "3"})],
            )
        ],
    )
    ev = _expected_values(
        fields=[],
        table_rows=[
            ExpectedTableRowValue(
                table_name="line_items",
                row_index=0,
                expected_columns={"description": "Anvils", "qty": "2"},
            )
        ],
    )
    result = MetricsEvaluator().evaluate_document(fo, ev)

    assert result.table_cell_total == 2
    assert result.table_cell_correct == 1
    assert result.table_cell_accuracy == 0.5


# ---------------------------------------------------------------------------
# Test 6: normalization — whitespace and case
# ---------------------------------------------------------------------------

def test_normalization_whitespace_and_case() -> None:
    fo = _final_output(
        fields=[
            FieldOutput(field_name="vendor_name", value=" ABC ", validation_status="valid"),
        ],
    )
    ev = _expected_values(
        fields=[
            ExpectedFieldValue(field_name="vendor_name", expected_value="abc"),
        ],
    )
    result = MetricsEvaluator().evaluate_document(fo, ev)

    assert result.field_correct == 1
    assert result.field_accuracy == 1.0


# ---------------------------------------------------------------------------
# Test 7: corrected counts come from ExpectedValues.corrected flags
# ---------------------------------------------------------------------------

def test_corrected_counts() -> None:
    fo = _final_output(
        fields=[
            FieldOutput(field_name="invoice_number", value="INV-001", validation_status="valid"),
            FieldOutput(field_name="total_amount", value="500.00", validation_status="valid"),
        ],
        tables=[
            TableOutput(
                table_name="line_items",
                rows=[RowOutput(row_index=0, columns={"qty": "2"})],
            )
        ],
    )
    ev = _expected_values(
        fields=[
            ExpectedFieldValue(field_name="invoice_number", expected_value="INV-001", corrected=False),
            ExpectedFieldValue(field_name="total_amount", expected_value="600.00", corrected=True),
        ],
        table_rows=[
            ExpectedTableRowValue(
                table_name="line_items",
                row_index=0,
                expected_columns={"qty": "2"},
                corrected=True,
            )
        ],
    )
    result = MetricsEvaluator().evaluate_document(fo, ev)

    assert result.corrected_field_count == 1
    assert result.corrected_table_row_count == 1


# ---------------------------------------------------------------------------
# Test 8: empty expected → None accuracies, no division by zero
# ---------------------------------------------------------------------------

def test_empty_expected_values_returns_none_accuracies() -> None:
    fo = _final_output(fields=[], tables=[])
    ev = _expected_values(fields=[], table_rows=[])

    result = MetricsEvaluator().evaluate_document(fo, ev)

    assert result.field_accuracy is None
    assert result.table_cell_accuracy is None
    assert result.overall_accuracy is None
    assert result.field_total == 0
    assert result.table_cell_total == 0


def test_prf_perfect_match() -> None:
    fo = _final_output(fields=[
        FieldOutput(field_name="invoice_number", value="INV-001", validation_status="valid"),
        FieldOutput(field_name="total_amount", value="500.00", validation_status="valid"),
    ])
    ev = _expected_values(fields=[
        ExpectedFieldValue(field_name="invoice_number", expected_value="INV-001"),
        ExpectedFieldValue(field_name="total_amount", expected_value="500.00"),
    ])
    r = MetricsEvaluator().evaluate_document(fo, ev)
    assert r.field_true_positive == 2 and r.field_false_positive == 0 and r.field_false_negative == 0
    assert r.field_precision == 1.0 and r.field_recall == 1.0 and r.field_f1 == 1.0


def test_prf_missing_expected_field() -> None:
    fo = _final_output(fields=[
        FieldOutput(field_name="invoice_number", value="INV-001", validation_status="valid"),
    ])
    ev = _expected_values(fields=[
        ExpectedFieldValue(field_name="invoice_number", expected_value="INV-001"),
        ExpectedFieldValue(field_name="total_amount", expected_value="500.00"),
    ])
    r = MetricsEvaluator().evaluate_document(fo, ev)
    assert r.field_true_positive == 1 and r.field_false_positive == 0 and r.field_false_negative == 1
    assert r.field_precision == 1.0 and r.field_recall == 0.5
    assert r.field_f1 == round(2 * 1.0 * 0.5 / 1.5, 6)


def test_prf_extra_extracted_field() -> None:
    fo = _final_output(fields=[
        FieldOutput(field_name="invoice_number", value="INV-001", validation_status="valid"),
        FieldOutput(field_name="unexpected_field", value="surprise", validation_status="valid"),
    ])
    ev = _expected_values(fields=[
        ExpectedFieldValue(field_name="invoice_number", expected_value="INV-001"),
    ])
    r = MetricsEvaluator().evaluate_document(fo, ev)
    assert r.field_true_positive == 1 and r.field_false_positive == 1 and r.field_false_negative == 0
    assert r.field_precision == 0.5 and r.field_recall == 1.0
    assert r.field_f1 == round(2 * 0.5 * 1.0 / 1.5, 6)


def test_prf_wrong_field_value() -> None:
    fo = _final_output(fields=[
        FieldOutput(field_name="invoice_number", value="INV-WRONG", validation_status="valid"),
    ])
    ev = _expected_values(fields=[
        ExpectedFieldValue(field_name="invoice_number", expected_value="INV-001"),
    ])
    r = MetricsEvaluator().evaluate_document(fo, ev)
    assert r.field_true_positive == 0 and r.field_false_positive == 1 and r.field_false_negative == 1
    assert r.field_precision == 0.0 and r.field_recall == 0.0 and r.field_f1 is None


def test_prf_no_fields_at_all() -> None:
    r = MetricsEvaluator().evaluate_document(_final_output(fields=[]), _expected_values(fields=[]))
    assert r.field_true_positive == 0 and r.field_false_positive == 0 and r.field_false_negative == 0
    assert r.field_precision is None and r.field_recall is None and r.field_f1 is None

def test_prf_normalization_counts_as_tp() -> None:
    fo = _final_output(fields=[FieldOutput(field_name="vendor_name", value=" ABC ", validation_status="valid")])
    ev = _expected_values(fields=[ExpectedFieldValue(field_name="vendor_name", expected_value="abc")])
    r = MetricsEvaluator().evaluate_document(fo, ev)
    assert r.field_true_positive == 1 and r.field_false_positive == 0 and r.field_false_negative == 0
    assert r.field_precision == 1.0 and r.field_recall == 1.0 and r.field_f1 == 1.0
