"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { idpoApi } from "@/lib/idpo-api";
import { IdpoCard } from "@/components/idpo/card";
import { StatusBadge } from "@/components/idpo/status-badge";
import { JsonViewer } from "@/components/idpo/json-viewer";
import type { ProvenanceEvent } from "@/types/idpo";

function toPercent(value: unknown) {
  const num = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(num)) {
    return "-";
  }
  return `${(num * 100).toFixed(1)}%`;
}

function formatNumber(value: unknown, digits = 2) {
  const num = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(num)) {
    return "-";
  }
  return num.toFixed(digits);
}

function adviceOutcomeLabel(metadata: Record<string, unknown>) {
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
      return policyChanged ? "accepted / changed" : "accepted / matched";
    case "rejected":
      return fallbackReason ? `rejected / ${fallbackReason}` : "rejected";
    default:
      if (policyChanged) {
        return adviceAccepted ? "accepted / changed" : "changed";
      }
      if (adviceAccepted) {
        return "accepted";
      }
      return fallbackReason || "matched baseline";
  }
}

function containmentLabel(metadata: Record<string, unknown>, safetyStatus: Record<string, unknown>) {
  if (Boolean(safetyStatus.rollback_triggered)) {
    return typeof safetyStatus.rollback_reason === "string" ? `rollback / ${safetyStatus.rollback_reason}` : "rollback";
  }
  if (Boolean(safetyStatus.blocked_policy)) {
    return "blocked";
  }
  if (typeof metadata.fallbackReason === "string" && metadata.fallbackReason.trim()) {
    return `fallback / ${metadata.fallbackReason}`;
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
  const [search, setSearch] = useState("");

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

  const fields = useMemo(() => (Array.isArray(doc?.fields) ? doc?.fields : []), [doc]);
  const issues = useMemo(() => (Array.isArray(doc?.validationIssues) ? doc?.validationIssues : []), [doc]);
  const recovery = useMemo(() => (Array.isArray(doc?.recoveryAttempts) ? doc?.recoveryAttempts : []), [doc]);
  const provenance = useMemo(() => (Array.isArray(doc?.provenanceEvents) ? (doc?.provenanceEvents as ProvenanceEvent[]) : []), [doc]);

  const filteredEvents = provenance.filter((event) => {
    if (!search.trim()) {
      return true;
    }
    const token = search.toLowerCase();
    return (
      event.eventType.toLowerCase().includes(token) ||
      event.agent.toLowerCase().includes(token) ||
      (event.docId ?? "").toLowerCase().includes(token)
    );
  });

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
  const transparency = (doc.transparency ?? {}) as Record<string, unknown>;
  const reward = (doc.reward ?? {}) as Record<string, unknown>;
  const rewardDetails = (reward.details ?? {}) as Record<string, unknown>;
  const advisorRecommendation = (doc.advisorRecommendation ?? {}) as Record<string, unknown>;
  const feedbackStatus = (doc.feedbackStatus ?? {}) as Record<string, unknown>;
  const safetyStatus = (doc.safetyStatus ?? {}) as Record<string, unknown>;
  const schemaQuality = (doc.schemaQuality ?? {}) as Record<string, unknown>;
  const fallbackCandidates = Array.isArray(doc.fallbackCandidates) ? (doc.fallbackCandidates as Record<string, unknown>[]) : [];
  const modelRoute = (transparency.model_route ?? {}) as Record<string, unknown>;
  const ocrRoute = (transparency.ocr_route ?? {}) as Record<string, unknown>;
  const fieldResolution = (transparency.field_resolution ?? {}) as Record<string, unknown>;

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-gradient-to-r from-amber-50 via-white to-cyan-50 p-6 dark:border-slate-800 dark:from-slate-900 dark:via-slate-900 dark:to-slate-900">
        <Link href={`/dashboard/idpo/runs/${runId}`} className="text-xs text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">
          Back to run
        </Link>
        <h1 className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">Document {docId}</h1>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          Document-level routing view with AHMN top-1 advice, selected policy, fallback and rollback status, and extraction outcomes.
        </p>
      </section>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <IdpoCard>
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Doc Type</p>
          <p className="mt-2 text-lg font-semibold text-slate-900 dark:text-white">{String(metadata.docType ?? "-")}</p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Vendor Cluster</p>
          <p className="mt-2 text-lg font-semibold text-slate-900 dark:text-white">{String(metadata.vendorCluster ?? "-")}</p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Complexity Bin</p>
          <p className="mt-2 text-lg font-semibold text-slate-900 dark:text-white">{String(metadata.complexityBin ?? "-")}</p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Route Bin</p>
          <p className="mt-2 text-lg font-semibold text-slate-900 dark:text-white">{String(metadata.routeBin ?? "-")}</p>
        </IdpoCard>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <IdpoCard>
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Static Baseline</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{String(metadata.staticPolicyId ?? "-")}</p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{String(metadata.staticPolicyReason ?? "-")}</p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Advisor Recommendation</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">
            {String(advisorRecommendation.policy_id ?? "-")}
          </p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Source: {String(metadata.adviceSource ?? "-")} | Status: {String(metadata.adviceStatus ?? "-")}
          </p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Selected Policy</p>
          <p className="mt-2 text-lg font-semibold text-slate-900 dark:text-white">{String(metadata.policyId ?? "-")}</p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Confidence: {formatNumber(metadata.adviceConfidence, 2)} | {metadata.policyChanged ? "changed vs static" : "matched static"}
          </p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Advice Outcome</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">
            {adviceOutcomeLabel(metadata)}
          </p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            {metadata.policyChanged
              ? `static ${String(metadata.staticPolicyId ?? "-")} -> executed ${String(metadata.policyId ?? "-")}`
              : "no route divergence"}
          </p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Feedback Status</p>
          <p className="mt-2 text-lg font-semibold text-slate-900 dark:text-white">{feedbackStatus.logged ? "logged" : "not logged"}</p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{String(feedbackStatus.error ?? "-")}</p>
        </IdpoCard>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <IdpoCard>
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Fallback / Safety</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">
            {containmentLabel(metadata, safetyStatus)}
          </p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            {String(metadata.fallbackReason ?? safetyStatus.rollback_reason ?? "-")}
          </p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Model Route</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">
            {String(metadata.modelMode ?? modelRoute.model_mode ?? "-")} / {String(metadata.modelUsed ?? modelRoute.model_used ?? "-")}
          </p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Reason: {String(metadata.modelReason ?? modelRoute.model_reason ?? "-")}</p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">OCR Route</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">
            {String(metadata.ocrEngineUsed ?? ocrRoute.engine ?? "-")} ({formatNumber(metadata.ocrAvgConfidence ?? ocrRoute.avg_confidence)})
          </p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Reruns: {String(metadata.ocrRerunUsedPages ?? ocrRoute.rerun_used_pages ?? 0)}/{String(metadata.ocrRerunAttemptedPages ?? ocrRoute.rerun_attempted_pages ?? 0)}
          </p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Extraction Outcome</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">
            {typeof rewardDetails.f1 === "number" ? `F1 ${formatNumber(rewardDetails.f1, 3)}` : typeof reward.reward === "number" ? `Reward ${formatNumber(reward.reward, 3)}` : "-"}
          </p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Precision {formatNumber(rewardDetails.precision, 3)} / Recall {formatNumber(rewardDetails.recall, 3)}
          </p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Fallback Candidates</p>
          <p className="mt-2 text-lg font-semibold text-slate-900 dark:text-white">{fallbackCandidates.length}</p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Unresolved Fields</p>
          <p className="mt-2 text-lg font-semibold text-slate-900 dark:text-white">
            {String(metadata.unresolvedFieldCount ?? fieldResolution.unresolved_count ?? "-")}
          </p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Defer / Review</p>
          <p className="mt-2 text-lg font-semibold text-slate-900 dark:text-white">
            {String(metadata.deferStatus ?? safetyStatus.defer_status ?? "not_needed")}
          </p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{String(metadata.deferReason ?? safetyStatus.defer_reason ?? "-")}</p>
        </IdpoCard>
        <IdpoCard>
          <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Schema Quality</p>
          <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">
            {typeof metadata.schemaCoverage === "number" ? `coverage ${formatNumber(metadata.schemaCoverage, 3)}` : typeof schemaQuality.coverage === "number" ? `coverage ${formatNumber(schemaQuality.coverage, 3)}` : "-"}
          </p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            grounded {typeof metadata.schemaGroundingCoverage === "number" ? formatNumber(metadata.schemaGroundingCoverage, 3) : formatNumber(schemaQuality.groundingCoverage, 3)} | valid {String(metadata.schemaValid ?? schemaQuality.valid ?? "-")}
          </p>
        </IdpoCard>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <IdpoCard>
          <h2 className="text-base font-semibold text-slate-900 dark:text-white">Extracted Fields</h2>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                  <th className="px-2 py-2">Field</th>
                  <th className="px-2 py-2">Value</th>
                  <th className="px-2 py-2">Confidence</th>
                  <th className="px-2 py-2">Confidence Type</th>
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
                      <td className="px-2 py-2 text-slate-700 dark:text-slate-200">{String(item.value ?? "")}</td>
                      <td className="px-2 py-2 text-slate-700 dark:text-slate-200">{toPercent(item.confidence)}</td>
                      <td className="px-2 py-2">
                        <StatusBadge value={String(item.confidence_type ?? "unknown")} />
                      </td>
                      <td className="px-2 py-2 text-slate-700 dark:text-slate-200">{String(item.extraction_method ?? "-")}</td>
                      <td className="px-2 py-2 text-xs text-slate-600 dark:text-slate-300">
                        span={Array.isArray(evidence.span) ? JSON.stringify(evidence.span) : "-"} page={String(evidence.page ?? "-")} bbox={Array.isArray(evidence.bbox) ? JSON.stringify(evidence.bbox) : "-"} source={String((item.metadata as Record<string, unknown> | undefined)?.source ?? "-")}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {fields.length === 0 ? <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">No fields extracted.</p> : null}
          </div>
        </IdpoCard>

        <IdpoCard>
          <h2 className="text-base font-semibold text-slate-900 dark:text-white">Validation Issues</h2>
          <div className="mt-3 space-y-2">
            {issues.map((issue, idx) => {
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
            })}
            {issues.length === 0 ? <p className="text-sm text-slate-500 dark:text-slate-400">No validation issues.</p> : null}
          </div>

          <h3 className="mt-6 text-base font-semibold text-slate-900 dark:text-white">Escalation</h3>
          <div className="mt-3 rounded-lg border border-slate-200 p-3 dark:border-slate-700">
            <p className="text-sm text-slate-700 dark:text-slate-200">Escalated: {String(escalation.escalated ? "yes" : "no")}</p>
            <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">Reason: {String(escalation.reason ?? "-")}</p>
            <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">Target: {String(escalation.targetModel ?? "-")}</p>
            <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">Cost: {String(escalation.costEstimate ?? "-")}</p>
          </div>
        </IdpoCard>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <IdpoCard>
          <h2 className="text-base font-semibold text-slate-900 dark:text-white">Recovery History</h2>
          <div className="mt-3 space-y-2">
            {recovery.map((attempt, idx) => {
              const item = attempt as Record<string, unknown>;
              return (
                <div key={`${String(item.field)}_${idx}`} className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-medium text-slate-900 dark:text-white">{String(item.field)}</p>
                    <StatusBadge value={Boolean(item.success) ? "ready" : "failed"} />
                  </div>
                  <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
                    attempt {String(item.attempt ?? 1)} via {String(item.strategy ?? "unknown")}
                  </p>
                </div>
              );
            })}
            {recovery.length === 0 ? <p className="text-sm text-slate-500 dark:text-slate-400">No recovery attempts.</p> : null}
          </div>
        </IdpoCard>

        <IdpoCard>
          <div className="mb-3 flex items-center justify-between gap-2">
            <h2 className="text-base font-semibold text-slate-900 dark:text-white">Provenance Events</h2>
            <input
              type="text"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search event/doc/agent"
              className="w-48 rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-900"
            />
          </div>

          <div className="max-h-[420px] overflow-auto rounded-xl border border-slate-200 dark:border-slate-700">
            <table className="w-full min-w-[720px] text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
                  <th className="px-2 py-2">Time</th>
                  <th className="px-2 py-2">Stage</th>
                  <th className="px-2 py-2">Event</th>
                  <th className="px-2 py-2">Agent</th>
                </tr>
              </thead>
              <tbody>
                {filteredEvents.map((event) => (
                  <tr key={event.eventId} className="border-b border-slate-100 dark:border-slate-800">
                    <td className="px-2 py-2 text-xs text-slate-600 dark:text-slate-300">{new Date(event.timestamp * 1000).toLocaleTimeString()}</td>
                    <td className="px-2 py-2">
                      <StatusBadge value={event.stage} />
                    </td>
                    <td className="px-2 py-2 text-slate-700 dark:text-slate-200">{event.eventType}</td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{event.agent}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </IdpoCard>
      </div>

      <IdpoCard>
        <JsonViewer title="Raw Document Bundle" value={doc.raw ?? {}} />
      </IdpoCard>

      <IdpoCard>
        <JsonViewer title="Transparency Artifact" value={transparency} />
      </IdpoCard>
    </div>
  );
}
