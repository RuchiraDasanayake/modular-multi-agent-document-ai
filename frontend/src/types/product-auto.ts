export type ProductAutoDocumentStatus = "processed" | "needs_review" | "unsupported" | "failed";
export type ProductAutoValueStatus = "accepted" | "needs_review" | "missing" | "rejected";
export type ProductAutoReviewDecision = "correct" | "incorrect" | "corrected" | "not_present" | "remove";
export type ProductAutoScalarType = "string" | "integer" | "decimal" | "boolean" | "date";

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
  evidence?: { page: number; start: number; end: number; quote: string };
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

export interface ProductAutoAddedField {
  field_id: string;
  type: ProductAutoScalarType;
  value: string | number | boolean;
  note?: string | null;
}

export interface ProductAutoAddedFieldInput {
  field_id: string;
  type: ProductAutoScalarType;
  value: string;
  note?: string | null;
}

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
  revision: number;
  audit_event_id: string;
}

export interface ProductAutoAuditEvent {
  audit_event_id: string;
  revision: number;
  previous_event_id?: string | null;
  created_at: string;
  reviewer_user_id: string;
  review_snapshot: ProductAutoReview;
  machine_fields: Array<{
    field_id: string;
    value: unknown;
    status: ProductAutoValueStatus | "not_proposed";
    evidence?: ProductAutoValue["evidence"];
  }>;
  review_fields: ProductAutoReviewField[];
  review_added_fields?: ProductAutoAddedField[];
}

export interface ProductAutoCorrectedField {
  field_id: string;
  type: string;
  group?: string;
  value: unknown;
  status: "accepted" | "needs_review" | "missing";
  provenance: "machine" | "human_verified" | "human_correction" | "human_added";
  evidence?: ProductAutoValue["evidence"];
}

export interface ProductAutoCorrectedResult {
  scope: "document";
  doc_id: string;
  review_revision: number;
  review_status: "unreviewed" | "pending" | "completed";
  fields: ProductAutoCorrectedField[];
  removed_field_ids: string[];
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
  status: "running" | "success" | "failed";
  createdAt: string;
  endedAt?: string;
  selectedCount: number;
  documents: ProductAutoRunDocument[];
  error?: string;
}

export interface ProductAutoDocumentDetail {
  runId: string;
  fileId: string;
  fileName: string;
  candidate: ProductAutoCandidate;
  correctedResult: ProductAutoCorrectedResult;
  review: ProductAutoReview | null;
  auditTrail: ProductAutoAuditEvent[];
}
