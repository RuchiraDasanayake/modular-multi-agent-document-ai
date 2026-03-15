/**
 * IDPO runner API types (frontend local runner endpoints under /api/*).
 */

export type JobState = "queued" | "running" | "success" | "failed";

export interface JobStatus {
  jobId: string;
  status: JobState;
  startedAt: string;
  endedAt?: string;
  commandId: string;
  runId: string | null;
  runPath: string | null;
  logs: string[];
  settings: Record<string, unknown>;
  uploadsPath?: string | null;
  error?: string;
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
  [key: string]: unknown;
}

export interface DocumentSummary {
  docId: string;
  filename: string;
  docType: string | null;
  vendorCluster: string | null;
  complexityBin: string | null;
  routeBin: string | null;
  status: string;
  latencyMs: number | null;
  policyId: string | null;
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
  transparencyPath?: string | null;
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
