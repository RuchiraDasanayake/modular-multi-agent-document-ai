export interface User {
  id: string;
  email: string;
  username: string;
  role: "admin" | "viewer";
  is_active: boolean;
}

export interface Stats {
  total_advice: number;
  total_outcomes: number;
  total_ltm_policies: number;
  total_experiments: number;
  total_users: number;
}

export interface LTMEntry {
  id: string;
  context_hash: string;
  policy_id: string;
  alpha: number;
  beta: number;
  confidence_score: number;
  last_promoted_at: string;
}

export interface MTMEntry {
  id: string;
  advice_id: string;
  policy_id_used: string;
  document_context: Record<string, unknown>;
  outcome_metrics: Record<string, unknown>;
  human_corrected: boolean;
  created_at: string;
}

export interface DAAFDemoResult {
  rewards: number[];
  recent_means: number[];
  drift_magnitudes: number[];
  gammas: number[];
  drift_types: string[];
  detection_delay: number | null;
  peak_gamma: number;
}

export interface RABIDemoResult {
  prior: { alpha: number; beta: number; mean: number; confidence: number; n_neighbors: number };
  neighbors: { hash: string; similarity: number; alpha: number; beta: number; mean: number }[];
  weights: number[];
  distribution: { x: number[]; flat_pdf: number[]; rabi_pdf: number[] };
}

export interface ComparisonResult {
  ts_cumulative_regret: number[];
  daaf_cumulative_regret: number[];
  ts_rolling_reward: number[];
  daaf_rolling_reward: number[];
  rolling_start: number;
  total_ts_regret: number;
  total_daaf_regret: number;
  improvement_pct: number;
}

// ── XAI Types ──

export interface ChatMessage {
  id: string;
  role: "user" | "bot";
  content: string;
  timestamp: string;
  confidence?: number;
}

export interface HighlightSpan {
  start: number;
  end: number;
  text: string;
  type: "answer" | "positive" | "negative" | "medium";
  shap_score: number;
  lime_score: number;
}

export interface SHAPExplanation {
  shap_values: Array<[string, number]>;
  base_value: number;
}

export interface LIMEExplanation {
  word_weights: Array<[string, number]>;
  prediction_proba: number;
}

export interface DerivationStep {
  step_number: number;
  action: string;
  description: string;
  details?: string;
  confidence: number;
}

export interface XAIExplanation {
  answer: string;
  confidence_score: number;
  highlighted_spans: HighlightSpan[];
  shap_explanation: SHAPExplanation;
  lime_explanation: LIMEExplanation;
  derivation_steps: DerivationStep[];
  evidence_sentences: string[];
}

export interface QARequest {
  paragraph: string;
  question: string;
}

export interface QAResponse {
  answer: string;
  confidence: number;
  explanation: XAIExplanation;
}

// ── HITL Types ──

export type FeedbackType = "correct" | "incorrect" | "partially_correct" | "needs_more_context";
export type FeedbackPriority = "low" | "medium" | "high" | "critical";

export interface HITLFeedback {
  feedback_id: string;
  timestamp: string;
  question: string;
  original_answer: string;
  feedback_type: FeedbackType;
  is_answer_correct: boolean;
  corrected_answer?: string;
  ratings: {
    explanation_quality: number;
    highlight_accuracy: number;
    xai_helpfulness: number;
  };
  additional_context?: string;
  knowledge_update?: string;
  priority: FeedbackPriority;
  reviewer_notes?: string;
  tags: string[];
}

export interface FeedbackSubmitRequest {
  question: string;
  original_answer: string;
  feedback_type: FeedbackType;
  corrected_answer?: string;
  explanation_quality: number;
  highlight_accuracy: number;
  xai_helpfulness: number;
  additional_context?: string;
  knowledge_update?: string;
}

export interface FeedbackHistory {
  items: HITLFeedback[];
  total: number;
  accuracy_rate: number;
}

// ── Guardrails Types ──

export interface GuardrailValidateRequest {
  document_context: {
    doc_type: string;
    vendor?: string;
    quality_bin?: string;
  };
  query: string;
  answer_json: string;
  source_contexts: string[];
  document_id?: string;
}

export interface GuardrailValidationMetric {
  name: string;
  score: number;
  is_pass: boolean;
  details: string;
  timestamp: string;
}

export interface GuardrailMetrics {
  num_checks: number;
  num_passed_checks: number;
  num_failed_checks: number;
  [key: string]: unknown;
}

export interface GuardrailValidateResponse {
  overall_passes: boolean;
  audit_log_id: string;
  processing_time_ms: number;
  timestamp: string;
  validation_results: GuardrailValidationMetric[];
  metrics: GuardrailMetrics;
}

export interface GuardrailStats {
  total_validations: number;
  total_passed: number;
  total_failed: number;
  pass_rate: number;
  avg_processing_time_ms: number;
  checks_breakdown: Record<string, { passed: number; failed: number }>;
}

// ── IDPO Types ──

export interface IDPOExtractionField {
  name: string;
  description: string;
}

export interface IDPOEntityDetail {
  key: string;
  label: string;
  value: string;
  confidence: number;
  page?: number | null;
  source: string;
  is_explicit: boolean;
}

export interface IDPOValidationIssue {
  field: string;
  issue: string;
  severity: string;
}

export interface IDPOSection {
  name: string;
  text: string;
  confidence: number;
}

export interface IDPODocRecord {
  doc_id: string;
  filename?: string;
  source?: string;
  category?: string;
  doc_type?: string;
  vendor_cluster?: string;
  quality_bin?: string;
  complexity_bin?: string;
  content_profile?: string;
  quality_score?: number;
  complexity_score?: number;
  summary?: string;
  status?: string;
  extracted_text?: string;
  entities?: Record<string, unknown>;
  entity_details?: IDPOEntityDetail[];
  sections?: IDPOSection[];
  validation_issues?: IDPOValidationIssue[];
  field_confidence?: Record<string, number>;
  recovered_fields?: Record<string, string>;
  entity_count?: number;
  explicit_entity_count?: number;
  default_entity_count?: number;
  validation_issue_count?: number;
  recovered_fields_count?: number;
  chunk_count?: number;
  escalated?: boolean;
  model_used?: string;
  model_mode?: string;
  policy_id?: string;
  policy_name?: string;
  plan_id?: string;
  plan_source?: string;
  preprocess_route?: string;
}

export interface IDPORunMetrics {
  doc_count?: number;
  duration_ms?: number;
  avg_confidence?: number;
  success_rate?: number;
  [key: string]: unknown;
}

// ── Pipeline Integration Types ──

export interface AHMNAdvice {
  advice_id: string;
  policy_id: string;
  policy_data: Record<string, unknown>;
  confidence: number;
  rabi_used: boolean;
  retrieval_source: string;
  n_neighbors: number | null;
  error: string | null;
}

export interface GuardrailValidationResult {
  name: string;
  score: number;
  is_pass: boolean;
  details: string;
  timestamp?: string;
}

export interface GuardrailDocResult {
  document_id: string;
  overall_passes: boolean;
  validation_results: GuardrailValidationResult[];
  metrics: Record<string, unknown>;
  processing_time_ms: number;
  error: string | null;
}

export interface XAIDocExplanation {
  document_id: string;
  answer: string;
  confidence: number;
  explanation: Record<string, unknown>;
  error: string | null;
}

export interface AHMNFeedback {
  status: string;
  advice_id: string;
  policy_id_used: string;
  metrics_sent: {
    f1_score?: number;
    cost?: number;
    processing_time_ms?: number;
    success?: boolean;
  };
  error: string | null;
}

export interface PipelineIntegration {
  ahmn_advice: AHMNAdvice;
  guardrails: GuardrailDocResult[];
  xai_explanations: XAIDocExplanation[];
  ahmn_feedback: AHMNFeedback;
  cycle_time_ms: number;
  skipped_guardrails?: boolean;
  skipped_xai?: boolean;
}

export interface IDPOPartialFailure {
  file: string;
  error: string;
}

export interface IDPORunResult {
  run_id: string;
  run_dir: string;
  metrics: IDPORunMetrics;
  docs: IDPODocRecord[];
  entities: Record<string, unknown>[];
  warnings: string[];
  partial_failures?: IDPOPartialFailure[];
  pipeline_integration?: PipelineIntegration;
}

export type IDPOPipelineStep = {
  id: number;
  label: string;
  description: string;
  icon: string;
  status: "pending" | "active" | "done" | "error";
}
