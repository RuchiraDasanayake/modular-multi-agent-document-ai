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
  IDPODocRecord,
  IDPOEntityDetail,
  IDPORunMetrics,
  IDPORunResult,
  AHMNAdvice,
  AHMNFeedback,
  PipelineIntegration,
} from "@/types";
import type { JobStatus } from "@/types/idpo";

const API_BASE = "";

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

async function localRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    cache: "no-store",
    ...options,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || body.detail || `API ${res.status}`);
  }
  return res.json() as Promise<T>;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function asString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim().length > 0 ? value : undefined;
}

function asNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function mapEntityDetails(detail: Record<string, unknown>): { entityDetails: IDPOEntityDetail[]; entities: Record<string, unknown> } {
  const fieldValues = Array.isArray(detail.fields) ? detail.fields : [];
  const entityDetails: IDPOEntityDetail[] = [];
  const entities: Record<string, unknown> = {};

  for (const fieldValue of fieldValues) {
    const field = asRecord(fieldValue);
    if (!field) {
      continue;
    }
    const key = asString(field.key);
    if (!key) {
      continue;
    }
    const metadata = asRecord(field.metadata) ?? {};
    const evidence = asRecord(field.evidence) ?? {};
    const value = field.value;
    const textValue =
      typeof value === "string" ? value : typeof value === "number" || typeof value === "boolean" ? String(value) : "";
    entities[key] = value ?? "";
    entityDetails.push({
      key,
      label: asString(metadata.label) ?? key,
      value: textValue,
      confidence: asNumber(field.confidence) ?? 0,
      page: asNumber(evidence.page) ?? null,
      source: asString(metadata.source) ?? asString(field.extraction_method) ?? "unknown",
      is_explicit: Boolean(metadata.explicit),
    });
  }

  return { entityDetails, entities };
}

function buildExtractedText(content: unknown): string {
  const payload = asRecord(content);
  const pages = Array.isArray(payload?.pages) ? payload.pages : [];
  const chunks: string[] = [];
  for (const pageValue of pages) {
    const page = asRecord(pageValue);
    if (!page) {
      continue;
    }
    const text = asString(page.text);
    if (!text) {
      continue;
    }
    const pageNumber = asNumber(page.number);
    chunks.push(pageNumber != null ? `--- Page ${pageNumber} ---\n${text}` : text);
  }
  return chunks.join("\n\n");
}

async function loadExtractedText(runId: string, docId: string): Promise<string> {
  const relativePath = `docs/${docId}/preprocessing/ocr/text.json`;
  try {
    const payload = await localRequest<{ type: "json" | "text"; content: unknown }>(
      `/api/runs/${encodeURIComponent(runId)}/file?path=${encodeURIComponent(relativePath)}`,
    );
    if (payload.type === "text") {
      return typeof payload.content === "string" ? payload.content : "";
    }
    return buildExtractedText(payload.content);
  } catch {
    return "";
  }
}

async function waitForJob(jobId: string, timeoutMs = 30 * 60 * 1000, intervalMs = 1200): Promise<JobStatus> {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    const job = await localRequest<JobStatus>(`/api/jobs/${encodeURIComponent(jobId)}`);
    if (job.status === "success") {
      return job;
    }
    if (job.status === "failed") {
      throw new Error(job.error || "IDPO job failed");
    }
    await sleep(intervalMs);
  }
  throw new Error("IDPO job timed out");
}

async function hydrateRunResult(job: JobStatus): Promise<IDPORunResult> {
  const runId = job.runId;
  if (!runId) {
    throw new Error("IDPO job completed without a run id");
  }

  const [overviewPayload, metricsPayload, docsPayload] = await Promise.all([
    localRequest<Record<string, unknown>>(`/api/runs/${encodeURIComponent(runId)}/summary`),
    localRequest<Record<string, unknown>>(`/api/runs/${encodeURIComponent(runId)}/metrics`),
    localRequest<{ docs: Array<Record<string, unknown>> }>(`/api/runs/${encodeURIComponent(runId)}/docs`),
  ]);

  const docs = await Promise.all(
    docsPayload.docs.map(async (summaryValue) => {
      const summary = asRecord(summaryValue) ?? {};
      const docId = asString(summary.docId);
      if (!docId) {
        throw new Error("Run document entry is missing docId");
      }

      const detail = await localRequest<Record<string, unknown>>(
        `/api/runs/${encodeURIComponent(runId)}/docs/${encodeURIComponent(docId)}`,
      );
      const metadata = asRecord(detail.metadata) ?? {};
      const raw = asRecord(detail.raw) ?? {};
      const dae = asRecord(raw.dae) ?? {};
      const route = asRecord(raw.route) ?? {};
      const extract = asRecord(raw.extract) ?? {};
      const transparency = asRecord(detail.transparency) ?? {};
      const reward = asRecord(detail.reward) ?? {};
      const rewardDetails = asRecord(reward.details) ?? {};
      const llmDiagnostics = asRecord(detail.llmDiagnostics) ?? {};
      const advisorRecommendation = asRecord(detail.advisorRecommendation);
      const fallbackCandidatesRaw = Array.isArray(detail.fallbackCandidates) ? detail.fallbackCandidates : [];
      const fallbackCandidates = fallbackCandidatesRaw
        .map((item) => asRecord(item))
        .filter((item): item is Record<string, unknown> => item !== null)
        .map((item) => ({
          policy_id: asString(item.policy_id) ?? "",
          score: asNumber(item.score),
          reason: asString(item.reason),
          source: asString(item.source),
        }))
        .filter((item) => item.policy_id);
      const feedbackStatus = asRecord(detail.feedbackStatus) ?? {};
      const safetyStatus = asRecord(detail.safetyStatus) ?? {};
      const validationIssues = Array.isArray(detail.validationIssues)
        ? (detail.validationIssues as Array<{ field: string; issue: string; severity: string }>)
        : [];
      const recoveryAttempts = Array.isArray(detail.recoveryAttempts)
        ? (detail.recoveryAttempts as Array<Record<string, unknown>>)
        : [];
      const { entityDetails, entities } = mapEntityDetails(detail);
      const extractedText = await loadExtractedText(runId, docId);

      const docRecord: IDPODocRecord = {
        doc_id: docId,
        filename: asString(summary.filename) ?? docId,
        source: asString(extract.source),
        category: asString(metadata.docType),
        doc_type: asString(metadata.docType),
        vendor_cluster: asString(metadata.vendorCluster),
        layout_cluster_id: asString(metadata.layoutClusterId),
        route_bin: asString(metadata.routeBin),
        route_specialization: asString(metadata.routeSpecialization),
        quality_bin: asString(dae.quality_bin),
        complexity_bin: asString(metadata.complexityBin) ?? asString(dae.complexity_bin),
        content_profile: asString(metadata.profile) ?? asString(dae.content_profile),
        quality_score: asNumber(dae.quality_score),
        complexity_score: asNumber(dae.complexity_score),
        analysis_confidence: asNumber(dae.analysis_confidence),
        summary: asString(extract.summary),
        status: asString(summary.status) ?? "success",
        extracted_text: extractedText || undefined,
        entities,
        entity_details: entityDetails,
        sections: [],
        validation_issues: validationIssues,
        field_confidence: {},
        recovered_fields: {},
        entity_count: entityDetails.length,
        explicit_entity_count: entityDetails.filter((item) => item.is_explicit).length,
        default_entity_count: entityDetails.filter((item) => !item.is_explicit).length,
        validation_issue_count: validationIssues.length,
        recovered_fields_count: recoveryAttempts.filter((item) => Boolean(asRecord(item)?.success)).length,
        chunk_count: Array.isArray(extract.chunks) ? extract.chunks.length : undefined,
        escalated: Boolean(summary.escalated),
        model_used: asString(metadata.modelUsed),
        model_mode: asString(metadata.modelMode),
        model_reason: asString(metadata.modelReason),
        policy_id: asString(metadata.policyId) ?? asString(route.policy_id),
        policy_name: asString(route.policy_name),
        advice_source: asString(metadata.adviceSource),
        advice_id: asString(metadata.adviceId) ?? null,
        advice_confidence: asNumber(metadata.adviceConfidence),
        retrieval_source: asString(metadata.retrievalSource) ?? null,
        rabi_used: Boolean(metadata.rabiUsed),
        n_neighbors: asNumber(metadata.nNeighbors) ?? null,
        fallback_reason: asString(metadata.fallbackReason) ?? null,
        advisor_recommendation: advisorRecommendation
          ? {
              policy_id: asString(advisorRecommendation.policy_id) ?? "",
              score: asNumber(advisorRecommendation.score),
              reason: asString(advisorRecommendation.reason),
              source: asString(advisorRecommendation.source),
            }
          : null,
        fallback_candidates: fallbackCandidates,
        feedback_status: {
          logged: Boolean(feedbackStatus.logged),
          error: asString(feedbackStatus.error) ?? null,
          advice_id: asString(feedbackStatus.advice_id) ?? asString(metadata.adviceId) ?? null,
        },
        safety_status: {
          blocked_policy: Boolean(safetyStatus.blocked_policy),
          rollback_triggered: Boolean(safetyStatus.rollback_triggered),
          rollback_reason: asString(safetyStatus.rollback_reason) ?? null,
          policy_blocked_count: asNumber(safetyStatus.policy_blocked_count) ?? null,
        },
        plan_id: asString(route.plan_id),
        plan_source: asString(route.source),
        preprocess_route: undefined,
        ocr_engine_used: asString(metadata.ocrEngineUsed),
        ocr_avg_confidence: asNumber(metadata.ocrAvgConfidence),
        ocr_rerun_attempted_pages: asNumber(metadata.ocrRerunAttemptedPages),
        ocr_rerun_used_pages: asNumber(metadata.ocrRerunUsedPages),
        fallback_path: asString(metadata.fallbackPath),
        unresolved_field_count: asNumber(metadata.unresolvedFieldCount),
        reward: asNumber(reward.reward),
        reward_type: asString(reward.rewardType),
        reward_details: rewardDetails,
        transparency,
        transparency_path: asString(metadata.transparencyPath),
        llm_diagnostics: Object.keys(llmDiagnostics).length > 0 ? llmDiagnostics : undefined,
      };
      return docRecord;
    }),
  );

  const entities = docs.flatMap((doc) =>
    (doc.entity_details ?? []).map((entity) => ({
      doc_id: doc.doc_id,
      key: entity.key,
      label: entity.label,
      value: entity.value,
      confidence: entity.confidence,
      page: entity.page ?? null,
      source: entity.source,
      is_explicit: entity.is_explicit,
    })),
  );

  const runInfo = asRecord(metricsPayload.runInfo) ?? {};
  const warningsText = asString(runInfo.preflight_warnings) ?? "";
  const metrics = (asRecord(metricsPayload.metrics) ?? {}) as IDPORunMetrics;
  const overview = asRecord(overviewPayload.run) ?? {};
  const ahmnAdvices: AHMNAdvice[] = docs.map((doc, idx) => {
    const recommendation = doc.advisor_recommendation;
    return {
      advice_id: doc.advice_id ?? `doc_${idx + 1}`,
      policy_id: recommendation?.policy_id ?? doc.policy_id ?? "default",
      policy_data: recommendation ? { ...recommendation } : {},
      confidence: doc.advice_confidence ?? 0,
      rabi_used: Boolean(doc.rabi_used),
      retrieval_source: doc.retrieval_source ?? "unknown",
      n_neighbors: doc.n_neighbors ?? null,
      selected_policy_id: doc.policy_id ?? null,
      advice_source: doc.advice_source ?? null,
      fallback_reason: doc.fallback_reason ?? null,
      advisor_recommendation: recommendation ?? null,
      fallback_candidates: doc.fallback_candidates ?? [],
      safety_status: doc.safety_status,
      error: doc.advice_source === "fallback" && !recommendation ? "fallback_only" : null,
    };
  });
  const ahmnFeedbacks: AHMNFeedback[] = docs.map((doc, idx) => ({
    status: doc.feedback_status?.logged ? "logged" : doc.advice_id ? "failed" : "skipped",
    advice_id: doc.feedback_status?.advice_id ?? doc.advice_id ?? `doc_${idx + 1}`,
    policy_id_used: doc.policy_id ?? "default",
    metrics_sent: {},
    feedback_status: doc.feedback_status,
    error: doc.feedback_status?.error ?? null,
  }));
  const pipelineIntegration: PipelineIntegration = {
    ahmn_advices: ahmnAdvices,
    guardrails: [],
    xai_explanations: [],
    ahmn_feedbacks: ahmnFeedbacks,
    cycle_time_ms: asNumber(metrics.duration_ms) ?? 0,
    skipped_guardrails: true,
    skipped_xai: true,
    ahmn_advice: ahmnAdvices[0] as AHMNAdvice,
    ahmn_feedback: ahmnFeedbacks[0] as AHMNFeedback,
  };

  return {
    run_id: runId,
    run_dir: job.runPath ?? asString(overview.rootPath) ?? "",
    metrics,
    docs,
    entities,
    warnings: warningsText ? warningsText.split(" | ").filter(Boolean) : [],
    pipeline_integration: pipelineIntegration,
  };
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

  askQuestion: (paragraph: string, question: string, includeXAI: boolean = false) =>
    request<QAResponse>("/api/xai/ask", {
      method: "POST",
      body: JSON.stringify({ paragraph, question, include_xai: includeXAI }),
    }),

  getExplanation: (questionId: string) =>
    request<QAResponse>(`/api/xai/explanation/${questionId}`),

  // Lazy XAI: Fetch explanations for an already-answered question
  fetchXAIExplanation: (paragraph: string, question: string, answer: string) =>
    request<{ shap_explanation: { shap_values: [string, number][]; base_value: number }; lime_explanation: { word_weights: [string, number][]; prediction_proba: number } }>("/api/xai/explain", {
      method: "POST",
      body: JSON.stringify({ paragraph, question, answer }),
    }),

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
    options?: {
      adaptiveMode?: "static" | "adaptive_safe";
      maxCostPerDoc?: number;
      escalationEnabled?: boolean;
    },
  ) => {
    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));
    formData.append(
      "settings",
      JSON.stringify({
        configPath,
        adaptiveMode: options?.adaptiveMode ?? "adaptive_safe",
        report: true,
        maxCostPerDoc: options?.maxCostPerDoc,
        escalationEnabled: options?.escalationEnabled,
        customFields: fields.map((field) => ({
          key: field.name,
          description: field.description,
        })),
      }),
    );

    const job = await localRequest<JobStatus>("/api/runs/start", {
      method: "POST",
      body: formData,
    });
    const completed = await waitForJob(job.jobId);
    return hydrateRunResult(completed);
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
