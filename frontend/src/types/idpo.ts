export interface RunSummary {
  runId: string;
  displayName: string;
  createdAt: string;
  updatedAt: string;
  status: "ready" | "running" | "failed" | "unknown";
  docCount: number;
  source: "runs" | "sample";
  rootPath: string;
  primaryPath: string;
  hasShadow: boolean;
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
}

export interface FieldExtraction {
  key: string;
  value: string | number | boolean | null;
  confidence: number | null;
  confidence_type: "calibrated" | "heuristic" | "unknown";
  extraction_method: "local_model" | "llm_tool" | "rule_based" | "unknown";
  evidence: {
    span?: [number, number] | null;
    bbox?: number[] | null;
    page?: number | null;
  };
  discovered?: boolean;
  metadata?: Record<string, unknown>;
}

export interface ValidationError {
  field: string;
  issue: string;
  severity: string;
  details?: Record<string, unknown>;
}

export interface GuardrailFinding {
  rule: string;
  result: "pass" | "fail" | "warn";
  message: string;
  field?: string | null;
  metadata?: Record<string, unknown>;
}

export interface RecoveryAttempt {
  field: string;
  attempt: number;
  strategy: string;
  pattern?: string;
  success: boolean;
  reason?: string | null;
}

export interface EscalationEvent {
  escalated: boolean;
  fields: string[];
  reason: string;
  targetModel: string | null;
  costEstimate: number | null;
  latencyEstimateMs: number | null;
  escalationUnavailable?: boolean;
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
  payload: Record<string, unknown>;
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
}

export interface RunFileInfo {
  path: string;
  size: number;
  modifiedAt: string;
  type: "json" | "jsonl" | "md" | "txt" | "csv" | "other";
}

export interface JobStatus {
  jobId: string;
  status: "queued" | "running" | "success" | "failed";
  startedAt: string;
  endedAt?: string;
  commandId: string;
  runId: string | null;
  runPath: string | null;
  logs: string[];
  error?: string;
  settings: Record<string, unknown>;
  uploadsPath: string;
}

export interface SystemStatus {
  timestamp: string;
  checks: Array<{
    id: string;
    kind: "cli" | "http";
    ok: boolean;
    detail: string;
  }>;
  defaultCommandId: string;
}
