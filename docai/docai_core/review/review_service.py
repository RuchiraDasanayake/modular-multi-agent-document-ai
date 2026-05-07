from __future__ import annotations

from dataclasses import dataclass

from docai_core.contracts.domain import FinalOutput
from docai_core.review.expected_values import (
    ExpectedFieldValue,
    ExpectedTableRowValue,
    ExpectedValues,
    ReviewRecord,
)


@dataclass(slots=True)
class ReviewService:
    """Creates ExpectedValues and ReviewRecord from a FinalOutput and reviewer corrections.

    Does not write artifacts, calculate metrics, create LearningRecords,
    or mutate policies, strategies, or prompts.
    """

    def build_expected_values_from_final_output(
        self,
        final_output: FinalOutput,
        field_corrections: dict[str, str] | None = None,
        table_row_corrections: dict[str, dict[str, str]] | None = None,
        reviewer_id: str | None = None,
    ) -> ExpectedValues:
        """Build ExpectedValues from a FinalOutput with optional reviewer corrections.

        field_corrections:       {field_name: corrected_value}
        table_row_corrections:   {"{table_name}:{row_index}": {col_name: corrected_value}}
        """
        corrections = field_corrections or {}
        row_corrections = table_row_corrections or {}

        expected_fields = self._build_expected_fields(final_output, corrections)
        expected_table_rows = self._build_expected_table_rows(final_output, row_corrections)

        return ExpectedValues(
            document_id=final_output.document_id,
            schema_id=final_output.schema_id,
            fields=expected_fields,
            table_rows=expected_table_rows,
            reviewer_id=reviewer_id,
        )

    def create_review_record(
        self,
        job_id: str,
        run_type: str,
        final_output: FinalOutput,
        expected_values: ExpectedValues,
        approved_final_output: bool = False,
        reviewer_id: str | None = None,
        reviewer_note: str | None = None,
    ) -> ReviewRecord:
        """Create a ReviewRecord from a completed review session."""
        review_id = f"{job_id}:{final_output.document_id}:review"
        review_status = self._derive_review_status(expected_values, approved_final_output)
        return ReviewRecord(
            review_id=review_id,
            job_id=job_id,
            document_id=final_output.document_id,
            schema_id=final_output.schema_id,
            run_type=run_type,
            expected_values=expected_values,
            review_status=review_status,
            approved_final_output=approved_final_output,
            reviewer_id=reviewer_id,
            reviewer_note=reviewer_note,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_expected_fields(
        self,
        final_output: FinalOutput,
        corrections: dict[str, str],
    ) -> list[ExpectedFieldValue]:
        result: list[ExpectedFieldValue] = []
        for field in final_output.fields:
            extracted = "" if field.value is None else str(field.value)
            correction = corrections.get(field.field_name)
            if correction is not None and correction != extracted:
                expected = correction
                corrected = True
            else:
                expected = extracted
                corrected = False
            result.append(
                ExpectedFieldValue(
                    field_name=field.field_name,
                    expected_value=expected,
                    extracted_value=extracted,
                    corrected=corrected,
                )
            )
        return result

    def _build_expected_table_rows(
        self,
        final_output: FinalOutput,
        row_corrections: dict[str, dict[str, str]],
    ) -> list[ExpectedTableRowValue]:
        result: list[ExpectedTableRowValue] = []
        for table in final_output.tables:
            for row in table.rows:
                key = f"{table.table_name}:{row.row_index}"
                extracted_cols = {k: ("" if v is None else str(v)) for k, v in row.columns.items()}
                correction = row_corrections.get(key)
                if correction is not None and correction != extracted_cols:
                    expected_cols = correction
                    corrected = True
                else:
                    expected_cols = dict(extracted_cols)
                    corrected = False
                result.append(
                    ExpectedTableRowValue(
                        table_name=table.table_name,
                        row_index=row.row_index,
                        expected_columns=expected_cols,
                        extracted_columns=extracted_cols,
                        corrected=corrected,
                    )
                )
        return result

    def _derive_review_status(
        self,
        expected_values: ExpectedValues,
        approved_final_output: bool,
    ) -> str:
        if approved_final_output:
            return "approved"
        any_corrected = any(f.corrected for f in expected_values.fields) or any(
            r.corrected for r in expected_values.table_rows
        )
        return "corrected" if any_corrected else "reviewed"
