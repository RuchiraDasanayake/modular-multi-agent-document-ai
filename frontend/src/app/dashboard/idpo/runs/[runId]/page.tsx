"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { IdpoCard } from "@/components/idpo/card";
import { StatusBadge } from "@/components/idpo/status-badge";
import { idpoApi } from "@/lib/idpo-api";
import type { DocumentSummary, RunOverview } from "@/types/idpo";

function formatNumber(value: number | null | undefined, digits = 2): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return value.toFixed(digits);
}

function adviceOutcomeLabel(doc: DocumentSummary): string {
  switch (doc.adviceStatus) {
    case "static":
      return "static";
    case "no_advice":
      return "no advice";
    case "accepted":
      return doc.policyChanged ? "changed" : "matched";
    case "rejected":
      return doc.fallbackReason ? `rejected / ${doc.fallbackReason}` : "rejected";
    default:
      if (doc.policyChanged) {
        return "changed";
      }
      if (doc.adviceAccepted) {
        return "accepted";
      }
      return doc.fallbackReason ?? "matched";
  }
}

function extractionOutcome(doc: DocumentSummary): string {
  if (typeof doc.exactF1 === "number") {
    return `F1 ${formatNumber(doc.exactF1, 3)}`;
  }
  if (typeof doc.reward === "number") {
    return `Reward ${formatNumber(doc.reward, 3)}`;
  }
  return "-";
}

function reviewState(doc: DocumentSummary): string {
  if (doc.status === "failed") {
    return "failed";
  }
  if ((doc.validationIssueCount ?? 0) > 0) {
    return `${doc.validationIssueCount} issue(s)`;
  }
  if (doc.deferStatus && doc.deferStatus !== "not_needed") {
    return doc.deferStatus;
  }
  if (doc.rollbackTriggered) {
    return "rollback";
  }
  if (doc.blockedPolicy) {
    return "blocked";
  }
  if (doc.fallbackReason) {
    return "fallback";
  }
  return "clear";
}

function routeSummary(doc: DocumentSummary): string {
  const route = doc.routeBin ?? "-";
  const policy = doc.policyId ?? "-";
  return `${route} / ${policy}`;
}

export default function RunDetailPage() {
  const params = useParams<{ runId: string }>();
  const runId = decodeURIComponent(params.runId);

  const [overview, setOverview] = useState<RunOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    idpoApi
      .runOverview(runId)
      .then((payload) => {
        setOverview(payload);
        setError("");
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load run details");
      })
      .finally(() => setLoading(false));
  }, [runId]);

  const docs = overview?.documents ?? [];

  const summary = useMemo(() => {
    const processedCount = docs.filter((doc) => doc.status === "ready" || doc.status === "success").length;
    const failedCount = docs.filter((doc) => doc.status === "failed").length;
    const needsReviewCount = docs.filter((doc) => reviewState(doc) !== "clear" && doc.status !== "failed").length;
    const policyChangedCount = docs.filter((doc) => doc.policyChanged).length;
    return {
      total: docs.length,
      processedCount,
      failedCount,
      needsReviewCount,
      policyChangedCount,
    };
  }, [docs]);

  if (loading) {
    return <div className="text-sm text-slate-600 dark:text-slate-300">Loading run details...</div>;
  }

  if (error || !overview) {
    return (
      <div className="rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300">
        {error || "Run not found"}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <Link
              href="/dashboard/idpo"
              className="text-xs text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
            >
              Back to job workspace
            </Link>
            <h1 className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">Run {runId}</h1>
            <p className="mt-1 max-w-3xl text-sm text-slate-600 dark:text-slate-300">
              Review the adaptive extraction outcome for this run, see which documents need attention, and open a
              document for deeper inspection.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge value={overview.run.status ?? "unknown"} />
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700 dark:bg-slate-800 dark:text-slate-200">
              {summary.total} docs
            </span>
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Documents</p>
          <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{summary.total}</p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Processed</p>
          <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{summary.processedCount}</p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Needs Review</p>
          <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{summary.needsReviewCount}</p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Policy Changed</p>
          <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{summary.policyChangedCount}</p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Failed</p>
          <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{summary.failedCount}</p>
        </IdpoCard>
      </section>

      <IdpoCard>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Documents</h2>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              The table focuses on route taken, extraction outcome, and what needs attention next.
            </p>
          </div>
        </div>

        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[980px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                <th className="px-2 py-2">Document</th>
                <th className="px-2 py-2">Status</th>
                <th className="px-2 py-2">Route / Policy</th>
                <th className="px-2 py-2">Advice</th>
                <th className="px-2 py-2">Extraction</th>
                <th className="px-2 py-2">Review</th>
                <th className="px-2 py-2">Next</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((doc) => (
                <tr key={doc.docId} className="border-b border-slate-100 dark:border-slate-800">
                  <td className="px-2 py-2">
                    <div className="min-w-0">
                      <p className="font-medium text-slate-900 dark:text-slate-100">{doc.filename || doc.docId}</p>
                      <p className="text-xs text-slate-500 dark:text-slate-400">{doc.docId}</p>
                    </div>
                  </td>
                  <td className="px-2 py-2">
                    <StatusBadge value={doc.status || "unknown"} />
                  </td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{routeSummary(doc)}</td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{adviceOutcomeLabel(doc)}</td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{extractionOutcome(doc)}</td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{reviewState(doc)}</td>
                  <td className="px-2 py-2">
                    <Link
                      href={`/dashboard/idpo/runs/${encodeURIComponent(runId)}/docs/${encodeURIComponent(doc.docId)}`}
                      className="text-xs font-medium text-cyan-700 hover:text-cyan-800 dark:text-cyan-300 dark:hover:text-cyan-200"
                    >
                      Open detail
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {docs.length === 0 ? (
            <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">No documents were found for this run.</p>
          ) : null}
        </div>
      </IdpoCard>
    </div>
  );
}
