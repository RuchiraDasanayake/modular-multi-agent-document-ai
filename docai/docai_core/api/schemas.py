from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    service: str


class RunResponse(BaseModel):
    run_id: str
    job_id: str
    is_stub: bool
    generated_by: str
    document_count: int
    completed_count: int
    artifact_root: str
    policies_used: list[str]
    note: str | None = None


class ArtifactListResponse(BaseModel):
    run_id: str
    artifact_count: int
    artifacts: list[str]


# ---------------------------------------------------------------------------
# Advisory endpoint schemas
# ---------------------------------------------------------------------------

class PolicyRecordInput(BaseModel):
    policy_id: str
    policy_version: str = "v1"
    document_type: str
    quality_bin: str
    document_count: int
    field_accuracy: float | None = None
    field_precision: float | None = None
    field_recall: float | None = None
    field_f1: float | None = None
    missing_rate: float | None = None
    correction_rate: float | None = None
    evaluated_at: datetime


class AdvisoryRequest(BaseModel):
    document_type: str
    quality_bin: str
    min_document_count: int = 10
    records: list[PolicyRecordInput]


class AdvisoryRecommendationOut(BaseModel):
    policy_id: str
    policy_version: str
    document_type: str
    quality_bin: str
    score: float | None
    reason: str
    evidence_document_count: int
    field_f1: float | None
    field_accuracy: float | None
    missing_rate: float | None
    correction_rate: float | None


class AdvisoryResponse(BaseModel):
    status: str
    reason: str
    recommendation: AdvisoryRecommendationOut | None = None


# ---------------------------------------------------------------------------
# Projects and Jobs endpoints
# ---------------------------------------------------------------------------

class ProjectCreate(BaseModel):
    name: str
    description: str | None = None


class ProjectOut(BaseModel):
    project_id: str
    name: str
    description: str | None
    status: str
    created_at: str


class JobCreate(BaseModel):
    name: str
    schema_id: str | None = None
    profile_id: str | None = None
    default_mode: str | None = None
    job_type: str = "training"


class JobOut(BaseModel):
    job_id: str
    project_id: str
    schema_id: str
    profile_id: str | None = None
    default_mode: str | None = None
    name: str
    job_type: str
    status: str
    created_at: str


class ExtractionProfileCreate(BaseModel):
    name: str
    schema_id: str
    mode: str
    ocr_strategy: str
    validation_level: str
    is_default: bool = False
    created_from_advice_id: str | None = None


class ExtractionProfileUpdate(BaseModel):
    name: str
    schema_id: str
    mode: str
    ocr_strategy: str
    validation_level: str
    is_default: bool
    created_from_advice_id: str | None = None


class ExtractionProfileOut(BaseModel):
    profile_id: str
    project_id: str
    name: str
    schema_id: str
    mode: str
    ocr_strategy: str
    validation_level: str
    is_default: bool
    created_from_advice_id: str | None
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Extraction Schemas endpoints
# ---------------------------------------------------------------------------

class ExtractionSchemaField(BaseModel):
    id: str | None = None
    name: str
    type: str | None = None
    required: bool = False
    description: str | None = None


class ExtractionSchemaColumn(BaseModel):
    id: str | None = None
    name: str
    type: str | None = None


class ExtractionSchemaTable(BaseModel):
    id: str | None = None
    name: str
    description: str | None = None
    columns: list[ExtractionSchemaColumn] = []


class ExtractionSchemaCreate(BaseModel):
    name: str
    document_type: str | None = None
    fields: list[ExtractionSchemaField] = []
    tables: list[ExtractionSchemaTable] = []


class ExtractionSchemaUpdate(BaseModel):
    name: str
    document_type: str | None = None
    fields: list[ExtractionSchemaField] = []
    tables: list[ExtractionSchemaTable] = []


class ExtractionSchemaOut(BaseModel):
    schema_id: str
    project_id: str
    name: str
    document_type: str | None
    version: int
    fields: list[ExtractionSchemaField]
    tables: list[ExtractionSchemaTable]
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Documents endpoints
# ---------------------------------------------------------------------------

class DocumentCreate(BaseModel):
    original_filename: str
    file_path: str
    file_hash: str | None = None
    file_type: str | None = None
    status: str = "registered"


class DocumentOut(BaseModel):
    document_id: str
    project_id: str
    job_id: str
    original_filename: str
    file_path: str
    file_hash: str | None
    file_type: str | None
    status: str
    created_at: str


# ---------------------------------------------------------------------------
# Runs endpoints
# ---------------------------------------------------------------------------

class RunCreate(BaseModel):
    policy_id: str | None = None
    mode: str | None = None
    run_type: str = "practice"
    status: str = "created"
    artifact_root: str | None = None


class RunOut(BaseModel):
    run_id: str
    project_id: str
    job_id: str
    schema_id: str
    policy_id: str | None
    mode: str | None
    run_type: str
    status: str
    artifact_root: str | None
    created_at: str
    completed_at: str | None


class RunDocumentCreate(BaseModel):
    document_id: str
    status: str = "pending"
    schema_id: str | None = None
    mode: str | None = None
    routing_reason: str | None = None


class RunDocumentRoutingUpdate(BaseModel):
    schema_id: str | None = None
    mode: str | None = None
    routing_reason: str | None = None


class RunDocumentOut(BaseModel):
    run_document_id: str
    run_id: str
    document_id: str
    schema_id: str | None = None
    mode: str | None = None
    routing_reason: str | None = None
    routing_source: Literal["run_default", "document_override"]
    status: str
    created_at: str
    completed_at: str | None


# ---------------------------------------------------------------------------
# Artifact indexing endpoints
# ---------------------------------------------------------------------------

class ArtifactIndexRequest(BaseModel):
    artifact_root: str | None = None
    document_id: str | None = None


class ArtifactIndexResponse(BaseModel):
    run_id: str
    document_id: str | None
    artifact_root: str
    artifacts_indexed: int
    metrics_indexed: bool
    warnings: list[str]
    errors: list[str]


# ---------------------------------------------------------------------------
# Run execution endpoints
# ---------------------------------------------------------------------------

class ExecuteRunRequest(BaseModel):
    artifact_root: str | None = None
    index_artifacts: bool = True


class ExecuteRunResponse(BaseModel):
    run_id: str
    project_id: str
    job_id: str
    status: str
    artifact_root: str
    document_count: int
    completed_count: int
    generated_by: str
    is_stub: bool
    artifacts_indexed: int
    metrics_indexed: bool
    execution_errors: list[str]
    indexing_warnings: list[str]
    indexing_errors: list[str]


# ---------------------------------------------------------------------------
# Review record endpoints
# ---------------------------------------------------------------------------

class ReviewCorrectionCreate(BaseModel):
    field_name: str
    decision: str
    corrected_value: str | None = None


class ReviewRecordCreate(BaseModel):
    reviewer_id: str | None = None
    review_status: str
    review_note: str | None = None
    corrections: list[ReviewCorrectionCreate]


class ReviewCorrectionOut(BaseModel):
    correction_id: str
    field_name: str
    extracted_value_snapshot: str | None
    corrected_value: str | None
    decision: str
    evidence_text_snapshot: str | None
    validation_status_snapshot: str | None
    created_at: str


class ReviewRecordOut(BaseModel):
    review_id: str
    run_id: str
    job_id: str
    document_id: str
    schema_id: str | None
    review_status: str
    reviewer_id: str | None
    review_note: str | None
    source: str
    created_at: str
    corrections: list[ReviewCorrectionOut]


class LearningSampleOut(BaseModel):
    """Learning sample derived from human review correction.

    Each correction in a review record becomes one learning sample
    for future training/evaluation. Samples are derived evidence only;
    no automatic training or model updates occur.
    """
    sample_id: str
    run_id: str
    document_id: str
    review_id: str
    field_name: str
    decision: str
    original_value: str | None = None
    corrected_value: str | None = None
    evidence_text: str | None = None
    validation_status: str | None = None
    source: str = "human_review"
    created_at: str


class LearningSampleListOut(BaseModel):
    run_id: str
    samples: list[LearningSampleOut]


# ---------------------------------------------------------------------------
# Adaptive Routing advice endpoints
# ---------------------------------------------------------------------------

class AdaptiveRoutingRecommendationOut(BaseModel):
    """Read-only recommendation based on reviewed evidence."""
    recommendation_id: str
    type: Literal[
        "field_frequently_corrected",
        "field_frequently_missing",
        "field_frequently_hallucinated",
        "schema_needs_review",
        "insufficient_evidence",
    ]
    severity: Literal["info", "warning"]
    schema_id: str | None = None
    field_name: str | None = None
    evidence_count: int
    correction_rate: float | None = None
    message: str
    suggested_action: str
    automatic_action_taken: bool


class AdaptiveRoutingAdviceOut(BaseModel):
    """Complete Adaptive Routing advice output."""
    project_id: str
    evidence_count: int
    minimum_required: int
    status: Literal["insufficient_evidence", "ready"]
    generated_by: str
    is_read_only: bool
    automatic_action_taken: bool
    recommendations: list[AdaptiveRoutingRecommendationOut]
    diagnostics: dict[str, Any] | None = None
