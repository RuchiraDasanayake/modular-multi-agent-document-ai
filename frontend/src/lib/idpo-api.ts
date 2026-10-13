import { removeToken } from "./auth";
import type {
  JobDocumentText,
  JobStatus,
  RunOverview,
  RunSummary,
  BenchmarkRunSummary,
  BenchmarkEvidencePayload,
} from "@/types/idpo";
import type { ProductAutoAddedFieldInput, ProductAutoCorrectedResult, ProductAutoDocumentDetail, ProductAutoReview, ProductAutoReviewField, ProductAutoRun, ProductAutoSourceDocument } from "@/types/product-auto";
import type { ProductAutoRecipeRevision } from "@/types/product-auto-recipes";
import type { ProductAutoBriefDetail, ProductAutoBriefField, ProductAutoBriefRevision, ProductAutoBriefSuggestion } from "@/types/product-auto-brief";
import { uploadInBatches, type UploadProgress } from "./upload-batches";

function handleUnauthorized(res: Response): void {
  if (res.status === 401 && typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    removeToken();
    window.location.href = "/login";
  }
}

async function localRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    cache: "no-store",
    ...options,
  });
  handleUnauthorized(res);

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || body.detail || `API ${res.status}`);
  }
  return res.json() as Promise<T>;
}

async function localDownload(path: string): Promise<Blob> {
  const res = await fetch(path, { cache: "no-store" });
  handleUnauthorized(res);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || body.detail || `API ${res.status}`);
  }
  return res.blob();
}

export function parseReportedActiveMinutes(input: string): number | undefined {
  if (!input.trim()) return undefined;
  const minutes = Number(input);
  const seconds = Math.round(minutes * 60);
  if (!Number.isFinite(minutes) || minutes < 0.1 || minutes > 240 ||
    !Number.isSafeInteger(seconds) || seconds < 1 || seconds > 14_400) {
    throw new Error("Enter 0.1 to 240 active minutes for this save, or leave it blank.");
  }
  return seconds;
}

export const idpoApi = {
  listProductAutoRuns(jobId: string): Promise<{ available: boolean; modelConfigured: boolean; sourceFiles: ProductAutoSourceDocument[]; runs: ProductAutoRun[] }> {
    return localRequest(`/api/jobs/${encodeURIComponent(jobId)}/auto`);
  },

  listProductAutoRecipes(jobId: string): Promise<{ recipes: ProductAutoRecipeRevision[] }> {
    return localRequest(`/api/jobs/${encodeURIComponent(jobId)}/auto/recipes`);
  },

  getProductAutoBrief(jobId: string): Promise<ProductAutoBriefDetail> {
    return localRequest(`/api/jobs/${encodeURIComponent(jobId)}/auto/brief`);
  },

  suggestProductAutoBrief(jobId: string, expectedRevision: number,
    expectedPayloadSha256: string): Promise<ProductAutoBriefSuggestion> {
    return localRequest(`/api/jobs/${encodeURIComponent(jobId)}/auto/brief/suggest`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expectedRevision, expectedPayloadSha256 }),
    });
  },

  saveProductAutoBrief(jobId: string, expectedRevision: number, intent: string,
    fields: ProductAutoBriefField[], sampleFileIds: string[]): Promise<{ brief: ProductAutoBriefRevision }> {
    return localRequest(`/api/jobs/${encodeURIComponent(jobId)}/auto/brief`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expectedRevision, intent, fields, sampleFileIds }),
    });
  },

  confirmProductAutoBrief(jobId: string, expectedRevision: number,
    expectedPayloadSha256: string): Promise<{ brief: ProductAutoBriefRevision }> {
    return localRequest(`/api/jobs/${encodeURIComponent(jobId)}/auto/brief`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expectedRevision, expectedPayloadSha256 }),
    });
  },

  startProductAutoRun(jobId: string, selectedFileIds: string[],
    approvedRecipe?: { recipeId: string; expectedRevision: number },
    confirmedBrief?: { expectedRevision: number; payloadSha256: string; phase: "preview" | "batch";
      previewRunId?: string }): Promise<ProductAutoRun> {
    return localRequest(`/api/jobs/${encodeURIComponent(jobId)}/auto`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selectedFileIds, ...(approvedRecipe ? { approvedRecipe } : {}),
        ...(confirmedBrief ? { confirmedBrief } : {}) }),
    });
  },

  getProductAutoDocument(jobId: string, runId: string, docId: string): Promise<ProductAutoDocumentDetail> {
    return localRequest(`/api/jobs/${encodeURIComponent(jobId)}/auto/${encodeURIComponent(runId)}/docs/${encodeURIComponent(docId)}`);
  },

  downloadProductAutoReviewedBatch(jobId: string, runId: string): Promise<Blob> {
    return localDownload(`/api/jobs/${encodeURIComponent(jobId)}/auto/${encodeURIComponent(runId)}/export`);
  },

  saveProductAutoReview(jobId: string, runId: string, docId: string, expectedRevision: number, fields: ProductAutoReviewField[], addedFields: ProductAutoAddedFieldInput[], reportedActiveMinutes = ""): Promise<{ review: ProductAutoReview; correctedResult: ProductAutoCorrectedResult }> {
    const reportedSeconds = parseReportedActiveMinutes(reportedActiveMinutes);
    return localRequest(`/api/jobs/${encodeURIComponent(jobId)}/auto/${encodeURIComponent(runId)}/docs/${encodeURIComponent(docId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ expected_revision: expectedRevision, fields, added_fields: addedFields,
        ...(reportedSeconds === undefined ? {} : { reported_active_review_seconds: reportedSeconds }) }),
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

  uploadJobDocuments(jobId: string, files: File[], onProgress?: (progress: UploadProgress<JobStatus>) => void,
    retryKey?: string): Promise<JobStatus> {
    return uploadInBatches(files, (batch, idempotencyKey) => {
      const formData = new FormData();
      batch.forEach((file) => formData.append("files", file));
      return localRequest(`/api/jobs/${encodeURIComponent(jobId)}/documents`, {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: formData,
      });
    }, onProgress, retryKey);
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
