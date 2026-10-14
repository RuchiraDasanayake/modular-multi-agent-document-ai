export type ProductAutoDocumentStatus = "processed" | "needs_review" | "unsupported" | "failed";
export const PRODUCT_AUTO_OUTCOME_REASONS = [
  "unsupported_file_type", "file_too_large", "too_many_pages", "native_limit_exceeded",
  "multi_frame_image_unsupported", "native_parser_unavailable", "parse_failed", "ocr_failed",
  "schema_provider_error", "invalid_schema_model_response", "values_provider_error",
  "invalid_values_model_response", "invalid_strict_values_model_response",
] as const;
export type ProductAutoOutcomeReason = typeof PRODUCT_AUTO_OUTCOME_REASONS[number];
export type ProductAutoValueStatus = "accepted" | "needs_review" | "missing" | "rejected";
export type ProductAutoReviewDecision = "correct" | "incorrect" | "corrected" | "not_present" | "remove";
export type ProductAutoScalarType = "string" | "integer" | "decimal" | "boolean" | "date";

export interface ProductAutoEvidence {
  page: number;
  start: number;
  end: number;
  quote: string;
  kind?: "text_match";
}

// A reviewer-observed page is a location in the original image, not OCR or pixel evidence.
export interface ProductAutoHumanSourcePage {
  kind: "human_observed_page";
  page: number;
}

export interface ProductAutoParsedDocument {
  contract_version: 2;
  source_sha256: string;
  source_format: string;
  parser_id: string;
  parser_version: string;
  units: Array<{ unit_id: string; kind: string; ordinal: number; text: string; label: string | null }>;
  tables: Array<{ table_id: string; cells: Array<{
    row: number;
    column: number;
    text: string;
    anchors: Array<{ unit_id: string; native_locator: string | null;
      text_span: [number, number] | null; quote: string | null;
      raw_box: null; display_box: null }>;
  }> }>;
}

export interface ProductAutoLinkedCell {
  row: number;
  value: string;
  status: "accepted" | "needs_review";
  evidence?: ProductAutoEvidence;
  // Present only on image-derived machine proposals. This is a page hint, not pixel evidence.
  visual_page?: number;
  visual_grounding_verified?: false;
  review_state?: "pending";
}

export interface ProductAutoLinkedCorrectionRow {
  row: number;
  value: string;
}

export interface ProductAutoField {
  field_id: string;
  type: string;
  group?: string;
}

export interface ProductAutoValue {
  field_id: string;
  value: unknown;
  status: ProductAutoValueStatus;
  review_state: "none" | "pending" | "completed";
  evidence?: ProductAutoEvidence;
  visual_pages?: number[];
  visual_grounding_verified?: false;
}

export interface ProductAutoCandidate {
  contract_version: 1;
  doc_id: string;
  document_status: ProductAutoDocumentStatus;
  proposed_schema: ProductAutoField[];
  extracted_values: ProductAutoValue[];
  measurements?: { latency_ms?: number | null };
}

export interface ProductAutoReviewField {
  field_id: string;
  decision: ProductAutoReviewDecision;
  corrected_value?: string | null;
  note?: string | null;
}

export interface ProductAutoAddedScalarField {
  field_id: string;
  type: ProductAutoScalarType;
  value: string | number | boolean;
  // Optional only for audit events saved before source-backed additions.
  evidence?: ProductAutoEvidence;
  human_source_page?: ProductAutoHumanSourcePage;
  note?: string | null;
}

export interface ProductAutoAddedScalarFieldInput {
  field_id: string;
  type: ProductAutoScalarType;
  value: string;
  evidence?: Pick<ProductAutoEvidence, "page" | "quote">;
  human_source_page?: ProductAutoHumanSourcePage;
  note?: string | null;
}

export interface ProductAutoAddedLinkedCell {
  row: number;
  value: string;
  status: "accepted" | "needs_review";
  evidence?: ProductAutoEvidence;
  human_source_page?: ProductAutoHumanSourcePage;
  visual_grounding_verified?: false;
}

export interface ProductAutoAddedLinkedField {
  field_id: string;
  type: "array[object]";
  group: string;
  value: ProductAutoAddedLinkedCell[];
  note?: string | null;
}

export interface ProductAutoAddedLinkedFieldInput {
  field_id: string;
  type: "array[object]";
  group: string;
  value: Array<{ row: number; value: string; evidence?: Pick<ProductAutoEvidence, "page" | "quote">;
    human_source_page?: ProductAutoHumanSourcePage }>;
  note?: string | null;
}

export type ProductAutoAddedField = ProductAutoAddedScalarField | ProductAutoAddedLinkedField;
export type ProductAutoAddedFieldInput = ProductAutoAddedScalarFieldInput | ProductAutoAddedLinkedFieldInput;

export interface ProductAutoReview {
  review_version: 1;
  job_id: string;
  run_id: string;
  doc_id: string;
  status: "pending" | "completed";
  reviewer_user_id: string;
  updated_at: string;
  fields: ProductAutoReviewField[];
  // Optional so review events written before human-added fields remain readable.
  added_fields?: ProductAutoAddedField[];
  // Present on source-verified reviews; absent in older review artifacts.
  source_container_sha256?: string;
  source_pages_sha256?: string;
  // Binds the review to the exact extraction artifact bytes, including the machine candidate.
  machine_result_sha256?: string;
  revision: number;
  audit_event_id: string;
}

export interface ProductAutoAuditEvent {
  audit_event_id: string;
  revision: number;
  previous_event_id?: string | null;
  created_at: string;
  reviewer_user_id: string;
  // Optional reviewer estimate for work on this save; never inferred from timestamps.
  reported_active_review_seconds?: number;
  review_snapshot: ProductAutoReview;
  machine_fields: Array<{
    field_id: string;
    value: unknown;
    status: ProductAutoValueStatus | "not_proposed";
    evidence?: ProductAutoValue["evidence"];
  }>;
  review_fields: ProductAutoReviewField[];
  review_added_fields?: ProductAutoAddedField[];
  source_container_sha256?: string;
  source_pages_sha256?: string;
  machine_result_sha256?: string;
}

export interface ProductAutoCorrectedField {
  field_id: string;
  type: string;
  group?: string;
  value: unknown;
  status: "accepted" | "needs_review" | "missing";
  provenance: "machine" | "human_verified" | "human_correction" | "human_added";
  evidence?: ProductAutoValue["evidence"];
  human_source_page?: ProductAutoHumanSourcePage;
  visual_pages?: number[];
  visual_grounding_verified?: false;
}

export interface ProductAutoCorrectedResult {
  scope: "document";
  doc_id: string;
  review_revision: number;
  review_status: "unreviewed" | "pending" | "completed";
  fields: ProductAutoCorrectedField[];
  removed_field_ids: string[];
}

export interface ProductAutoReviewedExport {
  contract_version: 1;
  job_id: string;
  run_id: string;
  document: {
    doc_id: string;
    file_id: string;
    file_name: string;
    source_sha256: string;
    machine_result_sha256: string;
  };
  review: {
    revision: number;
    audit_event_id: string;
    reviewer_user_id: string;
    updated_at: string;
  };
  result: ProductAutoCorrectedResult;
}

export interface ProductAutoSourceDocument {
  fileId: string;
  fileName: string;
  selected: boolean;
}

export interface ProductAutoRunDocument {
  docId: string;
  fileId: string;
  fileName: string;
  status: ProductAutoDocumentStatus;
  fieldCount: number;
  acceptedCount: number;
  reviewStatus: "unreviewed" | "pending" | "completed";
}

export interface ProductAutoRun {
  runId: string;
  // Owner-scoped key for reconciling an uncertain browser response; never the run identity.
  idempotencyKey?: string;
  status: "queued" | "running" | "success" | "failed";
  createdAt: string;
  endedAt?: string;
  selectedCount: number;
  documents: ProductAutoRunDocument[];
  approvedRecipe?: { recipeId: string; revision: number; familyName: string; snapshotSha256: string };
  confirmedBrief?: { briefId: string; revision: number; payloadSha256: string; snapshotSha256: string;
    phase: "preview" | "batch"; previewRunId?: string };
  error?: string;
}

export interface ProductAutoDocumentDetail {
  runId: string;
  fileId: string;
  fileName: string;
  candidate: ProductAutoCandidate;
  // Only a fixed allowlist from the sealed sidecar can reach this owner-scoped API response.
  outcomeReason?: ProductAutoOutcomeReason;
  sourcePages: Array<{ page: number; text: string }>;
  visualRoute?: "visual" | "text" | "not_executed";
  parsedDocument?: ProductAutoParsedDocument;
  correctedResult: ProductAutoCorrectedResult;
  review: ProductAutoReview | null;
  auditTrail: ProductAutoAuditEvent[];
}
