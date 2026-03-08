import { getToken, removeToken } from "./auth";
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
  IDPORun,
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

  // Auto-logout on 401 (expired or invalid token)
  if (res.status === 401) {
    removeToken();
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `API ${res.status}`);
  }
  return res.json();
}

// ── Auth ──
export const api = {
  request,

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

  forgotPassword: (email: string) =>
    request<{ message: string; token: string | null }>("/api/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),

  resetPassword: (token: string, new_password: string) =>
    request<{ message: string }>("/api/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ token, new_password }),
    }),

  changePassword: (current_password: string, new_password: string) =>
    request<{ message: string }>("/api/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ current_password, new_password }),
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

  // ── IDPO ──

  getIDPORuns: () =>
    request<{ runs: IDPORun[]; total: number }>("/api/idpo/runs"),

  runIDPO: async (
    files: File[],
    fields: { name: string; description: string }[],
    configPath: string,
    options?: { enableGuardrails?: boolean },
  ) => {
    const token = getToken();
    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));
    formData.append("fields", JSON.stringify(fields));
    formData.append("config_path", configPath);
    formData.append("skip_guardrails", String(!(options?.enableGuardrails ?? true)));
    // Keep XAI and AHMN enabled by default; guardrails is the only user-facing runtime toggle.
    formData.append("skip_xai", "false");
    formData.append("skip_ahmn", "false");

    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const res = await fetch(`${API_BASE}/api/idpo/run`, {
      method: "POST",
      headers,
      body: formData,
    });

    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.error || body.detail || `API ${res.status}`);
    }
    return res.json();
  },

  downloadIDPOFile: async (runId: string, file: "docs.xlsx" | "entities.xlsx" | "run.xlsx") => {
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;

    const res = await fetch(`${API_BASE}/api/idpo/runs/${runId}/${file}`, { headers });
    if (!res.ok) throw new Error(`Download failed: ${res.status}`);
    return res.blob();
  },

  forwardIDPOHITLCorrection: (adviceId: string, feedbackType: "correct" | "incorrect" | "partially_correct" | "needs_more_context") =>
    request<{ status: string; human_corrected?: boolean; error?: string }>("/api/idpo/hitl-correction", {
      method: "POST",
      body: JSON.stringify({ advice_id: adviceId, feedback_type: feedbackType }),
    }),
};
