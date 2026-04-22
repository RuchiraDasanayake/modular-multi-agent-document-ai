import Link from "next/link";
import type { RefObject } from "react";
import { IdpoCard } from "@/components/idpo/card";
import { StatusBadge } from "@/components/idpo/status-badge";
import type { IDPOExtractionField, IDPORunResult } from "@/types";

export const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024;
export const SUPPORTED_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".txt", ".json"];

export type QueueStatus = "loaded" | "processing" | "processed" | "failed";

export interface JobQueueItem {
  queueId: string;
  fileName: string;
  fileSizeLabel: string;
  selected: boolean;
  status: QueueStatus;
  docId?: string | null;
  runId?: string | null;
  selectedPolicy?: string | null;
  route?: string | null;
  errorSummary?: string | null;
  reviewState?: string | null;
  fieldValues: Record<string, string>;
  hasAhmnAdvice?: boolean;
  hasXai?: boolean;
  hitlStatus?: string | null;
}

export interface QueueSummary {
  loaded: number;
  processing: number;
  processed: number;
  failed: number;
}

export interface JobSupportSummary {
  ahmnAdviceCount: number;
  xaiExplanationCount: number;
  hitlFeedbackCount: number;
}

export function formatDuration(durationMs?: number): string {
  if (typeof durationMs !== "number" || Number.isNaN(durationMs)) {
    return "-";
  }
  const totalSeconds = Math.max(0, Math.round(durationMs / 1000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes === 0) {
    return `${seconds}s`;
  }
  return `${minutes}m ${seconds}s`;
}

function overallQueueStatus(summary: QueueSummary): QueueStatus | "ready" {
  if (summary.processing > 0) {
    return "processing";
  }
  if (summary.failed > 0 && summary.processed === 0 && summary.loaded === 0) {
    return "failed";
  }
  if (summary.processed > 0 && summary.loaded === 0 && summary.processing === 0) {
    return "processed";
  }
  if (summary.loaded > 0) {
    return "loaded";
  }
  return "ready";
}

interface UploadSectionProps {
  items: JobQueueItem[];
  fileInputRef: RefObject<HTMLInputElement | null>;
  appendFiles: (incomingFiles: File[]) => void;
  removeFile: (queueId: string) => void;
  toggleSelected: (queueId: string) => void;
}

export function UploadSection({
  items,
  fileInputRef,
  appendFiles,
  removeFile,
  toggleSelected,
}: UploadSectionProps) {
  const selectedCount = items.filter((item) => item.selected).length;

  return (
    <IdpoCard>
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-white">1. Job queue</h2>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
            Load documents into the job queue, then choose which ones to process.
          </p>
        </div>
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-700"
        >
          Add files
        </button>
      </div>

      <div
        className="mt-4 rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-6 dark:border-slate-700 dark:bg-slate-950/40"
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          appendFiles(Array.from(event.dataTransfer.files || []));
        }}
      >
        <p className="text-sm text-slate-600 dark:text-slate-300">Drag files here or use the add files button.</p>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          onChange={(event) => appendFiles(Array.from(event.target.files || []))}
        />
      </div>

      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[860px] text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
              <th className="px-2 py-2">Use</th>
              <th className="px-2 py-2">File name</th>
              <th className="px-2 py-2">File ID</th>
              <th className="px-2 py-2">Status</th>
              <th className="px-2 py-2">Policy / Route</th>
              <th className="px-2 py-2">Review / Failure</th>
              <th className="px-2 py-2">Action</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.queueId} className="border-b border-slate-100 dark:border-slate-800">
                <td className="px-2 py-2">
                  <input
                    type="checkbox"
                    checked={item.selected}
                    onChange={() => toggleSelected(item.queueId)}
                    disabled={item.status === "processing"}
                  />
                </td>
                <td className="px-2 py-2 font-medium text-slate-900 dark:text-slate-100">{item.fileName}</td>
                <td className="px-2 py-2 font-mono text-xs text-slate-600 dark:text-slate-300">{item.queueId.slice(0, 8)}</td>
                <td className="px-2 py-2">
                  <StatusBadge value={item.status} />
                </td>
                <td className="px-2 py-2 text-slate-600 dark:text-slate-300">
                  {item.selectedPolicy || item.route || "NA"}
                </td>
                <td className="px-2 py-2 text-slate-600 dark:text-slate-300">
                  {item.errorSummary || (item.reviewState && item.reviewState !== "clear" ? item.reviewState : "NA")}
                </td>
                <td className="px-2 py-2">
                  {item.runId && item.docId ? (
                    <Link
                      href={`/dashboard/idpo/runs/${encodeURIComponent(item.runId)}/docs/${encodeURIComponent(item.docId)}`}
                      className="text-xs font-medium text-cyan-700 hover:text-cyan-800 dark:text-cyan-300 dark:hover:text-cyan-200"
                    >
                      Open detail
                    </Link>
                  ) : item.status === "processing" ? (
                    <span className="text-xs text-slate-500 dark:text-slate-400">Processing</span>
                  ) : (
                    <button
                      type="button"
                      onClick={() => removeFile(item.queueId)}
                      className="text-xs font-medium text-rose-700 hover:text-rose-800 dark:text-rose-300 dark:hover:text-rose-200"
                    >
                      Remove
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {items.length === 0 ? (
          <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">No documents loaded into the job yet.</p>
        ) : (
          <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">
            {items.length} queued document(s), {selectedCount} selected for the next job run.
          </p>
        )}
      </div>
    </IdpoCard>
  );
}

interface FieldsSectionProps {
  fields: IDPOExtractionField[];
  newFieldName: string;
  newFieldDesc: string;
  setNewFieldName: (value: string) => void;
  setNewFieldDesc: (value: string) => void;
  addField: () => void;
  removeField: (index: number) => void;
}

export function FieldsSection({
  fields,
  newFieldName,
  newFieldDesc,
  setNewFieldName,
  setNewFieldDesc,
  addField,
  removeField,
}: FieldsSectionProps) {
  return (
    <IdpoCard>
      <h2 className="text-lg font-semibold text-slate-900 dark:text-white">2. Extraction fields</h2>
      <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
        Define the structured fields this job must extract.
      </p>

      <div className="mt-4 grid gap-3 sm:grid-cols-[1fr,1fr,auto]">
        <input
          value={newFieldName}
          onChange={(event) => setNewFieldName(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              addField();
            }
          }}
          placeholder="Field name"
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950 dark:text-white"
        />
        <input
          value={newFieldDesc}
          onChange={(event) => setNewFieldDesc(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              addField();
            }
          }}
          placeholder="Short description"
          className="rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950 dark:text-white"
        />
        <button
          type="button"
          onClick={addField}
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200"
        >
          Add field
        </button>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {fields.length > 0 ? (
          fields.map((field, index) => (
            <div
              key={`${field.name}-${index}`}
              className="flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-sm dark:border-slate-800 dark:bg-slate-950/40"
            >
              <span className="text-slate-900 dark:text-white">{field.name}</span>
              {field.description ? (
                <span className="text-xs text-slate-500 dark:text-slate-400">({field.description})</span>
              ) : null}
              <button
                type="button"
                onClick={() => removeField(index)}
                className="text-xs font-medium text-rose-700 hover:text-rose-800 dark:text-rose-300 dark:hover:text-rose-200"
              >
                x
              </button>
            </div>
          ))
        ) : (
          <p className="text-sm text-slate-500 dark:text-slate-400">No extraction fields configured yet.</p>
        )}
      </div>
    </IdpoCard>
  );
}

interface SettingsPanelProps {
  jobName: string;
  setJobName: (value: string) => void;
  adaptiveMode: "static" | "adaptive_safe";
  setAdaptiveMode: (value: "static" | "adaptive_safe") => void;
  maxCostPerDoc: string;
  setMaxCostPerDoc: (value: string) => void;
  escalationEnabled: boolean;
  setEscalationEnabled: (value: boolean) => void;
  showAdvancedSettings: boolean;
  setShowAdvancedSettings: (value: boolean | ((current: boolean) => boolean)) => void;
  loading: boolean;
  selectedCount: number;
}

export function SettingsPanel({
  jobName,
  setJobName,
  adaptiveMode,
  setAdaptiveMode,
  maxCostPerDoc,
  setMaxCostPerDoc,
  escalationEnabled,
  setEscalationEnabled,
  showAdvancedSettings,
  setShowAdvancedSettings,
  loading,
  selectedCount,
}: SettingsPanelProps) {
  return (
    <IdpoCard>
      <h2 className="text-lg font-semibold text-slate-900 dark:text-white">3. Job setup</h2>
      <div className="mt-4 space-y-4">
        <label className="block text-sm">
          <span className="mb-1 block text-slate-700 dark:text-slate-300">Job name</span>
          <input
            value={jobName}
            onChange={(event) => setJobName(event.target.value)}
            placeholder="Optional job label"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          />
        </label>

        <label className="block text-sm">
          <span className="mb-1 block text-slate-700 dark:text-slate-300">Mode</span>
          <select
            value={adaptiveMode}
            onChange={(event) => setAdaptiveMode(event.target.value as "static" | "adaptive_safe")}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-950 dark:text-white"
          >
            <option value="adaptive_safe">Adaptive</option>
            <option value="static">Strict</option>
          </select>
        </label>

        <button
          type="button"
          onClick={() => setShowAdvancedSettings((current) => !current)}
          className="text-sm font-medium text-cyan-700 hover:text-cyan-800 dark:text-cyan-300 dark:hover:text-cyan-200"
        >
          {showAdvancedSettings ? "Hide advanced settings" : "Show advanced settings"}
        </button>

        {showAdvancedSettings && (
          <div className="space-y-4 rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-950/40">
            <label className="block text-sm">
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
        )}

        <button
          type="submit"
          disabled={loading || selectedCount === 0}
          className="w-full rounded-xl bg-cyan-600 px-4 py-3 text-sm font-medium text-white hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading ? "Processing job..." : `Process ${selectedCount} selected document(s)`}
        </button>
      </div>
    </IdpoCard>
  );
}

interface StatusPanelProps {
  loading: boolean;
  elapsedSec: number;
  result: IDPORunResult | null;
  queueSummary: QueueSummary;
  jobName: string;
}

export function StatusPanel({ loading, elapsedSec, result, queueSummary, jobName }: StatusPanelProps) {
  const status = overallQueueStatus(queueSummary);

  return (
    <IdpoCard>
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Job status</h2>
        <StatusBadge value={loading ? "processing" : status} />
      </div>

      <div className="mt-4 space-y-2 text-sm text-slate-600 dark:text-slate-300">
        <p>Job: {jobName || "Untitled extraction job"}</p>
        <p>Loaded: {queueSummary.loaded}</p>
        <p>Processing: {queueSummary.processing}</p>
        <p>Processed: {queueSummary.processed}</p>
        <p>Failed: {queueSummary.failed}</p>
        {loading ? <p>Elapsed: {elapsedSec}s</p> : null}
        {result ? <p>Latest run: {result.run_id}</p> : null}
      </div>

      {loading ? (
        <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
          <div className="h-full w-1/3 animate-pulse rounded-full bg-cyan-500" />
        </div>
      ) : null}
    </IdpoCard>
  );
}

interface ResultsSectionProps {
  result: IDPORunResult | null;
  queueItems: JobQueueItem[];
  fields: IDPOExtractionField[];
  supportSummary: JobSupportSummary;
  handleDownload: (file: "docs.xlsx" | "entities.xlsx" | "run.xlsx", filename: string) => Promise<void>;
}

export function ResultsSection({
  result,
  queueItems,
  fields,
  supportSummary,
  handleDownload,
}: ResultsSectionProps) {
  const hasSupportSignals =
    supportSummary.ahmnAdviceCount > 0 || supportSummary.xaiExplanationCount > 0 || supportSummary.hitlFeedbackCount > 0;

  return (
    <section className="space-y-6">
      <IdpoCard>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Structured results</h2>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              Loaded and processing items remain `NA` until extraction completes.
            </p>
            {result ? (
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">Latest run ID: {result.run_id}</p>
            ) : null}
          </div>
          {result ? (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void handleDownload("docs.xlsx", "docs.xlsx")}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                Download docs
              </button>
              <button
                type="button"
                onClick={() => void handleDownload("entities.xlsx", "entities.xlsx")}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                Download entities
              </button>
              <button
                type="button"
                onClick={() => void handleDownload("run.xlsx", "run.xlsx")}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
              >
                Download run
              </button>
              <Link
                href={`/dashboard/idpo/runs/${encodeURIComponent(result.run_id)}`}
                className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200"
              >
                Open run detail
              </Link>
            </div>
          ) : null}
        </div>

        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[980px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                <th className="px-2 py-2">File name</th>
                <th className="px-2 py-2">File ID</th>
                <th className="px-2 py-2">Status</th>
                {fields.map((field) => (
                  <th key={field.name} className="px-2 py-2">
                    {field.name}
                  </th>
                ))}
                <th className="px-2 py-2">Next</th>
              </tr>
            </thead>
            <tbody>
              {queueItems.map((item) => (
                <tr key={item.queueId} className="border-b border-slate-100 dark:border-slate-800">
                  <td className="px-2 py-2 font-medium text-slate-900 dark:text-slate-100">{item.fileName}</td>
                  <td className="px-2 py-2 font-mono text-xs text-slate-600 dark:text-slate-300">
                    {item.docId || item.queueId.slice(0, 8)}
                  </td>
                  <td className="px-2 py-2">
                    <StatusBadge value={item.status} />
                  </td>
                  {fields.map((field) => (
                    <td key={`${item.queueId}-${field.name}`} className="px-2 py-2 text-slate-600 dark:text-slate-300">
                      {item.status === "processed" ? item.fieldValues[field.name] || "NA" : "NA"}
                    </td>
                  ))}
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">
                    {item.runId && item.docId ? (
                      <Link
                        href={`/dashboard/idpo/runs/${encodeURIComponent(item.runId)}/docs/${encodeURIComponent(item.docId)}`}
                        className="text-xs font-medium text-cyan-700 hover:text-cyan-800 dark:text-cyan-300 dark:hover:text-cyan-200"
                      >
                        Open detail
                      </Link>
                    ) : item.status === "failed" ? (
                      item.errorSummary || "Check error"
                    ) : item.status === "processing" ? (
                      "Wait"
                    ) : (
                      "Run job"
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {queueItems.length === 0 ? (
            <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">No queued documents yet.</p>
          ) : null}
        </div>
      </IdpoCard>

      {hasSupportSignals ? (
        <IdpoCard>
          <div className="flex flex-wrap items-center gap-3 text-sm text-slate-600 dark:text-slate-300">
            <span className="font-medium text-slate-900 dark:text-white">Adaptive support</span>
            <span>AHMN advice: {supportSummary.ahmnAdviceCount}</span>
            <span>XAI explanations: {supportSummary.xaiExplanationCount}</span>
            <span>HITL feedback: {supportSummary.hitlFeedbackCount}</span>
          </div>
        </IdpoCard>
      ) : null}
    </section>
  );
}
