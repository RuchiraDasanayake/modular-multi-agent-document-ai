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

// ══════════════════════════════════════════════════════════════════════════════
// XAI Types
// ══════════════════════════════════════════════════════════════════════════════

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

// ══════════════════════════════════════════════════════════════════════════════
// HITL Types
// ══════════════════════════════════════════════════════════════════════════════

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
