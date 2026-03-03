"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { idpoApi } from "@/lib/idpo-api";
import type { RunOverview, RunSummary } from "@/types/idpo";

const steps = [
  "Upload",
  "Run",
  "Show Answer",
  "Show Evidence",
  "Show Provenance",
  "Show Shadow Compare",
];

export default function PresentationModePage() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [overview, setOverview] = useState<RunOverview | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    idpoApi
      .listRuns()
      .then((payload) => {
        setRuns(payload.runs);
        const latest = payload.runs[0]?.runId ?? "";
        setSelectedRunId(latest);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load runs"));
  }, []);

  useEffect(() => {
    if (!selectedRunId) {
      setOverview(null);
      return;
    }

    idpoApi
      .runOverview(selectedRunId)
      .then(setOverview)
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load run"));
  }, [selectedRunId]);

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-white p-8 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <p className="text-xs uppercase tracking-[0.2em] text-slate-500 dark:text-slate-400">PP1 Demo Flow</p>
        <h1 className="mt-2 text-4xl font-semibold text-slate-900 dark:text-white">Presentation Mode</h1>
        <p className="mt-3 text-lg text-slate-600 dark:text-slate-300">
          Guided walkthrough for Upload, Run, Answer with citations, Evidence, Provenance timeline, and Shadow comparison.
        </p>
      </section>

      {error ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300">
          {error}
        </div>
      ) : null}

      <section className="grid gap-3 md:grid-cols-3">
        {steps.map((step, idx) => (
          <div key={step} className="rounded-2xl border border-slate-200 bg-white px-4 py-5 dark:border-slate-700 dark:bg-slate-900">
            <p className="text-xs text-slate-500 dark:text-slate-400">Step {idx + 1}</p>
            <p className="mt-2 text-xl font-semibold text-slate-900 dark:text-white">{step}</p>
          </div>
        ))}
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-6 dark:border-slate-700 dark:bg-slate-900">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-2xl font-semibold text-slate-900 dark:text-white">Select Run for Demo</h2>
          <div className="flex items-center gap-2">
            <label className="text-sm text-slate-600 dark:text-slate-300">Run</label>
            <select
              value={selectedRunId}
              onChange={(event) => setSelectedRunId(event.target.value)}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-950"
            >
              {runs.map((run) => (
                <option key={run.runId} value={run.runId}>
                  {run.runId}
                </option>
              ))}
            </select>
          </div>
        </div>

        {overview ? (
          <div className="mt-6 grid gap-3 md:grid-cols-4">
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800/50">
              <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Docs</p>
              <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{overview.documents.length}</p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800/50">
              <p className="text-xs uppercase text-slate-500 dark:text-slate-400">P95 Latency</p>
              <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">
                {typeof overview.p95LatencyMs === "number" ? `${overview.p95LatencyMs.toFixed(2)} ms` : "-"}
              </p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800/50">
              <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Escalations</p>
              <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{overview.escalationsCount}</p>
            </div>
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-800/50">
              <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Rollback Events</p>
              <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{overview.rollbackCount}</p>
            </div>
          </div>
        ) : (
          <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">Select a run to load presentation metrics.</p>
        )}

        <div className="mt-6 flex flex-wrap gap-3">
          <Link
            href="/dashboard/idpo"
            className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            Back to Runner
          </Link>
          {selectedRunId ? (
            <Link
              href={`/dashboard/idpo/runs/${selectedRunId}`}
              className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 dark:bg-brand-600 dark:hover:bg-brand-500"
            >
              Open Run Detail
            </Link>
          ) : null}
        </div>
      </section>
    </div>
  );
}
