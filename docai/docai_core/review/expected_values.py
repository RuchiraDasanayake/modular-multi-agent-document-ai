from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone


@dataclass(slots=True)
class ExpectedFieldValue:
    field_name: str
    expected_value: str
    extracted_value: str | None = None
    corrected: bool = False
    reviewer_note: str | None = None


@dataclass(slots=True)
class ExpectedTableRowValue:
    table_name: str
    row_index: int
    expected_columns: dict[str, str]
    extracted_columns: dict[str, str] = dc_field(default_factory=dict)
    corrected: bool = False
    reviewer_note: str | None = None


@dataclass(slots=True)
class ExpectedValues:
    document_id: str
    schema_id: str
    fields: list[ExpectedFieldValue] = dc_field(default_factory=list)
    table_rows: list[ExpectedTableRowValue] = dc_field(default_factory=list)
    reviewer_id: str | None = None
    created_at: datetime = dc_field(default_factory=lambda: datetime.now(timezone.utc))
    # Provenance: track whether these are human review labels or test/dataset labels.
    # "human_review" = human corrected extraction (production workflow)
    # "dataset_label" = labeled dataset for benchmarking
    # "test_fixture" = synthetic test fixture
    source: str = "human_review"
    is_human_review: bool = True


@dataclass(slots=True)
class ReviewRecord:
    review_id: str
    job_id: str
    document_id: str
    schema_id: str
    run_type: str
    expected_values: ExpectedValues
    review_status: str
    approved_final_output: bool = False
    reviewer_id: str | None = None
    reviewer_note: str | None = None
    created_at: datetime = dc_field(default_factory=lambda: datetime.now(timezone.utc))
