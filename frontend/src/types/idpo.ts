/**
 * IDPO runner API and job workspace types (frontend local runner endpoints under /api/*).
 */

export type JobState = "draft" | "queued" | "running" | "success" | "failed";
export type JobQueueStatus = "loaded" | "processing" | "processed" | "failed";
export type JobExecutionMode = "adaptive" | "strict" | "both";
export type JobRunMode = "adaptive" | "strict";
export type ReviewStatus = "unreviewed" | "ai_validated" | "human_reviewed";
export type ReviewSource = "ai" | "human";
export type ReviewStage = "local" | "cloud";
export type JobValidationContextSource = "auto_review" | "human_review" | "system" | "operator";

export interface JobValidationPromptPreview {
  autoReview: string;
  extraction: string;
}

export interface JobValidationContextSummary {
  jobPurpose: string;
  knownVendors: string[];
  fieldClarifications: string[];
  recurringFailurePatterns: string[];
  reviewedCorrectionPatterns: string[];
  validationNotes: string[];
}

export interface JobValidationContextManualInput {
  jobPurpose?: string;
  knownVendors?: string[];
  fieldClarifications?: string[];
  validationNotes?: string[];
}

export interface JobValidationContextVersion {
  versionNumber: number;
  updatedAt: string;
  source: JobValidationContextSource;
  changes: string[];
  summary: JobValidationContextSummary;
  promptPreview: JobValidationPromptPreview;
}

export interface JobValidationContextArtifact {
  version: 1;
  jobId: string;
  updatedAt: string;
  currentVersionNumber: number;
  manualInput: JobValidationContextManualInput;
  current: JobValidationContextVersion;
  history: JobValidationContextVersion[];
}

export interface JobFieldConfig {
  name: string;
  description?: string;
}

export interface JobDocumentRunOutcome {
  runId: string;
  mode: JobRunMode;
  docId: string | null;
  status: JobQueueStatus;
  route: string | null;
  policy: string | null;
  errorSummary: string | null;
  reviewState: string | null;
  reviewStatus?: ReviewStatus | null;
  reviewSource?: ReviewSource | null;
  reviewStage?: ReviewStage | null;
  reviewConfidence?: number | null;
  fieldValues: Record<string, string>;
  adviceInfluenced: boolean;
  feedbackLogged: boolean;
  fallbackReason?: string | null;
  exactPrecision?: number | null;
  exactRecall?: number | null;
  exactF1?: number | null;
  expectedFieldValues?: Record<string, string> | null;
}

export interface JobDocumentRecord {
  fileId: string;
  fileName: string;
  storedName: string;
  size: number;
  selected: boolean;
  status: JobQueueStatus;
  errorSummary: string | null;
  reviewState: string | null;
  reviewStatus?: ReviewStatus | null;
  reviewSource?: ReviewSource | null;
  reviewStage?: ReviewStage | null;
  reviewConfidence?: number | null;
  latestRoute: string | null;
  latestPolicy: string | null;
  latestRunId: string | null;
  latestDocId: string | null;
  createdAt: string;
  updatedAt: string;
  outcomes: JobDocumentRunOutcome[];
}

export interface JobDocumentText {
  jobId: string;
  fileId: string;
  fileName: string;
  runId: string | null;
  text: string;
  truncated: boolean;
}

export interface JobRunRecord {
  jobRunId: string;
  runId: string | null;
  mode: JobRunMode;
  status: JobState;
  createdAt: string;
  startedAt?: string;
  endedAt?: string;
  fieldSnapshot: JobFieldConfig[];
  selectedFileIds: string[];
  runPath?: string | null;
  error?: string | null;
  processedCount?: number;
  failedCount?: number;
  adviceDocumentCount?: number;
  loggedFeedbackCount?: number;
}

export interface JobAHMNSummary {
  jobProfile: string;
  memoryMatched: boolean;
  documentsWithAdvice: number;
  documentsLoggedBack: number;
  adviceInfluencedCount: number;
  reviewedDocumentCount: number;
  reviewedHumanCount: number;
  reviewedAiCount: number;
  reviewedFeedbackLoggedCount: number;
  reviewedFeedbackPendingCount: number;
  jobOverlayPolicies: number;
  jobOverlayReady: boolean;
  adaptationSummary: string;
}

export interface JobCounts {
  loadedCount: number;
  processingCount: number;
  processedCount: number;
  failedCount: number;
}

export interface JobStatus {
  jobId: string;
  status: JobState;
  createdAt: string;
  startedAt: string;
  endedAt?: string;
  commandId: string;
  runId: string | null;
  runPath: string | null;
  logs: string[];
  settings: Record<string, unknown>;
  jobName?: string;
  mode?: JobExecutionMode;
  fieldConfigCurrent?: JobFieldConfig[];
  documents?: JobDocumentRecord[];
  runs?: JobRunRecord[];
  ahmnSummary?: JobAHMNSummary;
  counts?: JobCounts;
  latestRunId?: string | null;
  uploadsPath?: string | null;
  reviewContext?: JobValidationContextArtifact | null;
  error?: string;
  serverInstanceId?: string;
  [key: string]: unknown;
}

export interface RunSummary {
  runId: string;
  displayName: string;
  createdAt: string;
  updatedAt: string;
  status: "ready" | "running" | "failed" | "unknown" | string;
  docCount: number;
  source: "runs" | "sample" | string;
  rootPath: string;
  primaryPath: string;
  hasShadow: boolean;
  [key: string]: unknown;
}

export interface SystemCheck {
  id: string;
  kind: "http" | "cli";
  ok: boolean;
  detail: string;
}

export interface SystemStatus {
  timestamp: string;
  checks: SystemCheck[];
  defaultCommandId: string;
  [key: string]: unknown;
}

export interface RunOverview {
  run: RunSummary;
  metrics: Record<string, number | string | boolean | null>;
  documents: DocumentSummary[];
  retriesCount: number;
  escalationsCount: number;
  rollbackCount: number;
  validationPassRate: number | null;
  p95LatencyMs: number | null;
  estimatedCost: number | null;
  adviceAcceptedCount?: number;
  policyChangedCount?: number;
  directScoredDocCount?: number;
  [key: string]: unknown;
}

export interface DocumentSummary {
  docId: string;
  filename: string;
  docType: string | null;
  vendorCluster: string | null;
  layoutClusterId?: string | null;
  complexityBin: string | null;
  routeBin: string | null;
  routeSpecialization?: string | null;
  status: string;
  latencyMs: number | null;
  policyId: string | null;
  staticPolicyId?: string | null;
  staticPolicyName?: string | null;
  staticPolicyReason?: string | null;
  advisorRecommendationPolicyId?: string | null;
  adviceSource?: string | null;
  adviceStatus?: string | null;
  adviceConfidence?: number | null;
  retrievalSource?: string | null;
  fallbackReason?: string | null;
  adviceAccepted?: boolean | null;
  policyChanged?: boolean | null;
  feedbackLogged?: boolean | null;
  rollbackTriggered?: boolean | null;
  rollbackReason?: string | null;
  blockedPolicy?: boolean | null;
  validationIssueCount: number;
  escalated: boolean;
  retriesCount?: number;
  modelUsed?: string | null;
  modelMode?: string | null;
  modelReason?: string | null;
  ocrEngineUsed?: string | null;
  ocrAvgConfidence?: number | null;
  ocrRerunAttemptedPages?: number | null;
  ocrRerunUsedPages?: number | null;
  fallbackPath?: string | null;
  unresolvedFieldCount?: number | null;
  deferStatus?: string | null;
  deferReason?: string | null;
  schemaCoverage?: number | null;
  schemaGroundingCoverage?: number | null;
  schemaValid?: boolean | null;
  missingRequiredCount?: number | null;
  hallucinatedFieldCount?: number | null;
  transparencyPath?: string | null;
  reward?: number | null;
  rewardType?: string | null;
  exactPrecision?: number | null;
  exactRecall?: number | null;
  exactF1?: number | null;
  reviewStatus?: ReviewStatus | null;
  reviewSource?: ReviewSource | null;
  exactWinLossState?: "win" | "match" | "loss" | "unscored" | null;
  [key: string]: unknown;
}

export interface FieldExtraction {
  key: string;
  value: string | number | boolean | null;
  confidence: number | null;
  confidence_type: "calibrated" | "heuristic" | "unknown";
  extraction_method: "local_model" | "llm_tool" | "rule_based" | "unknown";
  evidence: {
    span: [number, number] | null;
    bbox: number[] | null;
    page: number | null;
  };
  discovered: boolean;
  metadata: Record<string, unknown>;
}

export interface ValidationError {
  field: string;
  issue: string;
  severity: string;
  details: Record<string, unknown>;
}

export interface RecoveryAttempt {
  field: string;
  attempt: number;
  strategy: string;
  pattern?: string;
  success: boolean;
  reason: string | null;
}

export interface EscalationEvent {
  escalated: boolean;
  fields: string[];
  reason: string;
  targetModel: string | null;
  costEstimate: number | null;
  latencyEstimateMs: number | null;
  escalationUnavailable: boolean;
}

export interface GuardrailFinding {
  rule: string;
  result: "pass" | "warn" | "fail";
  message: string;
  field: string | null;
  metadata: Record<string, unknown>;
}

export interface RunFileInfo {
  path: string;
  size: number;
  modifiedAt: string;
  type: "json" | "jsonl" | "md" | "txt" | "csv" | "other";
  [key: string]: unknown;
}

export interface ProvenanceEvent {
  eventId: string;
  eventType: string;
  agent: string;
  timestamp: number;
  docId: string | null;
  latencyMs: number | null;
  costUnits: number | null;
  stage: string;
  payload: {
    inputs: Record<string, unknown>;
    outputs: Record<string, unknown>;
    parameters: Record<string, unknown>;
  };
  [key: string]: unknown;
}

export interface ShadowComparison {
  docId: string;
  policyId: string;
  canonicalLatencyMs: number | null;
  shadowLatencyMs: number | null;
  canonicalValidationFailure: number | null;
  shadowValidationFailure: number | null;
  canonicalQualityProxy: number | null;
  shadowQualityProxy: number | null;
  canonicalRetrievalProxy: number | null;
  shadowRetrievalProxy: number | null;
  [key: string]: unknown;
}

export interface BenchmarkRunSummary {
  benchmarkRunId: string;
  generatedAt: string;
  docCount: number;
  packName: string;
  configPath: string | null;
  reportPath: string;
  tablePath: string | null;
  csvPath: string | null;
  [key: string]: unknown;
}

export interface BenchmarkEvidencePayload {
  experiment: Record<string, unknown>;
  conditions: Record<string, unknown>;
  comparison: Record<string, unknown>;
  documents: Array<Record<string, unknown>>;
  [key: string]: unknown;
}
