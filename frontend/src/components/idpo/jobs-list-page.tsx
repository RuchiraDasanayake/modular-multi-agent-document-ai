"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { IdpoCard } from "@/components/idpo/card";
import { StatusBadge } from "@/components/idpo/status-badge";
import { Icon } from "@/components/icons";
import { idpoApi } from "@/lib/idpo-api";
import type { JobStatus } from "@/types/idpo";

const MODE_LABELS: Record<string, string> = {
  adaptive: "Adaptive",
  strict: "Strict",
  both: "Both",
};

function formatDate(value: string | undefined): string {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function documentSummary(job: JobStatus): string {
  const counts = job.counts;
  const total =
    (counts?.loadedCount ?? 0) + (counts?.processingCount ?? 0) + (counts?.processedCount ?? 0) + (counts?.failedCount ?? 0);
  if (total === 0) {
    return "No documents yet";
  }
  const parts = [`${counts?.processedCount ?? 0} of ${total} processed`];
  if (counts?.processingCount) parts.push(`${counts.processingCount} processing`);
  if (counts?.failedCount) parts.push(`${counts.failedCount} failed`);
  return parts.join(" · ");
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
        setError(err instanceof Error ? err.message : "Could not load jobs.");
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
      setError(err instanceof Error ? err.message : "Could not create a job.");
      setCreating(false);
    }
  }

  const newJobButton = (
    <button
      type="button"
      onClick={() => void handleCreateJob()}
      disabled={creating}
      className="inline-flex items-center gap-2 rounded-xl bg-cyan-600 px-4 py-2 text-sm font-medium text-white hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-60"
    >
      <Icon name="upload" />
      {creating ? "Creating..." : "New job"}
    </button>
  );

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900 dark:text-white">Document jobs</h1>
            <p className="mt-2 max-w-3xl text-sm text-slate-600 dark:text-slate-300">
              A job holds a batch of documents. Create one, upload the files and process them; open it later to check
              results or retry failures.
            </p>
          </div>
          {newJobButton}
        </div>
      </section>

      {error ? (
        <div
          role="alert"
          className="rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300"
        >
          {error}
        </div>
      ) : null}

      <IdpoCard>
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Recent jobs</h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">Newest first.</p>

        {loading ? (
          <div className="mt-4 space-y-2" aria-hidden="true">
            {[0, 1, 2].map((row) => (
              <div key={row} className="h-12 animate-pulse rounded-lg bg-slate-100 dark:bg-slate-800/70" />
            ))}
          </div>
        ) : jobs.length === 0 ? (
          <div className="mt-4 flex flex-col items-center rounded-xl border border-dashed border-slate-300 px-6 py-10 text-center dark:border-slate-700">
            <p className="text-sm font-medium text-slate-900 dark:text-white">No jobs yet</p>
            <p className="mt-1 max-w-sm text-sm text-slate-500 dark:text-slate-400">
              Create a job to upload receipts, invoices or forms and extract their fields.
            </p>
            <div className="mt-4">{newJobButton}</div>
          </div>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                  <th className="px-2 py-2 font-medium">Job</th>
                  <th className="px-2 py-2 font-medium">Created</th>
                  <th className="px-2 py-2 font-medium">Mode</th>
                  <th className="px-2 py-2 font-medium">Status</th>
                  <th className="px-2 py-2 font-medium">Documents</th>
                  <th className="px-2 py-2 font-medium">
                    <span className="sr-only">Open</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => {
                  const href = `/dashboard/idpo/jobs/${encodeURIComponent(job.jobId)}`;
                  return (
                    <tr
                      key={job.jobId}
                      className="border-b border-slate-100 last:border-0 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800/40"
                    >
                      <td className="px-2 py-2.5">
                        <Link href={href} className="font-medium text-slate-900 hover:underline dark:text-slate-100">
                          {job.jobName?.trim() || "Untitled job"}
                        </Link>
                        <p className="font-mono text-xs text-slate-500 dark:text-slate-400" title={job.jobId}>
                          {job.jobId.slice(0, 8)}
                        </p>
                      </td>
                      <td className="px-2 py-2.5 text-slate-600 dark:text-slate-300">{formatDate(job.createdAt)}</td>
                      <td className="px-2 py-2.5 text-slate-600 dark:text-slate-300">
                        {MODE_LABELS[job.mode ?? "adaptive"] ?? job.mode}
                      </td>
                      <td className="px-2 py-2.5">
                        <StatusBadge value={job.status} />
                      </td>
                      <td className="px-2 py-2.5 text-slate-600 dark:text-slate-300">{documentSummary(job)}</td>
                      <td className="px-2 py-2.5 text-right">
                        <Link href={href} className="whitespace-nowrap text-xs font-medium text-cyan-700 hover:underline dark:text-cyan-300">
                          Open →
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </IdpoCard>
    </div>
  );
}
