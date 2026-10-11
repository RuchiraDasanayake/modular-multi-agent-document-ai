import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { loadRunnerConfig, getCommandConfig } from "@/server/config";
import type { DocumentSummary, JobDocumentRecord, JobExecutionMode, JobFieldConfig, JobRunMode, JobStatus } from "@/types/idpo";
import {
  addDocumentsToJob,
  appendJobLog,
  createWorkspaceJob,
  getJobOrThrow,
  mutateJob,
  updateJob,
} from "@/server/jobs";
import { getRunDocument, getRunOverview } from "@/server/artifacts";
import { ensurePathInside, resolvePathForDisplay, resolvePrimaryRunPath, resolveRunRoot } from "@/server/paths";
import { ensureJobEffectivePolicyStore } from "@/server/policies";
import { readJobValidationContext } from "@/server/review-context";
import { buildJobOverlay, collectJobReviewLearningStats, readReviewArtifact, summarizeReviewState } from "@/server/review";

interface StartRunRequest {
  commandId?: string;
  settings: {
    configPath?: string;
    adaptiveMode?: "static" | "adaptive_safe";
    shadowMode?: boolean;
    shadowSampleRate?: number;
    maxCostPerDoc?: number;
    escalationEnabled?: boolean;
    report?: boolean;
    customFields?: Array<{
      key: string;
      description?: string;
      pattern?: string;
    }>;
    llmLocalModel?: string;
    llmCloudModel?: string;
    llmDefaultMode?: "local" | "cloud";
    forceLocalOnly?: boolean;
    llmUseExtraction?: boolean;
    llmUseSummarization?: boolean;
    flagshipModel?: string;
    autoInstallLocalModel?: boolean;
    apiKeys?: {
      openai?: string;
    };
  };
  files: File[];
  sourceRunId?: string;
}

interface UploadManifestFile {
  name: string;
  size: number;
  storedAs: string;
}

interface StartJobRunsRequest {
  jobId: string;
  selectedFileIds: string[];
  mode: JobExecutionMode;
  jobName?: string;
  fieldConfigCurrent?: JobFieldConfig[];
  settings: StartRunRequest["settings"];
}

function nowIso(): string {
  return new Date().toISOString();
}

function sanitizeFilename(name: string): string {
  return name.replace(/[^a-zA-Z0-9._-]/g, "_");
}

function listInputArtifacts(inputDir: string): string[] {
  if (!fs.existsSync(inputDir) || !fs.statSync(inputDir).isDirectory()) {
    return [];
  }

  const files: string[] = [];
  const walk = (dir: string) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        walk(full);
      } else if (entry.isFile()) {
        files.push(full);
      }
    }
  };
  walk(inputDir);
  return files;
}

function copySourceRunInputs(sourceRunId: string, uploadDir: string): UploadManifestFile[] {
  const config = loadRunnerConfig();
  const resolved = resolveRunRoot(sourceRunId);
  const primary = resolvePrimaryRunPath(resolved.rootPath);
  const inputDirPrimary = path.join(primary, "input");
  const inputDirRoot = path.join(resolved.rootPath, "input");
  const inputDir = fs.existsSync(inputDirPrimary) ? inputDirPrimary : inputDirRoot;
  const sourceFiles = listInputArtifacts(inputDir);

  const manifestFiles: UploadManifestFile[] = [];
  for (const sourceFile of sourceFiles) {
    const fileName = path.basename(sourceFile);
    const extension = path.extname(fileName).toLowerCase();
    if (!config.allowedExtensions.includes(extension)) {
      continue;
    }
    const finalName = `${Math.random().toString(36).slice(2, 8)}_${sanitizeFilename(fileName)}`;
    const target = path.join(uploadDir, finalName);
    fs.copyFileSync(sourceFile, target);

    const stat = fs.statSync(target);
    manifestFiles.push({
      name: fileName,
      size: stat.size,
      storedAs: finalName,
    });
  }

  return manifestFiles;
}

function resolveConfigPathFromSettings(settings: StartRunRequest["settings"]): string {
  const config = loadRunnerConfig();
  const defaultConfig = path.join(config.workspaceRoot, "configs", "idpo_research_config.json");

  if (!settings.configPath || settings.configPath.trim().length === 0) {
    return defaultConfig;
  }

  const candidate = path.resolve(config.workspaceRoot, settings.configPath);
  return ensurePathInside(config.workspaceRoot, candidate);
}

function reviewContextNotesForField(jobId: string, fieldKey: string): string[] {
  const context = readJobValidationContext(jobId);
  if (!context) {
    return [];
  }
  const normalizedField = fieldKey.trim().toLowerCase();
  const sections = [
    ...context.current.summary.fieldClarifications,
    ...context.current.summary.reviewedCorrectionPatterns,
    ...context.current.summary.recurringFailurePatterns,
  ];
  return sections.filter((entry) => entry.toLowerCase().includes(normalizedField)).slice(0, 3);
}

function mergeFieldDescription(baseDescription: string | undefined, reviewNotes: string[]): string | undefined {
  const parts = [baseDescription?.trim() ?? "", ...reviewNotes.map((note) => note.trim())].filter(Boolean);
  if (parts.length === 0) {
    return undefined;
  }
  return parts.join(" ");
}

export function patchConfig(baseConfig: Record<string, unknown>, settings: StartRunRequest["settings"], jobId: string): Record<string, unknown> {
  const updated = structuredClone(baseConfig);

  if (settings.adaptiveMode) {
    const ahmn = ((updated.ahmn as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
    if (settings.adaptiveMode === "static") {
      ahmn.enabled = false;
      ahmn.policy_mode = "static";
    } else {
      ahmn.enabled = true;
      ahmn.policy_mode = "adaptive";
      if (typeof ahmn.mode !== "string" || !String(ahmn.mode).trim()) {
        ahmn.mode = "http";
      }
    }
    updated.ahmn = ahmn;
  }

  if (settings.shadowMode !== undefined) {
    const shadow = ((updated.shadow as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
    shadow.enabled = settings.shadowMode;
    if (typeof settings.shadowSampleRate === "number" && Number.isFinite(settings.shadowSampleRate)) {
      shadow.sample_rate = Math.max(0, Math.min(1, settings.shadowSampleRate));
    }
    updated.shadow = shadow;
  }

  if (typeof settings.maxCostPerDoc === "number" && Number.isFinite(settings.maxCostPerDoc)) {
    const budget = ((updated.budget as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
    budget.max_cost_per_doc = settings.maxCostPerDoc;
    updated.budget = budget;
  }

  if (settings.escalationEnabled !== undefined) {
    const escalation = ((updated.escalation as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
    escalation.enabled = settings.escalationEnabled;
    updated.escalation = escalation;
  }

  if (settings.flagshipModel && settings.flagshipModel.trim()) {
    const escalation = ((updated.escalation as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
    escalation.flagship_model = settings.flagshipModel.trim();
    updated.escalation = escalation;
  }

  if (
    (settings.llmLocalModel && settings.llmLocalModel.trim()) ||
    (settings.llmCloudModel && settings.llmCloudModel.trim()) ||
    settings.llmDefaultMode ||
    settings.llmUseExtraction !== undefined ||
    settings.llmUseSummarization !== undefined
  ) {
    const llm = ((updated.llm as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
    if (settings.llmLocalModel && settings.llmLocalModel.trim()) {
      llm.local_model = settings.llmLocalModel.trim();
    }
    if (settings.llmCloudModel && settings.llmCloudModel.trim()) {
      llm.cloud_model = settings.llmCloudModel.trim();
    }
    if (settings.llmDefaultMode) {
      llm.default_mode = settings.llmDefaultMode;
    }
    if (settings.llmUseExtraction !== undefined) {
      llm.use_extraction = settings.llmUseExtraction;
    }
    if (settings.llmUseSummarization !== undefined) {
      llm.use_summarization = settings.llmUseSummarization;
    }
    updated.llm = llm;
  }

  if (settings.forceLocalOnly) {
    const llm = ((updated.llm as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
    llm.default_mode = "local";
    llm.history_mode = "local";
    llm.provider = "ollama";
    llm.allow_cloud_fallback = false;
    llm.enable_flagship_fallback = false;
    llm.description_refinement_use_cloud = false;
    updated.llm = llm;
    const escalation = ((updated.escalation as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
    escalation.enabled = false;
    updated.escalation = escalation;
  }

  if (Array.isArray(settings.customFields) && settings.customFields.length > 0) {
    const structuring = ((updated.structuring as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
    const currentRules = Array.isArray(structuring.extraction_rules)
      ? [...(structuring.extraction_rules as Array<Record<string, unknown>>)]
      : [];
    const requestedFields = Array.isArray(structuring.requested_fields)
      ? [...(structuring.requested_fields as Array<unknown>).map((item) => String(item).trim()).filter(Boolean)]
      : [];
    const descriptions =
      typeof structuring.field_descriptions === "object" && structuring.field_descriptions !== null
        ? ({ ...(structuring.field_descriptions as Record<string, unknown>) } as Record<string, unknown>)
        : {};

    for (const field of settings.customFields) {
      const key = (field.key || "").trim().toLowerCase().replace(/\s+/g, "_");
      if (!key) {
        continue;
      }
      if (!requestedFields.includes(key)) {
        requestedFields.push(key);
      }
      const label = key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
      const escapedLabel = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      const pattern = field.pattern?.trim() || `${escapedLabel}\\s*[:=\\-]\\s*(.+)`;
      currentRules.push({
        key,
        label,
        pattern,
      });
      const mergedDescription = mergeFieldDescription(field.description, reviewContextNotesForField(jobId, key));
      if (mergedDescription) {
        descriptions[key] = mergedDescription;
      }
    }

    structuring.extraction_rules = currentRules;
    structuring.requested_fields = requestedFields;
    structuring.field_descriptions = descriptions;
    updated.structuring = structuring;
  }

  return updated;
}

function prepareRuntimeConfig(baseConfigPath: string, jobId: string, settings: StartRunRequest["settings"]): string {
  let baseConfig: Record<string, unknown> = {};
  if (fs.existsSync(baseConfigPath)) {
    try {
      baseConfig = JSON.parse(fs.readFileSync(baseConfigPath, "utf-8")) as Record<string, unknown>;
    } catch {
      baseConfig = {};
    }
  }

  const finalConfig = patchConfig(baseConfig, settings, jobId);
  const knowledge = ((finalConfig.knowledge as Record<string, unknown> | undefined) ?? {}) as Record<string, unknown>;
  knowledge.policy_store_path = ensureJobEffectivePolicyStore(jobId);
  if (typeof knowledge.default_policy_id !== "string" || !knowledge.default_policy_id.trim()) {
    knowledge.default_policy_id = "default";
  }
  finalConfig.knowledge = knowledge;
  const runtimeConfigPath = path.join(loadRunnerConfig().jobsDir, `${jobId}_runtime_config.json`);
  fs.writeFileSync(runtimeConfigPath, JSON.stringify(finalConfig, null, 2), "utf-8");
  return runtimeConfigPath;
}

function redactSettings(settings: StartRunRequest["settings"]): Record<string, unknown> {
  const redacted: Record<string, unknown> = { ...settings };
  if (settings.apiKeys?.openai) {
    redacted.apiKeys = { openai: "***" };
  }
  return redacted;
}

function readOllamaBaseUrl(runtimeConfigPath: string): string {
  try {
    const config = JSON.parse(fs.readFileSync(runtimeConfigPath, "utf-8")) as { llm?: { base_url?: unknown } };
    const baseUrl = typeof config.llm?.base_url === "string" ? config.llm.base_url.trim() : "";
    return (baseUrl || "http://localhost:11434").replace(/\/+$/, "");
  } catch {
    return "http://localhost:11434";
  }
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export async function maybeInstallLocalModel(
  jobId: string,
  settings: StartRunRequest["settings"],
  runtimeConfigPath: string,
): Promise<void> {
  if (!settings.autoInstallLocalModel || !settings.llmLocalModel?.trim()) {
    return;
  }
  const model = settings.llmLocalModel.trim();
  const baseUrl = readOllamaBaseUrl(runtimeConfigPath);
  appendJobLog(jobId, `[runner] checking local model '${model}'`);

  let installed: string[];
  try {
    const response = await fetch(`${baseUrl}/api/tags`, { signal: AbortSignal.timeout(15_000) });
    const payload = (await response.json()) as { models?: Array<{ name?: string; model?: string }> };
    installed = (payload.models ?? []).map((entry) => String(entry.name ?? entry.model ?? "").toLowerCase());
  } catch (error) {
    appendJobLog(jobId, `[runner] ollama not available at ${baseUrl}: ${errorMessage(error)}`);
    return;
  }
  const wanted = model.toLowerCase();
  if (installed.some((name) => name === wanted || name === `${wanted}:latest`)) {
    appendJobLog(jobId, `[runner] local model already present: ${model}`);
    return;
  }

  appendJobLog(jobId, `[runner] pulling local model: ${model}`);
  try {
    // Streamed so progress lines keep the connection alive; a non-streamed pull sends nothing until it ends.
    const response = await fetch(`${baseUrl}/api/pull`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model, stream: true }),
      signal: AbortSignal.timeout(20 * 60 * 1000),
    });
    const lines = (await response.text()).split("\n").filter((line) => line.trim());
    const last = lines.length ? (JSON.parse(lines[lines.length - 1]) as { status?: string; error?: string }) : {};
    if (response.ok && last.status === "success") {
      appendJobLog(jobId, `[runner] model pull complete: ${model}`);
    } else {
      appendJobLog(jobId, `[runner] model pull failed (${response.status}): ${String(last.error ?? last.status ?? "").slice(0, 300)}`);
    }
  } catch (error) {
    appendJobLog(jobId, `[runner] model pull failed: ${errorMessage(error)}`);
  }
}

function buildCommandArgs(
  commandArgsTemplate: string[],
  placeholders: Record<string, string>,
): string[] {
  return commandArgsTemplate.map((value) => value.replace(/\{([a-z_]+)\}/g, (_, key) => placeholders[key] ?? ""));
}

function parseRunInfoFromLog(line: string): { runId: string | null; runPath: string | null } {
  const runDirMatch = line.match(/"run_dir"\s*:\s*"([^"]+)"/i);
  if (!runDirMatch) {
    return { runId: null, runPath: null };
  }

  const runPath = runDirMatch[1].replace(/\\\\/g, "\\");
  const runId = path.basename(runPath);
  return { runId, runPath };
}

function normalizeFieldKey(name: string): string {
  return name.trim().toLowerCase().replace(/\s+/g, "_");
}

function fieldSnapshotToCustomFields(fieldSnapshot: JobFieldConfig[]): NonNullable<StartRunRequest["settings"]["customFields"]> {
  return fieldSnapshot.map((field) => ({
    key: normalizeFieldKey(field.name),
    description: field.description,
  }));
}

function writeJobOverlayIfEligible(jobId: string, fieldSnapshot: JobFieldConfig[]): string | null {
  const job = getJobOrThrow(jobId);
  const overlay = buildJobOverlay(job, fieldSnapshot);
  if (overlay.entries.length === 0) {
    return null;
  }
  fs.writeFileSync(
    overlay.path,
    JSON.stringify(
      {
        job_id: jobId,
        generated_at: nowIso(),
        entries: overlay.entries,
      },
      null,
      2,
    ),
    "utf-8",
  );
  return overlay.path;
}

function jobModeToAdaptiveMode(mode: JobRunMode): "static" | "adaptive_safe" {
  return mode === "strict" ? "static" : "adaptive_safe";
}

function summarizeJobProfile(documents: DocumentSummary[]): string {
  if (documents.length === 0) {
    return "awaiting_run";
  }
  const buckets = new Map<string, number>();
  for (const doc of documents) {
    const key = doc.routeBin || doc.docType || doc.vendorCluster || "mixed_batch";
    buckets.set(key, (buckets.get(key) ?? 0) + 1);
  }
  return [...buckets.entries()].sort((left, right) => right[1] - left[1])[0]?.[0] ?? "mixed_batch";
}

function buildAhmnSummary(job: JobStatus, documents: DocumentSummary[]) {
  const documentsWithAdvice = documents.filter(
    (doc) => (doc.adviceStatus && !["static", "no_advice"].includes(doc.adviceStatus)) || doc.adviceAccepted || doc.policyChanged,
  ).length;
  const documentsLoggedBack = documents.filter((doc) => Boolean(doc.feedbackLogged)).length;
  const adviceInfluencedCount = documents.filter((doc) => Boolean(doc.policyChanged) || Boolean(doc.adviceAccepted)).length;
  const memoryMatched = documents.some(
    (doc) => typeof doc.retrievalSource === "string" && doc.retrievalSource.length > 0 && doc.retrievalSource !== "unknown",
  );
  const reviewStats = collectJobReviewLearningStats(job, job.fieldConfigCurrent ?? []);
  return {
    jobProfile: summarizeJobProfile(documents),
    memoryMatched,
    documentsWithAdvice,
    documentsLoggedBack,
    adviceInfluencedCount,
    reviewedDocumentCount: reviewStats.reviewedDocumentCount,
    reviewedHumanCount: reviewStats.reviewedHumanCount,
    reviewedAiCount: reviewStats.reviewedAiCount,
    reviewedFeedbackLoggedCount: reviewStats.reviewedFeedbackLoggedCount,
    reviewedFeedbackPendingCount: reviewStats.reviewedFeedbackPendingCount,
    jobOverlayPolicies: reviewStats.overlayEntryCount,
    jobOverlayReady: reviewStats.overlayReady,
    adaptationSummary:
      documents.length === 0
        ? "No completed runs yet."
        : `${adviceInfluencedCount} document(s) changed or matched adaptive advice; ${documentsLoggedBack} runtime feedback event(s), ${reviewStats.reviewedFeedbackLoggedCount} reviewed learning event(s), overlay ${reviewStats.overlayReady ? "ready" : "not ready"}.`,
  };
}

function buildFieldValuesFromDetail(detail: Record<string, unknown>): Record<string, string> {
  const values: Record<string, string> = {};
  const fields = Array.isArray(detail.fields) ? detail.fields : [];
  for (const field of fields) {
    if (!field || typeof field !== "object") {
      continue;
    }
    const entry = field as Record<string, unknown>;
    const key = typeof entry.key === "string" ? entry.key : "";
    if (!key) {
      continue;
    }
    const metadata = entry.metadata && typeof entry.metadata === "object" ? (entry.metadata as Record<string, unknown>) : {};
    const label = typeof metadata.label === "string" && metadata.label.trim() ? metadata.label.trim() : key;
    const rawValue = entry.value;
    const textValue =
      typeof rawValue === "string"
        ? rawValue
        : typeof rawValue === "number" || typeof rawValue === "boolean"
          ? String(rawValue)
          : "";
    values[key] = textValue;
    values[label] = textValue;
  }
  return values;
}

function buildReviewState(detail: Record<string, unknown>): string {
  const validationIssues = Array.isArray(detail.validationIssues) ? detail.validationIssues : [];
  if (validationIssues.length > 0) {
    return `${validationIssues.length} issue(s)`;
  }
  const metadata = detail.metadata && typeof detail.metadata === "object" ? (detail.metadata as Record<string, unknown>) : {};
  if (typeof metadata.deferStatus === "string" && metadata.deferStatus !== "not_needed") {
    return metadata.deferStatus;
  }
  if (typeof metadata.fallbackReason === "string" && metadata.fallbackReason.trim()) {
    return "fallback";
  }
  return "clear";
}

function matchesJobDocument(summary: DocumentSummary, document: JobDocumentRecord): boolean {
  const filename = summary.filename || "";
  return (
    filename === document.storedName ||
    filename === document.fileName ||
    filename.startsWith(`${document.fileId}__`) ||
    filename.endsWith(`__${sanitizeFilename(document.fileName)}`)
  );
}

function describeRunnerError(error: unknown): string {
  if (!(error instanceof Error)) {
    return "The document run failed.";
  }
  const code = "code" in error ? String((error as NodeJS.ErrnoException).code ?? "") : "";
  if (code === "ENOENT" || /ENOENT/.test(error.message)) {
    return "Processing did not start because the Python environment could not be found.";
  }
  return error.message;
}

function createExecutionUploadDir(): string {
  const config = loadRunnerConfig();
  const folderName = `jobrun_${new Date().toISOString().replace(/[:.]/g, "-")}_${Math.random().toString(36).slice(2, 8)}`;
  const uploadDir = path.join(config.uploadsDir, folderName);
  fs.mkdirSync(uploadDir, { recursive: true });
  return uploadDir;
}

function copyJobDocumentsToUploadDir(job: JobStatus, selectedDocs: JobDocumentRecord[], uploadDir: string): UploadManifestFile[] {
  const sourceRoot = job.uploadsPath || "";
  if (!sourceRoot || !fs.existsSync(sourceRoot)) {
    throw new Error("Job upload directory not found");
  }

  const manifestFiles: UploadManifestFile[] = [];
  for (const document of selectedDocs) {
    const source = path.join(sourceRoot, document.storedName);
    if (!fs.existsSync(source)) {
      throw new Error(`Missing job file '${document.fileName}'`);
    }
    const target = path.join(uploadDir, document.storedName);
    fs.copyFileSync(source, target);
    manifestFiles.push({
      name: document.fileName,
      size: document.size,
      storedAs: document.storedName,
    });
  }
  return manifestFiles;
}

async function executeRunnerCommand(
  jobId: string,
  commandId: string | undefined,
  settings: StartRunRequest["settings"],
  uploadDir: string,
  assignedRunId: string,
): Promise<{ runId: string | null; runPath: string | null }> {
  const commandConfig = getCommandConfig(commandId);
  const baseConfigPath = resolveConfigPathFromSettings(settings);
  const runtimeConfigPath = prepareRuntimeConfig(baseConfigPath, jobId, settings);
  const placeholders = {
    input_dir: uploadDir,
    config_path: runtimeConfigPath,
    workspace_root: loadRunnerConfig().workspaceRoot,
    run_id: assignedRunId,
  };
  const args = buildCommandArgs(commandConfig.args, placeholders);

  updateJob(jobId, {
    commandId: commandConfig.id,
    logs: [
      `Input directory: ${resolvePathForDisplay(uploadDir)}`,
      `Runtime config: ${resolvePathForDisplay(runtimeConfigPath)}`,
      `Executing: ${commandConfig.program} ${args.join(" ")}`,
      ...getJobOrThrow(jobId).logs,
    ],
  });

  await maybeInstallLocalModel(jobId, settings, runtimeConfigPath);

  const overlayPath = writeJobOverlayIfEligible(
    jobId,
    (settings.customFields ?? []).map((field) => ({
      name: field.key,
      description: field.description,
    })),
  );

  if (path.isAbsolute(commandConfig.program) && !fs.existsSync(commandConfig.program)) {
    return Promise.reject(
      new Error(`Processing did not start because Python was not found at ${commandConfig.program}.`),
    );
  }

  return new Promise((resolve, reject) => {
    const child = spawn(commandConfig.program, args, {
      cwd: commandConfig.cwd,
      env: {
        ...process.env,
        ...commandConfig.env,
        IDPO_EXECUTION_SURFACE: "frontend_job_runner",
        IDPO_JOB_ID: jobId,
        ...(overlayPath ? { IDPO_JOB_OVERLAY_PATH: overlayPath } : {}),
        ...(settings.apiKeys?.openai?.trim()
          ? {
              OPENAI_API_KEY: settings.apiKeys.openai.trim(),
            }
          : {}),
      },
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });

    let discoveredRunId: string | null = null;
    let discoveredRunPath: string | null = null;

    const handleChunk = (chunk: Buffer, stream: "stdout" | "stderr") => {
      const text = chunk.toString("utf-8");
      const lines = text.split(/\r?\n/).filter(Boolean);
      for (const line of lines) {
        appendJobLog(jobId, `[${stream}] ${line}`);
        const parsed = parseRunInfoFromLog(line);
        if (parsed.runId) {
          discoveredRunId = parsed.runId;
        }
        if (parsed.runPath) {
          discoveredRunPath = parsed.runPath;
        }
      }
    };

    child.stdout.on("data", (chunk) => handleChunk(chunk as Buffer, "stdout"));
    child.stderr.on("data", (chunk) => handleChunk(chunk as Buffer, "stderr"));

    child.on("error", (error) => {
      appendJobLog(jobId, `[runner] process error: ${error.message}`);
      reject(error);
    });

    child.on("close", (code) => {
      if (code !== 0) {
        const message = `Command failed with exit code ${code ?? "unknown"}`;
        appendJobLog(jobId, `[runner] ${message}`);
        reject(new Error(message));
        return;
      }

      const assignedRunPath = path.join(loadRunnerConfig().runsDir, assignedRunId);
      const resolvedRunId = discoveredRunId ?? (fs.existsSync(assignedRunPath) ? assignedRunId : null);
      const resolvedRunPath = discoveredRunPath ?? (resolvedRunId ? path.join(loadRunnerConfig().runsDir, resolvedRunId) : null);
      appendJobLog(jobId, `[runner] completed successfully`);
      if (resolvedRunId) {
        appendJobLog(jobId, `[runner] resolved runId=${resolvedRunId}`);
      }
      resolve({ runId: resolvedRunId, runPath: resolvedRunPath });
    });
  });
}

function appendRunOutcome(
  document: JobDocumentRecord,
  outcome: JobDocumentRecord["outcomes"][number],
  nextStatus: JobDocumentRecord["status"],
) {
  const existing = document.outcomes.filter(
    (item) => !(item.runId === outcome.runId && item.mode === outcome.mode),
  );
  document.outcomes = [...existing, outcome];
  document.latestRunId = outcome.runId;
  document.latestDocId = outcome.docId;
  document.latestRoute = outcome.route;
  document.latestPolicy = outcome.policy;
  document.errorSummary = outcome.errorSummary;
  // Never overwrite a persisted human review with a non-human result from a new run.
  if (document.reviewStatus !== "human_reviewed" || outcome.reviewStatus === "human_reviewed") {
    document.reviewState = outcome.reviewState;
    document.reviewStatus = outcome.reviewStatus ?? null;
    document.reviewSource = outcome.reviewSource ?? null;
  }
  document.status = nextStatus;
  document.updatedAt = nowIso();
}

function sameFieldValues(
  left: Record<string, string>,
  right: Record<string, string>,
): boolean {
  const leftEntries = Object.entries(left).sort(([a], [b]) => a.localeCompare(b));
  const rightEntries = Object.entries(right).sort(([a], [b]) => a.localeCompare(b));
  if (leftEntries.length !== rightEntries.length) {
    return false;
  }
  return leftEntries.every(([key, value], index) => {
    const [rightKey, rightValue] = rightEntries[index] ?? [];
    return key === rightKey && value === rightValue;
  });
}

function outcomeMatches(
  current: JobDocumentRecord["outcomes"][number] | null,
  next: JobDocumentRecord["outcomes"][number],
  nextStatus: JobDocumentRecord["status"],
  document: JobDocumentRecord,
): boolean {
  if (!current) {
    return false;
  }
  return (
    current.docId === next.docId &&
    current.status === next.status &&
    current.route === next.route &&
    current.policy === next.policy &&
    current.errorSummary === next.errorSummary &&
    current.reviewState === next.reviewState &&
    current.reviewStatus === next.reviewStatus &&
    current.reviewSource === next.reviewSource &&
    current.adviceInfluenced === next.adviceInfluenced &&
    current.feedbackLogged === next.feedbackLogged &&
    current.fallbackReason === next.fallbackReason &&
    current.exactPrecision === next.exactPrecision &&
    current.exactRecall === next.exactRecall &&
    current.exactF1 === next.exactF1 &&
    sameFieldValues(current.fieldValues, next.fieldValues) &&
    document.status === nextStatus
  );
}

function resolveActiveRunId(run: NonNullable<JobStatus["runs"]>[number]): { runId: string | null; runPath: string | null } {
  if (!run.runId) {
    return { runId: null, runPath: null };
  }
  return { runId: run.runId, runPath: run.runPath ?? resolvePathForDisplay(path.join(loadRunnerConfig().runsDir, run.runId)) };
}

function expectedRunDocId(document: JobDocumentRecord): string {
  return path.parse(document.storedName).name;
}

function hasCompletedRunArtifacts(runId: string, docId: string): boolean {
  let rootPath: string;
  try {
    rootPath = resolveRunRoot(runId).rootPath;
  } catch {
    // The run id is assigned before the pipeline creates its folder.
    return false;
  }
  const primaryPath = resolvePrimaryRunPath(rootPath);
  const docDir = path.join(primaryPath, "docs", docId);
  if (!fs.existsSync(docDir)) {
    return false;
  }
  const completionMarkers = [
    path.join(docDir, "decision_chain.json"),
    path.join(docDir, "reward.json"),
    path.join(docDir, "provenance", "transparency.json"),
  ];
  return completionMarkers.some((candidate) => fs.existsSync(candidate));
}

function isPlaceholderOutcome(outcome: JobDocumentRecord["outcomes"][number]): boolean {
  return (
    outcome.status === "processed" &&
    outcome.policy == null &&
    outcome.route == null &&
    outcome.errorSummary == null &&
    Object.keys(outcome.fieldValues).length === 0
  );
}

function nextDocumentStatusForRun(job: JobStatus, document: JobDocumentRecord, jobRunId: string): JobDocumentRecord["status"] {
  const hasOtherPendingRuns = (job.runs ?? []).some(
    (run) =>
      run.jobRunId !== jobRunId &&
      (run.status === "queued" || run.status === "running") &&
      run.selectedFileIds.includes(document.fileId),
  );
  return hasOtherPendingRuns ? "processing" : "processed";
}

export function syncActiveJobProgress(jobId: string): JobStatus {
  const current = getJobOrThrow(jobId);
  const activeRuns = (current.runs ?? []).filter((run) => (run.status === "queued" || run.status === "running"));
  if (activeRuns.length === 0) {
    return current;
  }

  let changed = false;
  const synced = mutateJob(jobId, (job) => {
    for (const run of job.runs ?? []) {
      if (run.status !== "queued" && run.status !== "running") {
        continue;
      }

      const resolved = resolveActiveRunId(run);
      if (!resolved.runId) {
        continue;
      }
      if (!run.runId) {
        run.runId = resolved.runId;
        run.runPath = resolved.runPath;
        run.status = "running";
        changed = true;
      }

      let completedCount = 0;

      for (const fileId of run.selectedFileIds) {
        const document = (job.documents ?? []).find((item) => item.fileId === fileId);
        if (!document) {
          continue;
        }

        const docId = expectedRunDocId(document);
        const existing = document.outcomes.find((item) => item.runId === resolved.runId && item.mode === run.mode) ?? null;
        if (!hasCompletedRunArtifacts(resolved.runId, docId)) {
          if (existing && isPlaceholderOutcome(existing)) {
            document.outcomes = document.outcomes.filter((item) => !(item.runId === resolved.runId && item.mode === run.mode));
            document.status = "processing";
            document.latestRunId = existing.runId === document.latestRunId ? null : document.latestRunId;
            document.latestDocId = existing.docId === document.latestDocId ? null : document.latestDocId;
            document.latestRoute = existing.route === document.latestRoute ? null : document.latestRoute;
            document.latestPolicy = existing.policy === document.latestPolicy ? null : document.latestPolicy;
            changed = true;
          }
          continue;
        }
        completedCount += 1;

        let outcome: JobDocumentRecord["outcomes"][number];
        try {
          const detail = getRunDocument(resolved.runId, docId);
          const reviewArtifact = readReviewArtifact(resolved.runId, docId);
          const metadata =
            detail.metadata && typeof detail.metadata === "object" ? (detail.metadata as Record<string, unknown>) : {};
          outcome = {
            runId: resolved.runId,
            mode: run.mode,
            docId,
            status: "processed",
            route: typeof metadata.routeBin === "string" ? metadata.routeBin : null,
            policy: typeof metadata.policyId === "string" ? metadata.policyId : null,
            errorSummary: null,
            reviewState: reviewArtifact ? summarizeReviewState(reviewArtifact) : buildReviewState(detail),
            reviewStatus: reviewArtifact?.reviewStatus ?? "unreviewed",
            reviewSource: reviewArtifact?.reviewSource ?? null,
            fieldValues: buildFieldValuesFromDetail(detail),
            adviceInfluenced: Boolean(metadata.policyChanged) || Boolean(metadata.adviceAccepted),
            feedbackLogged: Boolean(detail.feedbackStatus && typeof detail.feedbackStatus === "object" && (detail.feedbackStatus as Record<string, unknown>).logged),
            fallbackReason: typeof metadata.fallbackReason === "string" ? metadata.fallbackReason : null,
            exactPrecision: reviewArtifact?.metrics.precision ?? null,
            exactRecall: reviewArtifact?.metrics.recall ?? null,
            exactF1: reviewArtifact?.metrics.f1 ?? null,
          };
        } catch {
          outcome = {
            runId: resolved.runId,
            mode: run.mode,
            docId,
            status: "processed",
            route: null,
            policy: null,
            errorSummary: null,
            reviewState: "clear",
            reviewStatus: "unreviewed",
            reviewSource: null,
            fieldValues: {},
            adviceInfluenced: false,
            feedbackLogged: false,
            fallbackReason: null,
            exactPrecision: null,
            exactRecall: null,
            exactF1: null,
          };
        }

        const nextStatus = nextDocumentStatusForRun(job, document, run.jobRunId);
        if (outcomeMatches(existing, outcome, nextStatus, document)) {
          continue;
        }

        appendRunOutcome(document, outcome, nextStatus);
        changed = true;
      }
      run.processedCount = completedCount;
      run.failedCount = Math.max(run.selectedFileIds.length - completedCount, 0);
    }
    return job;
  });

  return changed ? synced : current;
}

function finalizeSelectedDocuments(
  job: JobStatus,
  selectedFileIds: string[],
  modes: JobRunMode[],
  runIdsByMode: Partial<Record<JobRunMode, string>>,
) {
  const selectedSet = new Set(selectedFileIds);
  const requiredModes = new Set(modes);
  for (const document of job.documents ?? []) {
    if (!selectedSet.has(document.fileId)) {
      continue;
    }
    const relevantOutcomes = document.outcomes.filter(
      (outcome) => requiredModes.has(outcome.mode) && runIdsByMode[outcome.mode] === outcome.runId,
    );
    const processedModes = new Set(relevantOutcomes.filter((outcome) => outcome.status === "processed").map((outcome) => outcome.mode));
    document.status = processedModes.size === requiredModes.size ? "processed" : "failed";
    document.updatedAt = nowIso();
  }
}

async function foldRunIntoJob(
  jobId: string,
  jobRunId: string,
  selectedFileIds: string[],
  runMode: JobRunMode,
  runId: string,
  runPath: string | null,
  remainingModesAfterCurrent: number,
) {
  const overview = getRunOverview(runId);
  const summaries = [...overview.documents];
  const matchedIds = new Set<string>();
  mutateJob(jobId, (job) => {
    const docMap = new Map((job.documents ?? []).map((document) => [document.fileId, document]));

    for (const fileId of selectedFileIds) {
      const document = docMap.get(fileId);
      if (!document) {
        continue;
      }

      const matchIndex = summaries.findIndex((summary) => !matchedIds.has(summary.docId) && matchesJobDocument(summary, document));
      if (matchIndex >= 0) {
        const summary = summaries[matchIndex];
        matchedIds.add(summary.docId);
        const detail = getRunDocument(runId, summary.docId);
        const reviewArtifact = readReviewArtifact(runId, summary.docId);
        appendRunOutcome(
          document,
          {
            runId,
            mode: runMode,
            docId: summary.docId,
            status: "processed",
            route: summary.routeBin ?? null,
            policy: summary.policyId ?? null,
            errorSummary: null,
            reviewState: reviewArtifact ? summarizeReviewState(reviewArtifact) : buildReviewState(detail),
            reviewStatus: reviewArtifact?.reviewStatus ?? "unreviewed",
            reviewSource: reviewArtifact?.reviewSource ?? null,
            fieldValues: buildFieldValuesFromDetail(detail),
            adviceInfluenced: Boolean(summary.policyChanged) || Boolean(summary.adviceAccepted),
            feedbackLogged: Boolean(summary.feedbackLogged),
            fallbackReason: summary.fallbackReason ?? null,
            exactPrecision: reviewArtifact?.metrics.precision ?? null,
            exactRecall: reviewArtifact?.metrics.recall ?? null,
            exactF1: reviewArtifact?.metrics.f1 ?? null,
          },
          remainingModesAfterCurrent > 0 ? "processing" : "processed",
        );
        continue;
      }

      appendRunOutcome(
        document,
        {
          runId,
          mode: runMode,
          docId: null,
          status: "failed",
          route: null,
          policy: null,
          errorSummary: "No result returned for this file.",
          reviewState: "failed",
          reviewStatus: "unreviewed",
          reviewSource: null,
          fieldValues: {},
          adviceInfluenced: false,
          feedbackLogged: false,
          fallbackReason: null,
          exactPrecision: null,
          exactRecall: null,
          exactF1: null,
        },
        remainingModesAfterCurrent > 0 ? "processing" : "failed",
      );
    }

    const runRecord = (job.runs ?? []).find((run) => run.jobRunId === jobRunId);
    if (runRecord) {
      runRecord.runId = runId;
      runRecord.runPath = runPath;
      runRecord.status = "success";
      runRecord.endedAt = nowIso();
      runRecord.processedCount = overview.documents.length;
      runRecord.failedCount = Math.max(selectedFileIds.length - overview.documents.length, 0);
      runRecord.adviceDocumentCount = overview.documents.filter(
        (doc) => (doc.adviceStatus && !["static", "no_advice"].includes(doc.adviceStatus)) || doc.adviceAccepted || doc.policyChanged,
      ).length;
      runRecord.loggedFeedbackCount = overview.documents.filter((doc) => Boolean(doc.feedbackLogged)).length;
    }

    job.ahmnSummary = buildAhmnSummary(job, overview.documents);
    job.runId = runId;
    job.runPath = runPath;
    job.latestRunId = runId;
    job.endedAt = nowIso();
    return job;
  });
}

function markRunFailed(jobId: string, jobRunId: string, selectedFileIds: string[], runMode: JobRunMode, error: string, remainingModesAfterCurrent: number) {
  mutateJob(jobId, (job) => {
    const runRecord = (job.runs ?? []).find((run) => run.jobRunId === jobRunId);
    if (runRecord) {
      runRecord.status = "failed";
      runRecord.error = error;
      runRecord.endedAt = nowIso();
    }
    const selectedSet = new Set(selectedFileIds);
    for (const document of job.documents ?? []) {
      if (!selectedSet.has(document.fileId)) {
        continue;
      }
      appendRunOutcome(
        document,
        {
          runId: jobRunId,
          mode: runMode,
          docId: null,
          status: "failed",
          route: null,
          policy: null,
          errorSummary: error,
          reviewState: "failed",
          reviewStatus: "unreviewed",
          reviewSource: null,
          fieldValues: {},
          adviceInfluenced: false,
          feedbackLogged: false,
          fallbackReason: null,
          exactPrecision: null,
          exactRecall: null,
          exactF1: null,
        },
        remainingModesAfterCurrent > 0 ? "processing" : "failed",
      );
    }
    return job;
  });
}

async function runSingleJobMode(
  jobId: string,
  jobRunId: string,
  runMode: JobRunMode,
  selectedFileIds: string[],
  fieldSnapshot: JobFieldConfig[],
  settings: StartRunRequest["settings"],
  commandId?: string,
  remainingModesAfterCurrent = 0,
): Promise<string | null> {
  const job = getJobOrThrow(jobId);
  const selectedDocs = (job.documents ?? []).filter((document) => selectedFileIds.includes(document.fileId));
  if (selectedDocs.length === 0) {
    throw new Error("No selected job documents found");
  }

  const assignedRunId = randomUUID().replace(/-/g, "");
  mutateJob(jobId, (current) => {
    current.status = "running";
    current.error = undefined;
    const runRecord = (current.runs ?? []).find((run) => run.jobRunId === jobRunId);
    if (runRecord) {
      runRecord.status = "running";
      runRecord.startedAt = nowIso();
      runRecord.runId = assignedRunId;
      runRecord.runPath = resolvePathForDisplay(path.join(loadRunnerConfig().runsDir, assignedRunId));
    }
    return current;
  });

  const uploadDir = createExecutionUploadDir();
  copyJobDocumentsToUploadDir(job, selectedDocs, uploadDir);

  const runSettings: StartRunRequest["settings"] = {
    ...settings,
    adaptiveMode: jobModeToAdaptiveMode(runMode),
    customFields: fieldSnapshotToCustomFields(fieldSnapshot),
  };

  try {
    const { runId, runPath } = await executeRunnerCommand(jobId, commandId ?? job.commandId, runSettings, uploadDir, assignedRunId);
    if (!runId) {
      throw new Error("The runner command finished but wrote no run output. Check the command in runner.config.json.");
    }
    await foldRunIntoJob(
      jobId,
      jobRunId,
      selectedFileIds,
      runMode,
      runId,
      runPath ? resolvePathForDisplay(runPath) : null,
      remainingModesAfterCurrent,
    );
    return runId;
  } catch (error) {
    const message = describeRunnerError(error);
    markRunFailed(jobId, jobRunId, selectedFileIds, runMode, message, remainingModesAfterCurrent);
    return null;
  }
}

export async function startJobRuns(payload: StartJobRunsRequest): Promise<JobStatus> {
  const currentJob = getJobOrThrow(payload.jobId);
  const selectedFileIds = Array.from(new Set(payload.selectedFileIds)).filter((fileId) =>
    (currentJob.documents ?? []).some((document) => document.fileId === fileId),
  );
  if (selectedFileIds.length === 0) {
    throw new Error("Select at least one document");
  }

  const fieldSnapshot = payload.fieldConfigCurrent && payload.fieldConfigCurrent.length > 0
    ? payload.fieldConfigCurrent
    : (currentJob.fieldConfigCurrent ?? []);
  const modes: JobRunMode[] = payload.mode === "both" ? ["adaptive", "strict"] : [payload.mode];
  const queuedRuns = modes.map((mode) => ({
    jobRunId: randomUUID().replace(/-/g, ""),
    runId: null,
    mode,
    status: "queued" as const,
    createdAt: nowIso(),
    fieldSnapshot,
    selectedFileIds,
    runPath: null,
    error: null,
  }));

  const queuedJob = mutateJob(payload.jobId, (job) => {
    job.jobName = payload.jobName?.trim() ?? job.jobName ?? "";
    job.mode = payload.mode;
    job.fieldConfigCurrent = fieldSnapshot;
    job.settings = {
      ...job.settings,
      ...redactSettings(payload.settings),
    };
    job.status = "queued";
    job.error = undefined;
    job.endedAt = undefined;
    job.runs = [...(job.runs ?? []), ...queuedRuns];
    const selectedSet = new Set(selectedFileIds);
    for (const document of job.documents ?? []) {
      document.selected = selectedSet.has(document.fileId);
      if (!selectedSet.has(document.fileId)) {
        continue;
      }
      document.status = "processing";
      document.errorSummary = null;
      // Preserve human review — only clear AI/unreviewed states so a human-reviewed
      // record is never silently wiped by a reprocess.
      if (document.reviewStatus !== "human_reviewed") {
        document.reviewState = null;
        document.reviewStatus = "unreviewed";
        document.reviewSource = null;
      }
      document.updatedAt = nowIso();
    }
    return job;
  });

  void (async () => {
    const runIdsByMode: Partial<Record<JobRunMode, string>> = {};
    for (let index = 0; index < queuedRuns.length; index += 1) {
      const queuedRun = queuedRuns[index];
      const remainingModes = queuedRuns.length - index - 1;
      const runId = await runSingleJobMode(
        payload.jobId,
        queuedRun.jobRunId,
        queuedRun.mode,
        selectedFileIds,
        fieldSnapshot,
        payload.settings,
        currentJob.commandId,
        remainingModes,
      );
      if (runId) {
        runIdsByMode[queuedRun.mode] = runId;
      }
    }

    mutateJob(payload.jobId, (job) => {
      finalizeSelectedDocuments(job, selectedFileIds, modes, runIdsByMode);
      const counts = (job.documents ?? []).reduce(
        (summary, document) => {
          if (selectedFileIds.includes(document.fileId)) {
            summary.anyFailed = summary.anyFailed || document.status === "failed";
            summary.anyProcessed = summary.anyProcessed || document.status === "processed";
          }
          return summary;
        },
        { anyFailed: false, anyProcessed: false },
      );
      const runError = (job.runs ?? []).find(
        (run) => queuedRuns.some((queued) => queued.jobRunId === run.jobRunId) && run.status === "failed" && run.error,
      )?.error;
      job.status = counts.anyFailed ? "failed" : "success";
      job.endedAt = nowIso();
      job.error = counts.anyFailed ? (runError ? `Run failed: ${runError}` : "One or more documents failed.") : undefined;
      return job;
    });
  })();

  return queuedJob;
}

export async function startRunJob(payload: StartRunRequest) {
  const hasFiles = Array.isArray(payload.files) && payload.files.length > 0;
  if (!hasFiles && !payload.sourceRunId) {
    throw new Error("Upload files or provide sourceRunId");
  }

  const commandConfig = getCommandConfig(payload.commandId);
  const mode: JobExecutionMode =
    payload.settings.adaptiveMode === "static" ? "strict" : "adaptive";
  const fieldConfigCurrent: JobFieldConfig[] = [];
  if (Array.isArray(payload.settings.customFields)) {
    for (const field of payload.settings.customFields) {
      const key = field.key?.trim();
      if (!key) {
        continue;
      }
      fieldConfigCurrent.push({
        name: key,
        description: field.description?.trim() || undefined,
      });
    }
  }

  let job = createWorkspaceJob({
    mode,
    fieldConfigCurrent,
    settings: redactSettings(payload.settings),
  });

  job = updateJob(job.jobId, {
    commandId: commandConfig.id,
    logs: [
      `Source run replay: ${payload.sourceRunId ?? "none"}`,
      ...job.logs,
    ],
  });

  if (hasFiles) {
    job = await addDocumentsToJob(job.jobId, payload.files);
  }

  if (payload.sourceRunId) {
    const replayFiles = copySourceRunInputs(payload.sourceRunId, job.uploadsPath ?? "");
    if (replayFiles.length > 0) {
      job = mutateJob(job.jobId, (current) => {
        const documents = [...(current.documents ?? [])];
        for (const file of replayFiles) {
          const fileId = randomUUID().replace(/-/g, "");
          const currentTarget = path.join(current.uploadsPath ?? "", file.storedAs);
          const renamedStoredName = `${fileId}__${sanitizeFilename(file.name)}`;
          const renamedTarget = path.join(current.uploadsPath ?? "", renamedStoredName);
          if (currentTarget !== renamedTarget && fs.existsSync(currentTarget)) {
            fs.renameSync(currentTarget, renamedTarget);
          }
          documents.push({
            fileId,
            fileName: file.name,
            storedName: renamedStoredName,
            size: file.size,
            selected: true,
            status: "loaded",
            errorSummary: null,
            reviewState: null,
            reviewStatus: "unreviewed",
            reviewSource: null,
            latestRoute: null,
            latestPolicy: null,
            latestRunId: null,
            latestDocId: null,
            createdAt: nowIso(),
            updatedAt: nowIso(),
            outcomes: [],
          });
        }
        current.documents = documents;
        return current;
      });
    }
  }

  if ((job.documents ?? []).length === 0) {
    throw new Error("No input artifacts found for run start");
  }

  job = await startJobRuns({
    jobId: job.jobId,
    selectedFileIds: (job.documents ?? []).map((document) => document.fileId),
    mode,
    fieldConfigCurrent,
    settings: payload.settings,
  });

  return job;
}
