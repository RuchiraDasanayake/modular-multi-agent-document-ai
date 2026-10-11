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
    return value.trim() ? value.replace(/_/g, " ") : "—";
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  if (typeof value === "number") {
    return String(value);
  }
  return "—";
}

function formatMetric(value: unknown, digits = 3): string {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return "—";
  }
  return value.toFixed(digits);
}

function gateLabel(metadata: Record<string, unknown>, safetyStatus: Record<string, unknown>): string {
  if (safetyStatus.rollback_triggered === true) {
    const reason = typeof safetyStatus.rollback_reason === "string" ? safetyStatus.rollback_reason : null;
    return reason ? `Rolled back: ${reason}` : "Rolled back";
  }
  if (safetyStatus.blocked_policy === true) {
    return "Policy blocked";
  }
  const fallbackReason = typeof metadata.fallbackReason === "string" ? metadata.fallbackReason : null;
  if (fallbackReason) {
    return `Fallback: ${fallbackReason.replace(/_/g, " ")}`;
  }
  if (metadata.deferStatus === "requested") {
    return "Deferred to review";
  }
  if (metadata.deferStatus === "blocked") {
    return "Deferral blocked";
  }
  return "No intervention";
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="text-right text-slate-800 [overflow-wrap:anywhere] dark:text-slate-200">{value}</dd>
    </div>
  );
}

export default async function IDPORunDocumentRoute({ params }: Params) {
  const { runId, docId } = await params;
  const decodedRunId = decodeURIComponent(runId);
  const decodedDocId = decodeURIComponent(docId);
  let detail: Record<string, unknown>;

  try {
    detail = getRunDocument(decodedRunId, decodedDocId);
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
  const filename = typeof metadata.filename === "string" && metadata.filename ? metadata.filename : decodedDocId;
  const docType = typeof metadata.docType === "string" && metadata.docType && metadata.docType !== "unknown" ? metadata.docType : null;

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-gradient-to-r from-slate-50 via-white to-cyan-50 p-6 dark:border-slate-800 dark:from-slate-900 dark:via-slate-900 dark:to-slate-900">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <Link
              href={`/dashboard/idpo/runs/${encodeURIComponent(decodedRunId)}`}
              className="text-xs font-medium text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
            >
              ← Back to run
            </Link>
            <h1 className="mt-2 truncate text-2xl font-semibold text-slate-900 dark:text-white" title={filename}>
              {filename}
            </h1>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              {docType ? `${docType.replace(/_/g, " ")} document. ` : ""}The policy it ran under, what the safety gate
              did, the fields it produced and how they scored.
            </p>
            <p className="mt-1 font-mono text-xs text-slate-500 [overflow-wrap:anywhere] dark:text-slate-400">
              {decodedRunId} / {decodedDocId}
            </p>
          </div>
          <StatusBadge value="processed" />
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Policy</p>
          <p className="mt-2 font-mono text-sm font-semibold text-slate-900 dark:text-white">
            {typeof metadata.policyId === "string" && metadata.policyId ? metadata.policyId : "—"}
          </p>
          <dl className="mt-3 space-y-1.5 text-sm">
            <Fact label="Static choice" value={typeof metadata.staticPolicyId === "string" ? metadata.staticPolicyId : "—"} />
            <Fact
              label="AHMN recommended"
              value={typeof advisorRecommendation.policy_id === "string" ? advisorRecommendation.policy_id : "—"}
            />
            <Fact label="Advice" value={formatValue(metadata.adviceStatus)} />
          </dl>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Safety gate</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{gateLabel(metadata, safetyStatus)}</p>
          <dl className="mt-3 space-y-1.5 text-sm">
            <Fact label="Outcome sent to AHMN" value={formatValue(feedbackStatus.logged)} />
            <Fact label="Escalated" value={formatValue(escalation.escalated)} />
            <Fact label="Escalation model" value={formatValue(escalation.targetModel)} />
          </dl>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Schema</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">
            {schemaQuality.valid === true ? "Schema valid" : schemaQuality.valid === false ? "Schema not valid" : "—"}
          </p>
          <dl className="mt-3 space-y-1.5 text-sm">
            <Fact label="Required fields extracted" value={formatMetric(schemaQuality.coverage)} />
            <Fact label="Grounded in OCR text" value={formatMetric(schemaQuality.groundingCoverage)} />
            <Fact label="Fields left unresolved" value={formatValue(metadata.unresolvedFieldCount)} />
          </dl>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Score against labels</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">
            {typeof metadata.exactF1 === "number" ? `F1 ${formatMetric(metadata.exactF1)}` : "No labels"}
          </p>
          <dl className="mt-3 space-y-1.5 text-sm">
            <Fact label="Precision" value={formatMetric(metadata.exactPrecision)} />
            <Fact label="Recall" value={formatMetric(metadata.exactRecall)} />
            <Fact label="Review" value={formatValue(review.reviewStatus)} />
          </dl>
        </IdpoCard>
      </div>

      <IdpoCard>
        <h2 className="text-base font-semibold text-slate-900 dark:text-white">Extracted fields</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                <th className="px-2 py-2 font-medium">Field</th>
                <th className="px-2 py-2 font-medium">Value</th>
                <th className="px-2 py-2 text-right font-medium">Confidence</th>
                <th className="px-2 py-2 font-medium">Method</th>
              </tr>
            </thead>
            <tbody>
              {fields.map((item, index) => {
                const field = asRecord(item) ?? {};
                return (
                  <tr key={`${String(field.key ?? "")}-${index}`} className="border-b border-slate-100 last:border-0 dark:border-slate-800">
                    <td className="px-2 py-2 font-medium text-slate-900 dark:text-slate-100">{String(field.key ?? "—")}</td>
                    <td className="px-2 py-2 text-slate-600 [overflow-wrap:anywhere] dark:text-slate-300">
                      {typeof field.value === "string" || typeof field.value === "number" ? String(field.value) || "—" : "—"}
                    </td>
                    <td className="px-2 py-2 text-right tabular-nums text-slate-600 dark:text-slate-300">
                      {formatMetric(field.confidence, 2)}
                    </td>
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
          <h2 className="text-base font-semibold text-slate-900 dark:text-white">Validation and reward</h2>
          <dl className="mt-3 space-y-2 text-sm">
            <Fact label="Validation issues" value={String(validationIssues.length)} />
            <Fact label="Recovery attempts" value={String(recoveryAttempts.length)} />
            <Fact label="Label-free reward" value={formatMetric(reward.reward)} />
            <Fact label="Reward type" value={formatValue(reward.rewardType)} />
          </dl>
          <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
            The reward measures field coverage, not correctness. Exact scores come from the labels above.
          </p>
        </IdpoCard>
        <IdpoCard>
          <h2 className="text-base font-semibold text-slate-900 dark:text-white">Processing trace</h2>
          <dl className="mt-3 space-y-2 text-sm">
            <Fact label="Quality route" value={formatValue(metadata.routeBin)} />
            <Fact label="Model used" value={typeof metadata.modelUsed === "string" && metadata.modelUsed ? metadata.modelUsed : "—"} />
            <Fact label="Fallback path" value={formatValue(metadata.fallbackPath)} />
            <Fact label="Recorded events" value={String(provenanceEvents.length)} />
          </dl>
        </IdpoCard>
      </div>
    </div>
  );
}
