import fs from "node:fs";
import path from "node:path";
import type {
  JobFieldConfig,
  JobStatus,
  JobValidationContextArtifact,
  JobValidationContextManualInput,
  JobValidationContextSource,
  JobValidationContextSummary,
  JobValidationContextVersion,
} from "@/types/idpo";
import { loadRunnerConfig } from "@/server/config";
import type { ReviewArtifact, ReviewFieldResult, ReviewState } from "@/server/review";
import { readReviewArtifact, sanitizeVendorIdentity } from "@/server/review";

function nowIso(): string {
  return new Date().toISOString();
}

function normalizeFieldKey(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, "_");
}

function titleCase(value: string): string {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function getJobValidationContextPath(jobId: string): string {
  return path.join(loadRunnerConfig().jobsDir, `${jobId}_validation_context.json`);
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function readJsonFile<T>(filePath: string): T | null {
  if (!fs.existsSync(filePath)) {
    return null;
  }
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf-8")) as T;
  } catch {
    return null;
  }
}

function uniqueStrings(values: Iterable<string>, limit = 8): string[] {
  const normalized: string[] = [];
  const seen = new Set<string>();
  for (const value of values) {
    const text = value.trim();
    if (!text) {
      continue;
    }
    const key = text.toLowerCase();
    if (seen.has(key)) {
      continue;
    }
    normalized.push(text);
    seen.add(key);
    if (normalized.length >= limit) {
      break;
    }
  }
  return normalized;
}

function normalizeManualInput(input: JobValidationContextManualInput | null | undefined): JobValidationContextManualInput {
  return {
    jobPurpose: typeof input?.jobPurpose === "string" ? input.jobPurpose.trim() || undefined : undefined,
    knownVendors: uniqueStrings(input?.knownVendors ?? [], 8),
    fieldClarifications: uniqueStrings(input?.fieldClarifications ?? [], 12),
    validationNotes: uniqueStrings(input?.validationNotes ?? [], 12),
  };
}

function mergeSummaryWithManualInput(
  summary: JobValidationContextSummary,
  manualInput: JobValidationContextManualInput,
): JobValidationContextSummary {
  return {
    jobPurpose: manualInput.jobPurpose || summary.jobPurpose,
    knownVendors: uniqueStrings([...(manualInput.knownVendors ?? []), ...summary.knownVendors], 8),
    fieldClarifications: uniqueStrings([...(manualInput.fieldClarifications ?? []), ...summary.fieldClarifications], 12),
    recurringFailurePatterns: summary.recurringFailurePatterns,
    reviewedCorrectionPatterns: summary.reviewedCorrectionPatterns,
    validationNotes: uniqueStrings([...(manualInput.validationNotes ?? []), ...summary.validationNotes], 12),
  };
}

function collectReviewedArtifacts(job: JobStatus): ReviewArtifact[] {
  const seen = new Set<string>();
  const artifacts: ReviewArtifact[] = [];

  for (const document of job.documents ?? []) {
    for (const outcome of document.outcomes) {
      if (!outcome.runId || !outcome.docId || outcome.status !== "processed") {
        continue;
      }
      const key = `${outcome.runId}:${outcome.docId}`;
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      const artifact = readReviewArtifact(outcome.runId, outcome.docId);
      if (artifact) {
        artifacts.push(artifact);
      }
    }
  }

  return artifacts.sort((left, right) => (left.reviewedAt < right.reviewedAt ? 1 : -1));
}

function buildFieldClarifications(
  artifacts: ReviewArtifact[],
  fieldConfig: JobFieldConfig[],
): string[] {
  const descriptions = new Map<string, string>();
  for (const field of fieldConfig) {
    if (field.description?.trim()) {
      descriptions.set(normalizeFieldKey(field.name), field.description.trim());
    }
  }

  const corrections = new Map<string, Set<string>>();
  for (const artifact of artifacts) {
    for (const field of artifact.fields) {
      const note = field.reviewNote?.trim();
      if (!note) {
        continue;
      }
      const key = normalizeFieldKey(field.fieldKey);
      const list = corrections.get(key) ?? new Set<string>();
      list.add(note);
      corrections.set(key, list);
    }
  }

  const entries: string[] = [];
  for (const [key, value] of descriptions.entries()) {
    entries.push(`${titleCase(key)}: ${value}`);
  }
  for (const [key, notes] of corrections.entries()) {
    const note = [...notes][0];
    if (note) {
      entries.push(`${titleCase(key)} note: ${note}`);
    }
  }
  return uniqueStrings(entries, 8);
}

function incrementStateCount(
  stateCounts: Map<string, Record<ReviewState, number>>,
  field: ReviewFieldResult,
): void {
  const key = normalizeFieldKey(field.fieldKey);
  const current = stateCounts.get(key) ?? {
    correct: 0,
    wrong_value: 0,
    missed_field: 0,
    correctly_skipped: 0,
    hallucinated_field: 0,
  };
  current[field.reviewState] += 1;
  stateCounts.set(key, current);
}

function buildFailurePatterns(artifacts: ReviewArtifact[]): string[] {
  const stateCounts = new Map<string, Record<ReviewState, number>>();
  for (const artifact of artifacts) {
    for (const field of artifact.fields) {
      incrementStateCount(stateCounts, field);
    }
  }

  const patterns: string[] = [];
  for (const [fieldKey, counts] of stateCounts.entries()) {
    if (counts.missed_field > 0) {
      patterns.push(`${titleCase(fieldKey)} is often missed (${counts.missed_field} reviewed doc${counts.missed_field === 1 ? "" : "s"}).`);
    }
    if (counts.wrong_value > 0) {
      patterns.push(`${titleCase(fieldKey)} is often extracted with the wrong value (${counts.wrong_value}).`);
    }
    if (counts.hallucinated_field > 0) {
      patterns.push(`${titleCase(fieldKey)} is sometimes hallucinated (${counts.hallucinated_field}).`);
    }
  }
  return uniqueStrings(patterns, 8);
}

function buildCorrectionPatterns(artifacts: ReviewArtifact[]): string[] {
  const corrections = new Map<string, Set<string>>();
  for (const artifact of artifacts) {
    for (const field of artifact.fields) {
      const corrected = field.correctedValue?.trim();
      if (!corrected) {
        continue;
      }
      const key = normalizeFieldKey(field.fieldKey);
      const list = corrections.get(key) ?? new Set<string>();
      list.add(corrected);
      corrections.set(key, list);
    }
  }

  const patterns: string[] = [];
  for (const [fieldKey, examples] of corrections.entries()) {
    const sample = [...examples].slice(0, 2).join(", ");
    patterns.push(`${titleCase(fieldKey)} has reviewed correction examples: ${sample}.`);
  }
  return uniqueStrings(patterns, 8);
}

function buildValidationNotes(artifacts: ReviewArtifact[]): string[] {
  const notes: string[] = [];
  for (const artifact of artifacts) {
    for (const field of artifact.fields) {
      if (field.reviewState === "missed_field" && !notes.includes("Treat blank or N/A as missing only when the field is expected to exist.")) {
        notes.push("Treat blank or N/A as missing only when the field is expected to exist.");
      }
      if (field.reviewState === "correctly_skipped" && !notes.includes("Do not force a value when the field is genuinely absent from the document.")) {
        notes.push("Do not force a value when the field is genuinely absent from the document.");
      }
      if (field.reviewNote?.trim()) {
        notes.push(field.reviewNote.trim());
      }
    }
  }
  return uniqueStrings(notes, 8);
}

function buildPromptPreview(summary: JobValidationContextSummary, fieldConfig: JobFieldConfig[]): { autoReview: string; extraction: string } {
  const fields = fieldConfig.map((field) => normalizeFieldKey(field.name)).filter(Boolean);
  const fieldList = fields.length > 0 ? fields.join(", ") : "requested fields from the current job";
  const vendorText = summary.knownVendors.length > 0 ? summary.knownVendors.join(", ") : "no stable vendor pattern yet";
  const clarificationText = summary.fieldClarifications.length > 0 ? summary.fieldClarifications.join(" | ") : "no field clarifications yet";
  const failureText = summary.recurringFailurePatterns.length > 0 ? summary.recurringFailurePatterns.join(" | ") : "no recurring failures recorded";
  const correctionText =
    summary.reviewedCorrectionPatterns.length > 0
      ? summary.reviewedCorrectionPatterns.join(" | ")
      : "no reviewed correction patterns recorded";
  const noteText = summary.validationNotes.length > 0 ? summary.validationNotes.join(" | ") : "no extra validation notes";

  return {
    autoReview: [
      `Job purpose: ${summary.jobPurpose}`,
      `Requested fields: ${fieldList}`,
      `Known vendors: ${vendorText}`,
      `Field clarifications: ${clarificationText}`,
      `Recurring failures: ${failureText}`,
      `Validation notes: ${noteText}`,
      "Review each requested field and choose exactly one state: correct, wrong_value, missed_field, correctly_skipped, hallucinated_field.",
    ].join("\n"),
    extraction: [
      `Job purpose: ${summary.jobPurpose}`,
      `Requested fields: ${fieldList}`,
      `Known vendors: ${vendorText}`,
      `Field clarifications: ${clarificationText}`,
      `Reviewed corrections: ${correctionText}`,
      `Failure patterns to avoid: ${failureText}`,
      "Follow the selected policy exactly. Use the context above only to improve field interpretation, not to change policy behavior.",
    ].join("\n"),
  };
}

function summarizeJobValidationContext(job: JobStatus, fieldConfig: JobFieldConfig[]): JobValidationContextSummary {
  const artifacts = collectReviewedArtifacts(job);
  const knownVendors = uniqueStrings(
    artifacts.flatMap((artifact) => {
      const vendorCluster = sanitizeVendorIdentity(artifact.documentContext.vendor_cluster);
      const vendor = sanitizeVendorIdentity(artifact.documentContext.vendor);
      return [vendorCluster ?? "", vendor ?? ""];
    }),
    6,
  );

  return {
    jobPurpose:
      job.jobName?.trim() ||
      (fieldConfig.length > 0
        ? `Review and extract ${fieldConfig.map((field) => field.name).join(", ")}`
        : "Review and extract the requested fields for this job"),
    knownVendors,
    fieldClarifications: buildFieldClarifications(artifacts, fieldConfig),
    recurringFailurePatterns: buildFailurePatterns(artifacts),
    reviewedCorrectionPatterns: buildCorrectionPatterns(artifacts),
    validationNotes: buildValidationNotes(artifacts),
  };
}

function compareSummary(previous: JobValidationContextSummary | null, next: JobValidationContextSummary): string[] {
  if (!previous) {
    return ["Created review context from the current reviewed documents."];
  }
  const changes: string[] = [];
  if (previous.knownVendors.join("|") !== next.knownVendors.join("|")) {
    changes.push("Known vendor patterns changed.");
  }
  if (previous.fieldClarifications.join("|") !== next.fieldClarifications.join("|")) {
    changes.push("Field clarifications were updated.");
  }
  if (previous.recurringFailurePatterns.join("|") !== next.recurringFailurePatterns.join("|")) {
    changes.push("Recurring failure patterns changed.");
  }
  if (previous.reviewedCorrectionPatterns.join("|") !== next.reviewedCorrectionPatterns.join("|")) {
    changes.push("Reviewed correction patterns changed.");
  }
  if (previous.validationNotes.join("|") !== next.validationNotes.join("|")) {
    changes.push("Validation notes changed.");
  }
  return changes.length > 0 ? changes : ["Review context refreshed from reviewed documents."];
}

export function readJobValidationContext(jobId: string): JobValidationContextArtifact | null {
  const artifact = readJsonFile<JobValidationContextArtifact>(getJobValidationContextPath(jobId));
  if (!artifact) {
    return null;
  }
  return {
    ...artifact,
    manualInput: normalizeManualInput(artifact.manualInput),
    current: {
      ...artifact.current,
      source: artifact.current.source,
    },
    history: Array.isArray(artifact.history)
      ? artifact.history.map((entry) => ({
          ...entry,
          source: entry.source,
        }))
      : [],
  };
}

function writeJobValidationContext(
  job: JobStatus,
  fieldConfig: JobFieldConfig[],
  source: JobValidationContextSource,
  manualInput: JobValidationContextManualInput,
): JobValidationContextArtifact {
  const previous = readJobValidationContext(job.jobId);
  const normalizedManualInput = normalizeManualInput(manualInput);
  const derivedSummary = summarizeJobValidationContext(job, fieldConfig);
  const summary = mergeSummaryWithManualInput(derivedSummary, normalizedManualInput);
  const promptPreview = buildPromptPreview(summary, fieldConfig);
  const nextVersionNumber = (previous?.currentVersionNumber ?? 0) + 1;
  const current: JobValidationContextVersion = {
    versionNumber: nextVersionNumber,
    updatedAt: nowIso(),
    source,
    changes: compareSummary(previous?.current?.summary ?? null, summary),
    summary,
    promptPreview,
  };

  const artifact: JobValidationContextArtifact = {
    version: 1,
    jobId: job.jobId,
    updatedAt: current.updatedAt,
    currentVersionNumber: nextVersionNumber,
    manualInput: normalizedManualInput,
    current,
    history: previous ? [previous.current, ...previous.history].slice(0, 12) : [],
  };

  fs.writeFileSync(getJobValidationContextPath(job.jobId), JSON.stringify(artifact, null, 2), "utf-8");
  return artifact;
}

export function refreshJobValidationContext(
  job: JobStatus,
  fieldConfig: JobFieldConfig[],
  source: Exclude<JobValidationContextSource, "operator">,
): JobValidationContextArtifact {
  const previous = readJobValidationContext(job.jobId);
  return writeJobValidationContext(job, fieldConfig, source, previous?.manualInput ?? {});
}

export function updateJobValidationContextManualInput(
  job: JobStatus,
  fieldConfig: JobFieldConfig[],
  manualInput: JobValidationContextManualInput,
): JobValidationContextArtifact {
  const previous = readJobValidationContext(job.jobId);
  const nextManualInput = normalizeManualInput({
    ...previous?.manualInput,
    ...manualInput,
  });
  return writeJobValidationContext(job, fieldConfig, "operator", nextManualInput);
}
