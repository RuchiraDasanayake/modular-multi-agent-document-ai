import Link from "next/link";
import { notFound } from "next/navigation";
import { headers } from "next/headers";
import { BackLink } from "@/components/back-link";
import { IdpoCard } from "@/components/idpo/card";
import { StatusBadge } from "@/components/idpo/status-badge";
import { getRunOverview } from "@/server/artifacts";
import { requireRun } from "@/server/access";
import { requireUser } from "@/server/auth";
import type { DocumentSummary, RunOverview } from "@/types/idpo";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ runId: string }>;
}

function formatNumber(value: number | null | undefined, digits = 2): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "—";
  }
  return value.toFixed(digits);
}

function formatSeconds(ms: number | null | undefined): string {
  return typeof ms === "number" && Number.isFinite(ms) ? `${(ms / 1000).toFixed(1)} s` : "—";
}

function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

function scoreLabel(doc: DocumentSummary): string {
  if (typeof doc.exactF1 === "number") {
    return `F1 ${formatNumber(doc.exactF1, 3)}`;
  }
  if (typeof doc.reward === "number") {
    return `Reward ${formatNumber(doc.reward, 3)}`;
  }
  return "—";
}

function gateLabel(doc: DocumentSummary): string {
  if (doc.rollbackTriggered) {
    return doc.rollbackReason ? `Rolled back: ${doc.rollbackReason}` : "Rolled back";
  }
  if (doc.blockedPolicy) {
    return "Policy blocked";
  }
  if (doc.fallbackReason) {
    return `Fallback: ${doc.fallbackReason.replace(/_/g, " ")}`;
  }
  if (doc.deferStatus === "requested") {
    return "Deferred to review";
  }
  if (doc.deferStatus === "blocked") {
    return "Deferral blocked";
  }
  return "—";
}

function reviewLabel(doc: DocumentSummary): string {
  if (doc.validationIssueCount > 0) {
    return plural(doc.validationIssueCount, "issue");
  }
  if (doc.reviewStatus === "ai_validated") {
    return "Auto reviewed";
  }
  if (doc.reviewStatus === "human_reviewed") {
    return "Human reviewed";
  }
  return "No issues";
}

function needsReviewCount(overview: RunOverview): number {
  return overview.documents.filter(
    (doc) =>
      doc.validationIssueCount > 0 ||
      doc.escalated ||
      (typeof doc.deferStatus === "string" && doc.deferStatus !== "not_needed"),
  ).length;
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

export default async function IDPORunDetailRoute({ params }: Params) {
  const { runId } = await params;
  let overview: RunOverview;

  try {
    requireRun(decodeURIComponent(runId), await requireUser(await headers()));
    overview = getRunOverview(decodeURIComponent(runId));
  } catch {
    notFound();
  }

  const isBenchmarkRun = /_batch_/.test(overview.run.runId);

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-gradient-to-r from-slate-50 via-white to-cyan-50 p-6 dark:border-slate-800 dark:from-slate-900 dark:via-slate-900 dark:to-slate-900">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <BackLink fallbackHref={isBenchmarkRun ? "/dashboard/idpo/benchmark" : "/dashboard/idpo/jobs"} />
            <h1 className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">Run details</h1>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              {isBenchmarkRun ? "Benchmark run" : "Job run"} with {plural(overview.run.docCount, "document")}, created{" "}
              {formatDate(overview.run.createdAt)}.
            </p>
            <p className="mt-1 font-mono text-xs text-slate-500 [overflow-wrap:anywhere] dark:text-slate-400">
              {overview.run.runId}
            </p>
          </div>
          <StatusBadge value={overview.run.status} />
        </div>
      </section>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Documents</p>
          <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{overview.run.docCount}</p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Need review</p>
          <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{needsReviewCount(overview)}</p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Validation issues, escalations or deferrals</p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Policy changed by advice</p>
          <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{overview.policyChangedCount ?? 0}</p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">95th percentile time</p>
          <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{formatSeconds(overview.p95LatencyMs)}</p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Per document</p>
        </IdpoCard>
      </div>

      <IdpoCard>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-slate-900 dark:text-white">Documents</h2>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              The policy each document used, the score it reached and what the safety gate did. Open a document for its
              fields and trace.
            </p>
          </div>
          <Link
            href="/dashboard/idpo/compare"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            Compare runs
          </Link>
        </div>

        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[960px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                <th className="px-2 py-2 font-medium">Document</th>
                <th className="px-2 py-2 font-medium">Status</th>
                <th className="px-2 py-2 font-medium">Policy (static → final)</th>
                <th className="px-2 py-2 font-medium">AHMN recommended</th>
                <th className="px-2 py-2 font-medium">Advice</th>
                <th className="px-2 py-2 font-medium">Score</th>
                <th className="px-2 py-2 font-medium">Safety gate</th>
                <th className="px-2 py-2 font-medium">Review</th>
                <th className="px-2 py-2 font-medium">
                  <span className="sr-only">Open</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {overview.documents.map((doc) => (
                <tr key={doc.docId} className="border-b border-slate-100 last:border-0 dark:border-slate-800">
                  <td className="max-w-[260px] px-2 py-2">
                    <p className="truncate font-medium text-slate-900 dark:text-slate-100" title={doc.filename}>
                      {doc.filename}
                    </p>
                    <p className="truncate font-mono text-xs text-slate-500 dark:text-slate-400">{doc.docId}</p>
                  </td>
                  <td className="px-2 py-2">
                    <StatusBadge value={doc.status} />
                  </td>
                  <td className="px-2 py-2 font-mono text-xs text-slate-600 dark:text-slate-300">
                    {doc.staticPolicyId ?? "—"}
                    <span className="px-1 text-slate-400">→</span>
                    <span
                      className={
                        doc.policyId && doc.policyId !== doc.staticPolicyId
                          ? "font-semibold text-slate-900 dark:text-white"
                          : undefined
                      }
                    >
                      {doc.policyId ?? "—"}
                    </span>
                  </td>
                  <td className="px-2 py-2 font-mono text-xs text-slate-600 dark:text-slate-300">
                    {doc.advisorRecommendationPolicyId ?? "—"}
                  </td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">
                    {doc.adviceStatus && doc.adviceStatus !== "static" ? doc.adviceStatus.replace(/_/g, " ") : "—"}
                  </td>
                  <td className="px-2 py-2 tabular-nums text-slate-600 dark:text-slate-300">{scoreLabel(doc)}</td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{gateLabel(doc)}</td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{reviewLabel(doc)}</td>
                  <td className="px-2 py-2 text-right">
                    <Link
                      href={`/dashboard/idpo/runs/${encodeURIComponent(overview.run.runId)}/docs/${encodeURIComponent(doc.docId)}`}
                      className="whitespace-nowrap text-xs font-medium text-cyan-700 hover:underline dark:text-cyan-300"
                    >
                      Open →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {overview.documents.length === 0 ? (
            <p className="px-2 py-4 text-sm text-slate-500 dark:text-slate-400">This run has no documents.</p>
          ) : null}
        </div>
      </IdpoCard>
    </div>
  );
}
