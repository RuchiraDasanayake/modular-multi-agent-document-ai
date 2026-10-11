"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { idpoApi } from "@/lib/idpo-api";
import { IdpoCard } from "@/components/idpo/card";
import type { DocumentSummary, RunOverview, RunSummary } from "@/types/idpo";

type RunGroup = "job" | "static" | "adaptive";

const GROUP_LABELS: Record<RunGroup, string> = {
  job: "Job runs",
  static: "Benchmark runs: static",
  adaptive: "Benchmark runs: adaptive",
};

function runGroup(runId: string): RunGroup {
  if (runId.startsWith("adaptive")) return "adaptive";
  if (runId.startsWith("static")) return "static";
  return "job";
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function runLabel(run: RunSummary): string {
  return `${run.runId} · ${run.docCount} docs · ${formatDate(run.createdAt)}`;
}

function formatSeconds(ms: number | null | undefined): string {
  return typeof ms === "number" && Number.isFinite(ms) ? `${(ms / 1000).toFixed(1)} s` : "—";
}

function formatPercent(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? `${Math.round(value * 100)}%` : "—";
}

function formatCount(value: number | null | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? String(value) : "—";
}

function scoreLabel(doc: DocumentSummary | null): string {
  if (!doc) return "—";
  if (typeof doc.exactF1 === "number") return `F1 ${doc.exactF1.toFixed(3)}`;
  if (typeof doc.reward === "number") return `reward ${doc.reward.toFixed(3)}`;
  return "—";
}

function gateLabel(doc: DocumentSummary | null): string {
  if (!doc) return "—";
  if (doc.rollbackTriggered) return "Rolled back";
  if (doc.blockedPolicy) return "Policy blocked";
  if (doc.fallbackReason) return `Fallback: ${doc.fallbackReason.replace(/_/g, " ")}`;
  if (doc.deferStatus === "requested") return "Deferred to review";
  if (doc.deferStatus === "blocked") return "Deferral blocked";
  return "—";
}

function docHref(runId: string, doc: DocumentSummary | null): string | null {
  return doc ? `/dashboard/idpo/runs/${encodeURIComponent(runId)}/docs/${encodeURIComponent(doc.docId)}` : null;
}

function RunSelect({
  id,
  label,
  value,
  runs,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  runs: RunSummary[];
  onChange: (value: string) => void;
}) {
  const groups = (Object.keys(GROUP_LABELS) as RunGroup[])
    .map((group) => ({ group, runs: runs.filter((run) => runGroup(run.runId) === group) }))
    .filter((entry) => entry.runs.length > 0);

  return (
    <div>
      <label htmlFor={id} className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
      >
        <option value="">Choose a run</option>
        {groups.map((entry) => (
          <optgroup key={entry.group} label={GROUP_LABELS[entry.group]}>
            {entry.runs.map((run) => (
              <option key={run.runId} value={run.runId}>
                {runLabel(run)}
              </option>
            ))}
          </optgroup>
        ))}
      </select>
    </div>
  );
}

function PairCell({ a, b, mono = false }: { a: string; b: string; mono?: boolean }) {
  const differs = a !== b;
  return (
    <td className="px-2 py-2 align-top">
      <div className={`grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 text-xs ${mono ? "font-mono" : ""}`}>
        <span className="font-sans text-slate-400 dark:text-slate-500">A</span>
        <span className="text-slate-700 dark:text-slate-200">{a}</span>
        <span className="font-sans text-slate-400 dark:text-slate-500">B</span>
        <span className={differs ? "font-semibold text-slate-900 dark:text-white" : "text-slate-700 dark:text-slate-200"}>{b}</span>
      </div>
    </td>
  );
}

function CompareRuns() {
  const searchParams = useSearchParams();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [runsLoading, setRunsLoading] = useState(true);
  const [leftRunId, setLeftRunId] = useState(searchParams.get("left") ?? "");
  const [rightRunId, setRightRunId] = useState(searchParams.get("right") ?? "");
  const [leftOverview, setLeftOverview] = useState<RunOverview | null>(null);
  const [rightOverview, setRightOverview] = useState<RunOverview | null>(null);
  const [comparing, setComparing] = useState(false);
  const [onlyDifferent, setOnlyDifferent] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    idpoApi
      .listRuns()
      .then((payload) => {
        if (cancelled) return;
        setRuns(payload.runs);
        setLeftRunId((current) => current || payload.runs[0]?.runId || "");
        setRightRunId((current) => current || payload.runs[1]?.runId || "");
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load the list of runs.");
      })
      .finally(() => {
        if (!cancelled) setRunsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!leftRunId || !rightRunId) {
      return;
    }
    let cancelled = false;
    setComparing(true);
    setError("");
    Promise.all([idpoApi.runOverview(leftRunId), idpoApi.runOverview(rightRunId)])
      .then(([left, right]) => {
        if (cancelled) return;
        setLeftOverview(left);
        setRightOverview(right);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load one of the runs.");
      })
      .finally(() => {
        if (!cancelled) setComparing(false);
      });
    return () => {
      cancelled = true;
    };
  }, [leftRunId, rightRunId]);

  const docRows = useMemo(() => {
    const leftDocs = new Map((leftOverview?.documents ?? []).map((doc) => [doc.docId, doc]));
    const rightDocs = new Map((rightOverview?.documents ?? []).map((doc) => [doc.docId, doc]));
    const docIds = [...new Set([...leftDocs.keys(), ...rightDocs.keys()])].sort();
    return docIds.map((docId) => {
      const left = leftDocs.get(docId) ?? null;
      const right = rightDocs.get(docId) ?? null;
      const differs =
        !left ||
        !right ||
        left.policyId !== right.policyId ||
        scoreLabel(left) !== scoreLabel(right) ||
        left.validationIssueCount !== right.validationIssueCount;
      return { docId, left, right, differs };
    });
  }, [leftOverview, rightOverview]);

  const visibleRows = onlyDifferent ? docRows.filter((row) => row.differs) : docRows;
  const differentCount = docRows.filter((row) => row.differs).length;

  const metricRows: Array<{ label: string; hint?: string; left: string; right: string }> =
    leftOverview && rightOverview
      ? [
          { label: "Documents", left: formatCount(leftOverview.run.docCount), right: formatCount(rightOverview.run.docCount) },
          {
            label: "Validation pass rate",
            hint: "Documents with no validation issue.",
            left: formatPercent(leftOverview.validationPassRate),
            right: formatPercent(rightOverview.validationPassRate),
          },
          {
            label: "95th percentile time per document",
            left: formatSeconds(leftOverview.p95LatencyMs),
            right: formatSeconds(rightOverview.p95LatencyMs),
          },
          {
            label: "Advice accepted",
            hint: "AHMN recommended a policy and the run used it.",
            left: formatCount(leftOverview.adviceAcceptedCount),
            right: formatCount(rightOverview.adviceAcceptedCount),
          },
          {
            label: "Policy changed by advice",
            hint: "The policy that ran differs from the static choice.",
            left: formatCount(leftOverview.policyChangedCount),
            right: formatCount(rightOverview.policyChangedCount),
          },
          {
            label: "Rollbacks",
            hint: "Policies the safety gate withdrew after they regressed.",
            left: formatCount(leftOverview.rollbackCount),
            right: formatCount(rightOverview.rollbackCount),
          },
          {
            label: "Documents with an exact score",
            hint: "Scored against labels or a review. The rest only have the label-free reward.",
            left: formatCount(leftOverview.directScoredDocCount),
            right: formatCount(rightOverview.directScoredDocCount),
          },
        ]
      : [];

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-gradient-to-r from-slate-50 via-white to-cyan-50 p-6 dark:border-slate-800 dark:from-slate-900 dark:via-slate-900 dark:to-slate-900">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-3xl">
            <h1 className="text-2xl font-semibold text-slate-900 dark:text-white">Compare two runs</h1>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              Put any two runs side by side: the policy each document used, its score, time and safety-gate outcome. To
              compare the conditions of a benchmark, pick its static run as A and its adaptive run as B.
            </p>
          </div>
          <Link
            href="/dashboard/idpo/benchmark"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            Benchmark results
          </Link>
        </div>
      </section>

      {error ? (
        <div
          role="alert"
          className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300"
        >
          {error}
        </div>
      ) : null}

      <IdpoCard>
        <div className="grid items-end gap-4 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
          <RunSelect id="run-a" label="Run A" value={leftRunId} runs={runs} onChange={setLeftRunId} />
          <button
            type="button"
            onClick={() => {
              setLeftRunId(rightRunId);
              setRightRunId(leftRunId);
            }}
            disabled={!leftRunId && !rightRunId}
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            Swap
          </button>
          <RunSelect id="run-b" label="Run B" value={rightRunId} runs={runs} onChange={setRightRunId} />
        </div>
        {runsLoading ? <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">Loading runs...</p> : null}
        {!runsLoading && runs.length === 0 && !error ? (
          <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">No runs yet. Process a job or run a benchmark first.</p>
        ) : null}
        {leftRunId && leftRunId === rightRunId ? (
          <p className="mt-3 text-sm text-amber-700 dark:text-amber-300">Both sides show the same run. Pick a different run for B.</p>
        ) : null}
      </IdpoCard>

      {comparing && !(leftOverview && rightOverview) ? (
        <div className="space-y-4" aria-hidden="true">
          <div className="h-56 animate-pulse rounded-2xl bg-slate-200/70 dark:bg-slate-800/70" />
          <div className="h-72 animate-pulse rounded-2xl bg-slate-200/70 dark:bg-slate-800/70" />
        </div>
      ) : null}

      {leftOverview && rightOverview ? (
        <div className={`space-y-6 transition-opacity ${comparing ? "opacity-60" : ""}`}>
          <IdpoCard>
            <h2 className="text-base font-semibold text-slate-900 dark:text-white">Run summary</h2>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[300px] text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                    <th className="px-2 py-2 font-medium">Metric</th>
                    <th className="whitespace-nowrap px-2 py-2 text-right font-medium">Run A</th>
                    <th className="whitespace-nowrap px-2 py-2 text-right font-medium">Run B</th>
                  </tr>
                </thead>
                <tbody>
                  {metricRows.map((row) => (
                    <tr key={row.label} className="border-b border-slate-100 last:border-0 dark:border-slate-800">
                      <td className="px-2 py-2 text-slate-700 dark:text-slate-200">
                        {row.label}
                        {row.hint ? <span className="block text-xs text-slate-500 dark:text-slate-400">{row.hint}</span> : null}
                      </td>
                      <td className="whitespace-nowrap px-2 py-2 text-right tabular-nums text-slate-700 dark:text-slate-200">{row.left}</td>
                      <td
                        className={`whitespace-nowrap px-2 py-2 text-right tabular-nums ${
                          row.left !== row.right ? "font-semibold text-slate-900 dark:text-white" : "text-slate-700 dark:text-slate-200"
                        }`}
                      >
                        {row.right}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </IdpoCard>

          <IdpoCard>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold text-slate-900 dark:text-white">Documents</h2>
                <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                  Each cell shows run A above run B. Values that differ are in bold.
                </p>
              </div>
              <div
                className="inline-flex rounded-lg border border-slate-300 p-0.5 text-sm dark:border-slate-700"
                role="group"
                aria-label="Filter documents"
              >
                {[
                  { value: false, label: `All (${docRows.length})` },
                  { value: true, label: `Differences (${differentCount})` },
                ].map((option) => (
                  <button
                    key={option.label}
                    type="button"
                    aria-pressed={onlyDifferent === option.value}
                    onClick={() => setOnlyDifferent(option.value)}
                    className={`rounded-md px-3 py-1 ${
                      onlyDifferent === option.value
                        ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900"
                        : "text-slate-600 hover:text-slate-900 dark:text-slate-300 dark:hover:text-white"
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[880px] text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                    <th className="px-2 py-2 font-medium">Document</th>
                    <th className="px-2 py-2 font-medium">Policy</th>
                    <th className="px-2 py-2 font-medium">Score</th>
                    <th className="px-2 py-2 font-medium">Time</th>
                    <th className="px-2 py-2 font-medium">Validation issues</th>
                    <th className="px-2 py-2 font-medium">Safety gate</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map(({ docId, left, right }) => {
                    const leftHref = docHref(leftOverview.run.runId, left);
                    const rightHref = docHref(rightOverview.run.runId, right);
                    return (
                      <tr key={docId} className="border-b border-slate-100 last:border-0 dark:border-slate-800">
                        <td className="max-w-[260px] px-2 py-2 align-top">
                          <p className="truncate font-mono text-xs text-slate-900 dark:text-slate-100" title={docId}>
                            {docId}
                          </p>
                          <p className="mt-1 text-xs">
                            {leftHref ? (
                              <Link href={leftHref} className="font-medium text-cyan-700 hover:underline dark:text-cyan-300">
                                Open A
                              </Link>
                            ) : (
                              <span className="text-slate-400">Not in A</span>
                            )}
                            <span className="px-1.5 text-slate-300 dark:text-slate-600">|</span>
                            {rightHref ? (
                              <Link href={rightHref} className="font-medium text-cyan-700 hover:underline dark:text-cyan-300">
                                Open B
                              </Link>
                            ) : (
                              <span className="text-slate-400">Not in B</span>
                            )}
                          </p>
                        </td>
                        <PairCell a={left?.policyId ?? "—"} b={right?.policyId ?? "—"} mono />
                        <PairCell a={scoreLabel(left)} b={scoreLabel(right)} />
                        <PairCell a={formatSeconds(left?.latencyMs)} b={formatSeconds(right?.latencyMs)} />
                        <PairCell
                          a={left ? String(left.validationIssueCount) : "—"}
                          b={right ? String(right.validationIssueCount) : "—"}
                        />
                        <PairCell a={gateLabel(left)} b={gateLabel(right)} />
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {visibleRows.length === 0 ? (
                <p className="px-2 py-4 text-sm text-slate-500 dark:text-slate-400">
                  {onlyDifferent ? "The two runs agree on every document." : "Neither run has documents."}
                </p>
              ) : null}
            </div>
          </IdpoCard>
        </div>
      ) : null}
    </div>
  );
}

export default function CompareRunsPage() {
  return (
    <Suspense fallback={<div className="mx-auto h-40 max-w-7xl animate-pulse rounded-3xl bg-slate-200/70 dark:bg-slate-800/70" />}>
      <CompareRuns />
    </Suspense>
  );
}
