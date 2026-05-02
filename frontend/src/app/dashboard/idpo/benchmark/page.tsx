"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { idpoApi } from "@/lib/idpo-api";
import { IdpoCard } from "@/components/idpo/card";
import { JsonViewer } from "@/components/idpo/json-viewer";
import type { BenchmarkEvidencePayload, BenchmarkRunSummary } from "@/types/idpo";

function formatNumber(value: unknown, digits = 4) {
  const num = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(num)) {
    return "-";
  }
  return num.toFixed(digits);
}

function metricNumber(table: Record<string, unknown>, key: string, condition: string): number | null {
  const metric = table[key] as Record<string, unknown> | undefined;
  const value = metric?.[condition];
  const num = typeof value === "number" ? value : Number(value);
  return Number.isFinite(num) ? num : null;
}

function formatDelta(delta: number | null, digits = 3) {
  if (delta === null) return "-";
  const prefix = delta > 0 ? "+" : "";
  return `${prefix}${delta.toFixed(digits)}`;
}

function buildOutcomeSummary(table: Record<string, unknown>, adaptiveLabel: string) {
  const staticF1 = metricNumber(table, "exact_f1", "static");
  const adaptiveF1 = metricNumber(table, "exact_f1", adaptiveLabel);
  const staticPrecision = metricNumber(table, "exact_precision", "static");
  const adaptivePrecision = metricNumber(table, "exact_precision", adaptiveLabel);
  const staticRecall = metricNumber(table, "exact_recall", "static");
  const adaptiveRecall = metricNumber(table, "exact_recall", adaptiveLabel);
  const staticLatency = metricNumber(table, "avg_latency_ms", "static");
  const adaptiveLatency = metricNumber(table, "avg_latency_ms", adaptiveLabel);
  const staticSchema = metricNumber(table, "schema_valid_rate", "static");
  const adaptiveSchema = metricNumber(table, "schema_valid_rate", adaptiveLabel);

  const f1Delta = staticF1 !== null && adaptiveF1 !== null ? adaptiveF1 - staticF1 : null;
  const precisionDelta = staticPrecision !== null && adaptivePrecision !== null ? adaptivePrecision - staticPrecision : null;
  const recallDelta = staticRecall !== null && adaptiveRecall !== null ? adaptiveRecall - staticRecall : null;
  const latencyDelta = staticLatency !== null && adaptiveLatency !== null ? staticLatency - adaptiveLatency : null;
  const schemaDelta = staticSchema !== null && adaptiveSchema !== null ? adaptiveSchema - staticSchema : null;

  let extractionHeadline = "Extraction change is not available in the current artifact.";
  if (f1Delta !== null) {
    if (f1Delta > 0.0005) extractionHeadline = `Adaptive improved exact F1 by ${formatDelta(f1Delta, 4)}.`;
    else if (f1Delta < -0.0005) extractionHeadline = `Adaptive reduced exact F1 by ${formatDelta(f1Delta, 4)}.`;
    else extractionHeadline = "Adaptive matched exact F1 in the current artifact.";
  } else if (precisionDelta !== null || recallDelta !== null) {
    extractionHeadline = `Precision delta ${formatDelta(precisionDelta, 4)} and recall delta ${formatDelta(recallDelta, 4)}.`;
  }

  let runtimeHeadline = "Runtime change is not available in the current artifact.";
  if (latencyDelta !== null) {
    if (latencyDelta > 0) runtimeHeadline = `Adaptive was faster by ${latencyDelta.toFixed(2)} ms on average.`;
    else if (latencyDelta < 0) runtimeHeadline = `Adaptive was slower by ${Math.abs(latencyDelta).toFixed(2)} ms on average.`;
    else runtimeHeadline = "Adaptive and static had the same average latency.";
  }

  let schemaHeadline = "Schema-validity change is not available in the current artifact.";
  if (schemaDelta !== null) {
    if (schemaDelta > 0.0005) schemaHeadline = `Adaptive improved schema valid rate by ${formatDelta(schemaDelta * 100, 2)} points.`;
    else if (schemaDelta < -0.0005) schemaHeadline = `Adaptive reduced schema valid rate by ${formatDelta(schemaDelta * 100, 2)} points.`;
    else schemaHeadline = "Adaptive matched schema valid rate in the current artifact.";
  }

  return {
    extractionHeadline,
    runtimeHeadline,
    schemaHeadline,
    f1Delta,
    precisionDelta,
    recallDelta,
    latencyDelta,
    schemaDelta,
  };
}

function adaptiveLabelFromTable(table: Record<string, unknown>): string {
  const avgLatency = table.avg_latency_ms as Record<string, unknown> | undefined;
  if (!avgLatency) {
    return "adaptive_safe";
  }
  return Object.keys(avgLatency).find((key) => key !== "static") ?? "adaptive_safe";
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function formatCountMap(value: unknown) {
  const record = asRecord(value);
  if (!record || Object.keys(record).length === 0) {
    return "-";
  }
  return Object.entries(record)
    .map(([key, count]) => `${key}: ${String(count)}`)
    .join(" | ");
}

function recommendationLabel(doc: Record<string, unknown>) {
  const recommendation = String(doc.advisor_recommendation ?? "").trim();
  return recommendation || "No recommendation";
}

function adviceOutcomeLabel(doc: Record<string, unknown>) {
  const status = String(doc.advice_status ?? "").trim();
  if (!status || status === "static") {
    return "Static";
  }
  if (status === "accepted") {
    return "Accepted";
  }
  if (status === "rejected") {
    return "Rejected";
  }
  if (status === "no_advice") {
    return "No advice";
  }
  return status.replace(/_/g, " ");
}

function containmentLabel(doc: Record<string, unknown>) {
  if (Boolean(doc.blocked_policy)) {
    return "Blocked policy";
  }
  if (Boolean(doc.rollback_triggered)) {
    return "Rollback";
  }
  const fallbackReason = String(doc.fallback_reason ?? "").trim();
  if (fallbackReason) {
    return `Fallback: ${fallbackReason}`;
  }
  const deferStatus = String(doc.defer_status ?? "").trim();
  if (deferStatus === "requested") {
    return "Deferred";
  }
  if (deferStatus === "blocked") {
    return "Defer blocked";
  }
  return "None";
}

function claimStatusLabel(value: unknown) {
  return value === true ? "Supported" : "Not supported";
}

function renderTable(
  title: string,
  table: Record<string, unknown>,
  adaptiveLabel: string,
) {
  const rows = [
    ["Avg Latency (ms)", "avg_latency_ms"],
    ["Avg Runtime Proxy Reward", "avg_reward"],
    ["Exact Precision", "exact_precision"],
    ["Exact Recall", "exact_recall"],
    ["Exact F1", "exact_f1"],
    ["Exact-Scored Doc Count", "exact_scored_doc_count"],
    ["Validation Pass Rate", "validation_pass_rate"],
    ["Recovery Rate", "recovery_rate"],
    ["Escalation Rate", "escalation_rate"],
    ["Rollback Count", "rollback_count"],
    ["Blocked Policy Count", "blocked_policy_count"],
    ["Fallback Count", "fallback_count"],
    ["Advice Accepted Count", "advice_accepted_count"],
    ["Policy Changed Count", "policy_changed_count"],
    ["Avg Schema Coverage", "avg_schema_coverage"],
    ["Avg Grounding Coverage", "avg_schema_grounding_coverage"],
    ["Schema Valid Rate", "schema_valid_rate"],
    ["Defer Requested Count", "defer_requested_count"],
    ["Defer Blocked Count", "defer_blocked_count"],
  ];

  return (
    <IdpoCard>
      <h3 className="text-base font-semibold text-slate-900 dark:text-white">{title}</h3>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full min-w-[520px] text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
              <th className="px-2 py-2">Metric</th>
              <th className="px-2 py-2">Static</th>
              <th className="px-2 py-2">{adaptiveLabel}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([label, key]) => {
              const metric = (table[key] as Record<string, unknown> | undefined) ?? {};
              return (
                <tr key={key} className="border-b border-slate-100 dark:border-slate-800">
                  <td className="px-2 py-2 text-slate-700 dark:text-slate-200">{label}</td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{typeof metric.static === "object" ? JSON.stringify(metric.static) : String(metric.static ?? "-")}</td>
                  <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{typeof metric[adaptiveLabel] === "object" ? JSON.stringify(metric[adaptiveLabel]) : String(metric[adaptiveLabel] ?? "-")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </IdpoCard>
  );
}

export default function BenchmarkPage() {
  const [runs, setRuns] = useState<BenchmarkRunSummary[]>([]);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [evidence, setEvidence] = useState<BenchmarkEvidencePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    idpoApi
      .benchmarkRuns()
      .then((payload) => {
        setRuns(payload.runs);
        const initial = payload.latest?.benchmarkRunId ?? payload.runs[0]?.benchmarkRunId ?? "";
        setSelectedRunId(initial);
        if (!initial) {
          setLoading(false);
          return;
        }
        return idpoApi.benchmarkEvidence(initial).then((result) => {
          setEvidence(result);
          setLoading(false);
        });
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load benchmark reports");
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    if (!selectedRunId) {
      return;
    }
    setError("");
    idpoApi
      .benchmarkEvidence(selectedRunId)
      .then((payload) => setEvidence(payload))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load benchmark evidence"));
  }, [selectedRunId]);

  const comparison = (evidence?.comparison ?? {}) as Record<string, unknown>;
  const table = (comparison.table ?? {}) as Record<string, unknown>;
  const groupsFromPayload = (comparison.groups ?? {}) as Record<string, Record<string, unknown>>;
  const bootstrap = (comparison.bootstrap ?? {}) as Record<string, unknown>;
  const overallBootstrap = (bootstrap.overall ?? {}) as Record<string, Record<string, unknown>>;
  const documents = Array.isArray(evidence?.documents) ? evidence?.documents : [];
  const adaptiveLabel = adaptiveLabelFromTable(table);
  const outcomeSummary = buildOutcomeSummary(table, adaptiveLabel);
  const conditions = (evidence?.conditions ?? {}) as Record<string, Record<string, unknown>>;
  const adaptiveCondition = (conditions[adaptiveLabel] ?? conditions.adaptive_safe ?? conditions.adaptive ?? {}) as Record<string, unknown>;
  const staticCondition = (conditions.static ?? {}) as Record<string, unknown>;
  const claimChecks = (comparison.claim_checks ?? {}) as Record<string, Record<string, unknown>>;
  const groups =
    Object.keys(groupsFromPayload).length > 0
      ? groupsFromPayload
      : Object.fromEntries(
          Object.entries(comparison).filter(([key, value]) => {
            if (["doc_count", "table", "static", adaptiveLabel, "adaptive_safe", "adaptive", "bootstrap"].includes(key)) {
              return false;
            }
            const record = asRecord(value);
            return Boolean(record && ("avg_latency_ms" in record || "avg_reward" in record || "exact_f1" in record));
          }),
        ) as Record<string, Record<string, unknown>>;

  const selectedRun = useMemo(
    () => runs.find((run) => run.benchmarkRunId === selectedRunId) ?? null,
    [runs, selectedRunId],
  );

  if (loading) {
    return <div className="text-sm text-slate-600 dark:text-slate-300">Loading benchmark evidence...</div>;
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-gradient-to-r from-slate-50 via-white to-emerald-50 p-6 dark:border-slate-800 dark:from-slate-900 dark:via-slate-900 dark:to-slate-900">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <Link href="/dashboard/idpo" className="text-xs text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">
              Back to IDPO dashboard
            </Link>
            <h1 className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">Benchmark Results</h1>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              Static versus adaptive_safe results on identical inputs, with IDPO containment and structured-output outcomes surfaced directly from run artifacts.
            </p>
          </div>
          <Link
            href="/dashboard/idpo/compare"
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
          >
            Open Run Comparison
          </Link>
        </div>
      </section>

      {error ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300">
          {error}
        </div>
      ) : null}

      <IdpoCard>
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-sm text-slate-700 dark:text-slate-200" htmlFor="benchmark-run">
            Benchmark Run
          </label>
          <select
            id="benchmark-run"
            value={selectedRunId}
            onChange={(event) => setSelectedRunId(event.target.value)}
            className="min-w-[280px] rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
          >
            {runs.map((run) => (
              <option key={run.benchmarkRunId} value={run.benchmarkRunId}>
                {run.benchmarkRunId} ({run.docCount} docs)
              </option>
            ))}
          </select>
          {selectedRun ? (
            <span className="text-xs text-slate-500 dark:text-slate-400">
              Generated: {new Date(selectedRun.generatedAt).toLocaleString()}
            </span>
          ) : null}
        </div>
        {runs.length === 0 ? (
          <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-800/60 dark:text-slate-300">
            <p>No benchmark reports found under the canonical benchmark directory.</p>
            <p className="mt-2 font-mono text-xs text-slate-500 dark:text-slate-400">
              python scripts/run_idpo_benchmark.py --config configs/idpo_research_config.json
            </p>
          </div>
        ) : null}
      </IdpoCard>

      {evidence ? (
        <>
          <IdpoCard>
            <h3 className="text-base font-semibold text-slate-900 dark:text-white">Outcome Summary</h3>
            <div className="mt-3 grid gap-3 lg:grid-cols-3">
              <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
                <p className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Extraction Outcome</p>
                <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{outcomeSummary.extractionHeadline}</p>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  F1 delta {formatDelta(outcomeSummary.f1Delta, 4)}, precision delta {formatDelta(outcomeSummary.precisionDelta, 4)}, recall delta {formatDelta(outcomeSummary.recallDelta, 4)}
                </p>
              </div>
              <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
                <p className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Runtime Outcome</p>
                <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{outcomeSummary.runtimeHeadline}</p>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  A positive latency delta means adaptive is faster than static.
                </p>
              </div>
              <div className="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
                <p className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Structured Output Outcome</p>
                <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">{outcomeSummary.schemaHeadline}</p>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  Adaptive only counts as better extraction when quality metrics improve, not just routing activity.
                </p>
              </div>
            </div>
          </IdpoCard>

          <IdpoCard>
            <h3 className="text-base font-semibold text-slate-900 dark:text-white">Claim Checks</h3>
            <div className="mt-3 grid gap-3 lg:grid-cols-2">
              {Object.entries(claimChecks).map(([key, item]) => (
                <div key={key} className="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
                  <p className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400">
                    {key.replace(/_/g, " ")}
                  </p>
                  <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">
                    {claimStatusLabel(item?.pass)}
                  </p>
                  <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                    {String(item?.detail ?? "-")}
                  </p>
                </div>
              ))}
              {Object.keys(claimChecks).length === 0 ? (
                <div className="rounded-xl border border-slate-200 p-4 text-sm text-slate-500 dark:border-slate-700 dark:text-slate-400">
                  This benchmark bundle does not include claim checks.
                </div>
              ) : null}
            </div>
          </IdpoCard>

          <div className="grid gap-4 md:grid-cols-4">
            <IdpoCard>
              <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Doc Count</p>
              <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{String(comparison.doc_count ?? "-")}</p>
            </IdpoCard>
            <IdpoCard>
              <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Policy Switch Rate</p>
              <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{formatNumber(comparison.policy_switch_rate, 4)}</p>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">advice acceptance {formatNumber(comparison.advice_acceptance_rate, 4)}</p>
            </IdpoCard>
            <IdpoCard>
              <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Advice Statuses</p>
              <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">
                {formatCountMap(adaptiveCondition.advice_status_counts)}
              </p>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Accepted and rejected are separated from no-advice cases.</p>
            </IdpoCard>
            <IdpoCard>
              <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Containment States</p>
              <p className="mt-2 text-sm font-semibold text-slate-900 dark:text-white">
                {formatCountMap(adaptiveCondition.containment_state_counts)}
              </p>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Fallback, rollback, blocking, and defer are counted directly from adaptive docs.</p>
            </IdpoCard>
            <IdpoCard>
              <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Exact Win / Match / Loss</p>
              <p className="mt-2 text-lg font-semibold text-slate-900 dark:text-white">
                {String(comparison.exact_win_count ?? 0)} / {String(comparison.exact_match_count ?? 0)} / {String(comparison.exact_loss_count ?? 0)}
              </p>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                exact-scored docs {String(comparison.exact_scored_doc_count ?? 0)}
              </p>
            </IdpoCard>
            <IdpoCard>
              <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Structural Win / Match / Loss</p>
              <p className="mt-2 text-lg font-semibold text-slate-900 dark:text-white">
                {String(comparison.structural_win_count ?? 0)} / {String(comparison.structural_match_count ?? 0)} / {String(comparison.structural_loss_count ?? 0)}
              </p>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                latency delta {formatNumber(overallBootstrap.latency_delta_ms?.mean, 2)} ms
              </p>
            </IdpoCard>
          </div>

          {renderTable("Overall Comparison", table, adaptiveLabel)}

          <div className="grid gap-4 lg:grid-cols-2">
            <IdpoCard>
              <h3 className="text-base font-semibold text-slate-900 dark:text-white">Adaptive Usage Snapshot</h3>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
                  <p className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Static Policy Distribution</p>
                  <p className="mt-2 text-xs text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
                    {JSON.stringify(staticCondition.policy_distribution ?? {}, null, 2)}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
                  <p className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400">{adaptiveLabel} Policy Distribution</p>
                  <p className="mt-2 text-xs text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
                    {JSON.stringify(adaptiveCondition.policy_distribution ?? {}, null, 2)}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
                  <p className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Advice Source Counts</p>
                  <p className="mt-2 text-xs text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
                    {JSON.stringify(adaptiveCondition.advice_source_counts ?? {}, null, 2)}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
                  <p className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Advice Status Counts</p>
                  <p className="mt-2 text-xs text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
                    {JSON.stringify(adaptiveCondition.advice_status_counts ?? {}, null, 2)}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
                  <p className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Containment State Counts</p>
                  <p className="mt-2 text-xs text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
                    {JSON.stringify(adaptiveCondition.containment_state_counts ?? {}, null, 2)}
                  </p>
                </div>
                <div className="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
                  <p className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Routing Impact</p>
                  <p className="mt-2 text-xs text-slate-700 dark:text-slate-300 whitespace-pre-wrap">
                    {JSON.stringify(
                      {
                        advice_accepted_count: adaptiveCondition.advice_accepted_count ?? 0,
                        policy_changed_count: adaptiveCondition.policy_changed_count ?? 0,
                        exact_scored_doc_count: adaptiveCondition.exact_scored_doc_count ?? 0,
                        retrieval_source_counts: adaptiveCondition.retrieval_source_counts ?? {},
                      },
                      null,
                      2,
                    )}
                  </p>
                </div>
              </div>
            </IdpoCard>

            <IdpoCard>
              <h3 className="text-base font-semibold text-slate-900 dark:text-white">Group Comparisons</h3>
              <div className="mt-3 space-y-4">
                {Object.entries(groups).map(([group, groupTable]) => (
                    <div key={group} className="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
                    <p className="text-sm font-semibold text-slate-900 dark:text-white">{group}</p>
                    <div className="mt-2 grid gap-2 sm:grid-cols-2">
                      <div className="rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-800/60">
                        <p className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Exact F1</p>
                        <p className="mt-1 text-sm text-slate-900 dark:text-white">
                          {String(((groupTable.exact_f1 as Record<string, unknown> | undefined)?.static) ?? "-")} / {String(((groupTable.exact_f1 as Record<string, unknown> | undefined)?.[adaptiveLabel]) ?? "-")}
                        </p>
                      </div>
                      <div className="rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-800/60">
                        <p className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Fallback Count</p>
                        <p className="mt-1 text-sm text-slate-900 dark:text-white">
                          {String(((groupTable.fallback_count as Record<string, unknown> | undefined)?.static) ?? "-")} / {String(((groupTable.fallback_count as Record<string, unknown> | undefined)?.[adaptiveLabel]) ?? "-")}
                        </p>
                      </div>
                      <div className="rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-800/60">
                        <p className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Schema Valid Rate</p>
                        <p className="mt-1 text-sm text-slate-900 dark:text-white">
                          {String(((groupTable.schema_valid_rate as Record<string, unknown> | undefined)?.static) ?? "-")} / {String(((groupTable.schema_valid_rate as Record<string, unknown> | undefined)?.[adaptiveLabel]) ?? "-")}
                        </p>
                      </div>
                      <div className="rounded-lg bg-slate-50 px-3 py-2 dark:bg-slate-800/60">
                        <p className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400">Advice Status Counts</p>
                        <p className="mt-1 text-sm text-slate-900 dark:text-white">
                          {formatCountMap((groupTable.advice_status_counts as Record<string, unknown> | undefined)?.[adaptiveLabel])}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
                {Object.keys(groups).length === 0 ? (
                  <p className="text-sm text-slate-500 dark:text-slate-400">No subgroup tables found in this benchmark bundle.</p>
                ) : null}
              </div>
            </IdpoCard>

            <IdpoCard>
              <h3 className="text-base font-semibold text-slate-900 dark:text-white">Bootstrap Summary</h3>
              <div className="mt-3 space-y-3">
                {([
                  ["Exact F1 Delta", overallBootstrap.exact_f1_delta],
                  ["Latency Delta (ms)", overallBootstrap.latency_delta_ms],
                  ["Validation Pass Rate Delta", overallBootstrap.validation_pass_rate_delta],
                ] as Array<[string, Record<string, unknown> | undefined]>).map(([label, metric]) => {
                  const item = (metric ?? {}) as Record<string, unknown>;
                  return (
                    <div key={label} className="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
                      <p className="text-sm font-medium text-slate-900 dark:text-white">{label}</p>
                      <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
                        mean={formatNumber(item.mean, 4)} | 95% CI [{formatNumber(item.ci_low, 4)}, {formatNumber(item.ci_high, 4)}]
                      </p>
                    </div>
                  );
                })}
              </div>
            </IdpoCard>
          </div>

          <IdpoCard>
            <h3 className="text-base font-semibold text-slate-900 dark:text-white">Per-Case Drilldown</h3>
            <div className="mt-3 overflow-x-auto">
              <table className="w-full min-w-[1080px] text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                    <th className="px-2 py-2">Case</th>
                    <th className="px-2 py-2">Tags</th>
                    <th className="px-2 py-2">Static Policy</th>
                    <th className="px-2 py-2">Recommended</th>
                    <th className="px-2 py-2">{adaptiveLabel} Policy</th>
                    <th className="px-2 py-2">Advice Outcome</th>
                    <th className="px-2 py-2">Containment</th>
                    <th className="px-2 py-2">Outcome</th>
                    <th className="px-2 py-2">F1 Delta</th>
                    <th className="px-2 py-2">Latency Delta</th>
                    <th className="px-2 py-2">Schema</th>
                    <th className="px-2 py-2">Review</th>
                    <th className="px-2 py-2">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((entry) => {
                    const item = entry as Record<string, unknown>;
                    const staticRecord = (item.static ?? {}) as Record<string, unknown>;
                    const adaptiveRecord = (item[adaptiveLabel] ?? item.adaptive_safe ?? item.adaptive ?? {}) as Record<string, unknown>;
                    const staticDoc = (staticRecord.doc ?? {}) as Record<string, unknown>;
                    const adaptiveDoc = (adaptiveRecord.doc ?? {}) as Record<string, unknown>;
                    const deltas = (item.deltas ?? {}) as Record<string, unknown>;
                    const adaptiveRunId = String(adaptiveRecord.run_id ?? "");
                    const adaptiveDocId = String(adaptiveDoc.doc_id ?? "");
                    return (
                      <tr key={String(item.case_id)} className="border-b border-slate-100 dark:border-slate-800">
                        <td className="px-2 py-2 text-slate-900 dark:text-slate-100">{String(item.case_id)}</td>
                        <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{Array.isArray(item.tags) ? item.tags.join(", ") : "-"}</td>
                        <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{String(staticDoc.policy_id ?? "-")}</td>
                        <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{recommendationLabel(adaptiveDoc)}</td>
                        <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{String(adaptiveDoc.policy_id ?? "-")}</td>
                        <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{adviceOutcomeLabel(adaptiveDoc)}</td>
                        <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{containmentLabel(adaptiveDoc)}</td>
                        <td className="px-2 py-2 text-slate-600 dark:text-slate-300">
                          {String(deltas.exact_win_loss_state ?? "unscored")} / {String(deltas.structural_win_loss_state ?? "match")}
                        </td>
                        <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{formatNumber(deltas.exact_f1_delta, 4)}</td>
                        <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{formatNumber(deltas.latency_ms, 2)}</td>
                        <td className="px-2 py-2 text-slate-600 dark:text-slate-300">
                          {typeof adaptiveDoc.schema_coverage === "number" ? formatNumber(adaptiveDoc.schema_coverage, 3) : "-"}
                        </td>
                        <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{String(adaptiveDoc.defer_status ?? "-")}</td>
                        <td className="px-2 py-2">
                          <span className="font-mono text-xs text-slate-500 dark:text-slate-400">
                            {adaptiveDocId ? adaptiveDocId.slice(0, 8) : "—"}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </IdpoCard>

          <IdpoCard>
            <JsonViewer title="Raw Benchmark Report" value={evidence} />
          </IdpoCard>
        </>
      ) : null}
    </div>
  );
}
