"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { IdpoCard } from "@/components/idpo/card";
import {
  mergeSavedReviewIntoDocumentPayload,
  suggestedReviewRowsFromDocumentPayload,
} from "@/components/idpo/job-document-review";
import { compareFieldValues } from "@/lib/idpo/exact-comparison";
import { StatusBadge } from "@/components/idpo/status-badge";
import { idpoApi } from "@/lib/idpo-api";
import type { FieldExtraction, ProvenanceEvent } from "@/types/idpo";

type ReviewState = "correct" | "wrong_value" | "missed_field" | "correctly_skipped" | "hallucinated_field";

interface ReviewRow {
  fieldKey: string;
  fieldLabel: string;
  extractedValue: string;
  correctedValue: string;
  reviewState: ReviewState;
  reviewNote: string;
}

function detectPreviewKind(filename: string | null): "pdf" | "image" | "text" | "unsupported" {
  if (!filename) {
    return "unsupported";
  }
  const lower = filename.toLowerCase();
  if (lower.endsWith(".pdf")) {
    return "pdf";
  }
  if (lower.endsWith(".png") || lower.endsWith(".jpg") || lower.endsWith(".jpeg") || lower.endsWith(".gif") || lower.endsWith(".webp")) {
    return "image";
  }
  if (lower.endsWith(".txt") || lower.endsWith(".json")) {
    return "text";
  }
  return "unsupported";
}

function formatValue(value: unknown): string {
  if (typeof value === "string") {
    return value || "-";
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return "-";
}

function formatMetric(value: unknown, suffix = ""): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "-";
  }
  return `${value}${suffix}`;
}

function expectedValueMatches(key: string, extractedValue: string | null, expectedValue: string | null): boolean {
  if (!extractedValue || !expectedValue) {
    return false;
  }
  return compareFieldValues(key, extractedValue, expectedValue);
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((entry) => (typeof entry === "string" ? entry.trim() : ""))
    .filter((entry) => entry.length > 0);
}

function formatConfidence(value: number | null): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "";
  }
  return `${Math.round(value * 100)}% confidence`;
}

function normalizeEventTimestamp(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  return value > 1_000_000_000_000 ? value : value * 1000;
}

function formatEventTime(value: unknown): string {
  const timestamp = normalizeEventTimestamp(value);
  if (timestamp == null) {
    return "-";
  }
  return new Date(timestamp).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function titleCase(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .trim()
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

type EvidenceTarget = "fields" | "review" | "notes" | null;
type InspectorTab = "fields" | "review" | "notes" | "log" | "llm";

function normalizeFieldKey(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, "_");
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function collectRelevantFieldKeys(event: ProvenanceEvent): string[] {
  const outputs = asRecord(event.payload?.outputs) ?? {};
  const keys = new Set<string>();

  const requestedFieldStatus = asRecord(outputs.requested_field_status);
  if (requestedFieldStatus) {
    for (const key of Object.keys(requestedFieldStatus)) {
      keys.add(normalizeFieldKey(key));
    }
  }

  const recoveredFields = asRecord(outputs.recovered_fields);
  if (recoveredFields) {
    for (const key of Object.keys(recoveredFields)) {
      keys.add(normalizeFieldKey(key));
    }
  }

  const issues = Array.isArray(outputs.issues) ? outputs.issues : [];
  for (const issue of issues) {
    const entry = asRecord(issue);
    const field = typeof entry?.field === "string" ? entry.field : "";
    if (field) {
      keys.add(normalizeFieldKey(field));
    }
  }

  return [...keys];
}

function collectRelevantIssueFields(event: ProvenanceEvent): string[] {
  const outputs = asRecord(event.payload?.outputs) ?? {};
  const inputs = asRecord(event.payload?.inputs) ?? {};
  const keys = new Set<string>();

  const issues = Array.isArray(outputs.issues) ? outputs.issues : [];
  for (const issue of issues) {
    const entry = asRecord(issue);
    const field = typeof entry?.field === "string" ? entry.field : "";
    if (field) {
      keys.add(normalizeFieldKey(field));
    }
  }

  const recoveredFields = asRecord(outputs.recovered_fields);
  if (recoveredFields) {
    for (const key of Object.keys(recoveredFields)) {
      keys.add(normalizeFieldKey(key));
    }
  }

  if (keys.size === 0) {
    const inputField = typeof inputs.field === "string" ? inputs.field : "";
    if (inputField) {
      keys.add(normalizeFieldKey(inputField));
    }
  }

  return [...keys];
}

function getEvidenceTarget(event: ProvenanceEvent): EvidenceTarget {
  if (event.eventType === "ValidationResult" || event.eventType === "RecoveryAction") {
    return "review";
  }
  if (event.eventType === "EscalationAction") {
    return "notes";
  }
  if (
    event.eventType === "OperatorExecution" ||
    event.eventType === "RouteSelection" ||
    event.eventType === "PolicyAdvice" ||
    event.stage === "extract"
  ) {
    return "fields";
  }
  return null;
}

function summarizeProvenanceEvent(event: ProvenanceEvent): string {
  const outputs = event.payload?.outputs ?? {};
  const parameters = event.payload?.parameters ?? {};

  if (event.eventType === "DAEOutput") {
    const docType = typeof outputs.doc_type === "string" ? outputs.doc_type : "unknown";
    const routeBin = typeof outputs.route_bin === "string" ? outputs.route_bin : "unknown";
    return `Classified as ${docType}; route bin ${routeBin}.`;
  }

  if (event.eventType === "PolicyAdvice" || event.eventType === "RouteSelection") {
    const policyId = typeof outputs.policy_id === "string" ? outputs.policy_id : "unknown";
    const adviceStatus = typeof outputs.advice_status === "string" ? outputs.advice_status : "no_advice";
    return `Selected policy ${policyId}; advice status ${adviceStatus}.`;
  }

  if (event.eventType === "OperatorExecution" && event.agent === "llm_extraction") {
    const model = typeof parameters.model === "string" ? parameters.model : "unknown";
    const mode = typeof parameters.model_mode === "string" ? parameters.model_mode : "unknown";
    return `Extraction ran with ${model} in ${mode} mode.`;
  }

  if (event.eventType === "ValidationResult") {
    const issueCount = typeof outputs.issue_count === "number" ? outputs.issue_count : 0;
    return issueCount > 0 ? `${issueCount} validation issue(s) found.` : "Validation passed with no issues.";
  }

  if (event.eventType === "RecoveryAction") {
    const skipped = outputs.skipped === true;
    const reason = typeof outputs.reason === "string" ? outputs.reason : "recovery evaluated";
    return skipped ? `Recovery skipped: ${reason}.` : `Recovery executed: ${reason}.`;
  }

  if (event.eventType === "EscalationAction") {
    const escalated = outputs.escalated === true;
    const reason = typeof outputs.reason === "string" ? outputs.reason : "no reason recorded";
    return escalated ? `Escalated: ${reason}.` : `Escalation not needed: ${reason}.`;
  }

  if (event.eventType === "RewardComputation") {
    const reward = typeof outputs.reward === "number" ? outputs.reward : null;
    return reward != null ? `Reward computed: ${reward}.` : "Reward computed.";
  }

  if (event.eventType === "AHMNFeedback") {
    const logged = outputs.feedback_logged === true || outputs.logged === true;
    return logged ? "AHMN feedback logged." : "AHMN feedback was not logged.";
  }

  if (event.eventType === "FinalArtifacts") {
    return "Final artifacts were written for this document.";
  }

  return `${titleCase(event.eventType)} completed.`;
}

function countObjectKeys(value: unknown): number {
  const record = asRecord(value);
  return record ? Object.keys(record).length : 0;
}

function collectEventFacts(event: ProvenanceEvent): Array<{ label: string; value: string }> {
  const outputs = asRecord(event.payload?.outputs) ?? {};
  const parameters = asRecord(event.payload?.parameters) ?? {};
  const facts: Array<{ label: string; value: string }> = [];

  const pushFact = (label: string, value: unknown) => {
    if (value == null) {
      return;
    }
    const normalized =
      typeof value === "boolean" ? (value ? "yes" : "no") : typeof value === "number" ? String(value) : String(value).trim();
    if (!normalized) {
      return;
    }
    facts.push({ label, value: normalized });
  };

  if (event.eventType === "DAEOutput") {
    pushFact("Doc type", outputs.doc_type);
    pushFact("Route", outputs.route_bin);
    pushFact("Profile", outputs.profile);
  }

  if (event.eventType === "PolicyAdvice" || event.eventType === "RouteSelection") {
    pushFact("Policy", outputs.policy_id);
    pushFact("Advice", outputs.advice_status);
    pushFact("Source", outputs.source);
    const selectedPolicy = typeof outputs.policy_id === "string" ? outputs.policy_id.trim() : "";
    const baselinePolicy = typeof outputs.static_policy_id === "string" ? outputs.static_policy_id.trim() : "";
    if (selectedPolicy && baselinePolicy && selectedPolicy !== baselinePolicy) {
      facts.push({ label: "Changed from", value: baselinePolicy });
    }
  }

  if (event.eventType === "OperatorExecution") {
    pushFact("Model", parameters.model);
    pushFact("Mode", parameters.model_mode);
    pushFact("Policy", parameters.policy_id);
    const requestedCount = countObjectKeys(outputs.requested_field_status);
    if (requestedCount > 0) {
      facts.push({ label: "Requested fields", value: String(requestedCount) });
    }
    pushFact("Fallback path", parameters.fallback_path);
  }

  if (event.eventType === "ValidationResult") {
    pushFact("Issue count", outputs.issue_count);
    pushFact("Valid", outputs.valid);
  }

  if (event.eventType === "RecoveryAction") {
    pushFact("Recovered fields", countObjectKeys(outputs.recovered_fields));
    pushFact("Skipped", outputs.skipped);
    pushFact("Reason", outputs.reason);
  }

  if (event.eventType === "EscalationAction") {
    pushFact("Escalated", outputs.escalated);
    pushFact("Target model", outputs.target_model);
    pushFact("Reason", outputs.reason);
  }

  if (event.eventType === "AHMNFeedback") {
    pushFact("Logged", outputs.feedback_logged ?? outputs.logged);
    pushFact("Advice id", outputs.advice_id);
  }

  if (event.eventType === "RewardComputation") {
    pushFact("Reward", outputs.reward);
    pushFact("Reward type", outputs.reward_type);
  }

  return facts;
}

function collectFieldEvidenceFacts(field: FieldExtraction | null): string[] {
  if (!field) {
    return [];
  }
  const facts: string[] = [];
  const confidence = formatConfidence(field.confidence);
  if (confidence) {
    facts.push(confidence);
  }
  if (field.extraction_method && field.extraction_method !== "unknown") {
    facts.push(titleCase(field.extraction_method));
  }
  if (typeof field.evidence?.page === "number") {
    facts.push(`Page ${field.evidence.page + 1}`);
  }
  const source = typeof field.metadata?.source === "string" ? field.metadata.source.trim() : "";
  if (source) {
    facts.push(`Source ${source}`);
  }
  const model = typeof field.metadata?.model === "string" ? field.metadata.model.trim() : "";
  if (model) {
    facts.push(model);
  }
  if (field.discovered) {
    facts.push("Discovered field");
  }
  return facts;
}

function asRecordArray(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((entry) => asRecord(entry))
    .filter((entry): entry is Record<string, unknown> => entry !== null);
}

function formatAuditValue(value: unknown): string {
  if (typeof value === "string") {
    return value.trim() || "-";
  }
  if (typeof value === "boolean") {
    return value ? "yes" : "no";
  }
  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      return "-";
    }
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  if (Array.isArray(value)) {
    const flattened = value.map((entry) => formatAuditValue(entry)).filter((entry) => entry !== "-");
    return flattened.length > 0 ? flattened.join(", ") : "-";
  }
  if (value && typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return "[object]";
    }
  }
  return "-";
}

function collectAuditFacts(
  call: Record<string, unknown>,
): Array<{ label: string; value: string }> {
  const request = asRecord(call.request) ?? {};
  const context = asRecord(call.context) ?? {};
  const facts: Array<{ label: string; value: string }> = [];

  const pushFact = (label: string, value: unknown) => {
    const formatted = formatAuditValue(value);
    if (formatted === "-") {
      return;
    }
    facts.push({ label, value: formatted });
  };

  pushFact("Provider", call.provider);
  pushFact("Model", call.model);
  pushFact("Endpoint", call.endpoint ?? request.endpoint);
  pushFact("Format", request.format);
  pushFact("Latency", typeof call.latency_ms === "number" ? `${formatAuditValue(call.latency_ms)} ms` : null);
  pushFact("Prompt tokens", call.prompt_tokens);
  pushFact("Completion tokens", call.completion_tokens);
  pushFact("Total tokens", call.total_tokens);
  pushFact("Prompt chars", call.prompt_chars);
  pushFact("Requested fields", call.requested_fields);
  pushFact("Returned fields", call.entity_count);
  pushFact("Done reason", call.done_reason);
  pushFact("Error", sanitizeUiErrorText(call.error));
  pushFact("Parse failed", call.parse_failed);
  pushFact("Context", context.strategy);
  pushFact("Truncated", context.truncated);
  pushFact("Temperature", request.temperature);
  pushFact("Top p", request.top_p);
  pushFact("Num predict", request.num_predict);
  pushFact("Max tokens", request.max_tokens);
  pushFact("Strict JSON", request.strict_json_output);

  return facts;
}

function formatPercentValue(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "-";
  }
  const percent = value > 1 ? value : value * 100;
  return `${percent.toFixed(1)}%`;
}

function formatScoreValue(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "-";
  }
  return value.toFixed(2);
}

function sanitizeUiErrorText(value: unknown): string {
  if (typeof value !== "string") {
    return formatAuditValue(value);
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return "-";
  }
  if (/incorrect api key|invalid api key|authentication|401/i.test(trimmed)) {
    return "authentication_failed";
  }
  return trimmed.replace(/\b(?:sk|rk|api[_-]?key)[-_a-zA-Z0-9]{8,}\b/gi, "[redacted]");
}

function describeExtractionSource(source: string): string {
  switch (source) {
    case "llm_local":
      return "local model";
    case "llm_cloud":
      return "cloud model";
    case "generic_kv":
      return "Generic KV";
    case "smart_heuristic":
      return "smart heuristic";
    case "schema_regex":
      return "schema regex";
    case "label_anchor":
      return "label anchor";
    case "label_anchor_next_line":
      return "next-line label anchor";
    case "schema_match":
      return "schema match";
    case "rule_based":
      return "rules";
    case "none":
      return "no model";
    default:
      return titleCase(source);
  }
}

function deriveFinalExtractionSummary(
  fields: FieldExtraction[],
  metadata: Record<string, unknown>,
  llmDiagnostics: Record<string, unknown>,
): {
  finalModel: string;
  finalSource: string;
  summary: string;
} {
  const fieldModels = [...new Set(
    fields
      .map((field) => (typeof field.metadata?.model === "string" ? field.metadata.model.trim() : ""))
      .filter((value) => value.length > 0),
  )];
  const fieldSources = [...new Set(
    fields
      .map((field) => (typeof field.metadata?.source === "string" ? field.metadata.source.trim() : ""))
      .filter((value) => value.length > 0),
  )];

  const plannedModel = typeof metadata.modelUsed === "string" ? metadata.modelUsed.trim() : "";
  const plannedMode = typeof metadata.modelMode === "string" ? metadata.modelMode.trim() : "";
  const localSucceeded = llmDiagnostics.local_succeeded === true;
  const localAttempted = llmDiagnostics.local_attempted === true;
  const cloudAttempted = llmDiagnostics.cloud_attempted === true;
  const cloudSucceeded = llmDiagnostics.cloud_succeeded === true;
  const singleFieldSource = fieldSources.length === 1 ? fieldSources[0] : "";
  const singleFieldSourceLabel = singleFieldSource ? describeExtractionSource(singleFieldSource) : "";
  const finalUsesPlannedLlmSource =
    (plannedMode === "local" && fieldSources.includes("llm_local")) ||
    (plannedMode === "cloud" && fieldSources.includes("llm_cloud"));

  const finalModel =
    fieldModels.length === 1
      ? fieldModels[0]
      : fieldModels.length > 1
        ? "Mixed models"
        : singleFieldSource && !fieldSources.some((source) => source.startsWith("llm_"))
          ? singleFieldSourceLabel
          : plannedModel || "-";
  const finalSource =
    fieldSources.length === 1
      ? singleFieldSourceLabel
      : fieldSources.length > 1
        ? "mixed sources"
        : plannedMode
          ? `${plannedMode} route`
          : "-";

  let summary = "No final extraction source was recorded.";
  if (fieldModels.length === 1) {
    summary =
      plannedModel && plannedModel !== fieldModels[0]
        ? `Planned ${plannedModel}; final value came from ${fieldModels[0]}.`
        : `Final value came from ${fieldModels[0]}.`;
  } else if (fieldSources.length > 1) {
    summary = "Final fields came from mixed extraction sources.";
  } else if (singleFieldSourceLabel && !finalUsesPlannedLlmSource) {
    summary =
      plannedModel && plannedModel.length > 0
        ? `Planned ${plannedModel}; final fields came from ${singleFieldSourceLabel}.`
        : `Final fields came from ${singleFieldSourceLabel}.`;
  } else if (plannedModel) {
    summary = `Final extraction followed the planned ${plannedModel} route.`;
  }

  if (cloudAttempted && !cloudSucceeded && localSucceeded && fieldSources.includes("llm_local")) {
    summary += " Cloud retries failed and were not used.";
  } else if (cloudSucceeded && fieldSources.includes("llm_cloud")) {
    summary += " Cloud fallback supplied the final value.";
  } else if (localAttempted && !localSucceeded && singleFieldSourceLabel && !fieldSources.includes("llm_local")) {
    summary += ` The local model failed, so the final fields came from ${singleFieldSourceLabel}.`;
  }

  return { finalModel, finalSource, summary };
}

function deriveFallbackSummary(
  llmDiagnostics: Record<string, unknown>,
  fallbackKeys: string[],
  finalSummary: { finalModel: string; finalSource: string },
): { title: string; detail: string } {
  const cloudAttempted = llmDiagnostics.cloud_attempted === true;
  const cloudSucceeded = llmDiagnostics.cloud_succeeded === true;
  const localSucceeded = llmDiagnostics.local_succeeded === true;
  const flagshipAttempted = llmDiagnostics.flagship_attempted === true;
  const localAttempted = llmDiagnostics.local_attempted === true;
  const finalSource = finalSummary.finalSource.toLowerCase();

  if (!cloudAttempted && !flagshipAttempted) {
    if (localAttempted && !localSucceeded && finalSource !== "-" && finalSource !== "local route") {
      return {
        title: "Built-in fallback used",
        detail: `The local model failed, so the final result came from ${finalSummary.finalSource}.`,
      };
    }
    return {
      title: "No fallback needed",
      detail: "The initial extraction path was enough.",
    };
  }
  if (cloudSucceeded) {
    return {
      title: "Cloud fallback used",
      detail:
        fallbackKeys.length > 0
          ? `Retried fields: ${fallbackKeys.join(", ")}.`
          : "A cloud retry supplied the final extraction.",
    };
  }
  if (localSucceeded && cloudAttempted) {
    return {
      title: "Recovered on the local model",
      detail:
        fallbackKeys.length > 0
          ? `Retried fields: ${fallbackKeys.join(", ")}. Final result stayed on ${finalSummary.finalModel}.`
          : `Final result stayed on ${finalSummary.finalModel}.`,
    };
  }
  return {
    title: "Fallback attempted",
    detail:
      fallbackKeys.length > 0
        ? `Retried fields: ${fallbackKeys.join(", ")}.`
        : "Retries were attempted, but no clear final fallback source was recorded.",
  };
}

export function JobDocumentPage() {
  const params = useParams<{ jobId: string; docId: string }>();
  const searchParams = useSearchParams();
  const jobId = decodeURIComponent(params.jobId);
  const docId = decodeURIComponent(params.docId);
  const mode = searchParams.get("mode");
  const runId = searchParams.get("runId");

  const [payload, setPayload] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [layoutMode, setLayoutMode] = useState<"split" | "stacked">("split");
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [focusedSection, setFocusedSection] = useState<EvidenceTarget>(null);
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("fields");
  const [focusedFieldKey, setFocusedFieldKey] = useState<string | null>(null);
  const [focusedIssueField, setFocusedIssueField] = useState<string | null>(null);
  const [reviewRows, setReviewRows] = useState<ReviewRow[]>([]);
  const [savingReview, setSavingReview] = useState(false);
  const extractedFieldsRef = useRef<HTMLDivElement>(null);
  const reviewIssuesRef = useRef<HTMLDivElement>(null);
  const executionNotesRef = useRef<HTMLDivElement>(null);
  const fieldRowRefs = useRef<Record<string, HTMLTableRowElement | null>>({});
  const issueCardRefs = useRef<Record<string, HTMLDivElement | null>>({});

  useEffect(() => {
    let active = true;
    setLoading(true);
    idpoApi
      .getJobDocument(jobId, docId, {
        mode: mode === "strict" ? "strict" : mode === "adaptive" ? "adaptive" : undefined,
        runId: runId ?? undefined,
      })
      .then((response) => {
        if (!active) {
          return;
        }
        setPayload(response);
        setError("");
      })
      .catch((err) => {
        if (!active) {
          return;
        }
        setError(err instanceof Error ? err.message : "Failed to load document detail");
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [jobId, docId, mode, runId]);

  useEffect(() => {
    const suggestedRows = suggestedReviewRowsFromDocumentPayload(payload).map((row) => ({
      ...row,
      reviewState: row.reviewState as ReviewState,
    }));
    setReviewRows(suggestedRows);
  }, [payload]);

  const fieldEntries = useMemo(() => {
    const fieldValues =
      payload?.fieldValues && typeof payload.fieldValues === "object" && !Array.isArray(payload.fieldValues)
        ? (payload.fieldValues as Record<string, unknown>)
        : {};
    return Object.entries(fieldValues);
  }, [payload]);

  const review = payload?.review && typeof payload.review === "object" ? (payload.review as Record<string, unknown>) : null;
  const support = (payload?.support ?? {}) as Record<string, unknown>;
  const ahmn = (support.ahmn ?? {}) as Record<string, unknown>;
  const xai = (support.xai ?? {}) as Record<string, unknown>;
  const hitl = (support.hitl ?? {}) as Record<string, unknown>;
  const detail = (payload?.detail ?? {}) as Record<string, unknown>;
  const llmDiagnostics = asRecord(detail.llmDiagnostics) ?? {};
  const detailedFields = (Array.isArray(detail.fields) ? detail.fields : []) as FieldExtraction[];
  const metadata = (detail.metadata ?? {}) as Record<string, unknown>;
  const validationIssues = Array.isArray(detail.validationIssues) ? detail.validationIssues : [];
  const escalation = (detail.escalation ?? {}) as Record<string, unknown>;
  const fileName = typeof payload?.fileName === "string" ? payload.fileName : null;
  const previewKind = detectPreviewKind(fileName);
  const previewUrl = `/api/jobs/${encodeURIComponent(jobId)}/docs/${encodeURIComponent(docId)}/content`;
  const downloadUrl = `${previewUrl}?download=1`;
  const selectedPolicyId =
    typeof payload?.latestPolicy === "string" && payload.latestPolicy.trim()
      ? payload.latestPolicy.trim()
      : typeof metadata.policyId === "string" && metadata.policyId.trim()
        ? metadata.policyId.trim()
        : "";
  const policyHref = selectedPolicyId
    ? `/dashboard/idpo/jobs/${encodeURIComponent(jobId)}/policies/${encodeURIComponent(selectedPolicyId)}`
    : null;
  const preprocessRoute = asStringArray(metadata.preprocessRoute);
  const staticPolicyId = typeof metadata.staticPolicyId === "string" && metadata.staticPolicyId.trim() ? metadata.staticPolicyId.trim() : null;
  const policyChanged = metadata.policyChanged === true;
  const escalationTarget = typeof escalation.targetModel === "string" && escalation.targetModel.trim() ? escalation.targetModel.trim() : null;
  const escalationReason = typeof escalation.reason === "string" && escalation.reason.trim() ? escalation.reason.trim() : null;
  const provenanceEvents = (Array.isArray(detail.provenanceEvents) ? detail.provenanceEvents : []) as ProvenanceEvent[];
  const orderedEvents = [...provenanceEvents].sort((left, right) => {
    const leftTs = normalizeEventTimestamp(left.timestamp) ?? 0;
    const rightTs = normalizeEventTimestamp(right.timestamp) ?? 0;
    return leftTs - rightTs;
  });
  const selectedEvent = orderedEvents.find((event) => event.eventId === selectedEventId) ?? null;
  const selectedFieldKeys = selectedEvent ? collectRelevantFieldKeys(selectedEvent) : [];
  const selectedIssueFields = selectedEvent ? collectRelevantIssueFields(selectedEvent) : [];
  const selectedEventFacts = selectedEvent ? collectEventFacts(selectedEvent) : [];
  const fieldDetailByKey = useMemo(
    () =>
      new Map(
        detailedFields
          .filter((field) => typeof field.key === "string" && field.key.trim())
          .map((field) => [normalizeFieldKey(field.key), field] as const),
      ),
    [detailedFields],
  );
  const pathStages = orderedEvents.reduce<Array<{ key: string; label: string }>>((stages, event) => {
    const key = `${event.stage}:${event.eventType}`;
    if (!stages.some((entry) => entry.key === key)) {
      stages.push({
        key,
        label: `${titleCase(event.stage)}: ${titleCase(event.eventType)}`,
      });
    }
    return stages;
  }, []);
  const visibleFieldEntries = useMemo(() => {
    if (!selectedEvent || getEvidenceTarget(selectedEvent) !== "fields" || selectedFieldKeys.length === 0) {
      return fieldEntries;
    }
    return fieldEntries.filter(([key]) => selectedFieldKeys.includes(normalizeFieldKey(key)));
  }, [fieldEntries, selectedEvent, selectedFieldKeys]);
  const visibleFieldRows = useMemo(
    () =>
      visibleFieldEntries.map(([key, value]) => ({
        key,
        value,
        detail: fieldDetailByKey.get(normalizeFieldKey(key)) ?? null,
      })),
    [fieldDetailByKey, visibleFieldEntries],
  );

  const visibleValidationIssues = useMemo(() => {
    if (!selectedEvent || getEvidenceTarget(selectedEvent) !== "review" || selectedIssueFields.length === 0) {
      return validationIssues;
    }
    return validationIssues.filter((issue) => {
      const entry = asRecord(issue);
      const field = typeof entry?.field === "string" ? entry.field : "";
      return field ? selectedIssueFields.includes(normalizeFieldKey(field)) : false;
    });
  }, [selectedEvent, selectedIssueFields, validationIssues]);

  const localCall = asRecord(llmDiagnostics.local_call);
  const cloudCalls = asRecordArray(llmDiagnostics.cloud_calls);
  const cloudUsage = asRecord(llmDiagnostics.cloud_usage) ?? {};
  const fallbackKeys = asStringArray(llmDiagnostics.fallback_keys);
  const llmCallSections = [
    ...(localCall ? [{ title: "Local attempt", value: localCall }] : []),
    ...cloudCalls.map((call, index) => ({
      title:
        typeof llmDiagnostics.flagship_model === "string" &&
        llmDiagnostics.flagship_model === call.model
          ? "Flagship retry"
          : index === 0
            ? "Cloud attempt"
            : `Cloud retry ${index + 1}`,
      value: call,
    })),
  ];
  const finalExtraction = deriveFinalExtractionSummary(detailedFields, metadata, llmDiagnostics);
  const fallbackSummary = deriveFallbackSummary(llmDiagnostics, fallbackKeys, finalExtraction);
  const reviewSource = typeof review?.reviewSource === "string" ? review.reviewSource : null;
  const reviewIsAi = reviewSource === "ai";
  const outcomeRecord = asRecord(payload?.outcome);
  const benchmarkBackedReview = !review && Boolean(payload?.expectedFieldValues);
  const reviewMetrics = (review?.metrics as Record<string, unknown> | undefined) ?? null;
  const displayedPrecision = reviewMetrics?.precision ?? outcomeRecord?.exactPrecision ?? null;
  const displayedRecall = reviewMetrics?.recall ?? outcomeRecord?.exactRecall ?? null;
  const displayedF1 = reviewMetrics?.f1 ?? outcomeRecord?.exactF1 ?? null;
  const reviewSourceLabel =
    reviewIsAi
      ? `auto review${typeof review?.reviewerConfidence === "number" ? ` / ${formatPercentValue(review.reviewerConfidence)}` : ""}`
      : reviewSource === "human"
        ? "human review"
        : benchmarkBackedReview
          ? "benchmark label"
        : "-";

  useEffect(() => {
    if (!focusedSection) {
      return undefined;
    }
    const timer = window.setTimeout(() => setFocusedSection(null), 2200);
    return () => window.clearTimeout(timer);
  }, [focusedSection]);

  useEffect(() => {
    if (!focusedFieldKey) {
      return undefined;
    }
    const timer = window.setTimeout(() => setFocusedFieldKey(null), 2200);
    return () => window.clearTimeout(timer);
  }, [focusedFieldKey]);

  useEffect(() => {
    if (!focusedIssueField) {
      return undefined;
    }
    const timer = window.setTimeout(() => setFocusedIssueField(null), 2200);
    return () => window.clearTimeout(timer);
  }, [focusedIssueField]);

  function focusEvidenceSection(event: ProvenanceEvent) {
    const target = getEvidenceTarget(event);
    setSelectedEventId(event.eventId);
    setFocusedSection(target);
    setFocusedFieldKey(null);
    setFocusedIssueField(null);
    if (target) {
      setInspectorTab(target);
    }

    if (target === "fields") {
      extractedFieldsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    if (target === "review") {
      reviewIssuesRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    if (target === "notes") {
      executionNotesRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  function clearEventFocus() {
    setSelectedEventId(null);
    setFocusedSection(null);
    setFocusedFieldKey(null);
    setFocusedIssueField(null);
  }

  function openExactField(fieldKey: string) {
    setInspectorTab("fields");
    setFocusedSection("fields");
    setFocusedFieldKey(fieldKey);
    setFocusedIssueField(null);
    window.requestAnimationFrame(() => {
      const target = fieldRowRefs.current[fieldKey];
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "center" });
      } else {
        extractedFieldsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  }

  function openExactIssue(fieldKey: string) {
    setInspectorTab("review");
    setFocusedSection("review");
    setFocusedIssueField(fieldKey);
    setFocusedFieldKey(null);
    window.requestAnimationFrame(() => {
      const target = issueCardRefs.current[fieldKey];
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "center" });
      } else {
        reviewIssuesRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  }

  async function reloadDocument() {
    const response = await idpoApi.getJobDocument(jobId, docId, {
      mode: mode === "strict" ? "strict" : mode === "adaptive" ? "adaptive" : undefined,
      runId: runId ?? undefined,
    });
    setPayload(response);
  }

  async function handleAiValidate() {
    setSavingReview(true);
    try {
      await idpoApi.validateJobDocuments(jobId, {
        selectedFileIds: [docId],
        mode: mode === "strict" ? "strict" : "adaptive",
      });
      await reloadDocument();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to auto review document");
    } finally {
      setSavingReview(false);
    }
  }

  async function handleSaveReview() {
    const activeRunId = payload && typeof payload.latestRunId === "string" ? payload.latestRunId : runId;
    if (!activeRunId) {
      setError("No run id available for review save.");
      return;
    }
    setSavingReview(true);
    try {
      const response = await idpoApi.saveJobDocumentReview(jobId, docId, {
        runId: activeRunId,
        mode: mode === "strict" ? "strict" : "adaptive",
        fields: reviewRows.map((row) => ({
          fieldKey: row.fieldKey,
          fieldLabel: row.fieldLabel,
          extractedValue: row.extractedValue,
          correctedValue: row.correctedValue || null,
          reviewState: row.reviewState,
          reviewNote: row.reviewNote || null,
        })),
      });
      const nextPayload = mergeSavedReviewIntoDocumentPayload(payload, response.review);
      setPayload(nextPayload);
      const savedRows = suggestedReviewRowsFromDocumentPayload(nextPayload).map((row) => ({
        ...row,
        reviewState: row.reviewState as ReviewState,
      }));
      if (savedRows.length > 0) {
        setReviewRows(savedRows);
      }
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save review");
    } finally {
      setSavingReview(false);
    }
  }

  if (loading) {
    return <div className="text-sm text-slate-600 dark:text-slate-300">Loading document detail...</div>;
  }

  if (!payload) {
    return (
      <div className="rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300">
        {error || "Document not found"}
      </div>
    );
  }

  const originalDocumentCard = (
    <IdpoCard>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold text-slate-900 dark:text-white">Original document</h2>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
            Validate the extraction against the actual source document, not just the output table.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <a
            href={previewUrl}
            target="_blank"
            rel="noreferrer"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            Open original
          </a>
          <a
            href={downloadUrl}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            Download
          </a>
        </div>
      </div>

      <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950/40">
        {previewKind === "pdf" ? (
          <iframe
            key={previewUrl}
            src={previewUrl}
            title={fileName ?? "Original document"}
            className="h-[900px] w-full bg-white dark:bg-slate-950"
          />
        ) : null}
        {previewKind === "image" ? (
          <div className="flex justify-center bg-slate-100 p-4 dark:bg-slate-950">
            <img
              src={previewUrl}
              alt={fileName ?? "Original document"}
              className="max-h-[900px] w-auto max-w-full rounded-lg object-contain"
            />
          </div>
        ) : null}
        {previewKind === "text" ? (
          <iframe
            key={previewUrl}
            src={previewUrl}
            title={fileName ?? "Original document"}
            className="h-[560px] w-full bg-white dark:bg-slate-950"
          />
        ) : null}
        {previewKind === "unsupported" ? (
          <div className="p-6 text-sm text-slate-600 dark:text-slate-300">
            Inline preview is not supported for this file type yet. Use <span className="font-medium text-slate-900 dark:text-white">Open original</span> or <span className="font-medium text-slate-900 dark:text-white">Download</span>.
          </div>
        ) : null}
      </div>
    </IdpoCard>
  );

  const extractedFieldsCard = (
    <div ref={extractedFieldsRef}>
      <IdpoCard className={focusedSection === "fields" ? "ring-2 ring-cyan-500/70 ring-offset-2 ring-offset-white dark:ring-offset-slate-950" : ""}>
        <h2 className="text-base font-semibold text-slate-900 dark:text-white">Extracted fields</h2>
        {selectedEvent && getEvidenceTarget(selectedEvent) === "fields" ? (
          <div className="mt-3 rounded-xl border border-cyan-200 bg-cyan-50 px-3 py-2 text-sm text-cyan-900 dark:border-cyan-800/50 dark:bg-cyan-950/30 dark:text-cyan-100">
            Focused by {titleCase(selectedEvent.eventType)} at {formatEventTime(selectedEvent.timestamp)}.
            {selectedFieldKeys.length > 0 ? ` Showing ${visibleFieldEntries.length} relevant field(s).` : ""}
            <button
              type="button"
              onClick={clearEventFocus}
              className="ml-2 underline underline-offset-2"
            >
              Clear
            </button>
          </div>
        ) : null}
        <div className="mt-3 overflow-x-auto">
          {(() => {
            const expectedMap =
              payload?.expectedFieldValues &&
              typeof payload.expectedFieldValues === "object" &&
              !Array.isArray(payload.expectedFieldValues)
                ? (payload.expectedFieldValues as Record<string, string>)
                : null;
            const sourceMap =
              payload?.expectedFieldSource &&
              typeof payload.expectedFieldSource === "object" &&
              !Array.isArray(payload.expectedFieldSource)
                ? (payload.expectedFieldSource as Record<string, string>)
                : null;
            const hasExpected = expectedMap !== null && Object.keys(expectedMap).length > 0;
            return (
              <table className="w-full min-w-[720px] text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                    <th className="px-2 py-2">Field</th>
                    <th className="px-2 py-2">Extracted</th>
                    {hasExpected ? <th className="px-2 py-2">Expected</th> : null}
                    {hasExpected ? <th className="px-2 py-2">Match</th> : null}
                  </tr>
                </thead>
                <tbody>
                  {visibleFieldRows.map(({ key, value, detail }) => {
                    const normKey = normalizeFieldKey(key);
                    const expectedRaw = hasExpected ? (expectedMap?.[key] ?? expectedMap?.[normKey] ?? null) : null;
                    const src = expectedRaw !== null ? (sourceMap?.[key] ?? sourceMap?.[normKey] ?? null) : null;
                    const extractedStr = typeof value === "string" ? value.trim() : formatValue(value);
                    const matched = expectedRaw !== null && expectedValueMatches(key, extractedStr, expectedRaw);
                    return (
                      <tr
                        key={key}
                        ref={(node) => {
                          fieldRowRefs.current[normKey] = node;
                        }}
                        className={`border-b border-slate-100 transition dark:border-slate-800 ${
                          focusedFieldKey === normKey ? "bg-cyan-50 dark:bg-cyan-950/20" : ""
                        }`}
                      >
                        <td className="px-2 py-2 font-medium text-slate-900 dark:text-slate-100">{key}</td>
                        <td className="px-2 py-2 text-slate-700 dark:text-slate-200">
                          <div>{formatValue(value)}</div>
                          {collectFieldEvidenceFacts(detail).length > 0 ? (
                            <div className="mt-1 flex flex-wrap gap-1">
                              {collectFieldEvidenceFacts(detail).map((fact) => (
                                <span
                                  key={`${key}_${fact}`}
                                  className="rounded-full border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] text-slate-600 dark:border-slate-700 dark:bg-slate-950/40 dark:text-slate-300"
                                >
                                  {fact}
                                </span>
                              ))}
                            </div>
                          ) : null}
                        </td>
                        {hasExpected ? (
                          <td className="px-2 py-2 text-slate-600 dark:text-slate-300">
                            {expectedRaw ?? <span className="text-slate-400">—</span>}
                            {src ? (
                              <span className={`ml-2 rounded-full px-1.5 py-0.5 text-[10px] font-medium ${src === "review" ? "bg-violet-100 text-violet-700 dark:bg-violet-900/30 dark:text-violet-300" : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"}`}>
                                {src}
                              </span>
                            ) : null}
                          </td>
                        ) : null}
                        {hasExpected ? (
                          <td className="px-2 py-2">
                            {expectedRaw !== null ? (
                              <span
                                className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${
                                  matched
                                    ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300"
                                    : "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300"
                                }`}
                              >
                                {matched ? "match" : "miss"}
                              </span>
                            ) : (
                              <span className="text-slate-400">—</span>
                            )}
                          </td>
                        ) : null}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            );
          })()}

          {visibleFieldEntries.length === 0 ? (
            selectedEvent && getEvidenceTarget(selectedEvent) === "fields" ? (
              <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">No field-specific evidence could be isolated for this event.</p>
            ) : null
          ) : null}
          {fieldEntries.length === 0 ? (
            <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">No extracted fields available for this document yet.</p>
          ) : null}
        </div>
      </IdpoCard>
    </div>
  );

  const logSection = (
    <div className="space-y-4">
      <IdpoCard>
        <h2 className="text-base font-semibold text-slate-900 dark:text-white">Document path</h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          The exact path this document followed through the pipeline, in order.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          {pathStages.length > 0 ? (
            pathStages.map((stage, index) => (
              <div key={stage.key} className="flex items-center gap-2">
                <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700 dark:border-slate-700 dark:bg-slate-950/40 dark:text-slate-200">
                  {stage.label}
                </span>
                {index < pathStages.length - 1 ? <span className="text-slate-400 dark:text-slate-500">-&gt;</span> : null}
              </div>
            ))
          ) : (
            <p className="text-sm text-slate-500 dark:text-slate-400">No document path events available yet.</p>
          )}
        </div>
      </IdpoCard>

      <IdpoCard>
        <h2 className="text-base font-semibold text-slate-900 dark:text-white">Document log</h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          Queue-item style timeline for this document. Keep it operational and readable.
        </p>
        {selectedEvent ? (
          <div className="mt-4 rounded-2xl border border-cyan-200 bg-cyan-50/70 p-4 text-sm text-cyan-950 dark:border-cyan-800/50 dark:bg-cyan-950/30 dark:text-cyan-50">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-wide text-cyan-700 dark:text-cyan-200">Selected event</p>
                <h3 className="mt-1 text-sm font-semibold text-cyan-950 dark:text-white">
                  {titleCase(selectedEvent.eventType)}
                </h3>
                <p className="mt-1 text-sm text-cyan-900 dark:text-cyan-100">
                  {summarizeProvenanceEvent(selectedEvent)}
                </p>
              </div>
              <div className="text-xs text-cyan-800 dark:text-cyan-200">
                <div>{titleCase(selectedEvent.stage)}</div>
                <div>{formatEventTime(selectedEvent.timestamp)}</div>
              </div>
            </div>
            <div className="mt-3 flex flex-wrap gap-2 text-xs">
              <button
                type="button"
                onClick={() => focusEvidenceSection(selectedEvent)}
                className="rounded-full border border-cyan-300 px-3 py-1 font-medium text-cyan-900 hover:bg-cyan-100 dark:border-cyan-700 dark:text-cyan-100 dark:hover:bg-cyan-900/40"
              >
                Open focused section
              </button>
              {selectedFieldKeys.map((fieldKey) => (
                <button
                  key={`field_${fieldKey}`}
                  type="button"
                  onClick={() => openExactField(fieldKey)}
                  className="rounded-full border border-cyan-300 px-3 py-1 font-medium text-cyan-900 hover:bg-cyan-100 dark:border-cyan-700 dark:text-cyan-100 dark:hover:bg-cyan-900/40"
                >
                  Open field: {titleCase(fieldKey)}
                </button>
              ))}
              {selectedIssueFields.map((fieldKey) => (
                <button
                  key={`issue_${fieldKey}`}
                  type="button"
                  onClick={() => openExactIssue(fieldKey)}
                  className="rounded-full border border-cyan-300 px-3 py-1 font-medium text-cyan-900 hover:bg-cyan-100 dark:border-cyan-700 dark:text-cyan-100 dark:hover:bg-cyan-900/40"
                >
                  Open issue: {titleCase(fieldKey)}
                </button>
              ))}
              <button
                type="button"
                onClick={clearEventFocus}
                className="rounded-full border border-cyan-300 px-3 py-1 font-medium text-cyan-900 hover:bg-cyan-100 dark:border-cyan-700 dark:text-cyan-100 dark:hover:bg-cyan-900/40"
              >
                Clear
              </button>
            </div>
            {selectedEventFacts.length > 0 ? (
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                {selectedEventFacts.map((fact) => (
                  <div
                    key={`${fact.label}_${fact.value}`}
                    className="rounded-xl border border-cyan-200/80 bg-white/60 px-3 py-2 dark:border-cyan-800/40 dark:bg-slate-950/30"
                  >
                    <p className="text-[11px] uppercase tracking-wide text-cyan-700 dark:text-cyan-300">{fact.label}</p>
                    <p className="mt-1 text-sm font-medium text-cyan-950 dark:text-white">{fact.value}</p>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[980px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                <th className="px-2 py-2">Time</th>
                <th className="px-2 py-2">Stage</th>
                <th className="px-2 py-2">Action</th>
                <th className="px-2 py-2">Agent</th>
                <th className="px-2 py-2">Latency</th>
                <th className="px-2 py-2">Details</th>
              </tr>
            </thead>
            <tbody>
              {orderedEvents.map((event) => (
                <tr
                  key={event.eventId}
                  role="button"
                  tabIndex={0}
                  onClick={() => focusEvidenceSection(event)}
                  onKeyDown={(keyboardEvent) => {
                    if (keyboardEvent.key === "Enter" || keyboardEvent.key === " ") {
                      keyboardEvent.preventDefault();
                      focusEvidenceSection(event);
                    }
                  }}
                  className={`border-b border-slate-100 transition hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-900/60 ${
                    selectedEventId === event.eventId ? "bg-cyan-50 dark:bg-cyan-950/20" : ""
                  }`}
                >
                  <td className="px-2 py-2 whitespace-nowrap text-slate-600 dark:text-slate-300">
                    {formatEventTime(event.timestamp)}
                  </td>
                  <td className="px-2 py-2 text-slate-700 dark:text-slate-200">{titleCase(event.stage)}</td>
                  <td className="px-2 py-2 font-medium text-slate-900 dark:text-slate-100">
                    {titleCase(event.eventType)}
                  </td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{event.agent}</td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">
                    {typeof event.latencyMs === "number" ? `${Math.round(event.latencyMs)} ms` : "-"}
                  </td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">
                    <div>{summarizeProvenanceEvent(event)}</div>
                    {getEvidenceTarget(event) ? (
                      <div className="mt-1 text-xs font-medium text-cyan-700 dark:text-cyan-300">
                        Focus evidence
                      </div>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {orderedEvents.length === 0 ? (
            <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">No document log events available yet.</p>
          ) : null}
        </div>
      </IdpoCard>
    </div>
  );

  const reviewSection = (
    <div ref={reviewIssuesRef}>
      <IdpoCard className={focusedSection === "review" ? "ring-2 ring-cyan-500/70 ring-offset-2 ring-offset-white dark:ring-offset-slate-950" : ""}>
        <h2 className="text-base font-semibold text-slate-900 dark:text-white">Review issues</h2>
        {selectedEvent && getEvidenceTarget(selectedEvent) === "review" ? (
          <div className="mt-3 rounded-xl border border-cyan-200 bg-cyan-50 px-3 py-2 text-sm text-cyan-900 dark:border-cyan-800/50 dark:bg-cyan-950/30 dark:text-cyan-100">
            Focused by {titleCase(selectedEvent.eventType)} at {formatEventTime(selectedEvent.timestamp)}.
            {selectedIssueFields.length > 0 ? ` Showing ${visibleValidationIssues.length} relevant issue(s).` : ""}
            <button
              type="button"
              onClick={clearEventFocus}
              className="ml-2 underline underline-offset-2"
            >
              Clear
            </button>
          </div>
        ) : null}
        <div className="mt-3 space-y-2 text-sm text-slate-600 dark:text-slate-300">
          {visibleValidationIssues.length > 0 ? (
            visibleValidationIssues.map((issue, index) => {
              const entry = issue as Record<string, unknown>;
              const normalizedField = normalizeFieldKey(String(entry.field ?? ""));
              return (
                <div
                  key={`${String(entry.field)}_${index}`}
                  ref={(node) => {
                    if (normalizedField) {
                      issueCardRefs.current[normalizedField] = node;
                    }
                  }}
                  className={`rounded-lg border p-3 transition dark:border-slate-700 ${
                    focusedIssueField === normalizedField
                      ? "border-cyan-300 bg-cyan-50 dark:border-cyan-700/60 dark:bg-cyan-950/20"
                      : "border-slate-200"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-medium text-slate-900 dark:text-white">{String(entry.field ?? "-")}</p>
                    <StatusBadge value={String(entry.severity ?? "unknown")} />
                  </div>
                  <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">{String(entry.issue ?? "-")}</p>
                </div>
              );
            })
          ) : (
            <p>
              {selectedEvent && getEvidenceTarget(selectedEvent) === "review" && selectedIssueFields.length > 0
                ? "No matching review issues for this focused event."
                : "No review issues recorded."}
            </p>
          )}
        </div>
      </IdpoCard>
    </div>
  );

  const notesSection = (
    <div className="space-y-4">
      <div ref={executionNotesRef}>
        <IdpoCard className={focusedSection === "notes" ? "ring-2 ring-cyan-500/70 ring-offset-2 ring-offset-white dark:ring-offset-slate-950" : ""}>
          <h2 className="text-base font-semibold text-slate-900 dark:text-white">Execution notes</h2>
          {selectedEvent && getEvidenceTarget(selectedEvent) === "notes" ? (
            <div className="mt-3 rounded-xl border border-cyan-200 bg-cyan-50 px-3 py-2 text-sm text-cyan-900 dark:border-cyan-800/50 dark:bg-cyan-950/30 dark:text-cyan-100">
              Focused by {titleCase(selectedEvent.eventType)} at {formatEventTime(selectedEvent.timestamp)}.
              <button
                type="button"
                onClick={clearEventFocus}
                className="ml-2 underline underline-offset-2"
              >
                Clear
              </button>
            </div>
          ) : null}
          <div className="mt-3 space-y-2 text-sm text-slate-600 dark:text-slate-300">
            <p>
              Doc type:
              <span className="ml-1 font-medium text-slate-900 dark:text-white">{formatValue(metadata.docType)}</span>
            </p>
            <p>
              Advice source:
              <span className="ml-1 font-medium text-slate-900 dark:text-white">{formatValue(metadata.adviceSource)}</span>
            </p>
            <p>
              Escalated:
              <span className="ml-1 font-medium text-slate-900 dark:text-white">
                {Boolean(escalation.escalated) ? "yes" : "no"}
              </span>
            </p>
            <p>
              Escalation reason:
              <span className="ml-1 font-medium text-slate-900 dark:text-white">{formatValue(escalation.reason)}</span>
            </p>
          </div>
        </IdpoCard>
      </div>

      <IdpoCard>
        <h2 className="text-base font-semibold text-slate-900 dark:text-white">Support signals</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 text-sm text-slate-600 dark:text-slate-300">
          <p>
            AHMN advice influenced:
            <span className="ml-1 font-medium text-slate-900 dark:text-white">
              {Boolean(ahmn.adviceInfluenced) ? "yes" : "no"}
            </span>
          </p>
          <p>
            AHMN feedback logged:
            <span className="ml-1 font-medium text-slate-900 dark:text-white">
              {Boolean(ahmn.feedbackLogged) ? "yes" : "no"}
            </span>
          </p>
          <p>
            Reviewed learning:
            <span className="ml-1 font-medium text-slate-900 dark:text-white">
              {Boolean(ahmn.reviewedFeedbackLogged) ? "logged to AHMN" : formatValue(ahmn.reviewedFeedbackError ?? "pending")}
            </span>
          </p>
          <p>
            HITL review state:
            <span className="ml-1 font-medium text-slate-900 dark:text-white">{formatValue(hitl.reviewState)}</span>
          </p>
          <p>
            HITL review source:
            <span className="ml-1 font-medium text-slate-900 dark:text-white">{formatValue(hitl.reviewSource)}</span>
          </p>
          <p>
            XAI availability:
            <span className="ml-1 font-medium text-slate-900 dark:text-white">{formatValue(xai.mode ?? xai.available)}</span>
          </p>
        </div>
      </IdpoCard>
    </div>
  );

  const llmSection = (
    <div className="space-y-4">
      <IdpoCard>
        <h2 className="text-base font-semibold text-slate-900 dark:text-white">LLM extraction</h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          Simple audit view for what the extraction model did, whether it fell back, and the exact prompt/response when
          persisted.
        </p>
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">{finalExtraction.summary}</p>
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-950/40">
            <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Routing</div>
            <div className="mt-1 font-medium text-slate-900 dark:text-white">{formatAuditValue(llmDiagnostics.strategy)}</div>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-950/40">
            <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Planned mode</div>
            <div className="mt-1 font-medium text-slate-900 dark:text-white">{formatAuditValue(llmDiagnostics.requested_mode)}</div>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-950/40">
            <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Retried fields</div>
            <div className="mt-1 font-medium text-slate-900 dark:text-white">
              {fallbackKeys.length > 0 ? fallbackKeys.join(", ") : "none"}
            </div>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-950/40">
            <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Local attempt</div>
            <div className="mt-1 font-medium text-slate-900 dark:text-white">
              {llmDiagnostics.local_attempted === true
                ? llmDiagnostics.local_succeeded === true
                  ? "succeeded"
                  : `failed${typeof llmDiagnostics.local_failure_reason === "string" ? ` - ${llmDiagnostics.local_failure_reason}` : ""}`
                : "not used"}
            </div>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-950/40">
            <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Cloud attempt</div>
            <div className="mt-1 font-medium text-slate-900 dark:text-white">
              {llmDiagnostics.cloud_attempted === true
                ? llmDiagnostics.cloud_succeeded === true
                  ? "succeeded"
                  : `failed${typeof llmDiagnostics.cloud_failure_reason === "string" ? ` - ${llmDiagnostics.cloud_failure_reason}` : ""}`
                : "not used"}
            </div>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-950/40">
            <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Cloud usage</div>
            <div className="mt-1 font-medium text-slate-900 dark:text-white">
              {typeof cloudUsage.total_tokens === "number" && cloudUsage.total_tokens > 0
                ? `${formatAuditValue(cloudUsage.total_tokens)} tokens`
                : "none"}
            </div>
            {typeof cloudUsage.estimated_cost_usd === "number" && cloudUsage.estimated_cost_usd > 0 ? (
              <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                ${cloudUsage.estimated_cost_usd.toFixed(4)}
              </div>
            ) : null}
          </div>
        </div>
      </IdpoCard>

      {llmCallSections.length === 0 ? (
        <IdpoCard>
          <p className="text-sm text-slate-600 dark:text-slate-300">
            No LLM extraction call was recorded for this document. This usually means extraction stayed on rules and
            heuristics, or no diagnostics were persisted for this run.
          </p>
        </IdpoCard>
      ) : (
        llmCallSections.map((section) => {
          const call = section.value;
          const rawPrompt = typeof call.raw_prompt === "string" ? call.raw_prompt.trim() : "";
          const rawResponse =
            typeof call.raw_response === "string"
              ? call.raw_response.trim()
              : typeof call.raw_response_preview === "string"
                ? call.raw_response_preview.trim()
                : "";
          const facts = collectAuditFacts(call);

          return (
            <IdpoCard key={section.title}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-slate-900 dark:text-white">{section.title}</h3>
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                    {formatAuditValue(call.model)} / {formatAuditValue(call.provider)}
                  </p>
                </div>
                {typeof call.success === "boolean" ? (
                  <StatusBadge value={call.success ? "succeeded" : "failed"} />
                ) : null}
              </div>

              {facts.length > 0 ? (
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  {facts.map((fact) => (
                    <div
                      key={`${section.title}_${fact.label}`}
                      className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-950/40"
                    >
                      <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{fact.label}</div>
                      <div className="mt-1 font-medium text-slate-900 dark:text-white">{fact.value}</div>
                    </div>
                  ))}
                </div>
              ) : null}

              {rawPrompt ? (
                <details className="mt-4 rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 dark:border-slate-800 dark:bg-slate-950/40">
                  <summary className="cursor-pointer text-sm font-medium text-slate-900 dark:text-white">Prompt</summary>
                  <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-700 dark:text-slate-200">
                    {rawPrompt}
                  </pre>
                </details>
              ) : null}

              {rawResponse ? (
                <details className="mt-4 rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 dark:border-slate-800 dark:bg-slate-950/40">
                  <summary className="cursor-pointer text-sm font-medium text-slate-900 dark:text-white">
                    Response
                    {typeof call.raw_response_preview === "string" && !("raw_response" in call) ? " preview" : ""}
                  </summary>
                  <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-700 dark:text-slate-200">
                    {rawResponse}
                  </pre>
                </details>
              ) : null}
            </IdpoCard>
          );
        })
      )}
    </div>
  );

  const inspectorSections: Record<InspectorTab, ReactNode> = {
    fields: extractedFieldsCard,
    review: reviewSection,
    notes: notesSection,
    log: logSection,
    llm: llmSection,
  };

  const inspectorPanel = (
    <div className="space-y-4 xl:sticky xl:top-6">
      <IdpoCard>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-slate-900 dark:text-white">Inspector</h2>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              Switch between extracted evidence, review findings, execution notes, the document log, and the LLM audit.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {[
              ["fields", "Fields"],
              ["review", "Review"],
              ["notes", "Notes"],
              ["log", "Log"],
              ["llm", "LLM"],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => setInspectorTab(value as InspectorTab)}
                className={`rounded-lg px-3 py-2 text-sm font-medium ${
                  inspectorTab === value
                    ? "bg-cyan-600 text-white"
                    : "border border-slate-300 text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </IdpoCard>

      {inspectorSections[inspectorTab]}
    </div>
  );

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <Link
          href={`/dashboard/idpo/jobs/${encodeURIComponent(jobId)}`}
          className="text-xs text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
        >
          Back to job
        </Link>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold text-slate-900 dark:text-white">
            {String(payload.fileName ?? payload.fileId ?? docId)}
          </h1>
          <StatusBadge value={String(payload.status ?? "unknown")} />
        </div>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
          Atomic document view. Extraction result first, then review state, route, fallback, and compact AHMN/XAI/HITL
          support signals.
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setLayoutMode("split")}
            className={`rounded-lg px-3 py-2 text-sm font-medium ${
              layoutMode === "split"
                ? "bg-cyan-600 text-white"
                : "border border-slate-300 text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
            }`}
          >
            Side by side
          </button>
          <button
            type="button"
            onClick={() => setLayoutMode("stacked")}
            className={`rounded-lg px-3 py-2 text-sm font-medium ${
              layoutMode === "stacked"
                ? "bg-cyan-600 text-white"
                : "border border-slate-300 text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
            }`}
          >
            Stacked
          </button>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Route</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{formatValue(payload.latestRoute)}</p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Policy</p>
          {policyHref ? (
            <Link href={policyHref} className="mt-2 inline-block text-sm font-semibold text-cyan-700 hover:text-cyan-800 dark:text-cyan-300 dark:hover:text-cyan-200">
              {selectedPolicyId}
            </Link>
          ) : (
            <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{formatValue(payload.latestPolicy)}</p>
          )}
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Review</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">
            {formatValue((review as Record<string, unknown> | null)?.reviewStatus ?? payload.reviewState)}
          </p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Final source</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{finalExtraction.finalModel}</p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{finalExtraction.finalSource}</p>
        </IdpoCard>
      </section>

      <IdpoCard>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-slate-900 dark:text-white">Execution path</h2>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              Planned route and final extraction outcome, without mixing them together.
            </p>
          </div>
          {policyHref ? (
            <Link
              href={policyHref}
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              Open policy
            </Link>
          ) : null}
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-sm dark:border-slate-800 dark:bg-slate-950/40">
            <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Policy decision</div>
            <div className="mt-2 font-medium text-slate-900 dark:text-white">{selectedPolicyId || "No policy recorded"}</div>
            <div className="mt-2 space-y-1 text-slate-600 dark:text-slate-300">
              <p>Route bin: {formatValue(metadata.routeBin ?? payload.latestRoute)}</p>
              <p>Advice: {formatValue(metadata.adviceStatus)}</p>
              <p>
                Baseline:{" "}
                {staticPolicyId
                  ? policyChanged
                    ? `${staticPolicyId} -> changed`
                    : staticPolicyId
                  : "none"}
              </p>
            </div>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-sm dark:border-slate-800 dark:bg-slate-950/40">
            <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">OCR and preprocessing</div>
            <div className="mt-2 font-medium text-slate-900 dark:text-white">
              {preprocessRoute.length > 0 ? preprocessRoute.join(" -> ") : "No extra preprocessing recorded"}
            </div>
            <div className="mt-2 space-y-1 text-slate-600 dark:text-slate-300">
              <p>OCR engine: {formatValue(metadata.ocrEngineUsed)}</p>
              <p>OCR confidence: {formatPercentValue(metadata.ocrAvgConfidence)}</p>
              <p>OCR rerun pages: {formatMetric(metadata.ocrRerunUsedPages)}</p>
            </div>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-sm dark:border-slate-800 dark:bg-slate-950/40">
            <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Extraction outcome</div>
            <div className="mt-2 font-medium text-slate-900 dark:text-white">
              {finalExtraction.finalModel}
            </div>
            <div className="mt-2 space-y-1 text-slate-600 dark:text-slate-300">
              <p>Planned route: {formatValue(metadata.modelUsed)} / {formatValue(metadata.modelMode)}</p>
              <p>Final source: {finalExtraction.finalSource}</p>
              <p>Unresolved fields: {formatMetric(metadata.unresolvedFieldCount)}</p>
            </div>
            <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">{finalExtraction.summary}</p>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3 text-sm dark:border-slate-800 dark:bg-slate-950/40">
            <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Fallback handling</div>
            <div className="mt-2 font-medium text-slate-900 dark:text-white">
              {fallbackSummary.title}
            </div>
            <div className="mt-2 space-y-1 text-slate-600 dark:text-slate-300">
              <p>Planned fallback path: {formatValue(metadata.fallbackPath)}</p>
              <p>Escalated: {formatValue(escalation.escalated)}</p>
              <p>Target model: {escalationTarget ?? "-"}</p>
            </div>
            <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
              {fallbackSummary.detail || escalationReason || formatValue(metadata.deferReason)}
            </p>
          </div>
        </div>
      </IdpoCard>

      <IdpoCard>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-slate-900 dark:text-white">Review</h2>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              {reviewIsAi
                ? "Auto review is provisional. Save human review when you want the document score to count as authoritative."
                : "Human review is authoritative for policy ranking. Auto review is only a prefill step."}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void handleAiValidate()}
              disabled={savingReview}
              className="rounded-lg border border-emerald-300 px-3 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-50 disabled:opacity-60 dark:border-emerald-700/40 dark:text-emerald-300 dark:hover:bg-emerald-900/20"
            >
              Run auto review
            </button>
            <button
              type="button"
              onClick={() => void handleSaveReview()}
              disabled={savingReview || reviewRows.length === 0}
              className="rounded-lg bg-cyan-600 px-3 py-2 text-sm font-medium text-white hover:bg-cyan-700 disabled:opacity-60"
            >
              Save review
            </button>
          </div>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-6">
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-950/40">
            <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Status</div>
            <div className="mt-1 font-medium text-slate-900 dark:text-white">
              {formatValue(review?.reviewStatus ?? payload.reviewState)}
            </div>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-950/40">
            <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Scored by</div>
            <div className="mt-1 font-medium text-slate-900 dark:text-white">
              {reviewSourceLabel}
            </div>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-950/40">
            <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
              {reviewIsAi ? "Precision (AI)" : "Precision"}
            </div>
            <div className="mt-1 font-medium text-slate-900 dark:text-white">
              {formatScoreValue(displayedPrecision)}
            </div>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-950/40">
            <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
              {reviewIsAi ? "Recall (AI)" : "Recall"}
            </div>
            <div className="mt-1 font-medium text-slate-900 dark:text-white">
              {formatScoreValue(displayedRecall)}
            </div>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-950/40">
            <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
              {reviewIsAi ? "F1 (AI)" : "F1"}
            </div>
            <div className="mt-1 font-medium text-slate-900 dark:text-white">
              {formatScoreValue(displayedF1)}
            </div>
          </div>
          <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-950/40">
            <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">AHMN learning</div>
            <div className="mt-1 font-medium text-slate-900 dark:text-white">
              {Boolean(ahmn.reviewedFeedbackLogged) ? "logged" : formatValue(ahmn.reviewedFeedbackError ?? "pending")}
            </div>
          </div>
        </div>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[920px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                <th className="px-2 py-2">Field</th>
                <th className="px-2 py-2">Extracted</th>
                <th className="px-2 py-2">Review state</th>
                <th className="px-2 py-2">Corrected value</th>
                <th className="px-2 py-2">Note</th>
              </tr>
            </thead>
            <tbody>
              {reviewRows.map((row, index) => (
                <tr key={`${row.fieldKey}-${index}`} className="border-b border-slate-100 dark:border-slate-800">
                  <td className="px-2 py-2 font-medium text-slate-900 dark:text-white">{row.fieldLabel}</td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{row.extractedValue}</td>
                  <td className="px-2 py-2">
                    <select
                      value={row.reviewState}
                      onChange={(event) =>
                        setReviewRows((current) =>
                          current.map((item, currentIndex) =>
                            currentIndex === index ? { ...item, reviewState: event.target.value as ReviewState } : item,
                          ),
                        )
                      }
                      className="w-full rounded-lg border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
                    >
                      <option value="correct">correct</option>
                      <option value="wrong_value">wrong_value</option>
                      <option value="missed_field">missed_field</option>
                      <option value="correctly_skipped">correctly_skipped</option>
                      <option value="hallucinated_field">hallucinated_field</option>
                    </select>
                  </td>
                  <td className="px-2 py-2">
                    <input
                      value={row.correctedValue}
                      onChange={(event) =>
                        setReviewRows((current) =>
                          current.map((item, currentIndex) =>
                            currentIndex === index ? { ...item, correctedValue: event.target.value } : item,
                          ),
                        )
                      }
                      className="w-full rounded-lg border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
                    />
                  </td>
                  <td className="px-2 py-2">
                    <input
                      value={row.reviewNote}
                      onChange={(event) =>
                        setReviewRows((current) =>
                          current.map((item, currentIndex) =>
                            currentIndex === index ? { ...item, reviewNote: event.target.value } : item,
                          ),
                        )
                      }
                      className="w-full rounded-lg border border-slate-300 px-2 py-1 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {reviewRows.length === 0 ? (
            <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">No requested fields available for review.</p>
          ) : null}
        </div>
      </IdpoCard>

      {layoutMode === "split" ? (
        <section className="grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(360px,0.95fr)]">
          <div>{originalDocumentCard}</div>
          <div>{inspectorPanel}</div>
        </section>
      ) : (
        <>
          {originalDocumentCard}
          <section>{inspectorPanel}</section>
        </>
      )}
    </div>
  );
}
