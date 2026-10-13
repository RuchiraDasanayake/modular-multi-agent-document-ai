"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import { useParams } from "next/navigation";
import { IdpoCard } from "@/components/idpo/card";
import { StatusBadge } from "@/components/idpo/status-badge";
import { Icon } from "@/components/icons";
import { api } from "@/lib/api";
import { idpoApi } from "@/lib/idpo-api";
import { UploadBatchError } from "@/lib/upload-batches";
import type {
  JobDocumentRecord,
  JobDocumentRunOutcome,
  JobExecutionMode,
  JobFieldConfig,
  JobRunMode,
  JobStatus,
  JobValidationContextManualInput,
} from "@/types/idpo";

const CONFIG_PATH = "configs/idpo_research_config.json";
const SYSTEM_DEFAULT_LOCAL_MODEL = "qwen3.5:9b";
const LOCAL_MODEL_OPTIONS = [
  { value: "", label: `System default (${SYSTEM_DEFAULT_LOCAL_MODEL})` },
  { value: "phi3:mini", label: "phi3:mini (faster, lower accuracy)" },
];
const MODE_OPTIONS: { value: JobExecutionMode; label: string }[] = [
  { value: "adaptive", label: "Adaptive: AHMN picks the policy" },
  { value: "strict", label: "Strict: default policy only" },
  { value: "both", label: "Both: run each and compare" },
];
const ACCEPTED_FILE_TYPES = ".pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.txt,.json,.docx,.xlsx,.pptx,.html,.eml";

const secondaryButton =
  "inline-flex items-center gap-2 rounded-xl border border-slate-300 px-3.5 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800";
const primaryButton =
  "inline-flex items-center gap-2 rounded-xl bg-cyan-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-50";
const linkStyle = "font-medium text-cyan-700 hover:text-cyan-800 dark:text-cyan-300 dark:hover:text-cyan-200";
const inputStyle =
  "w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-white";

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function formatDate(value: string | undefined | null): string {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function resultModeForJob(mode: JobExecutionMode): JobRunMode {
  return mode === "strict" ? "strict" : "adaptive";
}

function normalizeFieldKey(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, "_");
}

function formatFieldLabel(name: string): string {
  const spaced = name.replace(/_/g, " ").trim();
  return spaced ? spaced.charAt(0).toUpperCase() + spaced.slice(1) : name;
}

function getOutcome(document: JobDocumentRecord, mode: JobRunMode): JobDocumentRunOutcome | null {
  const matches = document.outcomes.filter((outcome) => outcome.mode === mode);
  return matches.length > 0 ? matches[matches.length - 1] ?? null : null;
}

function formatDuration(ms: number | null): string {
  if (ms == null || !Number.isFinite(ms) || ms < 0) {
    return "—";
  }
  const totalSeconds = Math.floor(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds}s`;
  }
  return `${seconds}s`;
}

function parseTimestamp(value: string | undefined | null): number | null {
  if (!value) {
    return null;
  }
  const time = new Date(value).getTime();
  return Number.isNaN(time) ? null : time;
}

function getOutcomeFieldValue(outcome: JobDocumentRunOutcome | null, fieldName: string): string {
  if (!outcome) {
    return "—";
  }
  const direct = outcome.fieldValues[fieldName];
  if (typeof direct === "string" && direct.trim().length > 0) {
    return direct;
  }
  const normalized = outcome.fieldValues[normalizeFieldKey(fieldName)];
  if (typeof normalized === "string" && normalized.trim().length > 0) {
    return normalized;
  }
  return "—";
}

function shortId(value: string): string {
  return value.slice(0, 8);
}

function displayError(message: string | null | undefined): string | null {
  if (!message) {
    return null;
  }
  if (/ENOENT/i.test(message)) {
    return "Processing did not start because Python could not be found. Select the file and use Retry failed.";
  }
  return message.replace(/^Run failed:\s*/i, "");
}

function formatReviewState(reviewState: string | null | undefined): string {
  if (!reviewState) {
    return "";
  }
  return reviewState.replace(/\(s\)/g, "s").replace(/\b1 issues\b/g, "1 issue").replace(/\s*\|\s*/g, " · ");
}

function formatList(values: string[] | undefined): string {
  return values && values.length > 0 ? values.join(", ") : "—";
}

function listToTextarea(value: string[] | undefined): string {
  return value && value.length > 0 ? value.join("\n") : "";
}

function textareaToList(value: string): string[] {
  return value
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function hasActiveRun(job: JobStatus | null): boolean {
  return Boolean(
    job &&
      (job.status === "queued" ||
        job.status === "running" ||
        (job.documents ?? []).some((document) => document.status === "processing")),
  );
}

function SummaryTile({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 dark:border-slate-800 dark:bg-slate-950/40" title={hint}>
      <div className="text-xs text-slate-500 dark:text-slate-400">{label}</div>
      <div className="mt-1 text-base font-semibold text-slate-900 dark:text-white">{value}</div>
    </div>
  );
}

export function JobDetailPage() {
  const params = useParams<{ jobId: string }>();
  const jobId = decodeURIComponent(params.jobId);
  const uploadRef = useRef<HTMLInputElement>(null);
  const hydratedJobIdRef = useRef<string | null>(null);

  const [job, setJob] = useState<JobStatus | null>(null);
  const [canonicalRunnerAvailable, setCanonicalRunnerAvailable] = useState(true);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busyAction, setBusyAction] = useState<"upload" | "process" | "retry" | "review" | null>(null);
  const [uploadProgress, setUploadProgress] = useState<{ uploaded: number; total: number } | null>(null);
  const [unconfirmedFiles, setUnconfirmedFiles] = useState<File[]>([]);
  const [unconfirmedRetryKey, setUnconfirmedRetryKey] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [pollFailed, setPollFailed] = useState(false);
  const [jobName, setJobName] = useState("");
  const [mode, setMode] = useState<JobExecutionMode>("adaptive");
  const [fieldConfig, setFieldConfig] = useState<JobFieldConfig[]>([]);
  const [selectedFileIds, setSelectedFileIds] = useState<string[]>([]);
  const [newFieldName, setNewFieldName] = useState("");
  const [newFieldDescription, setNewFieldDescription] = useState("");
  const [resultMode, setResultMode] = useState<JobRunMode>("adaptive");
  const [maxCostPerDoc, setMaxCostPerDoc] = useState("");
  const [escalationEnabled, setEscalationEnabled] = useState(true);
  const [localModel, setLocalModel] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [showRoutingDetails, setShowRoutingDetails] = useState(false);
  const [showReviewContext, setShowReviewContext] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [reviewContextDraft, setReviewContextDraft] = useState({
    jobPurpose: "",
    knownVendors: "",
    fieldClarifications: "",
    validationNotes: "",
  });
  const [nowMs, setNowMs] = useState(() => Date.now());

  async function loadJob(activeJobId = jobId, background = false) {
    try {
      if (!background) {
        setLoading(true);
      }
      const payload = await idpoApi.getJob(activeJobId);
      setJob(payload);
      setCanonicalRunnerAvailable(payload.canonicalRunnerAvailable !== false);
      setPollFailed(false);
      if (!background) {
        setError("");
      }
    } catch (err) {
      // A failed background poll keeps the last good data on screen.
      if (background) {
        setPollFailed(true);
      } else {
        setError(err instanceof Error ? err.message : "Failed to load job");
      }
    } finally {
      if (!background) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    void loadJob();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  useEffect(() => {
    let active = true;
    void api.me().then((user) => {
      if (active) setIsAdmin(user.role === "admin");
    }).catch(() => {
      if (active) setIsAdmin(false);
    });
    return () => { active = false; };
  }, []);

  // Form state comes from the first load only, so polling never overwrites what the user is editing.
  useEffect(() => {
    if (!job || hydratedJobIdRef.current === job.jobId) {
      return;
    }
    hydratedJobIdRef.current = job.jobId;
    const jobMode = job.mode ?? "adaptive";
    const settings = asRecord(job.settings) ?? {};
    setJobName(job.jobName?.trim() || "");
    setMode(jobMode);
    setResultMode(resultModeForJob(jobMode));
    setFieldConfig(job.fieldConfigCurrent ?? []);
    setSelectedFileIds((job.documents ?? []).filter((document) => document.selected).map((document) => document.fileId));
    setMaxCostPerDoc(
      typeof settings.maxCostPerDoc === "number" && Number.isFinite(settings.maxCostPerDoc) ? String(settings.maxCostPerDoc) : "",
    );
    setEscalationEnabled(typeof settings.escalationEnabled === "boolean" ? settings.escalationEnabled : true);
    setLocalModel(typeof settings.llmLocalModel === "string" ? settings.llmLocalModel.trim() : "");
  }, [job]);

  const runActive = hasActiveRun(job);

  useEffect(() => {
    if (!runActive) {
      return undefined;
    }
    const pollTimer = window.setInterval(() => {
      void loadJob(jobId, true);
    }, 2000);
    const clockTimer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => {
      window.clearInterval(pollTimer);
      window.clearInterval(clockTimer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runActive, jobId]);

  useEffect(() => {
    if (!showReviewContext) {
      return undefined;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setShowReviewContext(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [showReviewContext]);

  const documents = useMemo(() => job?.documents ?? [], [job]);
  const runs = useMemo(() => job?.runs ?? [], [job]);
  const orderedRuns = useMemo(
    () => [...runs].sort((left, right) => right.createdAt.localeCompare(left.createdAt)),
    [runs],
  );
  const activeRun = useMemo(
    () => orderedRuns.find((run) => run.status === "running" || run.status === "queued") ?? null,
    [orderedRuns],
  );

  const queueSummary = useMemo(
    () =>
      documents.reduce(
        (summary, document) => {
          summary[document.status] += 1;
          return summary;
        },
        { loaded: 0, processing: 0, processed: 0, failed: 0 },
      ),
    [documents],
  );

  const selectableDocumentIds = useMemo(
    () => documents.filter((document) => document.status !== "processing").map((document) => document.fileId),
    [documents],
  );
  const selectedDocuments = useMemo(
    () => documents.filter((document) => selectedFileIds.includes(document.fileId)),
    [documents, selectedFileIds],
  );
  const selectedFailedDocuments = useMemo(
    () => selectedDocuments.filter((document) => document.status === "failed"),
    [selectedDocuments],
  );
  const allSelectableSelected =
    selectableDocumentIds.length > 0 && selectableDocumentIds.every((fileId) => selectedFileIds.includes(fileId));
  const someSelected = selectedFileIds.length > 0;

  async function patchJob(payload: {
    jobName?: string;
    mode?: JobExecutionMode;
    fieldConfigCurrent?: JobFieldConfig[];
    selectedFileIds?: string[];
    settings?: {
      llmLocalModel?: string | null;
    };
  }) {
    setSaving(true);
    try {
      const updated = await idpoApi.updateJob(jobId, payload);
      setJob(updated);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update job");
    } finally {
      setSaving(false);
    }
  }

  function acceptUploadedJob(updated: JobStatus) {
    setJob(updated);
    setSelectedFileIds((current) => {
      const known = new Set(current);
      const next = [...current];
      for (const document of updated.documents ?? []) {
        if (!known.has(document.fileId) && document.selected) {
          next.push(document.fileId);
          known.add(document.fileId);
        }
      }
      return next;
    });
  }

  async function handleUpload(files: FileList | File[] | null, retryKey?: string) {
    if (!files || files.length === 0) {
      return;
    }
    const selectedFiles = Array.from(files);
    setUnconfirmedFiles([]);
    setUnconfirmedRetryKey(null);
    setUploadProgress({ uploaded: 0, total: selectedFiles.length });
    setSaving(true);
    setBusyAction("upload");
    try {
      const updated = await idpoApi.uploadJobDocuments(jobId, selectedFiles, (progress) => {
        acceptUploadedJob(progress.latest);
        setUploadProgress({ uploaded: progress.uploaded, total: progress.total });
      }, retryKey);
      acceptUploadedJob(updated);
      setError("");
    } catch (err) {
      if (err instanceof UploadBatchError) {
        if (err.latest) acceptUploadedJob(err.latest as JobStatus);
        setUnconfirmedFiles(err.remaining);
        setUnconfirmedRetryKey(err.retryKey);
        setError(`${err.uploaded} of ${err.total} files uploaded. ${err.remaining.length} not confirmed: ${err.message}`);
      } else {
        setError(err instanceof Error ? err.message : "Failed to upload documents");
      }
    } finally {
      if (uploadRef.current) uploadRef.current.value = "";
      setSaving(false);
      setBusyAction(null);
    }
  }

  function handleDragOver(event: DragEvent<HTMLElement>) {
    if (!Array.from(event.dataTransfer.types).includes("Files")) {
      return;
    }
    event.preventDefault();
    setDragActive(true);
  }

  function handleDrop(event: DragEvent<HTMLElement>) {
    event.preventDefault();
    setDragActive(false);
    if (!saving) {
      void handleUpload(event.dataTransfer.files);
    }
  }

  async function handleToggleSelection(fileId: string) {
    const next = selectedFileIds.includes(fileId)
      ? selectedFileIds.filter((value) => value !== fileId)
      : [...selectedFileIds, fileId];
    setSelectedFileIds(next);
    await patchJob({ selectedFileIds: next });
  }

  async function handleToggleAll() {
    const next = allSelectableSelected ? [] : selectableDocumentIds;
    setSelectedFileIds(next);
    await patchJob({ selectedFileIds: next });
  }

  async function handleBlurJobName() {
    if (!job) {
      return;
    }
    if ((job.jobName?.trim() || "") === jobName.trim()) {
      return;
    }
    await patchJob({ jobName: jobName.trim() });
  }

  async function handleChangeMode(nextMode: JobExecutionMode) {
    setMode(nextMode);
    setResultMode(resultModeForJob(nextMode));
    await patchJob({ mode: nextMode });
  }

  async function handleChangeLocalModel(nextModel: string) {
    setLocalModel(nextModel);
    await patchJob({
      settings: {
        llmLocalModel: nextModel.trim() || null,
      },
    });
  }

  async function handleAddField() {
    const name = newFieldName.trim();
    if (!name) {
      return;
    }
    const nextFields = [
      ...fieldConfig,
      {
        name,
        description: newFieldDescription.trim() || undefined,
      },
    ];
    setFieldConfig(nextFields);
    setNewFieldName("");
    setNewFieldDescription("");
    await patchJob({ fieldConfigCurrent: nextFields });
  }

  async function handleRemoveField(index: number) {
    const nextFields = fieldConfig.filter((_, currentIndex) => currentIndex !== index);
    setFieldConfig(nextFields);
    await patchJob({ fieldConfigCurrent: nextFields });
  }

  async function startRun(modeOverride?: JobExecutionMode, retryFailedOnly = false) {
    const effectiveMode = modeOverride ?? mode;
    const targetFileIds = retryFailedOnly
      ? selectedFailedDocuments.map((document) => document.fileId)
      : selectedDocuments.map((document) => document.fileId);
    if (targetFileIds.length === 0) {
      setError(retryFailedOnly ? "Select at least one failed document to retry." : "Select at least one document.");
      return;
    }
    setSaving(true);
    setBusyAction(retryFailedOnly ? "retry" : "process");
    try {
      const updated = await idpoApi.startJobRuns(jobId, {
        selectedFileIds: targetFileIds,
        mode: effectiveMode,
        jobName: jobName.trim(),
        fieldConfigCurrent: fieldConfig,
        settings: {
          configPath: CONFIG_PATH,
          adaptiveMode: effectiveMode === "strict" ? "static" : "adaptive_safe",
          report: true,
          escalationEnabled: isAdmin ? escalationEnabled : false,
          maxCostPerDoc: isAdmin && maxCostPerDoc.trim() ? Number(maxCostPerDoc) : undefined,
          llmLocalModel: isAdmin ? localModel.trim() || undefined : undefined,
          autoInstallLocalModel: isAdmin && Boolean(localModel.trim()),
          customFields: fieldConfig.map((field) => ({
            key: field.name,
            description: field.description,
          })),
        },
      });
      setJob(updated);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start job run");
    } finally {
      setSaving(false);
      setBusyAction(null);
    }
  }

  async function validateSelectedWithAi() {
    if (selectedDocuments.length === 0) {
      setError("Select at least one processed document.");
      return;
    }
    if (selectedDocuments.some((document) => document.status !== "processed")) {
      setError("Auto review only accepts processed documents.");
      return;
    }
    setSaving(true);
    setBusyAction("review");
    try {
      const response = await idpoApi.validateJobDocuments(jobId, {
        selectedFileIds: selectedDocuments.map((document) => document.fileId),
        mode: activeResultMode,
      });
      setJob(response.job);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to auto review selected documents");
    } finally {
      setSaving(false);
      setBusyAction(null);
    }
  }

  function openReviewContext() {
    const manual = job?.reviewContext?.manualInput ?? {};
    setReviewContextDraft({
      jobPurpose: manual.jobPurpose ?? "",
      knownVendors: listToTextarea(manual.knownVendors),
      fieldClarifications: listToTextarea(manual.fieldClarifications),
      validationNotes: listToTextarea(manual.validationNotes),
    });
    setShowReviewContext(true);
  }

  async function saveReviewContext() {
    const payload: JobValidationContextManualInput = {
      jobPurpose: reviewContextDraft.jobPurpose.trim() || undefined,
      knownVendors: textareaToList(reviewContextDraft.knownVendors),
      fieldClarifications: textareaToList(reviewContextDraft.fieldClarifications),
      validationNotes: textareaToList(reviewContextDraft.validationNotes),
    };
    setSaving(true);
    try {
      const updated = await idpoApi.updateJob(jobId, { reviewContextManualInput: payload });
      setJob(updated);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update review context");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-7xl space-y-4" aria-busy="true">
        <div className="h-48 animate-pulse rounded-3xl bg-slate-200/70 dark:bg-slate-800/60" />
        <div className="h-64 animate-pulse rounded-2xl bg-slate-200/70 dark:bg-slate-800/60" />
      </div>
    );
  }

  if (!job) {
    return (
      <div className="mx-auto max-w-3xl space-y-3">
        <Link href="/dashboard/idpo/jobs" className="text-xs text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">
          ← All jobs
        </Link>
        <div className="rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300">
          {error && error !== "Job not found" ? error : "This job does not exist or was removed."}
        </div>
      </div>
    );
  }

  const activeResultMode = job.mode === "both" ? resultMode : resultModeForJob(job.mode ?? mode);
  const activeRunFileIds = new Set(activeRun?.selectedFileIds ?? []);
  const trackerDocuments = activeRun ? documents.filter((document) => activeRunFileIds.has(document.fileId)) : documents;
  const trackerSummaryCounts = trackerDocuments.reduce(
    (summary, document) => {
      summary[document.status] += 1;
      return summary;
    },
    { loaded: 0, processing: 0, processed: 0, failed: 0 },
  );
  const totalDocuments = trackerDocuments.length;
  const completedDocuments = trackerSummaryCounts.processed + trackerSummaryCounts.failed;
  const completionRatio = totalDocuments > 0 ? completedDocuments / totalDocuments : 0;
  const progressBarWidth = totalDocuments > 0 ? Math.max(runActive ? 6 : 0, Math.round(completionRatio * 100)) : 0;
  const processingDocuments = trackerDocuments.filter((document) => document.status === "processing");
  const latestDocumentActivityMs = trackerDocuments.reduce<number | null>((latest, document) => {
    const updated = parseTimestamp(document.updatedAt);
    if (updated == null) {
      return latest;
    }
    return latest == null ? updated : Math.max(latest, updated);
  }, null);
  const activeRunStartedMs = parseTimestamp(activeRun?.startedAt ?? activeRun?.createdAt ?? job.startedAt);
  const lastActivityMs =
    latestDocumentActivityMs == null
      ? activeRunStartedMs
      : activeRunStartedMs == null
        ? latestDocumentActivityMs
        : Math.max(latestDocumentActivityMs, activeRunStartedMs);
  const latestRun = orderedRuns[0] ?? null;
  const latestRunStartMs = parseTimestamp(latestRun?.startedAt ?? latestRun?.createdAt);
  const latestRunEndMs = parseTimestamp(latestRun?.endedAt);
  const lastRunDurationMs =
    latestRunStartMs != null && latestRunEndMs != null ? Math.max(0, latestRunEndMs - latestRunStartMs) : null;
  const runElapsedMs = runActive && activeRunStartedMs != null ? Math.max(0, nowMs - activeRunStartedMs) : null;
  const trackerSummary =
    totalDocuments === 0
      ? "No documents yet"
      : runActive
        ? `${completedDocuments} of ${totalDocuments} done, ${processingDocuments.length} processing`
        : `${completedDocuments} of ${totalDocuments} finished`;
  const trackerDetail =
    totalDocuments === 0
      ? "Upload files below to get started."
      : runActive
        ? lastActivityMs != null
          ? `Last update ${formatDuration(Math.max(0, nowMs - lastActivityMs))} ago.`
          : "Waiting for the first update."
        : trackerSummaryCounts.failed > 0
          ? `${trackerSummaryCounts.failed} document${trackerSummaryCounts.failed === 1 ? "" : "s"} failed. Select ${trackerSummaryCounts.failed === 1 ? "it" : "them"} and use Retry failed.`
          : queueSummary.loaded > 0
            ? `${queueSummary.loaded} document${queueSummary.loaded === 1 ? " has" : "s have"} not been processed yet.`
            : "Nothing is running.";
  const displayJobName = jobName.trim() || job.jobName?.trim() || "New job";
  const reviewContext = job.reviewContext ?? null;
  const ahmn = job.ahmnSummary;
  const resultFieldNames =
    fieldConfig.length > 0
      ? fieldConfig.map((field) => field.name)
      : Array.from(
          new Set(documents.flatMap((document) => Object.keys(getOutcome(document, activeResultMode)?.fieldValues ?? {}))),
        );
  const processLabel =
    busyAction === "process" ? "Starting..." : `Process selected${selectedDocuments.length > 0 ? ` (${selectedDocuments.length})` : ""}`;
  const canAutoReview =
    selectedDocuments.length > 0 && selectedDocuments.every((document) => document.status === "processed");

  const reviewContextForm = (
    <div className="mt-4 grid gap-4">
      <label className="grid gap-2 text-sm text-slate-700 dark:text-slate-300">
        <span className="font-medium text-slate-900 dark:text-white">Job purpose</span>
        <input
          value={reviewContextDraft.jobPurpose}
          onChange={(event) => setReviewContextDraft((current) => ({ ...current, jobPurpose: event.target.value }))}
          className="rounded-xl border border-slate-300 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          placeholder="What are we trying to extract and validate in this job?"
        />
      </label>
      <label className="grid gap-2 text-sm text-slate-700 dark:text-slate-300">
        <span className="font-medium text-slate-900 dark:text-white">Known vendors</span>
        <textarea
          value={reviewContextDraft.knownVendors}
          onChange={(event) => setReviewContextDraft((current) => ({ ...current, knownVendors: event.target.value }))}
          rows={3}
          className="rounded-xl border border-slate-300 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          placeholder="One per line. Example: acme"
        />
      </label>
      <label className="grid gap-2 text-sm text-slate-700 dark:text-slate-300">
        <span className="font-medium text-slate-900 dark:text-white">Field clarifications</span>
        <textarea
          value={reviewContextDraft.fieldClarifications}
          onChange={(event) => setReviewContextDraft((current) => ({ ...current, fieldClarifications: event.target.value }))}
          rows={4}
          className="rounded-xl border border-slate-300 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          placeholder="One per line. Example: Approval code is usually stamped near the provider signature."
        />
      </label>
      <label className="grid gap-2 text-sm text-slate-700 dark:text-slate-300">
        <span className="font-medium text-slate-900 dark:text-white">Validation notes</span>
        <textarea
          value={reviewContextDraft.validationNotes}
          onChange={(event) => setReviewContextDraft((current) => ({ ...current, validationNotes: event.target.value }))}
          rows={4}
          className="rounded-xl border border-slate-300 bg-white px-3 py-2 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          placeholder="One per line. Example: If total amount is blank, treat it as missing instead of zero."
        />
      </label>
    </div>
  );

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:p-6 dark:border-slate-800 dark:bg-slate-900">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-[16rem] flex-1">
            <Link
              href="/dashboard/idpo/jobs"
              className="text-xs text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
            >
              ← All jobs
            </Link>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <h1 className="text-2xl font-semibold text-slate-900 dark:text-white">{displayJobName}</h1>
              <StatusBadge value={runActive ? "running" : job.status} />
            </div>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              {canonicalRunnerAvailable
                ? "Upload files, choose which ones to process, then open a finished document to check its fields."
                : "Upload files, then use Automatic schema extraction for Docker-backed processing and review."}
            </p>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              Job <span className="font-mono" title={job.jobId}>{shortId(job.jobId)}</span> · created {formatDate(job.createdAt)}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Link href={`/dashboard/idpo/jobs/${encodeURIComponent(job.jobId)}/auto`} className={secondaryButton}>
              Automatic schema extraction
            </Link>
            <Link href={`/dashboard/idpo/jobs/${encodeURIComponent(job.jobId)}/policies`} className={secondaryButton}>
              Policies
            </Link>
            <button type="button" onClick={openReviewContext} className={secondaryButton}>
              Review context
            </button>
          </div>
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-[minmax(0,1fr),300px] lg:max-w-4xl">
          <label className="text-sm">
            <span className="mb-1 block text-slate-700 dark:text-slate-300">Job name</span>
            <input
              value={jobName}
              onChange={(event) => setJobName(event.target.value)}
              onBlur={() => void handleBlurJobName()}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.currentTarget.blur();
                }
              }}
              placeholder="Give this job a clear name"
              className={inputStyle}
            />
          </label>
          <label className="text-sm">
            <span className="mb-1 block text-slate-700 dark:text-slate-300">Mode for the next run</span>
            <select
              value={mode}
              onChange={(event) => void handleChangeMode(event.target.value as JobExecutionMode)}
              className={inputStyle}
            >
              {MODE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="mt-5 rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/40">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
                {runActive ? (
                  <>
                    <span className="h-2 w-2 animate-pulse rounded-full bg-amber-500" />
                    <span className="capitalize">{activeRun?.mode ?? job.mode ?? "adaptive"} run in progress</span>
                  </>
                ) : (
                  "Progress"
                )}
              </p>
              <p className="mt-1 text-lg font-semibold text-slate-900 dark:text-white">{trackerSummary}</p>
              <p className="mt-0.5 text-sm text-slate-600 dark:text-slate-300">{trackerDetail}</p>
              {pollFailed ? (
                <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">Lost contact with the server. Retrying...</p>
              ) : null}
            </div>
            <dl className="grid grid-cols-2 gap-2 text-sm">
              <div className="rounded-xl border border-slate-200 bg-white px-3 py-2 dark:border-slate-800 dark:bg-slate-900">
                <dt className="text-xs text-slate-500 dark:text-slate-400">{runActive ? "Elapsed" : "Last run took"}</dt>
                <dd className="mt-0.5 font-medium text-slate-900 dark:text-white">
                  {formatDuration(runActive ? runElapsedMs : lastRunDurationMs)}
                </dd>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white px-3 py-2 dark:border-slate-800 dark:bg-slate-900">
                <dt className="text-xs text-slate-500 dark:text-slate-400">{runActive ? "Started" : "Finished"}</dt>
                <dd className="mt-0.5 font-medium text-slate-900 dark:text-white">
                  {runActive
                    ? activeRunStartedMs != null
                      ? new Date(activeRunStartedMs).toLocaleTimeString()
                      : "—"
                    : latestRunEndMs != null
                      ? new Date(latestRunEndMs).toLocaleString()
                      : "—"}
                </dd>
              </div>
            </dl>
          </div>
          <div
            className="mt-4 h-2.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={totalDocuments}
            aria-valuenow={completedDocuments}
            aria-label="Documents finished"
          >
            <div
              className="h-full rounded-full bg-gradient-to-r from-cyan-500 via-sky-500 to-emerald-500 transition-[width] duration-500"
              style={{ width: `${progressBarWidth}%` }}
            />
          </div>
          <div className="mt-3 flex flex-wrap gap-2 text-xs font-medium">
            <span className="rounded-full bg-white px-3 py-1 text-slate-700 ring-1 ring-slate-200 dark:bg-slate-900 dark:text-slate-200 dark:ring-slate-700">
              Not processed {queueSummary.loaded}
            </span>
            <span className="rounded-full bg-white px-3 py-1 text-amber-700 ring-1 ring-amber-200 dark:bg-slate-900 dark:text-amber-300 dark:ring-amber-700/40">
              Processing {queueSummary.processing}
            </span>
            <span className="rounded-full bg-white px-3 py-1 text-emerald-700 ring-1 ring-emerald-200 dark:bg-slate-900 dark:text-emerald-300 dark:ring-emerald-700/40">
              Processed {queueSummary.processed}
            </span>
            <span className="rounded-full bg-white px-3 py-1 text-rose-700 ring-1 ring-rose-200 dark:bg-slate-900 dark:text-rose-300 dark:ring-rose-700/40">
              Failed {queueSummary.failed}
            </span>
          </div>
          {processingDocuments.length > 0 ? (
            <ul className="mt-4 space-y-2">
              {processingDocuments.map((document, index) => (
                <li
                  key={document.fileId}
                  className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-white px-3 py-2 text-sm dark:bg-slate-900"
                >
                  <span className="min-w-0 truncate font-medium text-slate-900 dark:text-white">
                    {index + 1}. {document.fileName}
                  </span>
                  <span className="text-xs text-amber-700 dark:text-amber-300">
                    Processing{document.updatedAt ? ` since ${new Date(document.updatedAt).toLocaleTimeString()}` : ""}
                  </span>
                </li>
              ))}
              <li className="text-xs text-slate-500 dark:text-slate-400">
                The pipeline does not report individual stages, so only the queue position is shown.
              </li>
            </ul>
          ) : null}
        </div>
      </section>

      {error ? (
        <div
          role="alert"
          className="flex items-start justify-between gap-3 rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300"
        >
          <span>{displayError(error)}</span>
          <button
            type="button"
            onClick={() => setError("")}
            aria-label="Dismiss message"
            className="rounded p-0.5 hover:bg-rose-100 dark:hover:bg-rose-900/40"
          >
            <Icon name="close" className="h-4 w-4" />
          </button>
        </div>
      ) : null}

      {!error && job.status === "failed" && job.error ? (
        <div className="rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300">
          {displayError(job.error)}
        </div>
      ) : null}

      <IdpoCard
        className={dragActive ? "ring-2 ring-cyan-400 ring-offset-2 ring-offset-white dark:ring-offset-slate-950" : undefined}
      >
        <div
          onDragOver={handleDragOver}
          onDragLeave={() => setDragActive(false)}
          onDrop={handleDrop}
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Documents</h2>
              <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                {documents.length === 0
                  ? "Drop files here or use Upload files."
                  : `${documents.length} file${documents.length === 1 ? "" : "s"}, ${selectedDocuments.length} selected. Drop more files here to add them.`}
              </p>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                DOCX, XLSX, PPTX, HTML and EML run through Automatic extraction only; the research runner does not process them.
              </p>
              {uploadProgress ? <p className="mt-1 text-xs text-slate-500 dark:text-slate-400" role="status">
                Uploaded {uploadProgress.uploaded} of {uploadProgress.total} files.
              </p> : null}
              {unconfirmedFiles.length > 0 ? <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">
                Retry checks the original batch receipt for {unconfirmedFiles.length} unconfirmed file{unconfirmedFiles.length === 1 ? "" : "s"}. A committed upload will be returned without adding duplicates.
              </p> : null}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <input
                ref={uploadRef}
                type="file"
                multiple
                accept={ACCEPTED_FILE_TYPES}
                className="hidden"
                onChange={(event) => void handleUpload(event.target.files)}
              />
              <button
                type="button"
                onClick={() => uploadRef.current?.click()}
                disabled={saving}
                className={secondaryButton}
              >
                <Icon name="upload" className="h-4 w-4" />
                {busyAction === "upload" ? "Uploading..." : "Upload files"}
              </button>
              {unconfirmedFiles.length > 0 ? <button
                type="button"
                onClick={() => void handleUpload(unconfirmedFiles, unconfirmedRetryKey ?? undefined)}
                disabled={saving || !unconfirmedRetryKey}
                className={secondaryButton}
              >Retry unconfirmed ({unconfirmedFiles.length})</button> : null}
              {canonicalRunnerAvailable && queueSummary.failed > 0 ? (
                <button
                  type="button"
                  onClick={() => void startRun(mode, true)}
                  disabled={saving || selectedFailedDocuments.length === 0}
                  title={selectedFailedDocuments.length === 0 ? "Select failed documents to retry them" : undefined}
                  className="inline-flex items-center gap-2 rounded-xl border border-amber-300 px-3.5 py-2 text-sm font-medium text-amber-700 hover:bg-amber-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-amber-700/40 dark:text-amber-300 dark:hover:bg-amber-900/20"
                >
                  {busyAction === "retry" ? "Starting..." : `Retry failed${selectedFailedDocuments.length > 0 ? ` (${selectedFailedDocuments.length})` : ""}`}
                </button>
              ) : null}
              {isAdmin ? <button
                type="button"
                onClick={() => void validateSelectedWithAi()}
                disabled={saving || !canAutoReview}
                title={canAutoReview ? "Ask the model to check the extracted fields" : "Select processed documents to auto review them"}
                className={secondaryButton}
              >
                {busyAction === "review" ? "Reviewing..." : "Auto review"}
              </button> : null}
              {canonicalRunnerAvailable ? (
                <button
                  type="button"
                  onClick={() => void startRun(mode, false)}
                  disabled={saving || selectedDocuments.length === 0}
                  className={primaryButton}
                >
                  {processLabel}
                </button>
              ) : null}
            </div>
          </div>

          {documents.length === 0 ? (
            <button
              type="button"
              onClick={() => uploadRef.current?.click()}
              disabled={saving}
              className="mt-4 flex w-full flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-slate-300 px-6 py-10 text-sm text-slate-500 hover:border-cyan-400 hover:text-cyan-700 dark:border-slate-700 dark:text-slate-400 dark:hover:border-cyan-500 dark:hover:text-cyan-300"
            >
              <Icon name="upload" className="h-6 w-6" />
              <span className="font-medium">Drop files here or click to upload</span>
              <span className="text-xs">PDF, images, office files, TXT, JSON, HTML or EML; up to 20 MiB each</span>
            </button>
          ) : (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[720px] text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                    <th className="w-10 px-2 py-2">
                      <input
                        type="checkbox"
                        aria-label="Select all documents"
                        checked={allSelectableSelected}
                        ref={(element) => {
                          if (element) {
                            element.indeterminate = someSelected && !allSelectableSelected;
                          }
                        }}
                        onChange={() => void handleToggleAll()}
                        disabled={saving || selectableDocumentIds.length === 0}
                      />
                    </th>
                    <th className="px-2 py-2">File</th>
                    <th className="px-2 py-2">Status</th>
                    <th className="px-2 py-2">Policy</th>
                    <th className="px-2 py-2">Review</th>
                    <th className="px-2 py-2 text-right">Result</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((document) => {
                    const preferredOutcome = getOutcome(document, activeResultMode);
                    const routeValue = preferredOutcome?.route ?? document.latestRoute;
                    const policyValue = preferredOutcome?.policy ?? document.latestPolicy;
                    const actionRunId = preferredOutcome?.runId ?? document.latestRunId;
                    const hasExtractedDocument = Boolean(preferredOutcome?.docId || document.latestDocId);
                    const docHref =
                      hasExtractedDocument && actionRunId
                        ? `/dashboard/idpo/jobs/${encodeURIComponent(job.jobId)}/docs/${encodeURIComponent(document.fileId)}?mode=${encodeURIComponent(activeResultMode)}&runId=${encodeURIComponent(actionRunId)}`
                        : null;
                    const policyHref = policyValue
                      ? `/dashboard/idpo/jobs/${encodeURIComponent(job.jobId)}/policies/${encodeURIComponent(policyValue)}`
                      : null;
                    const reviewDetail = formatReviewState(document.reviewState);
                    return (
                      <tr key={document.fileId} className="border-b border-slate-100 align-top dark:border-slate-800">
                        <td className="px-2 py-3">
                          <input
                            type="checkbox"
                            aria-label={`Select ${document.fileName}`}
                            checked={selectedFileIds.includes(document.fileId)}
                            onChange={() => void handleToggleSelection(document.fileId)}
                            disabled={saving || document.status === "processing"}
                          />
                        </td>
                        <td className="max-w-[22rem] px-2 py-3">
                          <div className="truncate font-medium text-slate-900 dark:text-slate-100" title={`${document.fileName} (file ${shortId(document.fileId)})`}>
                            {document.fileName}
                          </div>
                          {document.errorSummary ? (
                            <div className="mt-1 text-xs text-rose-700 dark:text-rose-300">{displayError(document.errorSummary)}</div>
                          ) : null}
                        </td>
                        <td className="px-2 py-3">
                          <StatusBadge value={document.status} />
                        </td>
                        <td className="px-2 py-3 text-slate-600 dark:text-slate-300">
                          {policyHref ? (
                            <Link href={policyHref} className={linkStyle}>
                              {policyValue}
                            </Link>
                          ) : (
                            "—"
                          )}
                          {routeValue ? (
                            <div className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{routeValue} route</div>
                          ) : null}
                        </td>
                        <td className="px-2 py-3 text-slate-600 dark:text-slate-300">
                          {document.status === "processed" ? (
                            <>
                              <div className="flex flex-wrap items-center gap-2">
                                <StatusBadge value={document.reviewStatus ?? "unreviewed"} />
                                {preferredOutcome?.exactF1 != null ? (
                                  <span className="text-xs font-medium text-slate-700 dark:text-slate-200">
                                    F1 {preferredOutcome.exactF1.toFixed(2)}
                                  </span>
                                ) : null}
                              </div>
                              {reviewDetail ? (
                                <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{reviewDetail}</div>
                              ) : null}
                            </>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="px-2 py-3 text-right">
                          {docHref ? (
                            <Link
                              href={docHref}
                              className="inline-flex items-center gap-1 rounded-lg border border-cyan-200 px-2.5 py-1 text-xs font-semibold text-cyan-700 hover:bg-cyan-50 dark:border-cyan-800/60 dark:text-cyan-300 dark:hover:bg-cyan-950/40"
                            >
                              Open
                              <Icon name="arrowRight" className="h-3 w-3" />
                            </Link>
                          ) : (
                            <span className="text-xs text-slate-500 dark:text-slate-400">
                              {document.status === "processing"
                                ? "Processing..."
                                : document.status === "failed"
                                  ? "Failed"
                                  : "Not processed yet"}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </IdpoCard>

      <IdpoCard>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Extracted values</h2>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              {resultFieldNames.length === 0
                ? "Values appear here after a document is processed."
                : fieldConfig.length > 0
                  ? "The fields configured for this job, one row per document."
                  : "The fields each document's policy extracted, one row per document."}
            </p>
          </div>
          {job.mode === "both" ? (
            <div className="inline-flex rounded-lg border border-slate-300 p-0.5 dark:border-slate-700" role="group" aria-label="Result mode">
              {(["adaptive", "strict"] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setResultMode(value)}
                  aria-pressed={resultMode === value}
                  className={`rounded-md px-3 py-1.5 text-sm font-medium capitalize ${
                    resultMode === value
                      ? "bg-cyan-600 text-white"
                      : "text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800"
                  }`}
                >
                  {value}
                </button>
              ))}
            </div>
          ) : null}
        </div>

        {resultFieldNames.length > 0 ? (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                  <th className="px-2 py-2">File</th>
                  {resultFieldNames.map((name) => (
                    <th key={name} className="px-2 py-2" title={name}>
                      {formatFieldLabel(name)}
                    </th>
                  ))}
                  <th className="px-2 py-2 text-right">Detail</th>
                </tr>
              </thead>
              <tbody>
                {documents.map((document) => {
                  const outcome = getOutcome(document, activeResultMode);
                  return (
                    <tr key={document.fileId} className="border-b border-slate-100 dark:border-slate-800">
                      <td className="max-w-[18rem] truncate px-2 py-2 font-medium text-slate-900 dark:text-slate-100" title={document.fileName}>
                        {document.fileName}
                      </td>
                      {resultFieldNames.map((name) => (
                        <td key={`${document.fileId}-${name}`} className="px-2 py-2 text-slate-700 dark:text-slate-300">
                          {document.status === "processed" ? getOutcomeFieldValue(outcome, name) : "—"}
                        </td>
                      ))}
                      <td className="px-2 py-2 text-right text-xs text-slate-500 dark:text-slate-400">
                        {outcome?.docId && outcome.runId ? (
                          <Link
                            href={`/dashboard/idpo/jobs/${encodeURIComponent(job.jobId)}/docs/${encodeURIComponent(document.fileId)}?mode=${encodeURIComponent(activeResultMode)}&runId=${encodeURIComponent(outcome.runId)}`}
                            className={linkStyle}
                          >
                            Open
                          </Link>
                        ) : document.status === "failed" ? (
                          "Failed"
                        ) : document.status === "processing" ? (
                          "Processing..."
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}
      </IdpoCard>

      <IdpoCard>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Fields to extract</h2>
            <p className="mt-1 max-w-3xl text-sm text-slate-600 dark:text-slate-300">
              Leave this empty and the policy chosen for each document decides which fields to extract. Add a field to ask for a specific value, such as an invoice total.
            </p>
          </div>
          {isAdmin ? <button
            type="button"
            onClick={() => setShowAdvanced((current) => !current)}
            aria-expanded={showAdvanced}
            className={`text-sm ${linkStyle}`}
          >
            {showAdvanced ? "Hide advanced settings" : "Advanced settings"}
          </button> : null}
        </div>

        <form
          className="mt-4 grid gap-3 md:grid-cols-[1fr,1fr,auto]"
          onSubmit={(event) => {
            event.preventDefault();
            void handleAddField();
          }}
        >
          <label>
            <span className="sr-only">Field name</span>
            <input
              value={newFieldName}
              onChange={(event) => setNewFieldName(event.target.value)}
              placeholder="Field name, e.g. total_amount"
              className={inputStyle}
            />
          </label>
          <label>
            <span className="sr-only">Field description</span>
            <input
              value={newFieldDescription}
              onChange={(event) => setNewFieldDescription(event.target.value)}
              placeholder="What the value looks like (optional)"
              className={inputStyle}
            />
          </label>
          <button
            type="submit"
            disabled={saving || !newFieldName.trim()}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200"
          >
            Add field
          </button>
        </form>

        {fieldConfig.length > 0 ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {fieldConfig.map((field, index) => (
              <div
                key={`${field.name}-${index}`}
                className="flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 py-1 pl-3 pr-1.5 text-sm dark:border-slate-800 dark:bg-slate-950/40"
              >
                <span className="text-slate-900 dark:text-white">{field.name}</span>
                {field.description ? <span className="text-xs text-slate-500 dark:text-slate-400">{field.description}</span> : null}
                <button
                  type="button"
                  onClick={() => void handleRemoveField(index)}
                  aria-label={`Remove field ${field.name}`}
                  className="rounded-full p-1 text-slate-400 hover:bg-rose-50 hover:text-rose-700 dark:hover:bg-rose-900/30 dark:hover:text-rose-300"
                >
                  <Icon name="close" className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        ) : null}

        {isAdmin && showAdvanced ? (
          <div className="mt-4 grid gap-4 rounded-xl border border-slate-200 bg-slate-50 p-4 md:grid-cols-2 dark:border-slate-800 dark:bg-slate-950/40">
            <label className="text-sm">
              <span className="mb-1 block text-slate-700 dark:text-slate-300">Local extraction model</span>
              <select
                value={localModel}
                onChange={(event) => void handleChangeLocalModel(event.target.value)}
                className={inputStyle}
              >
                {LOCAL_MODEL_OPTIONS.map((option) => (
                  <option key={option.label} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <span className="mt-1 block text-xs text-slate-500 dark:text-slate-400">
                Applies to future runs of this job. A model that is not installed is pulled through Ollama first.
              </span>
            </label>
            <label className="text-sm">
              <span className="mb-1 block text-slate-700 dark:text-slate-300">Max cost per document</span>
              <input
                value={maxCostPerDoc}
                onChange={(event) => setMaxCostPerDoc(event.target.value)}
                inputMode="decimal"
                placeholder="No limit"
                className={inputStyle}
              />
              <span className="mt-1 block text-xs text-slate-500 dark:text-slate-400">Only matters when escalation can call a paid model.</span>
            </label>
            <label className="flex items-center gap-3 text-sm text-slate-700 dark:text-slate-300">
              <input
                type="checkbox"
                checked={escalationEnabled}
                onChange={(event) => setEscalationEnabled(event.target.checked)}
              />
              Allow escalation to the fallback model when local extraction is not good enough
            </label>
          </div>
        ) : null}
      </IdpoCard>

      <IdpoCard>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Adaptive routing</h2>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              How AHMN advice was used for this job and what was sent back to it.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowRoutingDetails((current) => !current)}
            aria-expanded={showRoutingDetails}
            className={`text-sm ${linkStyle}`}
          >
            {showRoutingDetails ? "Hide details" : "Show details"}
          </button>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
          <SummaryTile label="Documents with advice" value={ahmn?.documentsWithAdvice ?? 0} />
          <SummaryTile
            label="Advice accepted"
            value={ahmn?.adviceInfluencedCount ?? 0}
            hint="Documents where the advice was accepted or changed the policy"
          />
          <SummaryTile label="Outcomes sent to AHMN" value={ahmn?.documentsLoggedBack ?? 0} />
          <SummaryTile
            label="Reviewed"
            value={
              typeof ahmn?.reviewedHumanCount === "number" && typeof ahmn?.reviewedAiCount === "number"
                ? `${ahmn.reviewedDocumentCount} (${ahmn.reviewedHumanCount} human, ${ahmn.reviewedAiCount} auto)`
                : ahmn?.reviewedDocumentCount ?? 0
            }
          />
        </div>
        {showRoutingDetails ? (
          <dl className="mt-4 grid gap-x-6 gap-y-2 text-sm md:grid-cols-2">
            <div className="flex justify-between gap-3 border-b border-slate-100 py-1.5 dark:border-slate-800">
              <dt className="text-slate-500 dark:text-slate-400">Document profile</dt>
              <dd className="text-slate-900 dark:text-white">{ahmn?.jobProfile && ahmn.jobProfile !== "awaiting_run" ? ahmn.jobProfile : "—"}</dd>
            </div>
            <div className="flex justify-between gap-3 border-b border-slate-100 py-1.5 dark:border-slate-800">
              <dt className="text-slate-500 dark:text-slate-400">Matched earlier memory</dt>
              <dd className="text-slate-900 dark:text-white">{ahmn?.memoryMatched ? "Yes" : "No"}</dd>
            </div>
            <div className="flex justify-between gap-3 border-b border-slate-100 py-1.5 dark:border-slate-800">
              <dt className="text-slate-500 dark:text-slate-400">Review feedback sent</dt>
              <dd className="text-slate-900 dark:text-white">
                {ahmn?.reviewedFeedbackLoggedCount ?? 0}
                {typeof ahmn?.reviewedFeedbackPendingCount === "number" && ahmn.reviewedFeedbackPendingCount > 0
                  ? ` (${ahmn.reviewedFeedbackPendingCount} pending)`
                  : ""}
              </dd>
            </div>
            <div className="flex justify-between gap-3 border-b border-slate-100 py-1.5 dark:border-slate-800">
              <dt className="text-slate-500 dark:text-slate-400">Job-specific policy overlay</dt>
              <dd className="text-slate-900 dark:text-white">
                {ahmn?.jobOverlayReady
                  ? `Ready (${ahmn.jobOverlayPolicies} polic${ahmn.jobOverlayPolicies === 1 ? "y" : "ies"})`
                  : "Not ready yet"}
              </dd>
            </div>
          </dl>
        ) : null}
      </IdpoCard>

      <IdpoCard>
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Run history</h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          Every run of this job. In Both mode the adaptive and strict runs are listed separately.
        </p>
        {orderedRuns.length === 0 ? (
          <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">No runs yet. Select documents and use Process selected.</p>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                  <th className="px-2 py-2">Run</th>
                  <th className="px-2 py-2">Mode</th>
                  <th className="px-2 py-2">Status</th>
                  <th className="px-2 py-2">Started</th>
                  <th className="px-2 py-2">Duration</th>
                  <th className="px-2 py-2">Processed</th>
                  <th className="px-2 py-2">Failed</th>
                </tr>
              </thead>
              <tbody>
                {orderedRuns.map((run) => {
                  const startMs = parseTimestamp(run.startedAt ?? run.createdAt);
                  const endMs = parseTimestamp(run.endedAt);
                  const runningNow = run.status === "running" || run.status === "queued";
                  const durationMs =
                    startMs != null ? (endMs != null ? endMs - startMs : runningNow ? nowMs - startMs : null) : null;
                  const runId = run.runId ?? run.jobRunId;
                  return (
                    <tr key={run.jobRunId} className="border-b border-slate-100 align-top dark:border-slate-800">
                      <td className="px-2 py-2 font-mono text-xs text-slate-600 dark:text-slate-300">
                        {run.runId && run.status === "success" ? (
                          <Link href={`/dashboard/idpo/runs/${encodeURIComponent(run.runId)}`} className={linkStyle} title={run.runId}>
                            {shortId(runId)}
                          </Link>
                        ) : (
                          <span title={runId}>{shortId(runId)}</span>
                        )}
                      </td>
                      <td className="px-2 py-2 capitalize text-slate-600 dark:text-slate-300">{run.mode}</td>
                      <td className="px-2 py-2">
                        <StatusBadge value={run.status} />
                        {run.status === "failed" && run.error ? (
                          <div className="mt-1 max-w-xs text-xs text-rose-700 dark:text-rose-300">{displayError(run.error)}</div>
                        ) : null}
                      </td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{formatDate(run.startedAt ?? run.createdAt)}</td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{formatDuration(durationMs)}</td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{run.processedCount ?? 0}</td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{run.failedCount ?? 0}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </IdpoCard>

      {showReviewContext ? (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 px-4 py-8"
          onClick={(event) => {
            if (event.target === event.currentTarget) {
              setShowReviewContext(false);
            }
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="review-context-title"
            className="max-h-[88vh] w-full max-w-4xl overflow-y-auto rounded-3xl border border-slate-200 bg-white p-6 shadow-2xl dark:border-slate-800 dark:bg-slate-900"
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 id="review-context-title" className="text-lg font-semibold text-slate-900 dark:text-white">Review context</h2>
                <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                  Notes about this job that guide auto review and are added to the extraction prompts.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowReviewContext(false)}
                aria-label="Close review context"
                className="rounded-lg border border-slate-300 p-2 text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                <Icon name="close" className="h-4 w-4" />
              </button>
            </div>

            {reviewContext ? (
              <div className="mt-6 space-y-6">
                <div className="grid gap-3 md:grid-cols-2">
                  <IdpoCard className="p-4">
                    <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Job purpose</div>
                    <div className="mt-2 text-sm font-medium text-slate-900 dark:text-white">
                      {reviewContext.current.summary.jobPurpose}
                    </div>
                  </IdpoCard>
                  <IdpoCard className="p-4">
                    <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Current version</div>
                    <div className="mt-2 text-sm font-medium text-slate-900 dark:text-white">
                      v{reviewContext.current.versionNumber}, updated {formatDate(reviewContext.current.updatedAt)}
                    </div>
                    <div className="mt-2 text-xs text-slate-500 dark:text-slate-400">
                      Trigger: {reviewContext.current.source.replace(/_/g, " ")}
                    </div>
                  </IdpoCard>
                </div>

                <div className="grid gap-4 lg:grid-cols-2">
                  <IdpoCard className="p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Your notes</h3>
                        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                          Add stable knowledge about the job. Failures and corrections from reviews are added automatically.
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => void saveReviewContext()}
                        disabled={saving}
                        className={primaryButton}
                      >
                        Save
                      </button>
                    </div>
                    {reviewContextForm}
                  </IdpoCard>

                  <IdpoCard className="p-4">
                    <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Context summary</h3>
                    <dl className="mt-4 space-y-3 text-sm">
                      <div>
                        <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Known vendors</dt>
                        <dd className="mt-1 text-slate-700 dark:text-slate-200">{formatList(reviewContext.current.summary.knownVendors)}</dd>
                      </div>
                      <div>
                        <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Field clarifications</dt>
                        <dd className="mt-1 text-slate-700 dark:text-slate-200">{formatList(reviewContext.current.summary.fieldClarifications)}</dd>
                      </div>
                      <div>
                        <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Recurring failures</dt>
                        <dd className="mt-1 text-slate-700 dark:text-slate-200">{formatList(reviewContext.current.summary.recurringFailurePatterns)}</dd>
                      </div>
                      <div>
                        <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Reviewed corrections</dt>
                        <dd className="mt-1 text-slate-700 dark:text-slate-200">{formatList(reviewContext.current.summary.reviewedCorrectionPatterns)}</dd>
                      </div>
                      <div>
                        <dt className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Validation notes</dt>
                        <dd className="mt-1 text-slate-700 dark:text-slate-200">{formatList(reviewContext.current.summary.validationNotes)}</dd>
                      </div>
                    </dl>
                  </IdpoCard>

                  <div className="space-y-4 lg:col-span-2">
                    <IdpoCard className="p-4">
                      <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Auto review prompt preview</h3>
                      <pre className="mt-3 overflow-x-auto whitespace-pre-wrap rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700 dark:border-slate-800 dark:bg-slate-950/40 dark:text-slate-200">
                        {reviewContext.current.promptPreview.autoReview}
                      </pre>
                    </IdpoCard>
                    <IdpoCard className="p-4">
                      <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Extraction prompt preview</h3>
                      <pre className="mt-3 overflow-x-auto whitespace-pre-wrap rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700 dark:border-slate-800 dark:bg-slate-950/40 dark:text-slate-200">
                        {reviewContext.current.promptPreview.extraction}
                      </pre>
                    </IdpoCard>
                  </div>
                </div>

                <IdpoCard className="p-4">
                  <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Previous versions</h3>
                  {reviewContext.history.length > 0 ? (
                    <div className="mt-4 space-y-3">
                      {reviewContext.history.map((entry) => (
                        <div key={`${entry.versionNumber}-${entry.updatedAt}`} className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm dark:border-slate-800 dark:bg-slate-950/40">
                          <div className="flex flex-wrap items-center justify-between gap-3">
                            <div className="font-medium text-slate-900 dark:text-white">
                              v{entry.versionNumber} · {formatDate(entry.updatedAt)}
                            </div>
                            <div className="text-xs text-slate-500 dark:text-slate-400">{entry.source.replace(/_/g, " ")}</div>
                          </div>
                          <div className="mt-2 text-xs text-slate-600 dark:text-slate-300">{formatList(entry.changes)}</div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">No previous versions yet.</p>
                  )}
                </IdpoCard>
              </div>
            ) : (
              <div className="mt-6 space-y-4">
                <IdpoCard className="p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Your notes</h3>
                      <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                        You can add notes before the first review is saved.
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => void saveReviewContext()}
                      disabled={saving}
                      className={primaryButton}
                    >
                      Save
                    </button>
                  </div>
                  {reviewContextForm}
                </IdpoCard>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-950/40 dark:text-slate-300">
                  The context summary and prompt previews appear after the first auto review or human review is saved.
                </div>
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
