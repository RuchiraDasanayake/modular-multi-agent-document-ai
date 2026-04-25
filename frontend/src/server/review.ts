import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";
import type { JobDocumentRecord, JobFieldConfig, JobStatus, ReviewStage } from "@/types/idpo";
import { compareFieldValues } from "@/lib/idpo/exact-comparison";
import { loadRunnerConfig } from "@/server/config";
import { resolvePrimaryRunPath, resolveRunRoot } from "@/server/paths";
import { asNumber, readJsonFile } from "@/server/utils";

export type ReviewState =
  | "correct"
  | "wrong_value"
  | "missed_field"
  | "correctly_skipped"
  | "hallucinated_field";

export type ReviewStatus = "unreviewed" | "ai_validated" | "human_reviewed";
export type ReviewSource = "ai" | "human";

export interface ReviewFieldResult {
  fieldKey: string;
  fieldLabel: string;
  extractedValue: string;
  correctedValue: string | null;
  reviewState: ReviewState;
  reviewNote: string | null;
}

export interface ReviewMetrics {
  tp: number;
  fp: number;
  fn: number;
  precision: number;
  recall: number;
  f1: number;
  fieldStateCounts: Record<ReviewState, number>;
}

export interface ReviewFeedbackStatus {
  logged: boolean;
  error: string | null;
  attemptedAt: string | null;
}

export interface ReviewArtifact {
  version: 1;
  jobId: string | null;
  runId: string;
  docId: string;
  reviewStatus: ReviewStatus;
  reviewSource: ReviewSource;
  reviewWeight: number;
  reviewerStage: ReviewStage | null;
  reviewerConfidence: number | null;
  reviewedAt: string;
  fieldSetHash: string;
  overlayKey: string;
  policyIdUsed: string | null;
  adviceId: string | null;
  documentContext: {
    doc_type: string;
    vendor: string | null;
    content_profile: string | null;
    vendor_cluster: string | null;
    route_bin: string | null;
    layout_cluster_id: string | null;
  };
  metrics: ReviewMetrics;
  fields: ReviewFieldResult[];
  ahmnReviewFeedback: ReviewFeedbackStatus;
}

type DetailRecord = Record<string, unknown>;

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function normalizeFieldKey(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, "_");
}

function looksLikeSyntheticVendorIdentity(value: string): boolean {
  const text = value.trim().toLowerCase();
  if (!text) {
    return false;
  }
  return (
    /^[0-9a-f]{32}$/.test(text) ||
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(text) ||
    /^cord_validation_\d{4,}$/.test(text) ||
    /^jobrun[_-]/.test(text)
  );
}

export function sanitizeVendorIdentity(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const text = value.trim();
  if (!text || looksLikeSyntheticVendorIdentity(text)) {
    return null;
  }
  return text;
}

export function isConcreteValue(value: unknown): boolean {
  const text = String(value ?? "").trim();
  return text.length > 0 && text.toUpperCase() !== "N/A" && text.toUpperCase() !== "NA";
}

function normalizeReviewState(value: unknown): ReviewState {
  switch (value) {
    case "correct":
    case "wrong_value":
    case "missed_field":
    case "correctly_skipped":
    case "hallucinated_field":
      return value;
    default:
      return "wrong_value";
  }
}

function expectedFieldMap(value: Record<string, string> | null | undefined): Map<string, string> {
  const mapped = new Map<string, string>();
  for (const [key, raw] of Object.entries(value ?? {})) {
    const normalizedKey = normalizeFieldKey(key);
    const text = String(raw ?? "").trim();
    if (!normalizedKey || !text) {
      continue;
    }
    mapped.set(normalizedKey, text);
  }
  return mapped;
}

function canonicalizeReviewField(
  field: ReviewFieldResult,
  expectedByKey: Map<string, string>,
): ReviewFieldResult {
  const fieldKey = String(field.fieldKey ?? "").trim();
  const fieldLabel = String(field.fieldLabel ?? field.fieldKey ?? "").trim();
  const normalizedKey = normalizeFieldKey(fieldKey || fieldLabel);
  const extractedValue = String(field.extractedValue ?? "N/A").trim() || "N/A";
  const explicitCorrectedValue = typeof field.correctedValue === "string" && field.correctedValue.trim()
    ? field.correctedValue.trim()
    : null;
  const expectedValue = explicitCorrectedValue ?? expectedByKey.get(normalizedKey) ?? null;

  if (!expectedValue) {
    return {
      ...field,
      fieldKey,
      fieldLabel,
      extractedValue,
      correctedValue: explicitCorrectedValue,
      reviewState: normalizeReviewState(field.reviewState),
      reviewNote: field.reviewNote ?? null,
    };
  }

  let reviewState: ReviewState;
  if (!isConcreteValue(extractedValue)) {
    reviewState = "missed_field";
  } else if (compareFieldValues(fieldKey || fieldLabel, extractedValue, expectedValue)) {
    reviewState = "correct";
  } else {
    reviewState = "wrong_value";
  }

  return {
    ...field,
    fieldKey,
    fieldLabel,
    extractedValue,
    correctedValue: expectedValue,
    reviewState,
    reviewNote: field.reviewNote ?? null,
  };
}

export function scoreReviewFields(fields: ReviewFieldResult[]): ReviewMetrics {
  let tp = 0;
  let fp = 0;
  let fn = 0;
  const fieldStateCounts: Record<ReviewState, number> = {
    correct: 0,
    wrong_value: 0,
    missed_field: 0,
    correctly_skipped: 0,
    hallucinated_field: 0,
  };

  for (const field of fields) {
    fieldStateCounts[field.reviewState] += 1;
    if (field.reviewState === "correct") {
      tp += 1;
    } else if (field.reviewState === "wrong_value") {
      fp += 1;
      fn += 1;
    } else if (field.reviewState === "missed_field") {
      fn += 1;
    } else if (field.reviewState === "hallucinated_field") {
      fp += 1;
    }
  }

  const precision = tp + fp > 0 ? tp / (tp + fp) : 0;
  const recall = tp + fn > 0 ? tp / (tp + fn) : 0;
  const f1 = precision + recall > 0 ? (2 * precision * recall) / (precision + recall) : 0;
  return {
    tp,
    fp,
    fn,
    precision: Number(precision.toFixed(4)),
    recall: Number(recall.toFixed(4)),
    f1: Number(f1.toFixed(4)),
    fieldStateCounts,
  };
}

export function computeFieldSetHash(fieldKeys: string[]): string {
  const normalized = [...new Set(fieldKeys.map(normalizeFieldKey).filter(Boolean))].sort();
  return createHash("sha256").update(JSON.stringify(normalized)).digest("hex").slice(0, 16);
}

export function buildOverlayKey(parts: {
  vendorCluster: string | null;
  docType: string | null;
  contentProfile: string | null;
  fieldSetHash: string;
}): string {
  return [
    String(parts.vendorCluster || "unknown").trim().toLowerCase() || "unknown",
    String(parts.docType || "unknown").trim().toLowerCase() || "unknown",
    String(parts.contentProfile || "unknown").trim().toLowerCase() || "unknown",
    parts.fieldSetHash,
  ].join("|");
}

function getReviewArtifactPath(runId: string, docId: string): string {
  const resolved = resolveRunRoot(runId);
  const primaryPath = resolvePrimaryRunPath(resolved.rootPath);
  return path.join(primaryPath, "docs", docId, "review", "results.json");
}

export function readReviewArtifact(runId: string, docId: string): ReviewArtifact | null {
  try {
    return readJsonFile<ReviewArtifact>(getReviewArtifactPath(runId, docId));
  } catch {
    return null;
  }
}

export function writeReviewArtifact(artifact: ReviewArtifact): void {
  const target = getReviewArtifactPath(artifact.runId, artifact.docId);
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, JSON.stringify(artifact, null, 2), "utf-8");
}

function detailFieldMap(detail: DetailRecord): Map<string, Record<string, unknown>> {
  const fields = Array.isArray(detail.fields) ? detail.fields : [];
  return new Map(
    fields
      .filter((field) => field && typeof field === "object")
      .map((field) => {
        const entry = field as Record<string, unknown>;
        return [normalizeFieldKey(String(entry.key ?? "")), entry] as const;
      })
      .filter(([key]) => key.length > 0),
  );
}

function requestedStatusMap(detail: DetailRecord): Record<string, Record<string, unknown>> {
  const raw = asRecord(detail.raw);
  const extract = asRecord(raw?.extract);
  const requested = asRecord(extract?.requested_field_status);
  const map: Record<string, Record<string, unknown>> = {};
  for (const [key, value] of Object.entries(requested ?? {})) {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      map[normalizeFieldKey(key)] = value as Record<string, unknown>;
    }
  }
  return map;
}

function issueMap(detail: DetailRecord): Map<string, string[]> {
  const issues = Array.isArray(detail.validationIssues) ? detail.validationIssues : [];
  const map = new Map<string, string[]>();
  for (const issue of issues) {
    const entry = asRecord(issue);
    const key = normalizeFieldKey(String(entry?.field ?? ""));
    if (!key) {
      continue;
    }
    const list = map.get(key) ?? [];
    list.push(String(entry?.issue ?? "").toLowerCase());
    map.set(key, list);
  }
  return map;
}

export function buildRequestedReviewRows(detail: DetailRecord, fieldConfig: JobFieldConfig[]): ReviewFieldResult[] {
  const fieldMap = detailFieldMap(detail);
  const requestedStatus = requestedStatusMap(detail);
  const issues = issueMap(detail);
  const requestedFields =
    fieldConfig.length > 0
      ? fieldConfig.map((field) => ({ key: normalizeFieldKey(field.name), label: field.name }))
      : [...fieldMap.keys()].map((key) => ({ key, label: key }));

  return requestedFields.map(({ key, label }) => {
    const field = fieldMap.get(key) ?? requestedStatus[key] ?? {};
    const extractedValue = String(
      asRecord(field)?.value ?? asRecord(requestedStatus[key])?.value ?? "N/A",
    ).trim() || "N/A";
    const requestedField = requestedStatus[key] ?? {};
    const fieldIssues = issues.get(key) ?? [];
    const confidence = asNumber(asRecord(field)?.confidence ?? requestedField.confidence) ?? 0;
    const runtimeStatus = String(requestedField.status ?? "").trim().toLowerCase();
    let reviewState: ReviewState;

    if (!isConcreteValue(extractedValue)) {
      reviewState = fieldIssues.length > 0 || runtimeStatus === "missing" || runtimeStatus === "low_confidence"
        ? "missed_field"
        : "correctly_skipped";
    } else if (fieldIssues.some((issue) => issue.includes("hallucin"))) {
      reviewState = "hallucinated_field";
    } else if (fieldIssues.length > 0 || runtimeStatus === "low_confidence" || confidence < 0.55) {
      reviewState = "wrong_value";
    } else {
      reviewState = "correct";
    }

    return {
      fieldKey: key,
      fieldLabel: label,
      extractedValue,
      correctedValue: null,
      reviewState,
      reviewNote: fieldIssues.length > 0 ? fieldIssues.join("; ") : null,
    };
  });
}

function buildDocumentContext(detail: DetailRecord): ReviewArtifact["documentContext"] {
  const metadata = asRecord(detail.metadata) ?? {};
  const vendorIdentity =
    sanitizeVendorIdentity(metadata.vendorCluster) ??
    sanitizeVendorIdentity(metadata.vendor) ??
    null;
  return {
    doc_type: typeof metadata.docType === "string" && metadata.docType.trim() ? metadata.docType : "unknown",
    vendor: vendorIdentity,
    vendor_cluster: vendorIdentity,
    content_profile: typeof metadata.profile === "string" ? metadata.profile : null,
    route_bin: typeof metadata.routeBin === "string" ? metadata.routeBin : null,
    layout_cluster_id: typeof metadata.layoutClusterId === "string" ? metadata.layoutClusterId : null,
  };
}

export function buildReviewArtifact(input: {
  jobId: string | null;
  runId: string;
  docId: string;
  detail: DetailRecord;
  fieldConfig: JobFieldConfig[];
  reviewSource: ReviewSource;
  fields?: ReviewFieldResult[];
  expectedFieldValues?: Record<string, string> | null;
  reviewerStage?: ReviewStage | null;
  reviewerConfidence?: number | null;
}): ReviewArtifact {
  const expectedByKey = expectedFieldMap(input.expectedFieldValues);
  const rows = (input.fields ?? buildRequestedReviewRows(input.detail, input.fieldConfig)).map((field) =>
    canonicalizeReviewField(field, expectedByKey),
  );
  const fieldSetHash = computeFieldSetHash(rows.map((row) => row.fieldKey));
  const documentContext = buildDocumentContext(input.detail);
  const metrics = scoreReviewFields(rows);
  const metadata = asRecord(input.detail.metadata) ?? {};
  return {
    version: 1,
    jobId: input.jobId,
    runId: input.runId,
    docId: input.docId,
    reviewStatus: input.reviewSource === "human" ? "human_reviewed" : "ai_validated",
    reviewSource: input.reviewSource,
    reviewWeight: input.reviewSource === "human" ? 1.0 : 0.35,
    reviewerStage: input.reviewerStage ?? null,
    reviewerConfidence: typeof input.reviewerConfidence === "number" ? Number(input.reviewerConfidence.toFixed(4)) : null,
    reviewedAt: new Date().toISOString(),
    fieldSetHash,
    overlayKey: buildOverlayKey({
      vendorCluster: documentContext.vendor_cluster,
      docType: documentContext.doc_type,
      contentProfile: documentContext.content_profile,
      fieldSetHash,
    }),
    policyIdUsed: typeof metadata.policyId === "string" ? metadata.policyId : null,
    adviceId: typeof metadata.adviceId === "string" ? metadata.adviceId : null,
    documentContext,
    metrics,
    fields: rows,
    ahmnReviewFeedback: {
      logged: false,
      error: null,
      attemptedAt: null,
    },
  };
}

export async function postReviewedFeedback(artifact: ReviewArtifact): Promise<{ logged: boolean; error?: string }> {
  if (!artifact.adviceId || !artifact.policyIdUsed) {
    return { logged: false, error: "missing_advice_context" };
  }
  const endpoint = (process.env.AHMN_ENDPOINT || "http://localhost:8001").trim();
  if (!endpoint) {
    return { logged: false, error: "missing_ahmn_endpoint" };
  }

  const response = await fetch(`${endpoint.replace(/\/$/, "")}/advice/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      advice_id: artifact.adviceId,
      policy_id_used: artifact.policyIdUsed,
      document_context: artifact.documentContext,
      review_source: artifact.reviewSource,
      review_weight: artifact.reviewWeight,
      tp: artifact.metrics.tp,
      fp: artifact.metrics.fp,
      fn: artifact.metrics.fn,
      precision: artifact.metrics.precision,
      recall: artifact.metrics.recall,
      f1: artifact.metrics.f1,
      field_state_counts: artifact.metrics.fieldStateCounts,
      job_id: artifact.jobId,
      overlay_key: artifact.overlayKey,
    }),
  }).catch(() => null);

  if (!response || !response.ok) {
    return { logged: false, error: response ? `http_${response.status}` : "unreachable" };
  }
  return { logged: true };
}

export function attachReviewFeedbackResult(
  artifact: ReviewArtifact,
  result: { logged: boolean; error?: string },
): ReviewArtifact {
  return {
    ...artifact,
    ahmnReviewFeedback: {
      logged: result.logged,
      error: result.error ?? null,
      attemptedAt: new Date().toISOString(),
    },
  };
}

export function summarizeReviewState(artifact: ReviewArtifact | null): string | null {
  if (!artifact) {
    return null;
  }
  return `${artifact.reviewStatus} | F1 ${artifact.metrics.f1.toFixed(2)}`;
}

export function applyReviewToJobDocument(
  document: JobDocumentRecord,
  artifact: ReviewArtifact,
  runId: string,
  mode?: "adaptive" | "strict",
): void {
  document.reviewState = summarizeReviewState(artifact);
  document.reviewStatus = artifact.reviewStatus;
  document.reviewSource = artifact.reviewSource;
  document.reviewStage = artifact.reviewerStage;
  document.reviewConfidence = artifact.reviewerConfidence;
  document.updatedAt = new Date().toISOString();
  for (const outcome of document.outcomes) {
    if (outcome.runId !== runId) {
      continue;
    }
    if (mode && outcome.mode !== mode) {
      continue;
    }
    outcome.reviewState = summarizeReviewState(artifact);
    outcome.reviewStatus = artifact.reviewStatus;
    outcome.reviewSource = artifact.reviewSource;
    outcome.reviewStage = artifact.reviewerStage;
    outcome.reviewConfidence = artifact.reviewerConfidence;
    outcome.exactPrecision = artifact.metrics.precision;
    outcome.exactRecall = artifact.metrics.recall;
    outcome.exactF1 = artifact.metrics.f1;
  }
}

export function buildJobOverlay(job: JobStatus, fieldConfig: JobFieldConfig[]): { path: string; entries: Array<Record<string, unknown>> } {
  const targetFieldSetHash = computeFieldSetHash(fieldConfig.map((field) => field.name));
  const grouped = new Map<string, { policyId: string; totalWeight: number; weightedF1: number; humanReviewedDocs: number }>();
  const entriesByOverlay = new Map<string, Array<{ policyId: string; totalWeight: number; weightedF1: number; humanReviewedDocs: number }>>();

  for (const document of job.documents ?? []) {
    for (const outcome of document.outcomes) {
      if (!outcome.docId || !outcome.runId || outcome.status !== "processed") {
        continue;
      }
      const artifact = readReviewArtifact(outcome.runId, outcome.docId);
      if (!artifact || !artifact.policyIdUsed) {
        continue;
      }
      if (artifact.fieldSetHash !== targetFieldSetHash) {
        continue;
      }
      const bucketKey = `${artifact.overlayKey}::${artifact.policyIdUsed ?? "unknown"}`;
      const current = grouped.get(bucketKey) ?? {
        policyId: artifact.policyIdUsed ?? "unknown",
        totalWeight: 0,
        weightedF1: 0,
        humanReviewedDocs: 0,
      };
      current.totalWeight += artifact.reviewWeight;
      current.weightedF1 += artifact.reviewWeight * artifact.metrics.f1;
      if (artifact.reviewSource === "human") {
        current.humanReviewedDocs += 1;
      }
      grouped.set(bucketKey, current);
    }
  }

  for (const [bucketKey, value] of grouped.entries()) {
    const overlayKey = bucketKey.split("::")[0] ?? "";
    const list = entriesByOverlay.get(overlayKey) ?? [];
    list.push(value);
    entriesByOverlay.set(overlayKey, list);
  }

  const overlayEntries: Array<Record<string, unknown>> = [];
  for (const [overlayKey, candidates] of entriesByOverlay.entries()) {
    const best = [...candidates]
      .map((entry) => ({
        ...entry,
        meanReviewedF1: entry.totalWeight > 0 ? entry.weightedF1 / entry.totalWeight : 0,
      }))
      .sort((left, right) => right.meanReviewedF1 - left.meanReviewedF1)[0];
    if (!best) {
      continue;
    }
    if (best.meanReviewedF1 < 0.75) {
      continue;
    }
    if (best.humanReviewedDocs < 2 && best.totalWeight < 2.0) {
      continue;
    }
    overlayEntries.push({
      overlay_key: overlayKey,
      policy_id: best.policyId,
      total_weight: Number(best.totalWeight.toFixed(4)),
      human_reviewed_docs: best.humanReviewedDocs,
      mean_reviewed_f1: Number(best.meanReviewedF1.toFixed(4)),
    });
  }

  return {
    path: path.join(loadRunnerConfig().jobsDir, `${job.jobId}_overlay.json`),
    entries: overlayEntries,
  };
}

export interface JobReviewLearningStats {
  reviewedDocumentCount: number;
  reviewedHumanCount: number;
  reviewedAiCount: number;
  reviewedFeedbackLoggedCount: number;
  reviewedFeedbackPendingCount: number;
  overlayEntryCount: number;
  overlayReady: boolean;
}

export function collectJobReviewLearningStats(job: JobStatus, fieldConfig: JobFieldConfig[]): JobReviewLearningStats {
  const seenArtifacts = new Set<string>();
  let reviewedDocumentCount = 0;
  let reviewedHumanCount = 0;
  let reviewedAiCount = 0;
  let reviewedFeedbackLoggedCount = 0;
  let reviewedFeedbackPendingCount = 0;

  for (const document of job.documents ?? []) {
    for (const outcome of document.outcomes) {
      if (!outcome.runId || !outcome.docId || outcome.status !== "processed") {
        continue;
      }
      const artifactKey = `${outcome.runId}:${outcome.docId}`;
      if (seenArtifacts.has(artifactKey)) {
        continue;
      }
      seenArtifacts.add(artifactKey);
      const artifact = readReviewArtifact(outcome.runId, outcome.docId);
      if (!artifact) {
        continue;
      }
      reviewedDocumentCount += 1;
      if (artifact.reviewSource === "human") {
        reviewedHumanCount += 1;
      } else {
        reviewedAiCount += 1;
      }
      if (artifact.ahmnReviewFeedback?.logged) {
        reviewedFeedbackLoggedCount += 1;
      } else {
        reviewedFeedbackPendingCount += 1;
      }
    }
  }

  const overlayEntryCount = buildJobOverlay(job, fieldConfig).entries.length;
  return {
    reviewedDocumentCount,
    reviewedHumanCount,
    reviewedAiCount,
    reviewedFeedbackLoggedCount,
    reviewedFeedbackPendingCount,
    overlayEntryCount,
    overlayReady: overlayEntryCount > 0,
  };
}
