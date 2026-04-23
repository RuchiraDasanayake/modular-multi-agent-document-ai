"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { idpoApi } from "@/lib/idpo-api";
import { IdpoCard } from "@/components/idpo/card";
import type { DocumentSummary, RunOverview, RunSummary } from "@/types/idpo";

function formatNumber(value: number | null | undefined, digits = 2) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return value.toFixed(digits);
}

function recommendationLabel(doc: DocumentSummary | null) {
  return doc?.advisorRecommendationPolicyId ?? "-";
}

function adviceOutcomeLabel(doc: DocumentSummary | null) {
  if (!doc) {
    return "-";
  }
  switch (doc.adviceStatus) {
    case "static":
      return "static";
    case "no_advice":
      return "no advice";
    case "accepted":
      return doc.policyChanged ? "accepted / changed" : "accepted / matched";
    case "rejected":
      return doc.fallbackReason ? `rejected / ${doc.fallbackReason}` : "rejected";
    default:
      if (doc.policyChanged) {
        return doc.adviceAccepted ? "accepted / changed" : "changed";
      }
      if (doc.adviceAccepted) {
        return "accepted";
      }
      return doc.fallbackReason ?? "matched";
  }
}

function containmentLabel(doc: DocumentSummary | null) {
  if (!doc) {
    return "-";
  }
  if (doc.rollbackTriggered) {
    return doc.rollbackReason ? `rollback / ${doc.rollbackReason}` : "rollback";
  }
  if (doc.blockedPolicy) {
    return "blocked";
  }
  if (doc.fallbackReason) {
    return `fallback / ${doc.fallbackReason}`;
  }
  return "clear";
}

export default function CompareRunsPage() {
  const searchParams = useSearchParams();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [leftRunId, setLeftRunId] = useState(searchParams.get("left") ?? "");
  const [rightRunId, setRightRunId] = useState(searchParams.get("right") ?? "");
  const [leftOverview, setLeftOverview] = useState<RunOverview | null>(null);
  const [rightOverview, setRightOverview] = useState<RunOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    idpoApi
      .listRuns()
      .then((payload) => {
        setRuns(payload.runs);
        if (!leftRunId && payload.runs[0]?.runId) {
          setLeftRunId(payload.runs[0].runId);
        }
        if (!rightRunId && payload.runs[1]?.runId) {
          setRightRunId(payload.runs[1].runId);
        }
        setLoading(false);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load runs");
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!leftRunId || !rightRunId) {
      return;
    }
    setError("");
    Promise.all([idpoApi.runOverview(leftRunId), idpoApi.runOverview(rightRunId)])
      .then(([left, right]) => {
        setLeftOverview(left);
        setRightOverview(right);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load run comparison"));
  }, [leftRunId, rightRunId]);

  const docRows = useMemo(() => {
    const leftDocs = new Map((leftOverview?.documents ?? []).map((doc) => [doc.docId, doc]));
    const rightDocs = new Map((rightOverview?.documents ?? []).map((doc) => [doc.docId, doc]));
    const docIds = [...new Set([...leftDocs.keys(), ...rightDocs.keys()])].sort();
    return docIds.map((docId) => ({
      docId,
      left: leftDocs.get(docId) ?? null,
      right: rightDocs.get(docId) ?? null,
    }));
  }, [leftOverview, rightOverview]);

  const metricCards = [
    {
      label: "Validation Pass",
      hint: "Fraction of documents whose extraction passed all validation checks (schema + consistency).",
      left: leftOverview?.validationPassRate !== null && leftOverview?.validationPassRate !== undefined ? `${(leftOverview.validationPassRate * 100).toFixed(1)}%` : "-",
      right: rightOverview?.validationPassRate !== null && rightOverview?.validationPassRate !== undefined ? `${(rightOverview.validationPassRate * 100).toFixed(1)}%` : "-",
    },
    {
      label: "P95 Latency",
      hint: "95th-percentile end-to-end processing time per document, in milliseconds.",
      left: `${formatNumber(leftOverview?.p95LatencyMs)} ms`,
      right: `${formatNumber(rightOverview?.p95LatencyMs)} ms`,
    },
    {
      label: "Advice Accepted",
      hint: "Documents where AHMN returned a recommendation and IDPO executed it (not blocked, not replaced by fallback).",
      left: String(leftOverview?.adviceAcceptedCount ?? "-"),
      right: String(rightOverview?.adviceAcceptedCount ?? "-"),
    },
    {
      label: "Policy Changed",
      hint: "Documents where the policy actually executed differs from the static baseline (i.e. adaptive advice shifted the choice).",
      left: String(leftOverview?.policyChangedCount ?? "-"),
      right: String(rightOverview?.policyChangedCount ?? "-"),
    },
    {
      label: "Rollbacks",
      hint: "Documents where the rollback monitor blocked or reverted a policy due to latency/failure regression vs. the rolling window.",
      left: String(leftOverview?.rollbackCount ?? "-"),
      right: String(rightOverview?.rollbackCount ?? "-"),
    },
    {
      label: "Reviewed-F1 Docs",
      hint: "Documents with a human-reviewed F1 score (ground-truth comparison). Other documents only have the proxy reward.",
      left: String(leftOverview?.directScoredDocCount ?? "-"),
      right: String(rightOverview?.directScoredDocCount ?? "-"),
    },
  ];

  const qualityLabel = (doc: DocumentSummary | null) => {
    if (!doc) {
      return "-";
    }
    if (typeof doc.exactF1 === "number") {
      // Exact F1: precision/recall against reviewer-provided ground truth.
      return `F1 ${formatNumber(doc.exactF1, 3)} (reviewed)`;
    }
    if (typeof doc.reward === "number") {
      // Proxy reward: canonical doc-type field coverage + grounding + hallucination penalty.
      return `Reward ${formatNumber(doc.reward, 3)} (proxy)`;
    }
    return "-";
  };

  if (loading) {
    return <div className="text-sm text-slate-600 dark:text-slate-300">Loading runs...</div>;
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-gradient-to-r from-slate-50 via-white to-cyan-50 p-6 dark:border-slate-800 dark:from-slate-900 dark:via-slate-900 dark:to-slate-900">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <Link href="/dashboard/idpo" className="text-xs text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">
              Back to IDPO dashboard
            </Link>
            <h1 className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">Compare Runs</h1>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              Simple side-by-side comparison for the current IDPO path: selected policy, latency, validation outcome, fallback, rollback, and feedback.
            </p>
          </div>
          <Link
            href="/dashboard/idpo/benchmark"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            Open Benchmark Results
          </Link>
        </div>
      </section>

      {error ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300">
          {error}
        </div>
      ) : null}

      <IdpoCard>
        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="block text-sm text-slate-700 dark:text-slate-200">Left Run</label>
            <select
              value={leftRunId}
              onChange={(event) => setLeftRunId(event.target.value)}
              className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
            >
              <option value="">Select run</option>
              {runs.map((run) => (
                <option key={run.runId} value={run.runId}>
                  {run.runId}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm text-slate-700 dark:text-slate-200">Right Run</label>
            <select
              value={rightRunId}
              onChange={(event) => setRightRunId(event.target.value)}
              className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
            >
              <option value="">Select run</option>
              {runs.map((run) => (
                <option key={run.runId} value={run.runId}>
                  {run.runId}
                </option>
              ))}
            </select>
          </div>
        </div>
      </IdpoCard>

      {leftOverview && rightOverview ? (
        <>
          <div className="grid gap-4 md:grid-cols-4">
            {metricCards.map((metric) => (
              <IdpoCard key={metric.label}>
                <p className="text-xs uppercase text-slate-500 dark:text-slate-400" title={metric.hint}>
                  {metric.label}
                </p>
                <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">L: {metric.left}</p>
                <p className="mt-1 text-sm font-semibold text-slate-900 dark:text-white">R: {metric.right}</p>
                <p className="mt-2 text-[11px] leading-snug text-slate-500 dark:text-slate-400">{metric.hint}</p>
              </IdpoCard>
            ))}
          </div>

          <IdpoCard>
            <h3 className="text-base font-semibold text-slate-900 dark:text-white">Per-Document Comparison</h3>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[1380px] text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                    <th className="px-2 py-2">Doc</th>
                    <th className="px-2 py-2">Left Static</th>
                    <th className="px-2 py-2">Right Static</th>
                    <th className="px-2 py-2">Left Recommended</th>
                    <th className="px-2 py-2">Right Recommended</th>
                    <th className="px-2 py-2">Left Policy</th>
                    <th className="px-2 py-2">Right Policy</th>
                    <th className="px-2 py-2">Left Advice</th>
                    <th className="px-2 py-2">Right Advice</th>
                    <th className="px-2 py-2">Left Quality</th>
                    <th className="px-2 py-2">Right Quality</th>
                    <th className="px-2 py-2">Left Latency</th>
                    <th className="px-2 py-2">Right Latency</th>
                    <th className="px-2 py-2">Left Validation</th>
                    <th className="px-2 py-2">Right Validation</th>
                    <th className="px-2 py-2">Left Schema</th>
                    <th className="px-2 py-2">Right Schema</th>
                    <th className="px-2 py-2">Left Safety</th>
                    <th className="px-2 py-2">Right Safety</th>
                    <th className="px-2 py-2">Left Review</th>
                    <th className="px-2 py-2">Right Review</th>
                    <th className="px-2 py-2">Left Feedback</th>
                    <th className="px-2 py-2">Right Feedback</th>
                    <th className="px-2 py-2">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {docRows.map(({ docId, left, right }) => (
                    <tr key={docId} className="border-b border-slate-100 dark:border-slate-800">
                      <td className="px-2 py-2 text-slate-900 dark:text-slate-100">{docId}</td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{left?.staticPolicyId ?? "-"}</td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{right?.staticPolicyId ?? "-"}</td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{recommendationLabel(left)}</td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{recommendationLabel(right)}</td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{left?.policyId ?? "-"}</td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{right?.policyId ?? "-"}</td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{adviceOutcomeLabel(left)}</td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{adviceOutcomeLabel(right)}</td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{qualityLabel(left)}</td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{qualityLabel(right)}</td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{formatNumber(left?.latencyMs)} ms</td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{formatNumber(right?.latencyMs)} ms</td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{left ? String(left.validationIssueCount) : "-"}</td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{right ? String(right.validationIssueCount) : "-"}</td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{left && typeof left.schemaCoverage === "number" ? formatNumber(left.schemaCoverage, 3) : "-"}</td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{right && typeof right.schemaCoverage === "number" ? formatNumber(right.schemaCoverage, 3) : "-"}</td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{containmentLabel(left)}</td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{containmentLabel(right)}</td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{left?.deferStatus ?? "-"}</td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{right?.deferStatus ?? "-"}</td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{left?.feedbackLogged ? "logged" : "-"}</td>
                      <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{right?.feedbackLogged ? "logged" : "-"}</td>
                      <td className="px-2 py-2 text-xs text-slate-400 dark:text-slate-500">-</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </IdpoCard>
        </>
      ) : null}
    </div>
  );
}
