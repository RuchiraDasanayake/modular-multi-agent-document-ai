import { removeToken } from "./auth";
import type {
  JobDocumentText,
  JobStatus,
  RunOverview,
  RunSummary,
  BenchmarkRunSummary,
  BenchmarkEvidencePayload,
} from "@/types/idpo";
import type { ProductAutoDocumentDetail, ProductAutoReview, ProductAutoReviewField, ProductAutoRun, ProductAutoSourceDocument } from "@/types/product-auto";

async function localRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    cache: "no-store",
    ...options,
  });

  if (res.status === 401 && typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    removeToken();
    window.location.href = "/login";
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || body.detail || `API ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const idpoApi = {
  listProductAutoRuns(jobId: string): Promise<{ available: boolean; modelConfigured: boolean; sourceFiles: ProductAutoSourceDocument[]; runs: ProductAutoRun[] }> {
    return localRequest(`/api/jobs/${encodeURIComponent(jobId)}/auto`);
  },

  startProductAutoRun(jobId: string, selectedFileIds: string[]): Promise<ProductAutoRun> {
    return localRequest(`/api/jobs/${encodeURIComponent(jobId)}/auto`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selectedFileIds }),
    });
  },

  getProductAutoDocument(jobId: string, runId: string, docId: string): Promise<ProductAutoDocumentDetail> {
    return localRequest(`/api/jobs/${encodeURIComponent(jobId)}/auto/${encodeURIComponent(runId)}/docs/${encodeURIComponent(docId)}`);
  },

  saveProductAutoReview(jobId: string, runId: string, docId: string, expectedRevision: number, fields: ProductAutoReviewField[]): Promise<{ review: ProductAutoReview }> {
    return localRequest(`/api/jobs/${encodeURIComponent(jobId)}/auto/${encodeURIComponent(runId)}/docs/${encodeURIComponent(docId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_revision: expectedRevision, fields }),
    });
  },

  listJobs(): Promise<{ jobs: JobStatus[] }> {
    return localRequest("/api/jobs");
  },

  createJob(): Promise<JobStatus> {
    return localRequest("/api/jobs", { method: "POST" });
  },

  getJob(jobId: string): Promise<JobStatus> {
    return localRequest(`/api/jobs/${encodeURIComponent(jobId)}`);
  },

  getJobDocument(
    jobId: string,
    docId: string,
    options?: { mode?: string; runId?: string },
  ): Promise<Record<string, unknown>> {
    const params = new URLSearchParams();
    if (options?.mode) params.set("mode", options.mode);
    if (options?.runId) params.set("runId", options.runId);
    const qs = params.toString();
    return localRequest(
      `/api/jobs/${encodeURIComponent(jobId)}/docs/${encodeURIComponent(docId)}${qs ? `?${qs}` : ""}`,
    );
  },

  getJobDocumentText(jobId: string, docId: string): Promise<JobDocumentText> {
    return localRequest(`/api/jobs/${encodeURIComponent(jobId)}/docs/${encodeURIComponent(docId)}/text`);
  },

  saveJobDocumentReview(
    jobId: string,
    docId: string,
    data: Record<string, unknown>,
  ): Promise<{ review: unknown }> {
    return localRequest(
      `/api/jobs/${encodeURIComponent(jobId)}/docs/${encodeURIComponent(docId)}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      },
    );
  },

  validateJobDocuments(
    jobId: string,
    data: { selectedFileIds: string[]; mode: string },
  ): Promise<{ job: JobStatus }> {
    return localRequest(
      `/api/jobs/${encodeURIComponent(jobId)}/validate`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      },
    );
  },

  startJobRuns(jobId: string, data: Record<string, unknown>): Promise<JobStatus> {
    return localRequest(
      `/api/jobs/${encodeURIComponent(jobId)}/runs`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      },
    );
  },

  updateJob(jobId: string, payload: Record<string, unknown>): Promise<JobStatus> {
    return localRequest(
      `/api/jobs/${encodeURIComponent(jobId)}`,
      {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
    );
  },

  uploadJobDocuments(jobId: string, files: File[]): Promise<JobStatus> {
    const formData = new FormData();
    files.forEach((file) => formData.append("files", file));
    return localRequest(
      `/api/jobs/${encodeURIComponent(jobId)}/documents`,
      {
        method: "POST",
        body: formData,
      },
    );
  },

  runOverview(runId: string): Promise<RunOverview> {
    return localRequest(`/api/runs/${encodeURIComponent(runId)}/summary`);
  },

  listRuns(): Promise<{ runs: RunSummary[] }> {
    return localRequest("/api/runs");
  },

  benchmarkRuns(): Promise<{ runs: BenchmarkRunSummary[]; latest?: BenchmarkRunSummary }> {
    return localRequest("/api/benchmarks");
  },

  benchmarkEvidence(benchmarkRunId: string): Promise<BenchmarkEvidencePayload> {
    return localRequest(`/api/benchmarks/${encodeURIComponent(benchmarkRunId)}`);
  },
};
