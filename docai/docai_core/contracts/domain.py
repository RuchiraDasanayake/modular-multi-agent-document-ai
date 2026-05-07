from __future__ import annotations

from dataclasses import asdict, dataclass, field as dc_field
from datetime import datetime
import json
from typing import Literal

ScalarValue = str | int | float | bool | None

JobRunType = Literal["training", "production"]
JobStatus = Literal[
    "draft",
    "queued",
    "profiling",
    "assigning_strategies",
    "running",
    "needs_review",
    "completed",
    "failed",
]
DocumentStatus = Literal[
    "uploaded",
    "profiled",
    "strategy_pending",
    "ready",
    "processing",
    "completed",
    "needs_review",
    "failed",
]
ValidationStatus = Literal[
    "valid",
    "low_confidence",
    "not_grounded",
    "missing",
    "recovered",
    "needs_review",
    "failed",
]
RecoveryStatus = Literal[
    "not_attempted",
    "attempted",
    "recovered",
    "failed",
    "sent_to_review",
]
QueueStatus = Literal[
    "queued",
    "profiled",
    "strategy_assigned",
    "ready",
    "processing",
    "completed",
    "needs_review",
    "failed",
]


class Serializable:
    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=_json_default, sort_keys=True)


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


# Core contracts.
@dataclass(slots=True)
class Project(Serializable):
    project_id: str
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(slots=True)
class Field(Serializable):
    field_id: str
    name: str
    description: str | None
    type: str
    required: bool = False
    examples: list[str] = dc_field(default_factory=list)
    validation_rules: list[str] = dc_field(default_factory=list)
    aliases: list[str] = dc_field(default_factory=list)


@dataclass(slots=True)
class Column(Serializable):
    column_id: str
    name: str
    description: str | None
    type: str
    required: bool = False
    examples: list[str] = dc_field(default_factory=list)
    validation_rules: list[str] = dc_field(default_factory=list)


@dataclass(slots=True)
class Table(Serializable):
    table_id: str
    name: str
    description: str | None
    columns: list[Column] = dc_field(default_factory=list)
    required: bool = False
    validation_rules: list[str] = dc_field(default_factory=list)


@dataclass(slots=True)
class ExtractionSchema(Serializable):
    schema_id: str
    project_id: str
    name: str
    description: str | None
    version: str
    fields: list[Field] = dc_field(default_factory=list)
    tables: list[Table] = dc_field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class Job(Serializable):
    job_id: str
    project_id: str
    schema_id: str
    name: str
    run_type: JobRunType
    status: JobStatus
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


@dataclass(slots=True)
class DocumentProfile(Serializable):
    document_id: str
    detected_type: str | None = None
    layout_type: str | None = None
    quality_bin: str | None = None
    language: str | None = None
    content_profile: str | None = None
    risk_flags: list[str] = dc_field(default_factory=list)
    signals: dict[str, ScalarValue] = dc_field(default_factory=dict)


@dataclass(slots=True)
class Document(Serializable):
    document_id: str
    job_id: str
    original_filename: str
    file_path: str
    status: DocumentStatus
    uploaded_at: datetime
    profile: DocumentProfile
    page_count: int | None = None


@dataclass(slots=True)
class ProjectContext(Serializable):
    project_id: str
    domain: str = "general"
    document_type: str = "document"
    extraction_goal: str = "Extract structured data from documents."
    precision_preference: str = "balanced"
    local_model: str = "stub_local_model"
    ocr_preference: str = "stub_ocr"
    field_hints: list[str] = dc_field(default_factory=list)
    table_hints: list[str] = dc_field(default_factory=list)
    known_edge_cases: list[str] = dc_field(default_factory=list)
    approved_examples: list[str] = dc_field(default_factory=list)
    validation_preferences: dict[str, ScalarValue] = dc_field(default_factory=dict)
    recovery_preferences: dict[str, ScalarValue] = dc_field(default_factory=dict)
    preferred_strategies: list[str] = dc_field(default_factory=list)
    failed_strategies: list[str] = dc_field(default_factory=list)
    review_lessons: list[str] = dc_field(default_factory=list)
    learning_summary: str | None = None
    version: str = "v1"
    updated_at: datetime | None = None


@dataclass(slots=True)
class JobContext(Serializable):
    job_id: str
    project_id: str
    schema_id: str
    run_type: JobRunType
    job_name: str
    run_notes: str | None = None
    selected_model_config: dict[str, ScalarValue] = dc_field(default_factory=dict)
    selected_ocr_preference: str | None = None
    strategy_mode: str = "deterministic_policy"
    project_context_snapshot: ProjectContext | None = None
    document_count: int = 0
    queued_document_ids: list[str] = dc_field(default_factory=list)
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    is_stub: bool = False
    generated_by: str | None = None
    note: str | None = None


@dataclass(slots=True)
class QueuedDocument(Serializable):
    document_id: str
    job_id: str
    filename: str
    file_path: str
    queue_status: QueueStatus = "queued"
    profile_status: Literal["pending", "completed", "failed"] = "pending"
    strategy_status: Literal["pending", "assigned", "failed"] = "pending"
    processing_status: Literal["not_started", "processing", "completed", "failed"] = "not_started"
    review_status: Literal["required", "optional", "completed", "not_needed"] = "optional"
    created_at: datetime | None = None
    updated_at: datetime | None = None


# Tools and policy contracts.
@dataclass(slots=True)
class AvailableTool(Serializable):
    tool_id: str
    tool_type: str
    capabilities: list[str] = dc_field(default_factory=list)
    enabled: bool = True
    unavailable_reason: str | None = None


@dataclass(slots=True)
class AvailableTools(Serializable):
    available_ocr_engines: list[AvailableTool] = dc_field(default_factory=list)
    available_parsers: list[AvailableTool] = dc_field(default_factory=list)
    available_models: list[AvailableTool] = dc_field(default_factory=list)
    available_validators: list[AvailableTool] = dc_field(default_factory=list)
    available_recovery_strategies: list[AvailableTool] = dc_field(default_factory=list)


@dataclass(slots=True)
class DisabledCandidate(Serializable):
    policy_id: str
    reason_disabled: str


@dataclass(slots=True)
class SelectedPolicy(Serializable):
    policy_id: str
    policy_family: str
    policy_version: str
    selected_by: str
    confidence: float | None = None
    reasons: list[str] = dc_field(default_factory=list)
    disabled_candidates: list[DisabledCandidate] = dc_field(default_factory=list)


@dataclass(slots=True)
class RunPlan(Serializable):
    plan_id: str
    document_id: str
    schema_id: str
    policy_id: str
    preprocessing_steps: list[str] = dc_field(default_factory=list)
    ocr_config: dict[str, ScalarValue] = dc_field(default_factory=dict)
    parser_config: dict[str, ScalarValue] = dc_field(default_factory=dict)
    model_config: dict[str, ScalarValue] = dc_field(default_factory=dict)
    fields_to_extract: list[str] = dc_field(default_factory=list)
    tables_to_extract: list[str] = dc_field(default_factory=list)
    validation_rules: list[str] = dc_field(default_factory=list)
    recovery_rules: list[str] = dc_field(default_factory=list)
    artifact_paths: list[str] = dc_field(default_factory=list)


# Output contracts.
@dataclass(slots=True)
class OCRPage(Serializable):
    page_number: int
    text: str
    blocks: list[dict[str, ScalarValue]] = dc_field(default_factory=list)


@dataclass(slots=True)
class OCROutput(Serializable):
    document_id: str
    engine_id: str
    text: str
    pages: list[OCRPage] = dc_field(default_factory=list)
    blocks: list[dict[str, ScalarValue]] = dc_field(default_factory=list)
    tables_detected: list[str] = dc_field(default_factory=list)
    confidence: float | None = None
    artifact_paths: list[str] = dc_field(default_factory=list)


@dataclass(slots=True)
class FieldOutput(Serializable):
    field_name: str
    value: ScalarValue
    normalized_value: ScalarValue = None
    confidence: float | None = None
    evidence_text: str | None = None
    evidence_location: str | None = None
    extraction_method: str | None = None
    validation_status: ValidationStatus = "needs_review"
    issues: list[str] = dc_field(default_factory=list)


@dataclass(slots=True)
class RowOutput(Serializable):
    row_index: int
    columns: dict[str, ScalarValue]
    evidence_text: str | None = None
    evidence_location: str | None = None
    confidence: float | None = None
    validation_status: ValidationStatus = "needs_review"
    issues: list[str] = dc_field(default_factory=list)


@dataclass(slots=True)
class TableOutput(Serializable):
    table_name: str
    rows: list[RowOutput] = dc_field(default_factory=list)
    confidence: float | None = None
    validation_status: ValidationStatus = "needs_review"
    issues: list[str] = dc_field(default_factory=list)


@dataclass(slots=True)
class ExtractedOutput(Serializable):
    document_id: str
    schema_id: str
    policy_id: str
    fields: list[FieldOutput] = dc_field(default_factory=list)
    tables: list[TableOutput] = dc_field(default_factory=list)
    artifact_paths: list[str] = dc_field(default_factory=list)


@dataclass(slots=True)
class ValidationReport(Serializable):
    document_id: str
    field_issues: list[str] = dc_field(default_factory=list)
    table_issues: list[str] = dc_field(default_factory=list)
    document_issues: list[str] = dc_field(default_factory=list)
    pass_status: bool = False
    summary: str | None = None
    artifact_paths: list[str] = dc_field(default_factory=list)


@dataclass(slots=True)
class RecoveryReport(Serializable):
    document_id: str
    status: RecoveryStatus = "not_attempted"
    attempted: bool = False
    recovered_fields: list[str] = dc_field(default_factory=list)
    recovered_table_rows: list[int] = dc_field(default_factory=list)
    failed_items: list[str] = dc_field(default_factory=list)
    strategies_used: list[str] = dc_field(default_factory=list)
    summary: str | None = None
    artifact_paths: list[str] = dc_field(default_factory=list)


@dataclass(slots=True)
class FinalOutput(Serializable):
    document_id: str
    schema_id: str
    policy_id: str
    fields: list[FieldOutput]
    tables: list[TableOutput]
    validation_report: ValidationReport
    recovery_report: RecoveryReport
    quality_summary: str | None = None
    artifact_paths: list[str] = dc_field(default_factory=list)


@dataclass(slots=True)
class ExpectedOutput(Serializable):
    document_id: str
    expected_fields: dict[str, ScalarValue] = dc_field(default_factory=dict)
    expected_tables: list[dict[str, ScalarValue]] = dc_field(default_factory=list)
    source: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None


@dataclass(slots=True)
class MetricsReport(Serializable):
    job_id: str
    document_id: str | None = None
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    field_accuracy: float | None = None
    table_accuracy: float | None = None
    grounding_coverage: float | None = None
    validation_pass_rate: float | None = None
    recovery_success_rate: float | None = None
    latency_ms: int | None = None
    policy_id: str | None = None
    artifact_paths: list[str] = dc_field(default_factory=list)


@dataclass(slots=True)
class LearningRecord(Serializable):
    learning_record_id: str
    document_id: str
    schema_id: str
    policy_id: str
    metrics: MetricsReport | None = None
    validation_summary: str | None = None
    recovery_summary: str | None = None
    human_correction_summary: str | None = None
    created_at: datetime | None = None
