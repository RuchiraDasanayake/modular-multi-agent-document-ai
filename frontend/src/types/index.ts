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
