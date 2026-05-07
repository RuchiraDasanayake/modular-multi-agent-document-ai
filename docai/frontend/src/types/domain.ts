// Shared frontend domain types for DocAI v2.
// This file is intentionally practical and UI-oriented.

export type Timestamp = string;

// ---------------------------------------------------------------------------
// Project Types
// ---------------------------------------------------------------------------

export interface Project {
  project_id: string;
  name: string;
  description?: string;
  created_at: Timestamp;
  updated_at: Timestamp;
}

export interface ProjectSummary extends Project {
  job_count: number;
  last_run_status?: JobStatus;
  latest_metrics?: MetricsReport;
}

// ---------------------------------------------------------------------------
// Schema Types
// ---------------------------------------------------------------------------

export interface ExtractionSchema {
  schema_id: string;
  project_id: string;
  name: string;
  description?: string;
  version: string;
  fields: Field[];
  tables: Table[];
  created_at: Timestamp;
  updated_at: Timestamp;
}

export interface Field {
  field_id: string;
  name: string;
  description?: string;
  type: string;
  required: boolean;
  examples?: string[];
  validation_rules?: string[];
}

export interface Table {
  table_id: string;
  name: string;
  description?: string;
  columns: Column[];
  required: boolean;
  validation_rules?: string[];
}

export interface Column {
  column_id: string;
  name: string;
  description?: string;
  type: string;
  required: boolean;
  examples?: string[];
  validation_rules?: string[];
}

// ---------------------------------------------------------------------------
// Job Types
// ---------------------------------------------------------------------------

export type JobRunType = "training" | "production";

export type JobStatus =
  | "draft"
  | "queued"
  | "profiling"
  | "assigning_strategies"
  | "running"
  | "needs_review"
  | "completed"
  | "failed";

export interface Job {
  job_id: string;
  project_id: string;
  schema_id: string;
  name: string;
  run_type: JobRunType;
  status: JobStatus;
  created_at: Timestamp;
  started_at?: Timestamp;
  completed_at?: Timestamp;
}

// ---------------------------------------------------------------------------
// Document Types
// ---------------------------------------------------------------------------

export type DocumentStatus =
  | "uploaded"
  | "profiled"
  | "strategy_pending"
  | "ready"
  | "processing"
  | "completed"
  | "needs_review"
  | "failed";

export interface DocumentProfile {
  document_id: string;
  detected_type?: string;
  layout_type?: string;
  quality_bin?: string;
  language?: string;
  content_profile?: string;
  risk_flags?: string[];
  signals?: Record<string, unknown>;
}

export interface Document {
  document_id: string;
  job_id: string;
  original_filename: string;
  file_path: string;
  status: DocumentStatus;
  page_count?: number;
  uploaded_at: Timestamp;
  profile: DocumentProfile;
}

// ---------------------------------------------------------------------------
// Tool / Configuration Types
// ---------------------------------------------------------------------------

export interface AvailableTool {
  tool_id: string;
  tool_type: string;
  capabilities: string[];
  enabled: boolean;
  unavailable_reason?: string;
}

export interface AvailableTools {
  available_ocr_engines: AvailableTool[];
  available_parsers: AvailableTool[];
  available_models: AvailableTool[];
  available_validators: AvailableTool[];
  available_recovery_strategies: AvailableTool[];
}

export interface LocalModelConfig {
  provider: string;
  model: string;
  temperature: number;
  max_tokens: number;
  json_mode: boolean;
  fallback_model?: string;
}

// ---------------------------------------------------------------------------
// Strategy / Policy Types
// ---------------------------------------------------------------------------

export type StrategyStatus =
  | "candidate"
  | "testing"
  | "promoted"
  | "stable"
  | "drifting"
  | "retired";

export interface ExtractionStrategy {
  strategy_id: string;
  strategy_name: string;
  family?: string;
  version?: string;
  status: StrategyStatus;
  description?: string;
}

export interface StrategyAssignment {
  document_id: string;
  strategy_id: string;
  strategy_name: string;
  reason_assigned: string;
  compatible_tools: string[];
  learning_source?: string;
  status: StrategyStatus;
}

// ---------------------------------------------------------------------------
// Output Types
// ---------------------------------------------------------------------------

export interface FieldOutput {
  field_name: string;
  value: unknown;
  normalized_value?: unknown;
  confidence?: number;
  evidence_text?: string;
  evidence_location?: string;
  extraction_method?: string;
  validation_status?: ValidationStatus;
  issues?: ValidationIssue[];
}

export interface RowOutput {
  row_index: number;
  columns: Record<string, unknown>;
  evidence_text?: string;
  evidence_location?: string;
  confidence?: number;
  validation_status?: ValidationStatus;
  issues?: ValidationIssue[];
}

export interface TableOutput {
  table_name: string;
  rows: RowOutput[];
  confidence?: number;
  validation_status?: ValidationStatus;
  issues?: ValidationIssue[];
}

export interface ExtractedOutput {
  document_id: string;
  schema_id: string;
  strategy_id?: string;
  fields: FieldOutput[];
  tables: TableOutput[];
  artifact_paths?: string[];
}

export interface ExpectedOutput {
  document_id: string;
  expected_fields: Record<string, unknown>;
  expected_tables: Record<string, unknown>[];
  source?: string;
  reviewed_by?: string;
  reviewed_at?: Timestamp;
}

// ---------------------------------------------------------------------------
// Validation / Recovery Types
// ---------------------------------------------------------------------------

export type ValidationStatus =
  | "valid"
  | "low_confidence"
  | "not_grounded"
  | "missing"
  | "recovered"
  | "needs_review"
  | "failed";

export interface ValidationIssue {
  level: "field" | "row" | "table" | "document";
  target: string;
  code: string;
  message: string;
  suggested_fix?: string;
}

export interface ValidationReport {
  document_id: string;
  pass_status: boolean;
  field_issues: ValidationIssue[];
  table_issues: ValidationIssue[];
  document_issues: ValidationIssue[];
  summary?: string;
}

export type RecoveryStatus =
  | "not_attempted"
  | "attempted"
  | "recovered"
  | "failed"
  | "sent_to_review";

export interface RecoveryReport {
  document_id: string;
  status: RecoveryStatus;
  attempted: boolean;
  recovered_fields: string[];
  recovered_table_rows: string[];
  failed_items: string[];
  strategies_used: string[];
  summary?: string;
}

// ---------------------------------------------------------------------------
// Metrics Types
// ---------------------------------------------------------------------------

export interface StrategyMetrics {
  strategy_id: string;
  strategy_name: string;
  run_count: number;
  precision: number;
  recall: number;
  f1: number;
  validation_pass_rate: number;
  recovery_success_rate: number;
}

export interface MetricsReport {
  job_id: string;
  document_id?: string;
  precision?: number;
  recall?: number;
  f1?: number;
  field_accuracy?: number;
  table_accuracy?: number;
  grounding_coverage?: number;
  validation_pass_rate?: number;
  recovery_success_rate?: number;
  latency_ms?: number;
  strategy_id?: string;
}

export interface RunProgressionRecord {
  run_id: string;
  run_type: JobRunType;
  documents: number;
  reviewed: number;
  f1: number;
  validation_pass_rate: number;
  recovery_success_rate: number;
  best_strategy_id?: string;
  notes?: string;
}

// ---------------------------------------------------------------------------
// Learning Types
// ---------------------------------------------------------------------------

export interface LearningRecord {
  learning_record_id: string;
  document_id: string;
  schema_id: string;
  strategy_id?: string;
  metrics?: MetricsReport;
  validation_summary?: string;
  recovery_summary?: string;
  human_corrections?: Record<string, unknown>;
  created_at: Timestamp;
}

export interface StrategyRecommendation {
  strategy_id: string;
  strategy_name: string;
  recommendation: string;
  rationale: string;
  confidence?: "low" | "medium" | "high";
}

// ---------------------------------------------------------------------------
// Frontend Artifact Fixture Types (runtime spine aligned)
// ---------------------------------------------------------------------------

export interface FrontendStubMetadata {
  is_stub?: boolean;
  generated_by?: string;
  note?: string;
}

export interface FrontendJobContext extends FrontendStubMetadata {
  jobId: string;
  projectId: string;
  schemaId: string;
  jobName: string;
  runType: "Training Run" | "Production Run";
  jobStatus: "Queued" | "Profiling" | "Assigning Strategies" | "Running" | "Completed" | "Needs Review" | "Failed";
  documentCount: number;
  queuedDocumentIds: string[];
  strategyMode: string;
  selectedModel: string;
  selectedOcrPreference: string;
}

export interface FrontendQueuedDocument {
  documentId: string;
  filename: string;
  filePath: string;
  queueStatus: "Queued" | "Profiled" | "Strategy Assigned" | "Ready" | "Processing" | "Completed" | "Needs Review" | "Failed";
  profileStatus: "Queued" | "Profiled" | "Needs Review";
  strategyStatus: "Queued" | "Strategy Assigned" | "Needs Review";
  processingStatus: "Queued" | "Processing" | "Completed" | "Needs Review" | "Failed";
  reviewStatus: "Completed" | "Needs Review";
}

export interface FrontendSelectedPolicy extends FrontendStubMetadata {
  documentId: string;
  policyId: string;
  strategyName: string;
  selectedBy: string;
  reasons: string[];
  disabledCandidates?: Array<{
    policyId: string;
    reasonDisabled: string;
  }>;
}

export interface FrontendRunPlan extends FrontendStubMetadata {
  planId: string;
  documentId: string;
  schemaId: string;
  policyId: string;
  preprocessingSteps: string[];
  ocrConfig: Record<string, unknown>;
  parserConfig: Record<string, unknown>;
  modelConfig: Record<string, unknown>;
  fieldsToExtract: string[];
  tablesToExtract: string[];
  validationRules: string[];
  recoveryRules: string[];
}

export interface FrontendOCROutput extends FrontendStubMetadata {
  documentId: string;
  engineId: string;
  text: string;
  confidence: number;
  pages: Array<{
    pageNumber: number;
    text: string;
  }>;
}

export interface FrontendFieldOutput {
  fieldName: string;
  value: string;
  confidence: number;
  validationStatus: "Valid" | "Low Confidence" | "Not Grounded" | "Missing" | "Recovered" | "Needs Review" | "Failed";
  evidenceText?: string;
}

export interface FrontendTableOutput {
  tableName: string;
  rows: Array<{
    rowIndex: number;
    columns: Record<string, string>;
    validationStatus: "Valid" | "Low Confidence" | "Not Grounded" | "Missing" | "Recovered" | "Needs Review" | "Failed";
  }>;
}

export interface FrontendValidationReport extends FrontendStubMetadata {
  documentId: string;
  passStatus: boolean;
  summary: "Valid" | "Low Confidence" | "Not Grounded" | "Missing" | "Recovered" | "Needs Review" | "Failed";
  issues: Array<{
    target: string;
    message: string;
    status: "Valid" | "Low Confidence" | "Not Grounded" | "Missing" | "Recovered" | "Needs Review" | "Failed";
  }>;
}

export interface FrontendRecoveryReport extends FrontendStubMetadata {
  documentId: string;
  attempted: boolean;
  summary: "Recovered" | "Needs Review" | "Failed";
  recoveredItems: string[];
  failedItems: string[];
}

export interface FrontendFinalOutput extends FrontendStubMetadata {
  documentId: string;
  schemaId: string;
  policyId: string;
  fields: FrontendFieldOutput[];
  tables: FrontendTableOutput[];
  validationReport: FrontendValidationReport;
  recoveryReport: FrontendRecoveryReport;
  qualitySummary: "Completed" | "Needs Review";
}

export interface FrontendDocumentArtifacts {
  documentProfile: {
    documentId: string;
    detectedType: string;
    layoutType: string;
    qualityBin: string;
  } & FrontendStubMetadata;
  selectedPolicy: FrontendSelectedPolicy;
  runPlan: FrontendRunPlan;
  ocrOutput: FrontendOCROutput;
  extractedOutput: {
    documentId: string;
    fields: FrontendFieldOutput[];
    tables: FrontendTableOutput[];
  } & FrontendStubMetadata;
  validationReport: FrontendValidationReport;
  recoveryReport: FrontendRecoveryReport;
  finalOutput: FrontendFinalOutput;
}

export interface FrontendJobArtifacts {
  jobContext: FrontendJobContext;
  documentQueue: FrontendQueuedDocument[];
  selectedPoliciesByDocumentId: Record<string, FrontendSelectedPolicy>;
  runPlansByDocumentId: Record<string, FrontendRunPlan>;
  ocrOutputsByDocumentId: Record<string, FrontendOCROutput>;
  extractedOutputsByDocumentId: Record<
    string,
    {
      documentId: string;
      fields: FrontendFieldOutput[];
      tables: FrontendTableOutput[];
    } & FrontendStubMetadata
  >;
  validationReportsByDocumentId: Record<string, FrontendValidationReport>;
  recoveryReportsByDocumentId: Record<string, FrontendRecoveryReport>;
  finalOutputsByDocumentId: Record<string, FrontendFinalOutput>;
  metricsReport: (MetricsReport & FrontendStubMetadata) | null;
  extractedDataExport: {
    jobId: string;
    documentCount: number;
    documents: FrontendFinalOutput[];
  } & FrontendStubMetadata;
  runLog: Array<{
    event: string;
    documentId?: string;
    policyId?: string;
  }>;
}

export interface FrontendJobRunResult extends FrontendStubMetadata {
  jobId: string;
  documentCount: number;
  completedCount: number;
  policiesUsed: string[];
  artifactRoot: string;
}
