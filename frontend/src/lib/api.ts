import { getToken } from "./auth";
import type {
  User,
  Stats,
  QAResponse,
  FeedbackSubmitRequest,
  HITLFeedback,
  FeedbackHistory,
  GuardrailValidateRequest,
  GuardrailValidateResponse,
  GuardrailStats,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `API ${res.status}`);
  }
  return res.json();
}

// ── Auth ──
export const api = {
  login: (username: string, password: string) =>
    request<{ access_token: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    }),

  signup: (email: string, username: string, password: string) =>
    request<{ access_token: string }>("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify({ email, username, password }),
    }),

  me: () => request<User>("/api/auth/me"),

  getUsers: () => request<User[]>("/api/auth/users"),

  register: (data: { email: string; username: string; password: string; role: string }) =>
    request("/api/auth/register", { method: "POST", body: JSON.stringify(data) }),

  toggleUser: (userId: string) =>
    request(`/api/auth/users/${userId}/toggle`, { method: "PATCH" }),

  // ── Dashboard ──
  getStats: () => request<Stats>("/api/dashboard/stats"),

  getSTM: () => request<unknown[]>("/api/dashboard/memory/stm"),
  getMTM: (limit = 50) => request<unknown[]>(`/api/dashboard/memory/mtm?limit=${limit}`),
  getLTM: () => request<unknown[]>("/api/dashboard/memory/ltm"),
  getLTMChart: () => request<{ policy_id: string; avg_mean: number; count: number; avg_strength: number }[]>(
    "/api/dashboard/memory/ltm/chart"
  ),
  getActivity: (limit = 20) => request<unknown[]>(`/api/dashboard/activity?limit=${limit}`),

  // ── Experiments ──
  getResults: () => request<Record<string, unknown>>("/api/experiments/results"),
  getRobustness: () => request<Record<string, unknown>>("/api/experiments/robustness"),

  // ── Interactive Demos ──
  runDAAFDemo: (params: Record<string, number>) =>
    request("/api/experiments/demo/daaf", { method: "POST", body: JSON.stringify(params) }),

  runRABIDemo: (params: Record<string, number>) =>
    request("/api/experiments/demo/rabi", { method: "POST", body: JSON.stringify(params) }),

  runComparison: (params: Record<string, number>) =>
    request("/api/experiments/demo/comparison", { method: "POST", body: JSON.stringify(params) }),

  // ── XAI ──

  askQuestion: (paragraph: string, question: string) =>
    request<QAResponse>("/api/xai/ask", {
      method: "POST",
      body: JSON.stringify({ paragraph, question }),
    }),

  getExplanation: (questionId: string) =>
    request<QAResponse>(`/api/xai/explanation/${questionId}`),

  // ── HITL ──

  submitFeedback: (feedback: FeedbackSubmitRequest) =>
    request<{ feedback_id: string; status: string }>("/api/hitl/feedback", {
      method: "POST",
      body: JSON.stringify(feedback),
    }),

  getFeedbackHistory: (limit = 20) =>
    request<FeedbackHistory>(`/api/hitl/history?limit=${limit}`),

  getFeedbackById: (feedbackId: string) =>
    request<HITLFeedback>(`/api/hitl/feedback/${feedbackId}`),

  getHITLStats: () =>
    request<{
      total_feedback: number;
      correct_count: number;
      accuracy_rate: number;
      avg_explanation_quality: number;
      pending_reviews: number;
    }>("/api/hitl/stats"),

  // ── Guardrails ──

  validateGuardrail: (data: GuardrailValidateRequest) =>
    request<GuardrailValidateResponse>("/api/guardrails/validate", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getGuardrailStats: () =>
    request<GuardrailStats>("/api/guardrails/stats"),

  getGuardrailHistory: (limit = 50) =>
    request<unknown[]>(`/api/guardrails/history?limit=${limit}`),
};
