"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { IdpoCard } from "@/components/idpo/card";
import { StatusBadge } from "@/components/idpo/status-badge";
import { idpoApi } from "@/lib/idpo-api";

function toPercent(value: unknown): string {
  const num = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(num)) {
    return "-";
  }
  return `${(num * 100).toFixed(1)}%`;
}

function formatNumber(value: unknown, digits = 2): string {
  const num = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(num)) {
    return "-";
  }
  return num.toFixed(digits);
}

function adviceOutcomeLabel(metadata: Record<string, unknown>): string {
  const status = String(metadata.adviceStatus ?? "");
  const fallbackReason = String(metadata.fallbackReason ?? "").trim();
  const policyChanged = Boolean(metadata.policyChanged);
  const adviceAccepted = Boolean(metadata.adviceAccepted);
  switch (status) {
    case "static":
      return "static";
    case "no_advice":
      return "no advice";
    case "accepted":
      return policyChanged ? "changed" : "matched";
    case "rejected":
      return fallbackReason ? `rejected / ${fallbackReason}` : "rejected";
    default:
      if (policyChanged) {
        return "changed";
      }
      if (adviceAccepted) {
        return "accepted";
      }
      return fallbackReason || "matched";
  }
}

function reviewState(metadata: Record<string, unknown>, safetyStatus: Record<string, unknown>, issuesCount: number): string {
  if (issuesCount > 0) {
    return `${issuesCount} issue(s)`;
  }
  if (Boolean(safetyStatus.rollback_triggered)) {
    return "rollback";
  }
  if (Boolean(safetyStatus.blocked_policy)) {
    return "blocked";
  }
  if (typeof metadata.deferStatus === "string" && metadata.deferStatus !== "not_needed") {
    return metadata.deferStatus;
  }
  if (typeof metadata.fallbackReason === "string" && metadata.fallbackReason.trim()) {
    return "fallback";
  }
  return "clear";
}

export default function DocumentDetailPage() {
  const params = useParams<{ runId: string; docId: string }>();
  const runId = decodeURIComponent(params.runId);
  const docId = decodeURIComponent(params.docId);

  const [doc, setDoc] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setLoading(true);
    idpoApi
      .runDoc(runId, docId)
      .then((payload) => {
        setDoc(payload);
        setError("");
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load document detail");
      })
      .finally(() => setLoading(false));
  }, [runId, docId]);

  const fields = useMemo(() => (Array.isArray(doc?.fields) ? doc.fields : []), [doc]);
  const issues = useMemo(() => (Array.isArray(doc?.validationIssues) ? doc.validationIssues : []), [doc]);

  if (loading) {
    return <div className="text-sm text-slate-600 dark:text-slate-300">Loading document detail...</div>;
  }

  if (error || !doc) {
    return (
      <div className="rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300">
        {error || "Document not found"}
      </div>
    );
  }

  const metadata = (doc.metadata ?? {}) as Record<string, unknown>;
  const escalation = (doc.escalation ?? {}) as Record<string, unknown>;
  const reward = (doc.reward ?? {}) as Record<string, unknown>;
  const rewardDetails = (reward.details ?? {}) as Record<string, unknown>;
  const advisorRecommendation = (doc.advisorRecommendation ?? {}) as Record<string, unknown>;
  const feedbackStatus = (doc.feedbackStatus ?? {}) as Record<string, unknown>;
  const safetyStatus = (doc.safetyStatus ?? {}) as Record<string, unknown>;

  const extractionOutcome =
    typeof rewardDetails.f1 === "number"
      ? `F1 ${formatNumber(rewardDetails.f1, 3)}`
      : typeof reward.reward === "number"
        ? `Reward ${formatNumber(reward.reward, 3)}`
        : "-";

  const currentReviewState = reviewState(metadata, safetyStatus, issues.length);

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <Link
          href={`/dashboard/idpo/runs/${runId}`}
          className="text-xs text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
        >
          Back to run
        </Link>
        <h1 className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">
          {String(metadata.filename ?? docId)}
        </h1>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          Atomic document view for extraction outcome, review state, and the route that produced it.
        </p>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Status</p>
          <div className="mt-2">
            <StatusBadge value={String(metadata.status ?? doc.status ?? "unknown")} />
          </div>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Route / Policy</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">
            {String(metadata.routeBin ?? "-")} / {String(metadata.policyId ?? "-")}
          </p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Advice</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{adviceOutcomeLabel(metadata)}</p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Extraction</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{extractionOutcome}</p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Review</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{currentReviewState}</p>
        </IdpoCard>
      </section>

      <section className="grid gap-4 lg:grid-cols-[1.5fr,1fr]">
        <IdpoCard>
          <h2 className="text-base font-semibold text-slate-900 dark:text-white">Extracted fields</h2>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                  <th className="px-2 py-2">Field</th>
                  <th className="px-2 py-2">Value</th>
                  <th className="px-2 py-2">Confidence</th>
                  <th className="px-2 py-2">Method</th>
                  <th className="px-2 py-2">Evidence</th>
                </tr>
              </thead>
              <tbody>
                {fields.map((field) => {
                  const item = field as Record<string, unknown>;
                  const evidence = (item.evidence ?? {}) as Record<string, unknown>;
                  return (
                    <tr key={`${String(item.key)}_${String(item.value)}`} className="border-b border-slate-100 dark:border-slate-800">
                      <td className="px-2 py-2 font-medium text-slate-900 dark:text-slate-100">{String(item.key)}</td>
                      <td className="px-2 py-2 text-slate-700 dark:text-slate-200">{String(item.value ?? "") || "-"}</td>
                      <td className="px-2 py-2 text-slate-700 dark:text-slate-200">{toPercent(item.confidence)}</td>
                      <td className="px-2 py-2 text-slate-700 dark:text-slate-200">{String(item.extraction_method ?? "-")}</td>
                      <td className="px-2 py-2 text-xs text-slate-600 dark:text-slate-300">
                        page {String(evidence.page ?? "-")} / source {String((item.metadata as Record<string, unknown> | undefined)?.source ?? "-")}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {fields.length === 0 ? (
              <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">No fields extracted.</p>
            ) : null}
          </div>
        </IdpoCard>

        <div className="space-y-4">
          <IdpoCard>
            <h2 className="text-base font-semibold text-slate-900 dark:text-white">Review issues</h2>
            <div className="mt-3 space-y-2">
              {issues.length > 0 ? (
                issues.map((issue, idx) => {
                  const item = issue as Record<string, unknown>;
                  return (
                    <div key={`${String(item.field)}_${idx}`} className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-sm font-medium text-slate-900 dark:text-white">{String(item.field)}</p>
                        <StatusBadge value={String(item.severity ?? "unknown")} />
                      </div>
                      <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">{String(item.issue)}</p>
                    </div>
                  );
                })
              ) : (
                <p className="text-sm text-slate-500 dark:text-slate-400">No validation issues.</p>
              )}
            </div>
          </IdpoCard>

          <IdpoCard>
            <h2 className="text-base font-semibold text-slate-900 dark:text-white">Fallback / escalation</h2>
            <div className="mt-3 space-y-2 text-sm text-slate-600 dark:text-slate-300">
              <p>
                Fallback reason: <span className="font-medium text-slate-900 dark:text-white">{String(metadata.fallbackReason ?? "-")}</span>
              </p>
              <p>
                Escalated: <span className="font-medium text-slate-900 dark:text-white">{String(escalation.escalated ? "yes" : "no")}</span>
              </p>
              <p>
                Escalation reason: <span className="font-medium text-slate-900 dark:text-white">{String(escalation.reason ?? "-")}</span>
              </p>
              <p>
                Review state: <span className="font-medium text-slate-900 dark:text-white">{currentReviewState}</span>
              </p>
            </div>
          </IdpoCard>

          <IdpoCard>
            <h2 className="text-base font-semibold text-slate-900 dark:text-white">Adaptive support</h2>
            <div className="mt-3 space-y-2 text-sm text-slate-600 dark:text-slate-300">
              <p>
                AHMN recommendation:
                <span className="ml-1 font-medium text-slate-900 dark:text-white">
                  {String(advisorRecommendation.policy_id ?? "-")}
                </span>
              </p>
              <p>
                Advice confidence:
                <span className="ml-1 font-medium text-slate-900 dark:text-white">
                  {formatNumber(metadata.adviceConfidence, 2)}
                </span>
              </p>
              <p>
                XAI:
                <span className="ml-1 font-medium text-slate-900 dark:text-white">available later</span>
              </p>
              <p>
                HITL feedback:
                <span className="ml-1 font-medium text-slate-900 dark:text-white">
                  {feedbackStatus.logged ? "logged" : "not logged"}
                </span>
              </p>
            </div>
          </IdpoCard>
        </div>
      </section>
    </div>
  );
}
