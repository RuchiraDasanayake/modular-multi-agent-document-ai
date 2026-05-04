import Link from "next/link";
import { notFound } from "next/navigation";
import { IdpoCard } from "@/components/idpo/card";
import { StatusBadge } from "@/components/idpo/status-badge";
import { getRunOverview } from "@/server/artifacts";
import type { DocumentSummary, RunOverview } from "@/types/idpo";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ runId: string }>;
}

function formatNumber(value: number | null | undefined, digits = 2): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return value.toFixed(digits);
}

function qualityLabel(doc: DocumentSummary): string {
  if (typeof doc.exactF1 === "number") {
    return `F1 ${formatNumber(doc.exactF1, 3)}`;
  }
  if (typeof doc.reward === "number") {
    return `Reward ${formatNumber(doc.reward, 3)}`;
  }
  return "-";
}

function containmentLabel(doc: DocumentSummary): string {
  if (doc.rollbackTriggered) {
    return doc.rollbackReason ? `rollback / ${doc.rollbackReason}` : "rollback";
  }
  if (doc.blockedPolicy) {
    return "blocked";
  }
  if (doc.fallbackReason) {
    return `fallback / ${doc.fallbackReason}`;
  }
  if (doc.deferStatus && doc.deferStatus !== "not_needed") {
    return doc.deferReason ? `${doc.deferStatus} / ${doc.deferReason}` : doc.deferStatus;
  }
  return "clear";
}

function reviewLabel(doc: DocumentSummary): string {
  if (doc.validationIssueCount > 0) {
    return `${doc.validationIssueCount} issue(s)`;
  }
  if (doc.reviewStatus && doc.reviewStatus !== "unreviewed") {
    return doc.reviewStatus.replace(/_/g, " ");
  }
  return "clear";
}

function needsReviewCount(overview: RunOverview): number {
  return overview.documents.filter(
    (doc) =>
      doc.validationIssueCount > 0 ||
      doc.escalated ||
      (typeof doc.deferStatus === "string" && doc.deferStatus !== "not_needed"),
  ).length;
}

export default async function IDPORunDetailRoute({ params }: Params) {
  const { runId } = await params;
  let overview: RunOverview;

  try {
    overview = getRunOverview(decodeURIComponent(runId));
  } catch {
    notFound();
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-gradient-to-r from-slate-50 via-white to-cyan-50 p-6 dark:border-slate-800 dark:from-slate-900 dark:via-slate-900 dark:to-slate-900">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <Link href="/dashboard/idpo" className="text-xs text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">
              Back to IDPO dashboard
            </Link>
            <h1 className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">Run Detail</h1>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              Run {overview.run.runId} with the adaptive route, review-needed state, and per-document outcome kept in one place.
            </p>
          </div>
          <StatusBadge value={overview.run.status} />
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-4">
        <IdpoCard>
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Documents</p>
          <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{overview.run.docCount}</p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Needs Review</p>
          <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{needsReviewCount(overview)}</p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Policy Changed</p>
          <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{overview.policyChangedCount ?? 0}</p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">P95 Latency</p>
          <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{formatNumber(overview.p95LatencyMs)} ms</p>
        </IdpoCard>
      </div>

      <IdpoCard>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-slate-900 dark:text-white">Documents</h2>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              Baseline, recommendation, final policy, containment, and review state. Anything deeper belongs on the document page.
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
          <table className="w-full min-w-[1120px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                <th className="px-2 py-2">Document</th>
                <th className="px-2 py-2">Status</th>
                <th className="px-2 py-2">Static</th>
                <th className="px-2 py-2">Recommended</th>
                <th className="px-2 py-2">Final</th>
                <th className="px-2 py-2">Advice</th>
                <th className="px-2 py-2">Quality</th>
                <th className="px-2 py-2">Containment</th>
                <th className="px-2 py-2">Review</th>
                <th className="px-2 py-2">Open</th>
              </tr>
            </thead>
            <tbody>
              {overview.documents.map((doc) => (
                <tr key={doc.docId} className="border-b border-slate-100 dark:border-slate-800">
                  <td className="px-2 py-2 font-medium text-slate-900 dark:text-slate-100">
                    <div>{doc.filename}</div>
                    <div className="text-xs text-slate-500 dark:text-slate-400">{doc.docId}</div>
                  </td>
                  <td className="px-2 py-2">
                    <StatusBadge value={doc.status} />
                  </td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{doc.staticPolicyId ?? "-"}</td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{doc.advisorRecommendationPolicyId ?? "-"}</td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{doc.policyId ?? "-"}</td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{doc.adviceStatus ?? "-"}</td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{qualityLabel(doc)}</td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{containmentLabel(doc)}</td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{reviewLabel(doc)}</td>
                  <td className="px-2 py-2">
                    <Link
                      href={`/dashboard/idpo/runs/${encodeURIComponent(overview.run.runId)}/docs/${encodeURIComponent(doc.docId)}`}
                      className="text-xs font-medium text-cyan-700 hover:text-cyan-800 dark:text-cyan-300 dark:hover:text-cyan-200"
                    >
                      Open detail
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </IdpoCard>
    </div>
  );
}
