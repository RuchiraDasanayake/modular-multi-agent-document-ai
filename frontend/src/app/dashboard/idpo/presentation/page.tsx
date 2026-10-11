"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { idpoApi } from "@/lib/idpo-api";
import { Icon, type IconName } from "@/components/icons";
import type { RunOverview, RunSummary } from "@/types/idpo";

const STEPS: Array<{ title: string; body: string; href?: string; action: string; icon: IconName }> = [
  {
    title: "Upload and process",
    body: "Create a job, upload a few receipts or forms and choose \"Both: run each and compare\". Static uses the default policy; adaptive asks AHMN which policy to use, behind the safety gate.",
    href: "/dashboard/idpo/jobs",
    action: "Open jobs",
    icon: "upload",
  },
  {
    title: "Inspect one document",
    body: "Open a processed document. It shows the original next to the extracted values, the static choice, AHMN's advice and the policy that ran. Marking fields correct or wrong sends real feedback to AHMN.",
    action: "In the job from step 1",
    icon: "layers",
  },
  {
    title: "Present the benchmark",
    body: "Paired static and adaptive runs on receipts, forms and hard documents. Routing did not improve accuracy, and it was slower on receipts.",
    href: "/dashboard/idpo/benchmark",
    action: "Open benchmark results",
    icon: "chart",
  },
  {
    title: "Answer questions",
    body: "Ask the explanation service why a document was routed the way it was, then rate its answers in Expert Review.",
    href: "/dashboard/xai",
    action: "Open AI Q&A",
    icon: "chat",
  },
];

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function formatSeconds(ms: number | null | undefined): string {
  return typeof ms === "number" && Number.isFinite(ms) ? `${(ms / 1000).toFixed(1)} s` : "—";
}

export default function PresentationModePage() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [overview, setOverview] = useState<RunOverview | null>(null);
  const [loadingRun, setLoadingRun] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    idpoApi
      .listRuns()
      .then((payload) => {
        if (cancelled) return;
        setRuns(payload.runs);
        setSelectedRunId((current) => current || payload.runs[0]?.runId || "");
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load the list of runs.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedRunId) {
      return;
    }
    let cancelled = false;
    setLoadingRun(true);
    setError("");
    idpoApi
      .runOverview(selectedRunId)
      .then((payload) => {
        if (!cancelled) setOverview(payload);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load this run.");
      })
      .finally(() => {
        if (!cancelled) setLoadingRun(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedRunId]);

  const tiles = overview
    ? [
        { label: "Documents", value: String(overview.documents.length) },
        { label: "95th percentile time", value: formatSeconds(overview.p95LatencyMs) },
        { label: "Policy changed by advice", value: String(overview.policyChangedCount ?? 0) },
        { label: "Rollbacks", value: String(overview.rollbackCount) },
      ]
    : [];

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900 sm:p-8">
        <p className="text-xs font-medium uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400">Demo guide</p>
        <h1 className="mt-2 text-3xl font-semibold text-slate-900 dark:text-white sm:text-4xl">Run walkthrough</h1>
        <p className="mt-3 max-w-3xl text-base text-slate-600 dark:text-slate-300">
          A short path through the system for a live demo or a reviewer: upload, process with and without adaptive
          routing, inspect one decision, then show what the benchmark found.
        </p>
      </section>

      {error ? (
        <div
          role="alert"
          className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300"
        >
          {error}
        </div>
      ) : null}

      <ol className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {STEPS.map((step, index) => (
          <li
            key={step.title}
            className="flex flex-col rounded-2xl border border-slate-200 bg-white p-5 dark:border-slate-700 dark:bg-slate-900"
          >
            <div className="flex items-center gap-3">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-cyan-50 text-cyan-700 dark:bg-cyan-500/10 dark:text-cyan-300">
                <Icon name={step.icon} />
              </span>
              <div>
                <p className="text-xs text-slate-500 dark:text-slate-400">Step {index + 1}</p>
                <h2 className="text-base font-semibold text-slate-900 dark:text-white">{step.title}</h2>
              </div>
            </div>
            <p className="mt-3 flex-1 text-sm text-slate-600 dark:text-slate-300">{step.body}</p>
            {step.href ? (
              <Link
                href={step.href}
                className="mt-4 inline-flex items-center gap-1.5 self-start text-sm font-medium text-cyan-700 hover:underline dark:text-cyan-300"
              >
                {step.action}
                <Icon name="arrowRight" className="h-3.5 w-3.5" />
              </Link>
            ) : (
              <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">{step.action}</p>
            )}
          </li>
        ))}
      </ol>

      <section className="rounded-2xl border border-slate-200 bg-white p-6 dark:border-slate-700 dark:bg-slate-900">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div className="max-w-xl">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Show a finished run</h2>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              Pick any run to show its headline numbers, then open it for per-document routing.
            </p>
          </div>
          <div className="w-full sm:w-auto">
            <label htmlFor="walkthrough-run" className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
              Run
            </label>
            <select
              id="walkthrough-run"
              value={selectedRunId}
              onChange={(event) => setSelectedRunId(event.target.value)}
              className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 sm:w-[380px]"
            >
              {runs.length === 0 ? <option value="">No runs yet</option> : null}
              {runs.map((run) => (
                <option key={run.runId} value={run.runId}>
                  {run.runId} · {run.docCount} docs · {formatDate(run.createdAt)}
                </option>
              ))}
            </select>
          </div>
        </div>

        {overview ? (
          <div className={`mt-6 grid gap-3 sm:grid-cols-2 md:grid-cols-4 ${loadingRun ? "opacity-60" : ""}`}>
            {tiles.map((tile) => (
              <div
                key={tile.label}
                className="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800/50"
              >
                <p className="text-xs text-slate-500 dark:text-slate-400">{tile.label}</p>
                <p className="mt-1 text-2xl font-semibold tabular-nums text-slate-900 dark:text-white">{tile.value}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">
            {loadingRun ? "Loading run..." : "Choose a run to see its numbers."}
          </p>
        )}

        {selectedRunId ? (
          <div className="mt-6 flex flex-wrap gap-3">
            <Link
              href={`/dashboard/idpo/runs/${encodeURIComponent(selectedRunId)}`}
              className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 dark:bg-white dark:text-slate-900 dark:hover:bg-slate-200"
            >
              Open run details
            </Link>
            <Link
              href={`/dashboard/idpo/compare?left=${encodeURIComponent(selectedRunId)}`}
              className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
            >
              Compare with another run
            </Link>
          </div>
        ) : null}
      </section>
    </div>
  );
}
