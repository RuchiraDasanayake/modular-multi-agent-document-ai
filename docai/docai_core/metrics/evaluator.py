from __future__ import annotations

from dataclasses import dataclass

from docai_core.contracts.domain import FinalOutput
from docai_core.review.expected_values import ExpectedValues


def _norm(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


@dataclass(slots=True)
class DocumentMetrics:
    document_id: str
    schema_id: str
    field_total: int
    field_correct: int
    field_accuracy: float | None
    table_cell_total: int
    table_cell_correct: int
    table_cell_accuracy: float | None
    overall_accuracy: float | None
    corrected_field_count: int
    corrected_table_row_count: int
    missing_expected_field_count: int
    extra_extracted_field_count: int
    # Field-level precision / recall / F1 (strict TP/FP/FN extraction convention).
    # A wrong value counts as both one FP and one FN.
    field_true_positive: int
    field_false_positive: int
    field_false_negative: int
    field_precision: float | None
    field_recall: float | None
    field_f1: float | None


@dataclass(slots=True)
class MetricsEvaluator:
    """Computes deterministic review-based document metrics.

    Compares FinalOutput against human-reviewed ExpectedValues.
    Does not write artifacts, mutate policies, or invoke any model.
    """

    def evaluate_document(
        self,
        final_output: FinalOutput,
        expected_values: ExpectedValues,
    ) -> DocumentMetrics:
        field_metrics = self._evaluate_fields(final_output, expected_values)
        table_metrics = self._evaluate_table_cells(final_output, expected_values)

        field_total = field_metrics["total"]
        field_correct = field_metrics["correct"]
        table_cell_total = table_metrics["total"]
        table_cell_correct = table_metrics["correct"]

        field_accuracy = (
            round(field_correct / field_total, 6) if field_total > 0 else None
        )
        table_cell_accuracy = (
            round(table_cell_correct / table_cell_total, 6) if table_cell_total > 0 else None
        )

        combined_total = field_total + table_cell_total
        combined_correct = field_correct + table_cell_correct
        overall_accuracy = (
            round(combined_correct / combined_total, 6) if combined_total > 0 else None
        )

        corrected_field_count = sum(1 for f in expected_values.fields if f.corrected)
        corrected_table_row_count = sum(1 for r in expected_values.table_rows if r.corrected)

        tp = field_metrics["tp"]
        fp = field_metrics["fp"]
        fn = field_metrics["fn"]
        field_precision = (
            round(tp / (tp + fp), 6) if (tp + fp) > 0 else None
        )
        field_recall = (
            round(tp / (tp + fn), 6) if (tp + fn) > 0 else None
        )
        if field_precision is not None and field_recall is not None and (field_precision + field_recall) > 0:
            field_f1: float | None = round(
                2 * field_precision * field_recall / (field_precision + field_recall), 6
            )
        else:
            field_f1 = None

        return DocumentMetrics(
            document_id=final_output.document_id,
            schema_id=final_output.schema_id,
            field_total=field_total,
            field_correct=field_correct,
            field_accuracy=field_accuracy,
            table_cell_total=table_cell_total,
            table_cell_correct=table_cell_correct,
            table_cell_accuracy=table_cell_accuracy,
            overall_accuracy=overall_accuracy,
            corrected_field_count=corrected_field_count,
            corrected_table_row_count=corrected_table_row_count,
            missing_expected_field_count=field_metrics["missing"],
            extra_extracted_field_count=field_metrics["extra"],
            field_true_positive=tp,
            field_false_positive=fp,
            field_false_negative=fn,
            field_precision=field_precision,
            field_recall=field_recall,
            field_f1=field_f1,
        )

    def evaluate_documents(
        self,
        pairs: list[tuple[FinalOutput, ExpectedValues]],
    ) -> list[DocumentMetrics]:
        return [self.evaluate_document(fo, ev) for fo, ev in pairs]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _evaluate_fields(
        self,
        final_output: FinalOutput,
        expected_values: ExpectedValues,
    ) -> dict:
        extracted_by_name = {f.field_name: f for f in final_output.fields}
        expected_names = {ef.field_name for ef in expected_values.fields}

        total = len(expected_values.fields)
        correct = 0
        missing = 0
        tp = 0
        fp = 0
        fn = 0

        for ef in expected_values.fields:
            extracted_field = extracted_by_name.get(ef.field_name)
            if extracted_field is None:
                missing += 1
                fn += 1
            elif _norm(extracted_field.value) == _norm(ef.expected_value):
                correct += 1
                tp += 1
            else:
                # wrong value: one FP (hallucinated wrong value) + one FN (missed correct value)
                fp += 1
                fn += 1

        extra = sum(
            1 for f in final_output.fields if f.field_name not in expected_names
        )
        fp += extra  # extracted fields with no corresponding expected field

        return {
            "total": total, "correct": correct, "missing": missing, "extra": extra,
            "tp": tp, "fp": fp, "fn": fn,
        }

    def _evaluate_table_cells(
        self,
        final_output: FinalOutput,
        expected_values: ExpectedValues,
    ) -> dict:
        # Build lookup: (table_name, row_index) -> RowOutput
        extracted_rows: dict[tuple[str, int], dict] = {}
        for table in final_output.tables:
            for row in table.rows:
                extracted_rows[(table.table_name, row.row_index)] = {
                    k: v for k, v in row.columns.items()
                }

        total = 0
        correct = 0

        for ev_row in expected_values.table_rows:
            extracted_cols = extracted_rows.get((ev_row.table_name, ev_row.row_index), {})
            for col_name, expected_col_val in ev_row.expected_columns.items():
                total += 1
                extracted_col_val = extracted_cols.get(col_name)
                if _norm(extracted_col_val) == _norm(expected_col_val):
                    correct += 1

        return {"total": total, "correct": correct}
