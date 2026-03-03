"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { idpoApi } from "@/lib/idpo-api";
import type { JobStatus, RunSummary, SystemStatus } from "@/types/idpo";
import { IdpoCard } from "@/components/idpo/card";
import { StatusBadge } from "@/components/idpo/status-badge";

interface RunSettings {
  configPath: string;
  shadowMode: boolean;
  shadowSampleRate: number;
  policyPreference: string;
  routingMode: "auto" | "light" | "standard" | "heavy";
  maxCostPerDoc: number;
  escalationEnabled: boolean;
  report: boolean;
  customFields: Array<{
    key: string;
    description?: string;
    pattern?: string;
  }>;
  llmLocalModel: string;
  llmCloudModel: string;
  llmDefaultMode: "local" | "cloud";
  llmUseExtraction: boolean;
  llmUseSummarization: boolean;
  flagshipModel: string;
}

const defaultSettings: RunSettings = {
  configPath: "configs/idpo_research_config.json",
  shadowMode: true,
  shadowSampleRate: 0.1,
  policyPreference: "auto",
  routingMode: "auto",
  maxCostPerDoc: 7,
  escalationEnabled: true,
  report: true,
  customFields: [],
  llmLocalModel: "phi3:mini",
  llmCloudModel: "gpt-4o-mini",
  llmDefaultMode: "local",
  llmUseExtraction: false,
  llmUseSummarization: false,
  flagshipModel: "flagship-sim",
};

export default function IdpoDashboardPage() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [jobs, setJobs] = useState<JobStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>("");

  const [files, setFiles] = useState<File[]>([]);
  const [settings, setSettings] = useState<RunSettings>(defaultSettings);
  const [activeJob, setActiveJob] = useState<JobStatus | null>(null);
  const [starting, setStarting] = useState(false);
  const [fieldKey, setFieldKey] = useState("");
  const [fieldDescription, setFieldDescription] = useState("");
  const [fieldPattern, setFieldPattern] = useState("");

  const canStart = files.length > 0 && !starting;

  const refresh = async () => {
    const [system, data] = await Promise.all([idpoApi.systemStatus(), idpoApi.listRuns()]);
    setStatus(system);
    setRuns(data.runs);
    setJobs(data.jobs);
  };

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    refresh()
      .catch((err) => {
        if (mounted) {
          setError(err instanceof Error ? err.message : "Failed to load IDPO dashboard");
        }
      })
      .finally(() => {
        if (mounted) {
          setLoading(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!activeJob || activeJob.status === "success" || activeJob.status === "failed") {
      return;
    }

    const timer = window.setInterval(async () => {
      try {
        const next = await idpoApi.getJob(activeJob.jobId);
        setActiveJob(next);
        if (next.status === "success" || next.status === "failed") {
          await refresh();
        }
      } catch {
        // keep polling if transient failure
      }
    }, 1800);

    return () => window.clearInterval(timer);
  }, [activeJob]);

  const latestRun = useMemo(() => (runs.length > 0 ? runs[0] : null), [runs]);

  const startRun = async () => {
    try {
      setStarting(true);
      setError("");

      const form = new FormData();
      files.forEach((file) => form.append("files", file));
      form.append("settings", JSON.stringify(settings));

      const job = await idpoApi.startRun(form);
      setActiveJob(job);
      setFiles([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Run failed to start");
    } finally {
      setStarting(false);
    }
  };

  const addCustomField = () => {
    const key = fieldKey.trim();
    if (!key) {
      return;
    }
    setSettings((prev) => ({
      ...prev,
      customFields: [
        ...prev.customFields.filter((item) => item.key.toLowerCase() !== key.toLowerCase()),
        {
          key,
          description: fieldDescription.trim() || undefined,
          pattern: fieldPattern.trim() || undefined,
        },
      ],
    }));
    setFieldKey("");
    setFieldDescription("");
    setFieldPattern("");
  };

  const removeCustomField = (key: string) => {
    setSettings((prev) => ({
      ...prev,
      customFields: prev.customFields.filter((item) => item.key !== key),
    }));
  };

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-gradient-to-r from-cyan-50 via-white to-amber-50 p-6 shadow-sm dark:border-slate-800 dark:from-slate-900 dark:via-slate-900 dark:to-slate-900">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400">IDPO Control Plane</p>
            <h1 className="mt-1 text-3xl font-semibold text-slate-900 dark:text-white">Document AI Runner</h1>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">
              Upload documents, run orchestration, inspect provenance, compare shadow policies, and present the full flow.
            </p>
          </div>
          <div className="flex gap-2">
            <Link
              href="/dashboard/idpo/presentation"
              className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              Presentation Mode
            </Link>
            {latestRun ? (
              <Link
                href={`/dashboard/idpo/runs/${latestRun.runId}`}
                className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 dark:bg-brand-600 dark:hover:bg-brand-500"
              >
                Open Latest Run
              </Link>
            ) : null}
          </div>
        </div>
      </section>

      {error ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300">
          {error}
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <IdpoCard className="lg:col-span-2">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">System Status</h2>
            <button
              type="button"
              onClick={() => {
                setLoading(true);
                refresh()
                  .catch((err) => setError(err instanceof Error ? err.message : "Refresh failed"))
                  .finally(() => setLoading(false));
              }}
              className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              Refresh
            </button>
          </div>

          {loading ? (
            <p className="text-sm text-slate-500 dark:text-slate-400">Loading status...</p>
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {(status?.checks ?? []).map((check) => (
                <div
                  key={check.id}
                  className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800/60"
                >
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-medium text-slate-900 dark:text-white">{check.id}</p>
                    <StatusBadge value={check.ok ? "ready" : "failed"} />
                  </div>
                  <p className="mt-2 text-xs text-slate-600 dark:text-slate-400">{check.detail}</p>
                </div>
              ))}
            </div>
          )}
        </IdpoCard>

        <IdpoCard>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Recent Jobs</h2>
          <div className="mt-3 space-y-2">
            {(jobs.length === 0 ? [] : jobs).slice(0, 6).map((job) => (
              <div key={job.jobId} className="rounded-lg border border-slate-200 px-3 py-2 dark:border-slate-700">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-xs font-medium text-slate-700 dark:text-slate-200">{job.jobId.slice(0, 10)}</span>
                  <StatusBadge value={job.status} />
                </div>
                <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">{new Date(job.startedAt).toLocaleString()}</p>
              </div>
            ))}
            {jobs.length === 0 ? (
              <p className="text-sm text-slate-500 dark:text-slate-400">No jobs started yet.</p>
            ) : null}
          </div>
        </IdpoCard>
      </div>

      <IdpoCard>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-white">New Run Wizard</h2>
          <div className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-400">
            <span className="rounded-full bg-slate-100 px-2 py-1 dark:bg-slate-800">1 Upload</span>
            <span className="rounded-full bg-slate-100 px-2 py-1 dark:bg-slate-800">2 Configure</span>
            <span className="rounded-full bg-slate-100 px-2 py-1 dark:bg-slate-800">3 Launch</span>
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          <div className="space-y-3 lg:col-span-1">
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-200">Upload Documents</label>
            <input
              type="file"
              multiple
              accept=".pdf,.png,.jpg,.jpeg,.txt,.json"
              onChange={(event) => setFiles(Array.from(event.target.files ?? []))}
              className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 file:mr-3 file:rounded-md file:border-0 file:bg-slate-900 file:px-2 file:py-1.5 file:text-xs file:text-white dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:file:bg-brand-600"
            />
            <p className="text-xs text-slate-500 dark:text-slate-400">Accepted: pdf/png/jpg/txt/json</p>
            <div className="max-h-44 overflow-auto rounded-xl border border-slate-200 bg-slate-50 p-2 dark:border-slate-700 dark:bg-slate-800/50">
              {files.length === 0 ? (
                <p className="text-xs text-slate-500 dark:text-slate-400">No files selected.</p>
              ) : (
                files.map((file) => (
                  <div key={file.name} className="flex items-center justify-between gap-3 py-1 text-xs">
                    <span className="truncate text-slate-700 dark:text-slate-200">{file.name}</span>
                    <span className="text-slate-500 dark:text-slate-400">{(file.size / 1024).toFixed(1)} KB</span>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="grid gap-3 lg:col-span-2 md:grid-cols-2">
            <label className="space-y-1 text-sm">
              <span className="text-slate-700 dark:text-slate-200">Config Path</span>
              <input
                type="text"
                value={settings.configPath}
                onChange={(event) => setSettings((prev) => ({ ...prev, configPath: event.target.value }))}
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
              />
            </label>

            <label className="space-y-1 text-sm">
              <span className="text-slate-700 dark:text-slate-200">Policy Preference</span>
              <select
                value={settings.policyPreference}
                onChange={(event) => setSettings((prev) => ({ ...prev, policyPreference: event.target.value }))}
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
              >
                <option value="auto">auto</option>
                <option value="baseline">baseline</option>
                <option value="default">default</option>
                <option value="forms">forms</option>
                <option value="table_heavy">table_heavy</option>
              </select>
            </label>

            <label className="space-y-1 text-sm">
              <span className="text-slate-700 dark:text-slate-200">Routing Mode</span>
              <select
                value={settings.routingMode}
                onChange={(event) =>
                  setSettings((prev) => ({ ...prev, routingMode: event.target.value as RunSettings["routingMode"] }))
                }
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
              >
                <option value="auto">auto</option>
                <option value="light">light</option>
                <option value="standard">standard</option>
                <option value="heavy">heavy</option>
              </select>
            </label>

            <label className="space-y-1 text-sm">
              <span className="text-slate-700 dark:text-slate-200">Max Cost Per Doc</span>
              <input
                type="number"
                min={0}
                step={0.1}
                value={settings.maxCostPerDoc}
                onChange={(event) =>
                  setSettings((prev) => ({ ...prev, maxCostPerDoc: Number(event.target.value || 0) }))
                }
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
              />
            </label>

            <label className="flex items-center gap-3 rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-700">
              <input
                type="checkbox"
                checked={settings.shadowMode}
                onChange={(event) => setSettings((prev) => ({ ...prev, shadowMode: event.target.checked }))}
              />
              <span>Enable Shadow Mode</span>
            </label>

            <label className="space-y-1 text-sm">
              <span className="text-slate-700 dark:text-slate-200">Shadow Sample Rate (0-1)</span>
              <input
                type="number"
                min={0}
                max={1}
                step={0.01}
                value={settings.shadowSampleRate}
                onChange={(event) =>
                  setSettings((prev) => ({ ...prev, shadowSampleRate: Number(event.target.value || 0) }))
                }
                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
              />
            </label>

            <label className="flex items-center gap-3 rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-700">
              <input
                type="checkbox"
                checked={settings.escalationEnabled}
                onChange={(event) => setSettings((prev) => ({ ...prev, escalationEnabled: event.target.checked }))}
              />
              <span>Escalation Enabled</span>
            </label>

            <label className="flex items-center gap-3 rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-700">
              <input
                type="checkbox"
                checked={settings.report}
                onChange={(event) => setSettings((prev) => ({ ...prev, report: event.target.checked }))}
              />
              <span>Generate Report</span>
            </label>

            <div className="md:col-span-2 rounded-lg border border-slate-200 p-3 dark:border-slate-700">
              <p className="mb-2 text-sm font-medium text-slate-800 dark:text-slate-100">LLM + Escalation Models</p>
              <div className="grid gap-2 md:grid-cols-2">
                <label className="space-y-1 text-sm">
                  <span className="text-slate-700 dark:text-slate-200">Local LLM Model</span>
                  <input
                    type="text"
                    value={settings.llmLocalModel}
                    onChange={(event) => setSettings((prev) => ({ ...prev, llmLocalModel: event.target.value }))}
                    placeholder="phi3:mini"
                    className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
                  />
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-slate-700 dark:text-slate-200">Cloud LLM Model</span>
                  <input
                    type="text"
                    value={settings.llmCloudModel}
                    onChange={(event) => setSettings((prev) => ({ ...prev, llmCloudModel: event.target.value }))}
                    placeholder="gpt-4o-mini"
                    className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
                  />
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-slate-700 dark:text-slate-200">Default LLM Mode</span>
                  <select
                    value={settings.llmDefaultMode}
                    onChange={(event) =>
                      setSettings((prev) => ({ ...prev, llmDefaultMode: event.target.value as "local" | "cloud" }))
                    }
                    className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
                  >
                    <option value="local">local</option>
                    <option value="cloud">cloud</option>
                  </select>
                </label>
                <label className="space-y-1 text-sm">
                  <span className="text-slate-700 dark:text-slate-200">Flagship (Tier-2) Model</span>
                  <input
                    type="text"
                    value={settings.flagshipModel}
                    onChange={(event) => setSettings((prev) => ({ ...prev, flagshipModel: event.target.value }))}
                    placeholder="flagship-sim"
                    className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
                  />
                </label>
                <label className="flex items-center gap-3 rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-700">
                  <input
                    type="checkbox"
                    checked={settings.llmUseExtraction}
                    onChange={(event) => setSettings((prev) => ({ ...prev, llmUseExtraction: event.target.checked }))}
                  />
                  <span>Use LLM For Extraction</span>
                </label>
                <label className="flex items-center gap-3 rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-700">
                  <input
                    type="checkbox"
                    checked={settings.llmUseSummarization}
                    onChange={(event) =>
                      setSettings((prev) => ({ ...prev, llmUseSummarization: event.target.checked }))
                    }
                  />
                  <span>Use LLM For Summarization</span>
                </label>
              </div>
            </div>

            <div className="md:col-span-2 rounded-lg border border-slate-200 p-3 dark:border-slate-700">
              <p className="mb-2 text-sm font-medium text-slate-800 dark:text-slate-100">Custom Fields To Extract</p>
              <div className="grid gap-2 md:grid-cols-3">
                <input
                  type="text"
                  value={fieldKey}
                  onChange={(event) => setFieldKey(event.target.value)}
                  placeholder="field_key (required)"
                  className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
                />
                <input
                  type="text"
                  value={fieldDescription}
                  onChange={(event) => setFieldDescription(event.target.value)}
                  placeholder="description (optional)"
                  className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
                />
                <input
                  type="text"
                  value={fieldPattern}
                  onChange={(event) => setFieldPattern(event.target.value)}
                  placeholder="regex pattern (optional)"
                  className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
                />
              </div>
              <div className="mt-2 flex items-center justify-between gap-2">
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  If no regex is provided, IDPO will use `Field Label: value` style matching.
                </p>
                <button
                  type="button"
                  onClick={addCustomField}
                  className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  Add Field
                </button>
              </div>
              <div className="mt-2 max-h-28 space-y-1 overflow-auto">
                {settings.customFields.length === 0 ? (
                  <p className="text-xs text-slate-500 dark:text-slate-400">No custom fields configured.</p>
                ) : (
                  settings.customFields.map((field) => (
                    <div key={field.key} className="flex items-center justify-between rounded bg-slate-100 px-2 py-1 text-xs dark:bg-slate-800">
                      <span className="truncate text-slate-700 dark:text-slate-200">
                        {field.key}
                        {field.description ? ` - ${field.description}` : ""}
                        {field.pattern ? ` [${field.pattern}]` : ""}
                      </span>
                      <button
                        type="button"
                        onClick={() => removeCustomField(field.key)}
                        className="ml-2 rounded border border-slate-300 px-2 py-0.5 text-[11px] text-slate-700 hover:bg-slate-200 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-700"
                      >
                        Remove
                      </button>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="md:col-span-2">
              <button
                type="button"
                disabled={!canStart}
                onClick={startRun}
                className="w-full rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-medium text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50 dark:bg-brand-600 dark:hover:bg-brand-500"
              >
                {starting ? "Starting..." : "Start IDPO Run"}
              </button>
            </div>
          </div>
        </div>

        {activeJob ? (
          <div className="mt-6 rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-900">
            <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-3">
                <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Active Job {activeJob.jobId.slice(0, 10)}</h3>
                <StatusBadge value={activeJob.status} />
              </div>
              {activeJob.runId ? (
                <Link
                  href={`/dashboard/idpo/runs/${activeJob.runId}`}
                  className="rounded-lg border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  Open Run
                </Link>
              ) : null}
            </div>
            <pre className="max-h-56 overflow-auto rounded-lg border border-slate-200 bg-white p-3 text-xs leading-relaxed text-slate-700 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-300">
              {(activeJob.logs ?? []).slice(-120).join("\n") || "No logs yet"}
            </pre>
          </div>
        ) : null}
      </IdpoCard>

      <IdpoCard>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Recent Runs</h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">{runs.length} run(s)</p>
        </div>

        {runs.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
            No run artifacts found. Use the wizard to start a run, or drop sample runs under `frontend/demo_sample_runs/`.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[700px] text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                  <th className="px-2 py-2">Run</th>
                  <th className="px-2 py-2">Status</th>
                  <th className="px-2 py-2">Docs</th>
                  <th className="px-2 py-2">Source</th>
                  <th className="px-2 py-2">Updated</th>
                  <th className="px-2 py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {runs.slice(0, 20).map((run) => (
                  <tr key={run.runId} className="border-b border-slate-100 dark:border-slate-800">
                    <td className="px-2 py-2 font-medium text-slate-800 dark:text-slate-100">{run.runId}</td>
                    <td className="px-2 py-2">
                      <StatusBadge value={run.status} />
                    </td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{run.docCount}</td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{run.source}</td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">
                      {new Date(run.updatedAt).toLocaleString()}
                    </td>
                    <td className="px-2 py-2">
                      <Link
                        href={`/dashboard/idpo/runs/${run.runId}`}
                        className="rounded-lg border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
                      >
                        View Run
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </IdpoCard>
    </div>
  );
}
