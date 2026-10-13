import fs from "node:fs";
import path from "node:path";
import { createHash, randomUUID } from "node:crypto";
import { writeFileSync as writeFileAtomicSync } from "atomically";
import type {
  JobAHMNSummary,
  JobCounts,
  JobDocumentRecord,
  JobExecutionMode,
  JobFieldConfig,
  JobRunRecord,
  JobState,
  JobStatus,
} from "@/types/idpo";
import { loadRunnerConfig } from "@/server/config";
import {
  cleanupStagedUploads,
  jobUploadDirectory,
  MAX_UPLOAD_REQUEST_BYTES,
  MAX_UPLOAD_REQUEST_FILES,
  stageFileObject,
  type StagedUpload,
  UploadRequestError,
  validateStagedUpload,
} from "@/server/upload-stream";

const inMemoryJobs = new Map<string, JobStatus>();
const JOB_FILE_PATTERN = /^[a-f0-9]{32}\.json$/i;
const JOB_ID_PATTERN = /^[a-f0-9]{32}$/i;
const UPLOAD_KEY_PATTERN = /^[a-f0-9]{32}$/;
const SHA256_PATTERN = /^[a-f0-9]{64}$/;
const INTERRUPTED_JOB_ERROR = "Interrupted: the server restarted while this job was running. Run it again.";

// Kept on globalThis so dev-mode module reloads in the same process keep the same id.
const SERVER_INSTANCE_ID: string = (() => {
  const holder = globalThis as typeof globalThis & { __idpoServerInstanceId?: string };
  holder.__idpoServerInstanceId ??= randomUUID();
  return holder.__idpoServerInstanceId;
})();

function nowIso(): string {
  return new Date().toISOString();
}

function defaultJobName(createdAt?: string): string {
  const timestamp = typeof createdAt === "string" ? createdAt : nowIso();
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return "New job";
  }
  const stamp = new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
  return `Job ${stamp}`;
}

function emptyAhmnSummary(): JobAHMNSummary {
  return {
    jobProfile: "awaiting_run",
    memoryMatched: false,
    documentsWithAdvice: 0,
    documentsLoggedBack: 0,
    adviceInfluencedCount: 0,
    reviewedDocumentCount: 0,
    reviewedHumanCount: 0,
    reviewedAiCount: 0,
    reviewedFeedbackLoggedCount: 0,
    reviewedFeedbackPendingCount: 0,
    jobOverlayPolicies: 0,
    jobOverlayReady: false,
    adaptationSummary: "No completed runs yet.",
  };
}

function computeCounts(documents: JobDocumentRecord[]): JobCounts {
  return documents.reduce<JobCounts>(
    (counts, document) => {
      if (document.status === "loaded") {
        counts.loadedCount += 1;
      } else if (document.status === "processing") {
        counts.processingCount += 1;
      } else if (document.status === "processed") {
        counts.processedCount += 1;
      } else if (document.status === "failed") {
        counts.failedCount += 1;
      }
      return counts;
    },
    {
      loadedCount: 0,
      processingCount: 0,
      processedCount: 0,
      failedCount: 0,
    },
  );
}

function sanitizeFilename(name: string): string {
  return name.replace(/[^a-zA-Z0-9._-]/g, "_");
}

function normalizeFieldConfig(value: unknown): JobFieldConfig[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const fields: JobFieldConfig[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const entry = item as Record<string, unknown>;
    const name = typeof entry.name === "string" ? entry.name.trim() : "";
    if (!name) {
      continue;
    }
    fields.push({
      name,
      description: typeof entry.description === "string" ? entry.description.trim() || undefined : undefined,
    });
  }
  return fields;
}

function failInterruptedJob(job: JobStatus, documents: JobDocumentRecord[], runs: JobRunRecord[]): void {
  if (job.status !== "running" || job.serverInstanceId === SERVER_INSTANCE_ID) {
    return;
  }
  const endedAt = nowIso();
  job.status = "failed";
  job.error = INTERRUPTED_JOB_ERROR;
  job.endedAt = job.endedAt ?? endedAt;
  for (const run of runs) {
    if (run.status === "running" || run.status === "queued") {
      run.status = "failed";
      run.error = INTERRUPTED_JOB_ERROR;
      run.endedAt = run.endedAt ?? endedAt;
    }
  }
  for (const document of documents) {
    if (document.status === "processing") {
      document.status = "failed";
      document.errorSummary = INTERRUPTED_JOB_ERROR;
    }
  }
}

function repairCompletedRuns(job: JobStatus, documents: JobDocumentRecord[], runs: JobRunRecord[]): void {
  const terminalJob = job.status === "success" || job.status === "failed";
  const hasProcessingDocuments = documents.some((document) => document.status === "processing");
  if (!terminalJob || hasProcessingDocuments) {
    return;
  }

  for (const run of runs) {
    if (run.status !== "running" && run.status !== "queued") {
      continue;
    }

    const selectedSet = new Set(run.selectedFileIds);
    const matchingOutcomes = documents
      .filter((document) => selectedSet.has(document.fileId))
      .flatMap((document) => document.outcomes.filter((outcome) => outcome.mode === run.mode));

    if (matchingOutcomes.length === 0) {
      if (job.status === "failed") {
        run.status = "failed";
        run.error = run.error ?? job.error ?? "Run did not complete successfully.";
        run.endedAt = run.endedAt ?? job.endedAt ?? nowIso();
      }
      continue;
    }

    const runIdCounts = new Map<string, number>();
    for (const outcome of matchingOutcomes) {
      runIdCounts.set(outcome.runId, (runIdCounts.get(outcome.runId) ?? 0) + 1);
    }
    const inferredRunId =
      [...runIdCounts.entries()].sort((left, right) => right[1] - left[1])[0]?.[0] ?? null;
    const inferredOutcomes = inferredRunId
      ? matchingOutcomes.filter((outcome) => outcome.runId === inferredRunId)
      : matchingOutcomes;
    const processedCount = inferredOutcomes.filter((outcome) => outcome.status === "processed").length;
    const failedCount = Math.max(run.selectedFileIds.length - processedCount, 0);

    run.runId = run.runId ?? inferredRunId;
    run.status = failedCount > 0 ? "failed" : "success";
    run.processedCount = processedCount;
    run.failedCount = failedCount;
    run.endedAt = run.endedAt ?? job.endedAt ?? nowIso();
  }
}

function normalizeDocuments(value: unknown): JobDocumentRecord[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const documents: JobDocumentRecord[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const entry = item as Record<string, unknown>;
    const fileId = typeof entry.fileId === "string" ? entry.fileId : "";
    const fileName = typeof entry.fileName === "string" ? entry.fileName : "";
    const storedName = typeof entry.storedName === "string" ? entry.storedName : "";
    if (!fileId || !fileName || !storedName) {
      continue;
    }
    const outcomes: JobDocumentRecord["outcomes"] = [];
    if (Array.isArray(entry.outcomes)) {
      for (const outcome of entry.outcomes) {
        if (!outcome || typeof outcome !== "object") {
          continue;
        }
        const record = outcome as Record<string, unknown>;
        const runId = typeof record.runId === "string" ? record.runId : "";
        if (!runId) {
          continue;
        }
        outcomes.push({
          runId,
          mode: record.mode === "strict" ? "strict" : "adaptive",
          docId: typeof record.docId === "string" ? record.docId : null,
          status:
            record.status === "processing" || record.status === "failed" || record.status === "loaded"
              ? record.status
              : "processed",
          route: typeof record.route === "string" ? record.route : null,
          policy: typeof record.policy === "string" ? record.policy : null,
          errorSummary: typeof record.errorSummary === "string" ? record.errorSummary : null,
          reviewState: typeof record.reviewState === "string" ? record.reviewState : null,
          reviewStatus:
            record.reviewStatus === "ai_validated" || record.reviewStatus === "human_reviewed" || record.reviewStatus === "unreviewed"
              ? record.reviewStatus
              : null,
          reviewSource: record.reviewSource === "ai" || record.reviewSource === "human" ? record.reviewSource : null,
          reviewStage: record.reviewStage === "local" || record.reviewStage === "cloud" ? record.reviewStage : null,
          reviewConfidence: typeof record.reviewConfidence === "number" ? record.reviewConfidence : null,
          fieldValues:
            record.fieldValues && typeof record.fieldValues === "object" && !Array.isArray(record.fieldValues)
              ? (record.fieldValues as Record<string, string>)
              : {},
          adviceInfluenced: Boolean(record.adviceInfluenced),
          feedbackLogged: Boolean(record.feedbackLogged),
          fallbackReason: typeof record.fallbackReason === "string" ? record.fallbackReason : null,
          exactPrecision: typeof record.exactPrecision === "number" ? record.exactPrecision : null,
          exactRecall: typeof record.exactRecall === "number" ? record.exactRecall : null,
          exactF1: typeof record.exactF1 === "number" ? record.exactF1 : null,
          expectedFieldValues:
            record.expectedFieldValues &&
            typeof record.expectedFieldValues === "object" &&
            !Array.isArray(record.expectedFieldValues)
              ? (record.expectedFieldValues as Record<string, string>)
              : null,
        });
      }
    }
    documents.push({
      fileId,
      fileName,
      storedName,
      size: typeof entry.size === "number" ? entry.size : 0,
      selected: typeof entry.selected === "boolean" ? entry.selected : true,
      status: entry.status === "processing" || entry.status === "processed" || entry.status === "failed" ? entry.status : "loaded",
      errorSummary: typeof entry.errorSummary === "string" ? entry.errorSummary : null,
      reviewState: typeof entry.reviewState === "string" ? entry.reviewState : null,
      reviewStatus:
        entry.reviewStatus === "ai_validated" || entry.reviewStatus === "human_reviewed" || entry.reviewStatus === "unreviewed"
          ? entry.reviewStatus
          : null,
      reviewSource: entry.reviewSource === "ai" || entry.reviewSource === "human" ? entry.reviewSource : null,
      reviewStage: entry.reviewStage === "local" || entry.reviewStage === "cloud" ? entry.reviewStage : null,
      reviewConfidence: typeof entry.reviewConfidence === "number" ? entry.reviewConfidence : null,
      latestRoute: typeof entry.latestRoute === "string" ? entry.latestRoute : null,
      latestPolicy: typeof entry.latestPolicy === "string" ? entry.latestPolicy : null,
      latestRunId: typeof entry.latestRunId === "string" ? entry.latestRunId : null,
      latestDocId: typeof entry.latestDocId === "string" ? entry.latestDocId : null,
      createdAt: typeof entry.createdAt === "string" ? entry.createdAt : nowIso(),
      updatedAt: typeof entry.updatedAt === "string" ? entry.updatedAt : nowIso(),
      outcomes,
    });
  }
  return documents;
}

function normalizeRuns(value: unknown): JobRunRecord[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const runs: JobRunRecord[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const entry = item as Record<string, unknown>;
    const jobRunId = typeof entry.jobRunId === "string" ? entry.jobRunId : "";
    if (!jobRunId) {
      continue;
    }
    const status: JobState =
      entry.status === "draft" || entry.status === "queued" || entry.status === "running" || entry.status === "success" || entry.status === "failed"
        ? entry.status
        : "queued";
    runs.push({
      jobRunId,
      runId: typeof entry.runId === "string" ? entry.runId : null,
      mode: entry.mode === "strict" ? "strict" : "adaptive",
      status,
      createdAt: typeof entry.createdAt === "string" ? entry.createdAt : nowIso(),
      startedAt: typeof entry.startedAt === "string" ? entry.startedAt : undefined,
      endedAt: typeof entry.endedAt === "string" ? entry.endedAt : undefined,
      fieldSnapshot: normalizeFieldConfig(entry.fieldSnapshot),
      selectedFileIds: Array.isArray(entry.selectedFileIds)
        ? entry.selectedFileIds.filter((value): value is string => typeof value === "string")
        : [],
      runPath: typeof entry.runPath === "string" ? entry.runPath : null,
      error: typeof entry.error === "string" ? entry.error : null,
      processedCount: typeof entry.processedCount === "number" ? entry.processedCount : undefined,
      failedCount: typeof entry.failedCount === "number" ? entry.failedCount : undefined,
      adviceDocumentCount: typeof entry.adviceDocumentCount === "number" ? entry.adviceDocumentCount : undefined,
      loggedFeedbackCount: typeof entry.loggedFeedbackCount === "number" ? entry.loggedFeedbackCount : undefined,
    });
  }
  return runs;
}

function getJobFile(jobId: string): string {
  const config = loadRunnerConfig();
  return path.join(config.jobsDir, `${jobId}.json`);
}

function getJobUploadDir(jobId: string): string {
  const config = loadRunnerConfig();
  return path.join(config.uploadsDir, `job_${jobId}`);
}

function normalizeJob(job: JobStatus): JobStatus {
  const createdAt = typeof job.createdAt === "string" ? job.createdAt : job.startedAt || nowIso();
  const startedAt = typeof job.startedAt === "string" ? job.startedAt : createdAt;
  const documents = normalizeDocuments(job.documents);
  const runs = normalizeRuns(job.runs);
  failInterruptedJob(job, documents, runs);
  repairCompletedRuns(job, documents, runs);
  const counts = computeCounts(documents);
  const uploadsPath = typeof job.uploadsPath === "string" && job.uploadsPath.trim()
    ? job.uploadsPath
    : getJobUploadDir(job.jobId);

  const normalized: JobStatus = {
    ...job,
    status:
      job.status === "draft" || job.status === "queued" || job.status === "running" || job.status === "success" || job.status === "failed"
        ? job.status
        : "draft",
    createdAt,
    startedAt,
    commandId: typeof job.commandId === "string" ? job.commandId : loadRunnerConfig().defaultCommandId,
    runId: typeof job.runId === "string" ? job.runId : null,
    runPath: typeof job.runPath === "string" ? job.runPath : null,
    logs: Array.isArray(job.logs) ? job.logs.filter((line): line is string => typeof line === "string") : [],
    settings: job.settings && typeof job.settings === "object" ? job.settings : {},
    jobName:
      typeof job.jobName === "string" && job.jobName.trim()
        ? job.jobName.trim()
        : defaultJobName(createdAt),
    mode: job.mode === "adaptive" || job.mode === "strict" || job.mode === "both" ? job.mode : "adaptive",
    fieldConfigCurrent: normalizeFieldConfig(job.fieldConfigCurrent),
    documents,
    runs,
    ahmnSummary:
      job.ahmnSummary && typeof job.ahmnSummary === "object"
        ? {
            ...emptyAhmnSummary(),
            ...(job.ahmnSummary as JobAHMNSummary),
          }
        : emptyAhmnSummary(),
    counts,
    latestRunId: typeof job.latestRunId === "string" ? job.latestRunId : job.runId ?? null,
    uploadsPath,
  };

  fs.mkdirSync(uploadsPath, { recursive: true });
  return normalized;
}

function claimIfRunning(job: JobStatus): JobStatus {
  return job.status === "running" ? { ...job, serverInstanceId: SERVER_INSTANCE_ID } : job;
}

function persistJob(job: JobStatus): void {
  const normalized = normalizeJob(claimIfRunning(job));
  const filePath = getJobFile(normalized.jobId);
  writeFileAtomicSync(filePath, JSON.stringify(normalized, null, 2), "utf8");
  inMemoryJobs.set(normalized.jobId, normalized);
}

export function createWorkspaceJob(
  options?: {
    ownerUserId?: string;
    jobName?: string;
    mode?: JobExecutionMode;
    fieldConfigCurrent?: JobFieldConfig[];
    settings?: Record<string, unknown>;
  },
): JobStatus {
  const config = loadRunnerConfig();
  const jobId = randomUUID().replace(/-/g, "");
  const createdAt = nowIso();
  const uploadsPath = getJobUploadDir(jobId);
  fs.mkdirSync(uploadsPath, { recursive: true });

  const job: JobStatus = {
    jobId,
    ownerUserId: options?.ownerUserId,
    status: "draft",
    createdAt,
    startedAt: createdAt,
    commandId: config.defaultCommandId,
    runId: null,
    runPath: null,
    logs: [],
    settings: options?.settings ?? {},
    jobName: options?.jobName?.trim() || defaultJobName(createdAt),
    mode: options?.mode ?? "adaptive",
    fieldConfigCurrent: options?.fieldConfigCurrent ?? [],
    documents: [],
    runs: [],
    ahmnSummary: emptyAhmnSummary(),
    counts: computeCounts([]),
    latestRunId: null,
    uploadsPath,
  };

  persistJob(job);
  return job;
}

export async function addDocumentsToJob(jobId: string, files: File[]): Promise<JobStatus> {
  if (!Array.isArray(files) || files.length === 0) {
    return getJobOrThrow(jobId);
  }
  if (files.length > MAX_UPLOAD_REQUEST_FILES) throw new UploadRequestError("Upload exceeds 32 files.", 413);
  if (files.reduce((size, file) => size + file.size, 0) > MAX_UPLOAD_REQUEST_BYTES) {
    throw new UploadRequestError("Upload exceeds 32 MiB.", 413);
  }
  getJobOrThrow(jobId);
  const staged: StagedUpload[] = [];
  try {
    for (const file of files) staged.push(await stageFileObject(jobId, file));
    return addStagedDocumentsToJob(jobId, staged);
  } finally {
    cleanupStagedUploads(staged);
  }
}

function stagedFileSha256(filePath: string): string {
  const hash = createHash("sha256");
  const handle = fs.openSync(filePath, "r");
  const buffer = Buffer.allocUnsafe(1024 * 1024);
  try {
    let read: number;
    while ((read = fs.readSync(handle, buffer, 0, buffer.length, null)) > 0) {
      hash.update(buffer.subarray(0, read));
    }
  } finally { fs.closeSync(handle); }
  return hash.digest("hex");
}

function uploadReceipt(job: JobStatus, key: string): NonNullable<JobStatus["uploadReceipts"]>[string] | null {
  const raw = job.uploadReceipts?.[key];
  if (raw === undefined) return null;
  if (!raw || raw.contractVersion !== 1 || !SHA256_PATTERN.test(raw.payloadSha256) ||
    !Array.isArray(raw.files) || raw.files.length < 1 || raw.files.length > MAX_UPLOAD_REQUEST_FILES ||
    raw.files.some((file) => !file || !JOB_ID_PATTERN.test(file.fileId) ||
      !SHA256_PATTERN.test(file.sourceSha256)) ||
    new Set(raw.files.map((file) => file.fileId)).size !== raw.files.length) {
    throw new UploadRequestError("The upload retry receipt is invalid.", 409);
  }
  return raw;
}

export function addStagedDocumentsToJob(jobId: string, staged: readonly StagedUpload[],
  idempotencyKey?: string): JobStatus {
  const current = getJobOrThrow(jobId);
  if (idempotencyKey !== undefined && !UPLOAD_KEY_PATTERN.test(idempotencyKey)) {
    throw new UploadRequestError("Invalid upload idempotency key.");
  }
  if (staged.length < 1 || staged.length > MAX_UPLOAD_REQUEST_FILES) {
    throw new UploadRequestError("Upload requires 1–32 files.");
  }
  const uploadDir = jobUploadDirectory(jobId);
  if (path.resolve(current.uploadsPath ?? "") !== path.resolve(uploadDir)) {
    throw new UploadRequestError("Job upload directory is invalid.");
  }
  for (const file of staged) validateStagedUpload(jobId, file);
  const sourceHashes = idempotencyKey ? staged.map((file) => stagedFileSha256(file.tempPath)) : [];
  const payloadSha256 = idempotencyKey ? createHash("sha256").update(JSON.stringify(staged.map((file, index) =>
    ({ name: file.name, type: file.type, size: file.size, sha256: sourceHashes[index] })))).digest("hex") : null;
  if (idempotencyKey) {
    const receipt = uploadReceipt(current, idempotencyKey);
    if (receipt) {
      if (receipt.payloadSha256 !== payloadSha256 || receipt.files.length !== staged.length) {
        throw new UploadRequestError("This upload retry key was used for different file contents.", 409);
      }
      for (const [index, file] of receipt.files.entries()) {
        const document = current.documents?.find((item) => item.fileId === file.fileId);
        const original = document && path.resolve(uploadDir, document.storedName);
        if (!document || document.fileName !== staged[index].name || document.size !== staged[index].size ||
          !original || path.dirname(original) !== path.resolve(uploadDir) ||
          !fs.existsSync(original) || !fs.lstatSync(original).isFile() ||
          stagedFileSha256(original) !== file.sourceSha256 ||
          sourceHashes[index] !== file.sourceSha256) {
          throw new UploadRequestError("The original upload receipt no longer matches this job.", 409);
        }
      }
      return current;
    }
  }

  const moved: string[] = [];
  const records: JobDocumentRecord[] = [];
  try {
    for (const file of staged) {
      const fileId = randomUUID().replace(/-/g, "");
      const storedName = `${fileId}__${sanitizeFilename(file.name)}`;
      const target = path.join(uploadDir, storedName);
      if (fs.existsSync(target)) throw new UploadRequestError("Upload artifact name collision.");
      fs.renameSync(file.tempPath, target);
      moved.push(target);
      const timestamp = nowIso();
      records.push({
        fileId, fileName: file.name, storedName, size: file.size,
        selected: true, status: "loaded", errorSummary: null, reviewState: null,
        reviewStatus: "unreviewed", reviewSource: null, latestRoute: null,
        latestPolicy: null, latestRunId: null, latestDocId: null,
        createdAt: timestamp, updatedAt: timestamp, outcomes: [],
      });
    }
    return mutateJob(jobId, (job) => {
      if (path.resolve(job.uploadsPath ?? "") !== path.resolve(uploadDir)) {
        throw new UploadRequestError("Job upload directory changed during upload.");
      }
      job.documents = [...(job.documents ?? []), ...records];
      if (idempotencyKey && payloadSha256) {
        if (uploadReceipt(job, idempotencyKey)) {
          throw new UploadRequestError("This upload retry key changed during commit.", 409);
        }
        job.uploadReceipts = { ...job.uploadReceipts,
          [idempotencyKey]: { contractVersion: 1, payloadSha256,
            files: records.map((record, index) => ({ fileId: record.fileId,
              sourceSha256: sourceHashes[index] })) } };
      }
      if (job.status !== "running") job.status = "queued";
      return job;
    });
  } catch (error) {
    for (const target of moved) fs.rmSync(target, { force: true });
    throw error;
  }
}

export function getJobOrThrow(jobId: string): JobStatus {
  const job = getJob(jobId);
  if (!job) {
    throw new Error(`Job ${jobId} not found`);
  }
  return job;
}

export function mutateJob(jobId: string, mutator: (job: JobStatus) => JobStatus | void): JobStatus {
  const current = getJobOrThrow(jobId);
  const candidate = mutator(structuredClone(current));
  const next = normalizeJob(claimIfRunning({ ...(candidate ?? current), ownerUserId: current.ownerUserId } as JobStatus));
  persistJob(next);
  return next;
}

export function appendJobLog(jobId: string, line: string): JobStatus {
  return mutateJob(jobId, (job) => {
    const trimmed = line.trimEnd();
    if (trimmed.length > 0) {
      const logs = Array.isArray(job.logs) ? [...job.logs, trimmed] : [trimmed];
      if (logs.length > 2000) {
        logs.splice(0, logs.length - 2000);
      }
      job.logs = logs;
    }
    return job;
  });
}

export function updateJob(jobId: string, patch: Partial<JobStatus>): JobStatus {
  const current = getJobOrThrow(jobId);
  const next: JobStatus = normalizeJob(claimIfRunning({
    ...current,
    ...patch,
    ownerUserId: current.ownerUserId,
    logs: patch.logs ?? current.logs,
    settings: patch.settings ?? current.settings,
  }));
  persistJob(next);
  return next;
}

export function setJobRunning(jobId: string): JobStatus {
  return updateJob(jobId, { status: "running", startedAt: nowIso(), error: undefined });
}

export function setJobSuccess(jobId: string, runId: string | null, runPath: string | null): JobStatus {
  return updateJob(jobId, {
    status: "success",
    runId,
    runPath,
    latestRunId: runId,
    endedAt: nowIso(),
  });
}

export function setJobFailed(jobId: string, error: string): JobStatus {
  return updateJob(jobId, {
    status: "failed",
    error,
    endedAt: nowIso(),
  });
}

export function getJob(jobId: string): JobStatus | null {
  // Route params arrive URL-decoded, so an unchecked id could point the file lookup outside the jobs folder.
  const filePath = JOB_ID_PATTERN.test(jobId) ? getJobFile(jobId) : null;
  if (filePath && fs.existsSync(filePath)) {
    try {
      const job = normalizeJob(JSON.parse(fs.readFileSync(filePath, "utf-8")) as JobStatus);
      inMemoryJobs.set(jobId, job);
      return job;
    } catch {
      return null;
    }
  }

  return inMemoryJobs.get(jobId) ?? null;
}

export function listJobs(limit = 50): JobStatus[] {
  const config = loadRunnerConfig();
  const files = fs
    .readdirSync(config.jobsDir, { withFileTypes: true })
    .filter((entry) => entry.isFile() && JOB_FILE_PATTERN.test(entry.name))
    .map((entry) => path.join(config.jobsDir, entry.name))
    .sort((a, b) => {
      const aStat = fs.statSync(a);
      const bStat = fs.statSync(b);
      return bStat.mtimeMs - aStat.mtimeMs;
    })
    .slice(0, limit);

  return files
    .map((filePath) => {
      try {
        const job = normalizeJob(JSON.parse(fs.readFileSync(filePath, "utf-8")) as JobStatus);
        inMemoryJobs.set(job.jobId, job);
        return job;
      } catch {
        return null;
      }
    })
    .filter((job): job is JobStatus => job !== null);
}
