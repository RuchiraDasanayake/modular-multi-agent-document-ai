/**
 * IDPO-specific types for the API client
 */

export interface JobStatus {
  job_id: string;
  status: "pending" | "running" | "completed" | "failed";
  run_id?: string;
  progress?: number;
  message?: string;
  started_at?: string;
  completed_at?: string;
  error?: string;
}

export interface RunSummary {
  run_id: string;
  status: string;
  started_at?: string;
  completed_at?: string;
  doc_count?: number;
  failed_count?: number;
  duration_ms?: number;
  source?: string;
}

export interface SystemStatus {
  status: string;
  version?: string;
  services?: Record<string, {
    status: string;
    latency_ms?: number;
  }>;
  timestamp?: string;
}

export interface RunOverview {
  run_id: string;
  status: string;
  doc_count?: number;
  metrics?: Record<string, unknown>;
  config?: Record<string, unknown>;
  pipeline_integration?: Record<string, unknown>;
  started_at?: string;
  completed_at?: string;
}

export interface DocumentSummary {
  doc_id: string;
  filename?: string;
  docType?: string;
  status?: string;
  vendorCluster?: string;
  policyId?: string;
  validationIssueCount?: number;
  escalated?: boolean;
  confidence?: number;
}

export interface RunFileInfo {
  name: string;
  path: string;
  size?: number;
  type?: string;
}

export interface ProvenanceEvent {
  timestamp: string;
  stage: string;
  event: string;
  details?: Record<string, unknown>;
  file?: string;
}

export interface ShadowComparison {
  doc_id: string;
  primary_policy: string;
  shadow_policy: string;
  primary_result?: Record<string, unknown>;
  shadow_result?: Record<string, unknown>;
  differences?: string[];
  metrics_comparison?: Record<string, unknown>;
}
