"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { IdpoCard } from "@/components/idpo/card";
import { StatusBadge } from "@/components/idpo/status-badge";
import { idpoApi } from "@/lib/idpo-api";
import type { JobStatus } from "@/types/idpo";

function formatDate(value: string | undefined): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

export function JobsListPage() {
  const router = useRouter();
  const [jobs, setJobs] = useState<JobStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    idpoApi
      .listJobs()
      .then((payload) => {
        if (!active) {
          return;
        }
        setJobs(payload.jobs);
        setError("");
      })
      .catch((err) => {
        if (!active) {
          return;
        }
        setError(err instanceof Error ? err.message : "Failed to load jobs");
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, []);

  async function handleCreateJob() {
    try {
      setCreating(true);
      const job = await idpoApi.createJob();
      router.push(`/dashboard/idpo/jobs/${encodeURIComponent(job.jobId)}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create job");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900 dark:text-white">IDPO jobs</h1>
            <p className="mt-2 max-w-4xl text-sm text-slate-600 dark:text-slate-300">
              Jobs are the operator-facing batch unit. Create a job first, load documents into its queue, then run
              adaptive, strict, or both paths against the same batch.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void handleCreateJob()}
            disabled={creating}
            className="rounded-xl bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {creating ? "Creating..." : "New job"}
          </button>
        </div>
      </section>

      {error ? (
        <div className="rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300">
          {error}
        </div>
      ) : null}

      <IdpoCard>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Jobs control board</h2>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              Operational status first. Open a job to manage its queue, runs, AHMN summary, and structured results.
            </p>
          </div>
        </div>

        {loading ? (
          <p className="mt-4 text-sm text-slate-600 dark:text-slate-300">Loading jobs...</p>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[980px] text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                  <th className="px-2 py-2">Job ID</th>
                  <th className="px-2 py-2">Job name</th>
                  <th className="px-2 py-2">Created</th>
                  <th className="px-2 py-2">Mode</th>
                  <th className="px-2 py-2">Status</th>
                  <th className="px-2 py-2">Loaded</th>
                  <th className="px-2 py-2">Processing</th>
                  <th className="px-2 py-2">Processed</th>
                  <th className="px-2 py-2">Failed</th>
                  <th className="px-2 py-2">Open</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.jobId} className="border-b border-slate-100 dark:border-slate-800">
                    <td className="px-2 py-2 font-mono text-xs text-slate-600 dark:text-slate-300">{job.jobId}</td>
                    <td className="px-2 py-2 font-medium text-slate-900 dark:text-slate-100">
                      {job.jobName?.trim() || "Untitled job"}
                    </td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{formatDate(job.createdAt)}</td>
                    <td className="px-2 py-2 text-slate-600 capitalize dark:text-slate-300">{job.mode ?? "adaptive"}</td>
                    <td className="px-2 py-2">
                      <StatusBadge value={job.status} />
                    </td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{job.counts?.loadedCount ?? 0}</td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{job.counts?.processingCount ?? 0}</td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{job.counts?.processedCount ?? 0}</td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{job.counts?.failedCount ?? 0}</td>
                    <td className="px-2 py-2">
                      <Link
                        href={`/dashboard/idpo/jobs/${encodeURIComponent(job.jobId)}`}
                        className="text-xs font-medium text-cyan-700 hover:text-cyan-800 dark:text-cyan-300 dark:hover:text-cyan-200"
                      >
                        Open job
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {jobs.length === 0 ? (
              <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">No jobs yet. Create one to start a batch.</p>
            ) : null}
          </div>
        )}
      </IdpoCard>
    </div>
  );
}
