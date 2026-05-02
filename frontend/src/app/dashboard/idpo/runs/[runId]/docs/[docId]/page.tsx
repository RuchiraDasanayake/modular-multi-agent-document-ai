import Link from "next/link";
import { notFound } from "next/navigation";
import { IdpoCard } from "@/components/idpo/card";
import { StatusBadge } from "@/components/idpo/status-badge";
import { getRunDocument } from "@/server/artifacts";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ runId: string; docId: string }>;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function formatValue(value: unknown): string {
  if (typeof value === "string") {
    return value || "-";
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return "-";
}

function formatMetric(value: unknown, digits = 3): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "-";
  }
  return value.toFixed(digits);
}

function containmentLabel(metadata: Record<string, unknown>, safetyStatus: Record<string, unknown>): string {
  if (safetyStatus.rollback_triggered === true) {
    const reason = typeof safetyStatus.rollback_reason === "string" ? safetyStatus.rollback_reason : null;
    return reason ? `rollback / ${reason}` : "rollback";
  }
  if (safetyStatus.blocked_policy === true) {
    return "blocked";
  }
  const fallbackReason = typeof metadata.fallbackReason === "string" ? metadata.fallbackReason : null;
  if (fallbackReason) {
    return `fallback / ${fallbackReason}`;
  }
  const deferStatus = typeof metadata.deferStatus === "string" ? metadata.deferStatus : null;
  if (deferStatus && deferStatus !== "not_needed") {
    const deferReason = typeof metadata.deferReason === "string" ? metadata.deferReason : null;
    return deferReason ? `${deferStatus} / ${deferReason}` : deferStatus;
  }
  return "clear";
}

export default async function IDPORunDocumentRoute({ params }: Params) {
  const { runId, docId } = await params;
  let detail: Record<string, unknown>;

  try {
    detail = getRunDocument(decodeURIComponent(runId), decodeURIComponent(docId));
  } catch {
    notFound();
  }

  const metadata = asRecord(detail.metadata) ?? {};
  const reward = asRecord(detail.reward) ?? {};
  const review = asRecord(detail.review) ?? {};
  const escalation = asRecord(detail.escalation) ?? {};
  const safetyStatus = asRecord(detail.safetyStatus) ?? {};
  const feedbackStatus = asRecord(detail.feedbackStatus) ?? {};
  const advisorRecommendation = asRecord(detail.advisorRecommendation) ?? {};
  const schemaQuality = asRecord(detail.schemaQuality) ?? {};
  const fields = Array.isArray(detail.fields) ? detail.fields : [];
  const validationIssues = Array.isArray(detail.validationIssues) ? detail.validationIssues : [];
  const recoveryAttempts = Array.isArray(detail.recoveryAttempts) ? detail.recoveryAttempts : [];
  const provenanceEvents = Array.isArray(detail.provenanceEvents) ? detail.provenanceEvents : [];

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-gradient-to-r from-slate-50 via-white to-cyan-50 p-6 dark:border-slate-800 dark:from-slate-900 dark:via-slate-900 dark:to-slate-900">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <Link
              href={`/dashboard/idpo/runs/${encodeURIComponent(decodeURIComponent(runId))}`}
              className="text-xs text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
            >
              Back to run
            </Link>
            <h1 className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">Document Detail</h1>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              {formatValue(metadata.docType)} document with the selected policy, containment outcome, extracted fields, and review signal surfaced directly.
            </p>
          </div>
          <StatusBadge value="processed" />
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <IdpoCard>
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Policy Routing</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{formatValue(metadata.policyId)}</p>
          <div className="mt-2 space-y-1 text-sm text-slate-600 dark:text-slate-300">
            <p>Static: {formatValue(metadata.staticPolicyId)}</p>
            <p>Recommended: {formatValue(advisorRecommendation.policy_id)}</p>
            <p>Advice: {formatValue(metadata.adviceStatus)}</p>
          </div>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Containment</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{containmentLabel(metadata, safetyStatus)}</p>
          <div className="mt-2 space-y-1 text-sm text-slate-600 dark:text-slate-300">
            <p>Feedback logged: {formatValue(feedbackStatus.logged)}</p>
            <p>Escalated: {formatValue(escalation.escalated)}</p>
            <p>Target model: {formatValue(escalation.targetModel)}</p>
          </div>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Structured Quality</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">schema {formatValue(schemaQuality.valid)}</p>
          <div className="mt-2 space-y-1 text-sm text-slate-600 dark:text-slate-300">
            <p>Coverage: {formatMetric(schemaQuality.coverage)}</p>
            <p>Grounding: {formatMetric(schemaQuality.groundingCoverage)}</p>
            <p>Unresolved: {formatValue(metadata.unresolvedFieldCount)}</p>
          </div>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Exact Review</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{formatValue(review.reviewStatus)}</p>
          <div className="mt-2 space-y-1 text-sm text-slate-600 dark:text-slate-300">
            <p>Precision: {formatMetric(metadata.exactPrecision)}</p>
            <p>Recall: {formatMetric(metadata.exactRecall)}</p>
            <p>F1: {formatMetric(metadata.exactF1)}</p>
          </div>
        </IdpoCard>
      </div>

      <IdpoCard>
        <h2 className="text-base font-semibold text-slate-900 dark:text-white">Extracted Fields</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                <th className="px-2 py-2">Field</th>
                <th className="px-2 py-2">Value</th>
                <th className="px-2 py-2">Confidence</th>
                <th className="px-2 py-2">Method</th>
              </tr>
            </thead>
            <tbody>
              {fields.map((item, index) => {
                const field = asRecord(item) ?? {};
                return (
                  <tr key={`${formatValue(field.key)}-${index}`} className="border-b border-slate-100 dark:border-slate-800">
                    <td className="px-2 py-2 font-medium text-slate-900 dark:text-slate-100">{formatValue(field.key)}</td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{formatValue(field.value)}</td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{formatMetric(field.confidence)}</td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{formatValue(field.extraction_method)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {fields.length === 0 ? (
            <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">No extracted fields were recorded for this document.</p>
          ) : null}
        </div>
      </IdpoCard>

      <div className="grid gap-4 lg:grid-cols-2">
        <IdpoCard>
          <h2 className="text-base font-semibold text-slate-900 dark:text-white">Validation and Recovery</h2>
          <div className="mt-3 space-y-3 text-sm text-slate-600 dark:text-slate-300">
            <p>Validation issues: {validationIssues.length}</p>
            <p>Recovery attempts: {recoveryAttempts.length}</p>
            <p>Reward: {formatMetric(reward.reward)}</p>
            <p>Reward type: {formatValue(reward.rewardType)}</p>
          </div>
        </IdpoCard>
        <IdpoCard>
          <h2 className="text-base font-semibold text-slate-900 dark:text-white">Trace</h2>
          <div className="mt-3 space-y-3 text-sm text-slate-600 dark:text-slate-300">
            <p>Route bin: {formatValue(metadata.routeBin)}</p>
            <p>Model used: {formatValue(metadata.modelUsed)}</p>
            <p>Fallback path: {formatValue(metadata.fallbackPath)}</p>
            <p>Provenance events: {provenanceEvents.length}</p>
          </div>
        </IdpoCard>
      </div>
    </div>
  );
}
