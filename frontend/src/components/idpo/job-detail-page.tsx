"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { IdpoCard } from "@/components/idpo/card";
import { StatusBadge } from "@/components/idpo/status-badge";
import { idpoApi } from "@/lib/idpo-api";
import type {
  JobDocumentRecord,
  JobDocumentRunOutcome,
  JobExecutionMode,
  JobFieldConfig,
  JobRunMode,
  JobStatus,
} from "@/types/idpo";

const CONFIG_PATH = "configs/idpo_research_config.json";

function formatDate(value: string | undefined): string {
  if (!value) {
    return "-";
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

function getOutcome(document: JobDocumentRecord, mode: JobRunMode): JobDocumentRunOutcome | null {
  const matches = document.outcomes.filter((outcome) => outcome.mode === mode);
  return matches.length > 0 ? matches[matches.length - 1] ?? null : null;
}

function getOutcomeFieldValue(outcome: JobDocumentRunOutcome | null, field: JobFieldConfig): string {
  if (!outcome) {
    return "NA";
  }
  const direct = outcome.fieldValues[field.name];
  if (typeof direct === "string" && direct.trim().length > 0) {
    return direct;
  }
  const normalized = outcome.fieldValues[normalizeFieldKey(field.name)];
  if (typeof normalized === "string" && normalized.trim().length > 0) {
    return normalized;
  }
  return "NA";
}

function fileIdSummary(fileId: string): string {
  return fileId.slice(0, 8);
}

function formatReviewState(reviewState: string | null | undefined): string {
  if (!reviewState) {
    return "NA";
  }
  return reviewState.replace(/\s*\|\s*/g, " | ");
}

function hasActiveRun(job: JobStatus | null): boolean {
  return Boolean(
    job &&
      (job.status === "queued" ||
        job.status === "running" ||
        (job.documents ?? []).some((document) => document.status === "processing")),
  );
}

export function JobDetailPage() {
  const params = useParams<{ jobId: string }>();
  const jobId = decodeURIComponent(params.jobId);
  const uploadRef = useRef<HTMLInputElement>(null);

  const [job, setJob] = useState<JobStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [jobName, setJobName] = useState("");
  const [mode, setMode] = useState<JobExecutionMode>("adaptive");
  const [fieldConfig, setFieldConfig] = useState<JobFieldConfig[]>([]);
  const [selectedFileIds, setSelectedFileIds] = useState<string[]>([]);
  const [newFieldName, setNewFieldName] = useState("");
  const [newFieldDescription, setNewFieldDescription] = useState("");
  const [resultMode, setResultMode] = useState<JobRunMode>("adaptive");
  const [maxCostPerDoc, setMaxCostPerDoc] = useState("");
  const [escalationEnabled, setEscalationEnabled] = useState(true);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [lastRefreshedAt, setLastRefreshedAt] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  async function loadJob(activeJobId = jobId, preserveLoading = false) {
    try {
      if (!preserveLoading) {
        setLoading(true);
      }
      const payload = await idpoApi.getJob(activeJobId);
      setJob(payload);
      setLastRefreshedAt(new Date().toISOString());
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load job");
    } finally {
      if (!preserveLoading) {
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    void loadJob();
  }, [jobId]);

  useEffect(() => {
    if (!job) {
      return;
    }
    setJobName((current) => (current ? current : job.jobName?.trim() || ""));
    setMode((current) => current ?? (job.mode ?? "adaptive"));
    setFieldConfig((current) => (current.length > 0 ? current : job.fieldConfigCurrent ?? []));
    setSelectedFileIds((current) =>
      current.length > 0 ? current : (job.documents ?? []).filter((document) => document.selected).map((document) => document.fileId),
    );
    setResultMode(resultModeForJob(job.mode ?? "adaptive"));
  }, [job]);

  useEffect(() => {
    if (!hasActiveRun(job)) {
      return undefined;
    }
    const timer = window.setInterval(() => {
      setIsRefreshing(true);
      void loadJob(jobId, true).finally(() => setIsRefreshing(false));
    }, 2000);
    return () => window.clearInterval(timer);
  }, [job, jobId]);

  const documents = job?.documents ?? [];
  const runs = job?.runs ?? [];
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

  async function patchJob(payload: {
    jobName?: string;
    mode?: JobExecutionMode;
    fieldConfigCurrent?: JobFieldConfig[];
    selectedFileIds?: string[];
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

  async function handleUpload(files: FileList | null) {
    if (!files || files.length === 0) {
      return;
    }
    const formData = new FormData();
    Array.from(files).forEach((file) => formData.append("files", file));
    setSaving(true);
    try {
      const updated = await idpoApi.uploadJobDocuments(jobId, formData);
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
      setError("");
      if (uploadRef.current) {
        uploadRef.current.value = "";
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to upload documents");
    } finally {
      setSaving(false);
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
    const next =
      selectedFileIds.length === selectableDocumentIds.length
        ? []
        : selectableDocumentIds;
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
          escalationEnabled,
          maxCostPerDoc: maxCostPerDoc.trim() ? Number(maxCostPerDoc) : undefined,
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
    }
  }

  async function validateSelectedWithAi() {
    if (selectedDocuments.length === 0) {
      setError("Select at least one processed document.");
      return;
    }
    if (selectedDocuments.some((document) => document.status !== "processed")) {
      setError("AI validation only accepts processed documents.");
      return;
    }
    setSaving(true);
    try {
      const response = await idpoApi.validateJobDocuments(jobId, {
        selectedFileIds: selectedDocuments.map((document) => document.fileId),
        mode: activeResultMode,
      });
      setJob(response.job);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to validate selected documents");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div className="text-sm text-slate-600 dark:text-slate-300">Loading job workspace...</div>;
  }

  if (!job) {
    return (
      <div className="rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300">
        {error || "Job not found"}
      </div>
    );
  }

  const activeResultMode = job.mode === "both" ? resultMode : resultModeForJob(job.mode ?? mode);
  const totalDocuments = documents.length;
  const pendingDocuments = queueSummary.loaded + queueSummary.processing;
  const reviewedDocuments = job.ahmnSummary?.reviewedDocumentCount ?? 0;

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div className="space-y-4">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-[280px] flex-1">
              <Link
                href="/dashboard/idpo/jobs"
                className="text-xs text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
              >
                Back to jobs
              </Link>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <h1 className="text-2xl font-semibold text-slate-900 dark:text-white">Job {job.jobId}</h1>
                <StatusBadge value={job.status} />
              </div>
              <p className="mt-2 max-w-4xl text-sm text-slate-600 dark:text-slate-300">
                Queue-first job workspace. Select documents, run extraction, then review structured results.
              </p>
            </div>

            <div className="flex flex-wrap items-center justify-start gap-2 xl:max-w-[44rem] xl:justify-end">
              <Link
                href={`/dashboard/idpo/jobs/${encodeURIComponent(job.jobId)}/policies`}
                className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                Policy workspace
              </Link>
              <input
                ref={uploadRef}
                type="file"
                multiple
                className="hidden"
                onChange={(event) => void handleUpload(event.target.files)}
              />
              <button
                type="button"
                onClick={() => uploadRef.current?.click()}
                disabled={saving}
                className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                Upload files
              </button>
              <button
                type="button"
                onClick={() => void startRun(mode, false)}
                disabled={saving || selectedDocuments.length === 0}
                className="rounded-xl bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                Process selected
              </button>
              <button
                type="button"
                onClick={() => void startRun(mode, true)}
                disabled={saving || selectedFailedDocuments.length === 0}
                className="rounded-xl border border-amber-300 px-4 py-2 text-sm font-medium text-amber-700 hover:bg-amber-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-amber-700/40 dark:text-amber-300 dark:hover:bg-amber-900/20"
              >
                Rerun selected failed
              </button>
              <button
                type="button"
                onClick={() => void validateSelectedWithAi()}
                disabled={saving || selectedDocuments.length === 0 || selectedDocuments.some((document) => document.status !== "processed")}
                className="rounded-xl border border-emerald-300 px-4 py-2 text-sm font-medium text-emerald-700 hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-emerald-700/40 dark:text-emerald-300 dark:hover:bg-emerald-900/20"
              >
                Validate with AI
              </button>
              <button
                type="button"
                onClick={() => void startRun(mode, false)}
                disabled={saving || selectedDocuments.length === 0}
                className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                Create new run
              </button>
            </div>
          </div>

          <div className="space-y-4">
            <div className="grid gap-3 md:grid-cols-[minmax(0,1fr),220px] lg:max-w-3xl">
              <label className="text-sm">
                <span className="mb-1 block text-slate-700 dark:text-slate-300">Job name</span>
                <input
                  value={jobName}
                  onChange={(event) => setJobName(event.target.value)}
                  onBlur={() => void handleBlurJobName()}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
                />
              </label>
              <label className="text-sm">
                <span className="mb-1 block text-slate-700 dark:text-slate-300">Mode</span>
                <select
                  value={mode}
                  onChange={(event) => void handleChangeMode(event.target.value as JobExecutionMode)}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 capitalize dark:border-slate-700 dark:bg-slate-950 dark:text-white"
                >
                  <option value="adaptive">adaptive</option>
                  <option value="strict">strict</option>
                  <option value="both">both</option>
                </select>
              </label>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4 dark:border-slate-800 dark:bg-slate-950/40">
              <div className="grid gap-4 lg:grid-cols-[1.2fr,1fr,1fr,1fr]">
                <div>
                  <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Queue status</p>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <StatusBadge value={hasActiveRun(job) ? "running" : job.status} />
                    <span className="text-sm text-slate-600 dark:text-slate-300">
                      {isRefreshing ? "Refreshing..." : lastRefreshedAt ? `Updated ${formatDate(lastRefreshedAt)}` : "Awaiting refresh"}
                    </span>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2 text-xs font-medium">
                    <span className="rounded-full bg-white px-3 py-1 text-slate-700 ring-1 ring-slate-200 dark:bg-slate-900 dark:text-slate-200 dark:ring-slate-700">
                      Loaded {queueSummary.loaded}
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
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Current run</p>
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <StatusBadge value={activeRun?.status ?? "idle"} />
                    <span className="text-sm font-medium capitalize text-slate-900 dark:text-white">
                      {activeRun ? `${activeRun.mode} run` : "No active run"}
                    </span>
                  </div>
                  <dl className="mt-3 space-y-1 text-sm">
                    <div className="flex items-center justify-between gap-3">
                      <dt className="text-slate-500 dark:text-slate-400">Processed</dt>
                      <dd className="text-slate-900 dark:text-white">{activeRun?.processedCount ?? 0}</dd>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <dt className="text-slate-500 dark:text-slate-400">Failed</dt>
                      <dd className="text-slate-900 dark:text-white">{activeRun?.failedCount ?? 0}</dd>
                    </div>
                  </dl>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Progress</p>
                  <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">
                    {queueSummary.processed}/{totalDocuments || 0}
                  </p>
                  <dl className="mt-3 space-y-1 text-sm">
                    <div className="flex items-center justify-between gap-3">
                      <dt className="text-slate-500 dark:text-slate-400">Pending</dt>
                      <dd className="text-slate-900 dark:text-white">{pendingDocuments}</dd>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <dt className="text-slate-500 dark:text-slate-400">Reviewed</dt>
                      <dd className="text-slate-900 dark:text-white">{reviewedDocuments}</dd>
                    </div>
                  </dl>
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Job snapshot</p>
                  <dl className="mt-2 space-y-1 text-sm">
                    <div className="flex items-center justify-between gap-3">
                      <dt className="text-slate-500 dark:text-slate-400">Created</dt>
                      <dd className="text-right text-slate-900 dark:text-white">{formatDate(job.createdAt)}</dd>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <dt className="text-slate-500 dark:text-slate-400">Selected</dt>
                      <dd className="text-slate-900 dark:text-white">
                        {selectedDocuments.length}/{totalDocuments || 0}
                      </dd>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <dt className="text-slate-500 dark:text-slate-400">Fields</dt>
                      <dd className="text-slate-900 dark:text-white">{fieldConfig.length}</dd>
                    </div>
                  </dl>
                </div>
              </div>
            </div>
          </div>
          
        </div>

      </section>

      {error ? (
        <div className="rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300">
          {error}
        </div>
      ) : null}

      <IdpoCard>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Queue</h2>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              The queue is the primary operator surface. Keep statuses simple and open a document only when atomic detail
              is needed.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void handleToggleAll()}
            disabled={saving || selectableDocumentIds.length === 0}
            className="text-sm font-medium text-cyan-700 hover:text-cyan-800 disabled:opacity-50 dark:text-cyan-300 dark:hover:text-cyan-200"
          >
            {selectedFileIds.length === selectableDocumentIds.length ? "Clear selection" : "Select all available"}
          </button>
        </div>

        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[1280px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                <th className="px-2 py-2">Select</th>
                <th className="px-2 py-2">File name</th>
                <th className="px-2 py-2">File ID</th>
                <th className="px-2 py-2">Status</th>
                <th className="px-2 py-2">Mode</th>
                <th className="px-2 py-2">Route</th>
                <th className="px-2 py-2">Policy</th>
                <th className="px-2 py-2">Review / Error</th>
                <th className="px-2 py-2">Action</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((document) => {
                const preferredOutcome = getOutcome(document, activeResultMode);
                const routeValue = preferredOutcome?.route ?? document.latestRoute;
                const policyValue = preferredOutcome?.policy ?? document.latestPolicy;
                const actionRunId = preferredOutcome?.runId ?? document.latestRunId;
                const docHref =
                  actionRunId
                    ? `/dashboard/idpo/jobs/${encodeURIComponent(job.jobId)}/docs/${encodeURIComponent(document.fileId)}?mode=${encodeURIComponent(activeResultMode)}&runId=${encodeURIComponent(actionRunId)}`
                    : null;
                const policyHref = policyValue
                  ? `/dashboard/idpo/jobs/${encodeURIComponent(job.jobId)}/policies/${encodeURIComponent(policyValue)}`
                  : null;
                return (
                  <tr key={document.fileId} className="border-b border-slate-100 dark:border-slate-800">
                    <td className="px-2 py-2">
                      <input
                        type="checkbox"
                        checked={selectedFileIds.includes(document.fileId)}
                        onChange={() => void handleToggleSelection(document.fileId)}
                        disabled={saving || document.status === "processing"}
                      />
                    </td>
                    <td className="px-2 py-2 font-medium text-slate-900 dark:text-slate-100">{document.fileName}</td>
                    <td className="px-2 py-2 font-mono text-xs text-slate-600 dark:text-slate-300">
                      {fileIdSummary(document.fileId)}
                    </td>
                    <td className="px-2 py-2">
                      <StatusBadge value={document.status} />
                    </td>
                    <td className="px-2 py-2 capitalize text-slate-600 dark:text-slate-300">
                      {preferredOutcome?.mode ?? activeRun?.mode ?? job.mode ?? mode}
                    </td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">
                      {routeValue ?? "NA"}
                    </td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">
                      {policyHref ? (
                        <Link
                          href={policyHref}
                          className="text-xs font-medium text-cyan-700 hover:text-cyan-800 dark:text-cyan-300 dark:hover:text-cyan-200"
                        >
                          {policyValue}
                        </Link>
                      ) : (
                        "NA"
                      )}
                    </td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusBadge value={document.reviewStatus ?? "unreviewed"} />
                        {preferredOutcome?.exactF1 != null ? (
                          <span className="text-xs font-medium text-slate-700 dark:text-slate-200">
                            F1 {preferredOutcome.exactF1.toFixed(2)}
                          </span>
                        ) : null}
                      </div>
                      {document.errorSummary ? (
                        <div className="mt-1 text-xs text-rose-700 dark:text-rose-300">{document.errorSummary}</div>
                      ) : (
                        <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                          {formatReviewState(document.reviewState)}
                        </div>
                      )}
                    </td>
                    <td className="px-2 py-2">
                      {docHref ? (
                        <Link
                          href={docHref}
                          className="text-xs font-medium text-cyan-700 hover:text-cyan-800 dark:text-cyan-300 dark:hover:text-cyan-200"
                        >
                          Open detail
                        </Link>
                      ) : document.status === "processing" ? (
                        <span className="text-xs text-slate-500 dark:text-slate-400">
                          {activeRun ? `Processing in ${activeRun.mode}` : "Processing"}
                        </span>
                      ) : (
                        <span className="text-xs text-slate-500 dark:text-slate-400">Waiting</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {documents.length === 0 ? (
            <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">No documents in this job yet.</p>
          ) : null}
        </div>
      </IdpoCard>

      <IdpoCard>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Field configuration</h2>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              These fields are snapshotted per run. Edit them here before starting the next run.
            </p>
          </div>
          <button
            type="button"
            onClick={() => setShowAdvanced((current) => !current)}
            className="text-sm font-medium text-cyan-700 hover:text-cyan-800 dark:text-cyan-300 dark:hover:text-cyan-200"
          >
            {showAdvanced ? "Hide advanced settings" : "Show advanced settings"}
          </button>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-[1fr,1fr,auto]">
          <input
            value={newFieldName}
            onChange={(event) => setNewFieldName(event.target.value)}
            placeholder="Field name"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          />
          <input
            value={newFieldDescription}
            onChange={(event) => setNewFieldDescription(event.target.value)}
            placeholder="Short description"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          />
          <button
            type="button"
            onClick={() => void handleAddField()}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200"
          >
            Add field
          </button>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          {fieldConfig.map((field, index) => (
            <div
              key={`${field.name}-${index}`}
              className="flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm dark:border-slate-800 dark:bg-slate-950/40"
            >
              <span className="text-slate-900 dark:text-white">{field.name}</span>
              {field.description ? <span className="text-xs text-slate-500 dark:text-slate-400">({field.description})</span> : null}
              <button
                type="button"
                onClick={() => void handleRemoveField(index)}
                className="text-xs font-medium text-rose-700 hover:text-rose-800 dark:text-rose-300 dark:hover:text-rose-200"
              >
                x
              </button>
            </div>
          ))}
          {fieldConfig.length === 0 ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">No fields configured yet.</p>
          ) : null}
        </div>

        {showAdvanced ? (
          <div className="mt-4 grid gap-4 rounded-xl border border-slate-200 bg-slate-50 p-4 md:grid-cols-2 dark:border-slate-800 dark:bg-slate-950/40">
            <label className="text-sm">
              <span className="mb-1 block text-slate-700 dark:text-slate-300">Max cost per document</span>
              <input
                value={maxCostPerDoc}
                onChange={(event) => setMaxCostPerDoc(event.target.value)}
                placeholder="Optional"
                className="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
              />
            </label>
            <label className="flex items-center gap-3 text-sm text-slate-700 dark:text-slate-300">
              <input
                type="checkbox"
                checked={escalationEnabled}
                onChange={(event) => setEscalationEnabled(event.target.checked)}
              />
              Allow escalation
            </label>
          </div>
        ) : null}
      </IdpoCard>

      <IdpoCard>
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">AHMN job summary</h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          Visible but restrained. This is the job-level adaptive memory view, not a second dashboard.
        </p>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[680px] text-sm">
            <tbody>
              <tr className="border-b border-slate-100 dark:border-slate-800">
                <td className="px-2 py-3 font-medium text-slate-900 dark:text-slate-100">Job nature / profile</td>
                <td className="px-2 py-3 text-slate-600 dark:text-slate-300">{job.ahmnSummary?.jobProfile ?? "awaiting_run"}</td>
              </tr>
              <tr className="border-b border-slate-100 dark:border-slate-800">
                <td className="px-2 py-3 font-medium text-slate-900 dark:text-slate-100">Memory matched</td>
                <td className="px-2 py-3 text-slate-600 dark:text-slate-300">
                  {job.ahmnSummary?.memoryMatched ? "yes" : "no"}
                </td>
              </tr>
              <tr className="border-b border-slate-100 dark:border-slate-800">
                <td className="px-2 py-3 font-medium text-slate-900 dark:text-slate-100">Advice influenced routing</td>
                <td className="px-2 py-3 text-slate-600 dark:text-slate-300">
                  {job.ahmnSummary?.adviceInfluencedCount ?? 0} document(s)
                </td>
              </tr>
              <tr className="border-b border-slate-100 dark:border-slate-800">
                <td className="px-2 py-3 font-medium text-slate-900 dark:text-slate-100">Documents with advice</td>
                <td className="px-2 py-3 text-slate-600 dark:text-slate-300">
                  {job.ahmnSummary?.documentsWithAdvice ?? 0}
                </td>
              </tr>
              <tr className="border-b border-slate-100 dark:border-slate-800">
                <td className="px-2 py-3 font-medium text-slate-900 dark:text-slate-100">Documents logged back</td>
                <td className="px-2 py-3 text-slate-600 dark:text-slate-300">
                  {job.ahmnSummary?.documentsLoggedBack ?? 0}
                </td>
              </tr>
              <tr className="border-b border-slate-100 dark:border-slate-800">
                <td className="px-2 py-3 font-medium text-slate-900 dark:text-slate-100">Reviewed documents</td>
                <td className="px-2 py-3 text-slate-600 dark:text-slate-300">
                  {job.ahmnSummary?.reviewedDocumentCount ?? 0}
                  {typeof job.ahmnSummary?.reviewedHumanCount === "number" && typeof job.ahmnSummary?.reviewedAiCount === "number"
                    ? ` (${job.ahmnSummary.reviewedHumanCount} human, ${job.ahmnSummary.reviewedAiCount} AI)`
                    : ""}
                </td>
              </tr>
              <tr className="border-b border-slate-100 dark:border-slate-800">
                <td className="px-2 py-3 font-medium text-slate-900 dark:text-slate-100">Reviewed learning logged</td>
                <td className="px-2 py-3 text-slate-600 dark:text-slate-300">
                  {job.ahmnSummary?.reviewedFeedbackLoggedCount ?? 0}
                  {typeof job.ahmnSummary?.reviewedFeedbackPendingCount === "number"
                    ? ` (${job.ahmnSummary.reviewedFeedbackPendingCount} pending)`
                    : ""}
                </td>
              </tr>
              <tr className="border-b border-slate-100 dark:border-slate-800">
                <td className="px-2 py-3 font-medium text-slate-900 dark:text-slate-100">Job overlay</td>
                <td className="px-2 py-3 text-slate-600 dark:text-slate-300">
                  {job.ahmnSummary?.jobOverlayReady
                    ? `ready (${job.ahmnSummary?.jobOverlayPolicies ?? 0} policy bucket${(job.ahmnSummary?.jobOverlayPolicies ?? 0) === 1 ? "" : "s"})`
                    : "not ready"}
                </td>
              </tr>
              <tr>
                <td className="px-2 py-3 font-medium text-slate-900 dark:text-slate-100">Adaptation summary</td>
                <td className="px-2 py-3 text-slate-600 dark:text-slate-300">
                  {job.ahmnSummary?.adaptationSummary ?? "No completed runs yet."}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </IdpoCard>

      <IdpoCard>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Structured results</h2>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              Results stay field-oriented. Loaded and processing rows remain <code>NA</code> until that run mode completes.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {hasActiveRun(job) ? (
              <span className="rounded-full border border-cyan-200 bg-cyan-50 px-3 py-1 text-xs font-medium text-cyan-800 dark:border-cyan-800/50 dark:bg-cyan-950/30 dark:text-cyan-200">
                Live updates active
              </span>
            ) : null}
            {job.mode === "both" ? (
              <>
              <button
                type="button"
                onClick={() => setResultMode("adaptive")}
                className={`rounded-lg px-3 py-2 text-sm font-medium ${
                  resultMode === "adaptive"
                    ? "bg-cyan-600 text-white"
                    : "border border-slate-300 text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                }`}
              >
                Adaptive
              </button>
              <button
                type="button"
                onClick={() => setResultMode("strict")}
                className={`rounded-lg px-3 py-2 text-sm font-medium ${
                  resultMode === "strict"
                    ? "bg-cyan-600 text-white"
                    : "border border-slate-300 text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
                }`}
              >
                Strict
              </button>
              </>
            ) : null}
          </div>
        </div>

        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[980px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                <th className="px-2 py-2">File name</th>
                <th className="px-2 py-2">File ID</th>
                <th className="px-2 py-2">Status</th>
                {fieldConfig.map((field) => (
                  <th key={field.name} className="px-2 py-2">
                    {field.name}
                  </th>
                ))}
                <th className="px-2 py-2">Next</th>
              </tr>
            </thead>
            <tbody>
              {documents.map((document) => {
                const outcome = getOutcome(document, activeResultMode);
                return (
                  <tr key={document.fileId} className="border-b border-slate-100 dark:border-slate-800">
                    <td className="px-2 py-2 font-medium text-slate-900 dark:text-slate-100">{document.fileName}</td>
                    <td className="px-2 py-2 font-mono text-xs text-slate-600 dark:text-slate-300">{document.fileId}</td>
                    <td className="px-2 py-2">
                      <StatusBadge value={document.status} />
                    </td>
                    {fieldConfig.map((field) => (
                      <td key={`${document.fileId}-${field.name}`} className="px-2 py-2 text-slate-600 dark:text-slate-300">
                        {document.status === "processed" ? getOutcomeFieldValue(outcome, field) : "NA"}
                      </td>
                    ))}
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">
                      {outcome?.runId ? (
                        <Link
                          href={`/dashboard/idpo/jobs/${encodeURIComponent(job.jobId)}/docs/${encodeURIComponent(document.fileId)}?mode=${encodeURIComponent(activeResultMode)}&runId=${encodeURIComponent(outcome.runId)}`}
                          className="text-xs font-medium text-cyan-700 hover:text-cyan-800 dark:text-cyan-300 dark:hover:text-cyan-200"
                        >
                          Open detail
                        </Link>
                      ) : document.status === "failed" ? (
                        document.errorSummary || "Failed"
                      ) : document.status === "processing" ? (
                        "Wait"
                      ) : (
                        "NA"
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </IdpoCard>

      <IdpoCard>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Prior runs</h2>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              Explicit run history under this job. When mode is <code>both</code>, the adaptive and strict runs remain separate.
            </p>
          </div>
        </div>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[920px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                <th className="px-2 py-2">Run</th>
                <th className="px-2 py-2">Mode</th>
                <th className="px-2 py-2">Status</th>
                <th className="px-2 py-2">Created</th>
                <th className="px-2 py-2">Processed</th>
                <th className="px-2 py-2">Failed</th>
                <th className="px-2 py-2">Open</th>
              </tr>
            </thead>
            <tbody>
              {orderedRuns.map((run) => (
                <tr key={run.jobRunId} className="border-b border-slate-100 dark:border-slate-800">
                  <td className="px-2 py-2 font-mono text-xs text-slate-600 dark:text-slate-300">
                    {run.runId ?? run.jobRunId}
                  </td>
                  <td className="px-2 py-2 capitalize text-slate-600 dark:text-slate-300">{run.mode}</td>
                  <td className="px-2 py-2">
                    <StatusBadge value={run.status} />
                  </td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{formatDate(run.createdAt)}</td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{run.processedCount ?? 0}</td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{run.failedCount ?? 0}</td>
                  <td className="px-2 py-2">
                    {run.runId ? (
                      <Link
                        href={`/dashboard/idpo/runs/${encodeURIComponent(run.runId)}`}
                        className="text-xs font-medium text-cyan-700 hover:text-cyan-800 dark:text-cyan-300 dark:hover:text-cyan-200"
                      >
                        Open run
                      </Link>
                    ) : (
                      <span className="text-xs text-slate-500 dark:text-slate-400">Pending</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {orderedRuns.length === 0 ? (
            <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">No runs yet for this job.</p>
          ) : null}
        </div>
      </IdpoCard>
    </div>
  );
}
