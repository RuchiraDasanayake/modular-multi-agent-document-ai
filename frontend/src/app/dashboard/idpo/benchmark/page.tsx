"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { idpoApi } from "@/lib/idpo-api";
import { IdpoCard } from "@/components/idpo/card";
import { Icon } from "@/components/icons";
import type { BenchmarkEvidencePayload, BenchmarkRunSummary } from "@/types/idpo";

type Row = Record<string, unknown>;
type Tone = "neutral" | "good" | "bad";
type MetricKind = "score" | "seconds" | "rate" | "count";

interface Interval {
  mean: number;
  low: number;
  high: number;
}

// Run folders listed in paper/FINAL_EVIDENCE.md.
const PAPER_RUNS: Record<string, { pack: string; round: "final" | "first" }> = {
  benchmark_1791441991: { pack: "CORD-dev", round: "final" },
  benchmark_1791274931: { pack: "CORD-holdout", round: "final" },
  benchmark_1791274020: { pack: "FUNSD-20", round: "final" },
  benchmark_1791274329: { pack: "HARD-13", round: "final" },
  benchmark_1791272981: { pack: "CORD-dev", round: "first" },
  benchmark_1791272484: { pack: "CORD-holdout", round: "first" },
  benchmark_1791271549: { pack: "FUNSD-20", round: "first" },
  benchmark_1791271853: { pack: "HARD-13", round: "first" },
};

const PACK_ORDER = ["CORD-dev", "CORD-holdout", "FUNSD-20", "HARD-13"];

const RUN_GROUPS = [
  { key: "final", label: "Paper: final runs (safety limits relative to default)" },
  { key: "first", label: "Paper: first runs (absolute safety limits)" },
  { key: "other", label: "Other runs" },
] as const;

const METRICS: Array<{ key: string; label: string; kind: MetricKind; hint?: string }> = [
  { key: "exact_f1", label: "Exact F1 (micro)", kind: "score" },
  { key: "exact_precision", label: "Exact precision", kind: "score" },
  { key: "exact_recall", label: "Exact recall", kind: "score" },
  { key: "exact_scored_doc_count", label: "Labelled documents", kind: "count" },
  { key: "avg_latency_ms", label: "Average time per document", kind: "seconds" },
  {
    key: "avg_reward",
    label: "Label-free reward",
    kind: "score",
    hint: "The coverage reward the router learns from. It does not measure correctness.",
  },
  { key: "validation_pass_rate", label: "Validation pass rate", kind: "rate", hint: "Documents with no validation issue." },
  {
    key: "schema_valid_rate",
    label: "Schema-valid rate",
    kind: "rate",
    hint: "Every required field extracted, no extra fields and no validation issue.",
  },
  { key: "avg_schema_coverage", label: "Required fields extracted", kind: "score", hint: "Mean share of required fields that were extracted." },
  {
    key: "avg_schema_grounding_coverage",
    label: "Grounded in OCR text",
    kind: "score",
    hint: "Mean share of extracted required fields that appear in the OCR text.",
  },
  { key: "recovery_rate", label: "Recovery rate", kind: "rate" },
  { key: "escalation_rate", label: "Escalation rate", kind: "rate" },
  { key: "policy_changed_count", label: "Policy changed by advice", kind: "count" },
  { key: "advice_accepted_count", label: "Advice accepted", kind: "count" },
  { key: "rollback_count", label: "Rollbacks", kind: "count" },
  { key: "blocked_policy_count", label: "Blocked policies", kind: "count" },
  { key: "fallback_count", label: "Fallbacks", kind: "count" },
  { key: "defer_requested_count", label: "Deferred to review", kind: "count" },
  { key: "defer_blocked_count", label: "Deferral blocked", kind: "count" },
];

const CHECK_LABELS: Record<string, string> = {
  llm_reachable_for_every_document: "The language model answered for every document",
  adaptive_safe_runtime_real: "Adaptive runs received live AHMN advice",
  ahmn_changes_policy: "AHMN changed the policy for some documents",
  idpo_containment_exercised: "The safety gate recorded its decisions",
  adaptive_improves_any_supported_metric: "At least one point estimate favours adaptive (not a significance test)",
  claims_remain_limited: "Claims stay within what was measured",
};

const ADVICE_LABELS: Record<string, string> = {
  accepted: "Accepted",
  rejected: "Rejected",
  no_advice: "No advice",
};

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "border-slate-200 bg-slate-100 text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200",
  good: "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300",
  bad: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300",
};

const SECONDARY_BUTTON =
  "inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800";

function asRecord(value: unknown): Row {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Row) : {};
}

function toNumber(value: unknown): number | null {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function signed(value: number, digits: number, unit = ""): string {
  const rounded = Number(value.toFixed(digits));
  const sign = rounded > 0 ? "+" : rounded < 0 ? "−" : "";
  return `${sign}${Math.abs(rounded).toFixed(digits)}${unit}`;
}

function readInterval(value: unknown): Interval | null {
  const record = asRecord(value);
  const mean = toNumber(record.mean);
  const low = toNumber(record.ci_low);
  const high = toNumber(record.ci_high);
  return mean === null || low === null || high === null ? null : { mean, low, high };
}

function verdictFor(interval: Interval | null, higherIsBetter: boolean, better: string, worse: string) {
  if (!interval) {
    return { label: "No interval in this report", tone: "neutral" as Tone };
  }
  if (interval.low === 0 && interval.high === 0) {
    return { label: "Same on every document", tone: "neutral" as Tone };
  }
  if (interval.low <= 0 && interval.high >= 0) {
    return { label: "No clear difference", tone: "neutral" as Tone };
  }
  return (interval.low > 0) === higherIsBetter
    ? { label: better, tone: "good" as Tone }
    : { label: worse, tone: "bad" as Tone };
}

function metricPair(table: Row, key: string, adaptiveKey: string) {
  const metric = asRecord(table[key]);
  return { static: toNumber(metric.static), adaptive: toNumber(metric[adaptiveKey]) };
}

function formatMetric(value: number | null, kind: MetricKind): string {
  if (value === null) {
    return "—";
  }
  if (kind === "seconds") return `${(value / 1000).toFixed(1)} s`;
  if (kind === "rate") return `${Math.round(value * 100)}%`;
  if (kind === "count") return String(Math.round(value));
  return value.toFixed(3);
}

function formatMetricDelta(staticValue: number | null, adaptiveValue: number | null, kind: MetricKind): string {
  if (staticValue === null || adaptiveValue === null) {
    return "—";
  }
  const delta = adaptiveValue - staticValue;
  if (kind === "seconds") return signed(delta / 1000, 1, " s");
  if (kind === "rate") return signed(delta * 100, 0, " pts");
  if (kind === "count") return signed(delta, 0);
  return signed(delta, 3);
}

function formatCounts(value: unknown): string {
  const entries = Object.entries(asRecord(value));
  return entries.length > 0
    ? entries.map(([key, count]) => `${key.replace(/_/g, " ")}: ${String(count)}`).join(", ")
    : "—";
}

function formatCheckDetail(detail: unknown): string {
  const text = String(detail ?? "").trim();
  if (text.startsWith("{")) {
    try {
      return formatCounts(JSON.parse(text));
    } catch {
      return text;
    }
  }
  return text.replace(/_/g, " ");
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function runLabel(run: BenchmarkRunSummary): string {
  const pack = PAPER_RUNS[run.benchmarkRunId]?.pack ?? run.packName;
  return `${pack} · ${run.docCount} docs · ${formatDateTime(run.generatedAt)}`;
}

function runDescription(run: BenchmarkRunSummary): string {
  const paper = PAPER_RUNS[run.benchmarkRunId];
  if (!paper) {
    return "Not one of the runs reported in the paper.";
  }
  return paper.round === "final"
    ? `Reported in the paper: final ${paper.pack} run, with safety limits relative to the default policy.`
    : `Reported in the paper: first ${paper.pack} run, with absolute safety limits.`;
}

function packRank(run: BenchmarkRunSummary): number {
  const index = PACK_ORDER.indexOf(PAPER_RUNS[run.benchmarkRunId]?.pack ?? "");
  return index === -1 ? PACK_ORDER.length : index;
}

function adaptiveKeyFrom(table: Row): string {
  return Object.keys(asRecord(table.avg_latency_ms)).find((key) => key !== "static") ?? "adaptive_safe";
}

function recommendedPolicy(value: unknown): string {
  if (typeof value === "string") {
    return value.trim() || "—";
  }
  const policyId = asRecord(value).policy_id;
  return typeof policyId === "string" && policyId ? policyId : "—";
}

function adviceLabel(doc: Row): string {
  const status = String(doc.advice_status ?? "").trim();
  if (!status || status === "static") {
    return "—";
  }
  return ADVICE_LABELS[status] ?? status.replace(/_/g, " ");
}

function gateLabel(doc: Row): string {
  if (Boolean(doc.rollback_triggered)) return "Rolled back";
  if (Boolean(doc.blocked_policy)) return "Policy blocked";
  const fallbackReason = String(doc.fallback_reason ?? "").trim();
  if (fallbackReason) return `Fallback: ${fallbackReason.replace(/_/g, " ")}`;
  if (doc.defer_status === "requested") return "Deferred to review";
  if (doc.defer_status === "blocked") return "Deferral blocked";
  return "—";
}

function docHref(runId: unknown, docId: unknown): string | null {
  return typeof runId === "string" && runId && typeof docId === "string" && docId
    ? `/dashboard/idpo/runs/${encodeURIComponent(runId)}/docs/${encodeURIComponent(docId)}`
    : null;
}

function VerdictChip({ label, tone }: { label: string; tone: Tone }) {
  return (
    <span className={`inline-flex shrink-0 rounded-full border px-2.5 py-0.5 text-xs font-medium ${TONE_CLASSES[tone]}`}>
      {label}
    </span>
  );
}

function OutcomeCard({
  title,
  value,
  verdict,
  interval,
  lines,
}: {
  title: string;
  value: string;
  verdict: { label: string; tone: Tone };
  interval: string | null;
  lines: string[];
}) {
  return (
    <div className="flex flex-col rounded-xl border border-slate-200 p-4 dark:border-slate-700">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">{title}</p>
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-2xl font-semibold tabular-nums text-slate-900 dark:text-white">{value}</p>
        <VerdictChip label={verdict.label} tone={verdict.tone} />
      </div>
      <p className="mt-1 text-xs tabular-nums text-slate-500 dark:text-slate-400">
        {interval ? `95% interval ${interval}` : "No bootstrap interval in this report"}
      </p>
      <div className="mt-3 space-y-1 border-t border-slate-100 pt-3 text-sm text-slate-600 dark:border-slate-800 dark:text-slate-300">
        {lines.map((line) => (
          <p key={line}>{line}</p>
        ))}
      </div>
    </div>
  );
}

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 px-4 py-3 dark:border-slate-700" title={hint}>
      <p className="text-xs text-slate-500 dark:text-slate-400">{label}</p>
      <p className="mt-1 text-lg font-semibold tabular-nums text-slate-900 dark:text-white">{value}</p>
    </div>
  );
}

function PolicyBars({ title, distribution, total }: { title: string; distribution: unknown; total: number }) {
  const entries = Object.entries(asRecord(distribution))
    .map(([policy, count]) => [policy, toNumber(count) ?? 0] as const)
    .sort((a, b) => b[1] - a[1]);
  return (
    <div>
      <p className="text-sm font-medium text-slate-900 dark:text-white">{title}</p>
      <ul className="mt-2 space-y-2.5">
        {entries.map(([policy, count]) => (
          <li key={policy}>
            <div className="flex justify-between gap-3 text-xs text-slate-600 dark:text-slate-300">
              <span className="truncate font-mono">{policy}</span>
              <span className="tabular-nums">{count}</span>
            </div>
            <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
              <div
                className="h-full rounded-full bg-cyan-500"
                style={{ width: `${total > 0 ? Math.min(100, (count / total) * 100) : 0}%` }}
              />
            </div>
          </li>
        ))}
        {entries.length === 0 ? <li className="text-xs text-slate-500 dark:text-slate-400">Not recorded.</li> : null}
      </ul>
    </div>
  );
}

function SkeletonBlock({ className }: { className: string }) {
  return <div className={`animate-pulse rounded-2xl bg-slate-200/70 dark:bg-slate-800/70 ${className}`} />;
}

export default function BenchmarkPage() {
  const [runs, setRuns] = useState<BenchmarkRunSummary[]>([]);
  const [runsLoading, setRunsLoading] = useState(true);
  const [selectedRunId, setSelectedRunId] = useState("");
  const [evidence, setEvidence] = useState<BenchmarkEvidencePayload | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [error, setError] = useState("");
  const [onlyDifferent, setOnlyDifferent] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setRunsLoading(true);
    idpoApi
      .benchmarkRuns()
      .then((payload) => {
        if (cancelled) return;
        setRuns(payload.runs);
        const paperCordDev = payload.runs.find((run) => {
          const paper = PAPER_RUNS[run.benchmarkRunId];
          return paper?.round === "final" && paper.pack === "CORD-dev";
        });
        setSelectedRunId(
          (current) =>
            current || paperCordDev?.benchmarkRunId || payload.latest?.benchmarkRunId || payload.runs[0]?.benchmarkRunId || "",
        );
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load the list of benchmark runs.");
      })
      .finally(() => {
        if (!cancelled) setRunsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  useEffect(() => {
    if (!selectedRunId) {
      return;
    }
    let cancelled = false;
    setEvidenceLoading(true);
    setError("");
    idpoApi
      .benchmarkEvidence(selectedRunId)
      .then((payload) => {
        if (!cancelled) setEvidence(payload);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Could not load this benchmark report.");
      })
      .finally(() => {
        if (!cancelled) setEvidenceLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedRunId, reloadKey]);

  const selectedRun = useMemo(
    () => runs.find((run) => run.benchmarkRunId === selectedRunId) ?? null,
    [runs, selectedRunId],
  );

  const runGroups = useMemo(
    () =>
      RUN_GROUPS.map((group) => ({
        ...group,
        runs: runs
          .filter((run) => (PAPER_RUNS[run.benchmarkRunId]?.round ?? "other") === group.key)
          .sort((a, b) => (group.key === "other" ? 0 : packRank(a) - packRank(b))),
      })).filter((group) => group.runs.length > 0),
    [runs],
  );

  const view = useMemo(() => {
    if (!evidence) {
      return null;
    }
    const comparison = asRecord(evidence.comparison);
    const table = asRecord(comparison.table);
    const adaptiveKey = adaptiveKeyFrom(table);
    const conditions = asRecord(evidence.conditions);
    const bootstrap = asRecord(comparison.bootstrap);
    const overall = asRecord(bootstrap.overall);
    const groupIntervals = asRecord(bootstrap.groups);
    const docCount = toNumber(comparison.doc_count) ?? 0;

    const groups = Object.entries(asRecord(comparison.groups)).map(([tag, value]) => {
      const groupTable = asRecord(value);
      const intervals = asRecord(groupIntervals[tag]);
      return {
        tag,
        docCount: toNumber(groupTable.doc_count) ?? 0,
        f1: metricPair(groupTable, "exact_f1", adaptiveKey),
        f1Interval: readInterval(intervals.exact_f1_delta),
        latencyInterval: readInterval(intervals.latency_delta_ms),
      };
    });

    const documents = (Array.isArray(evidence.documents) ? evidence.documents : []).map((entry) => {
      const item = asRecord(entry);
      const staticRecord = asRecord(item.static);
      const adaptiveRecord = asRecord(item[adaptiveKey]);
      const staticDoc = asRecord(staticRecord.doc);
      const adaptiveDoc = asRecord(adaptiveRecord.doc);
      const staticF1 = toNumber(asRecord(staticRecord.exact_metrics).f1);
      const adaptiveF1 = toNumber(asRecord(adaptiveRecord.exact_metrics).f1);
      const staticLatency = toNumber(staticDoc.latency_ms);
      const adaptiveLatency = toNumber(adaptiveDoc.latency_ms);
      return {
        caseId: String(item.case_id ?? adaptiveDoc.doc_id ?? ""),
        tags: Array.isArray(item.tags) ? item.tags.map(String) : [],
        staticPolicy: String(staticDoc.policy_id ?? "—"),
        adaptivePolicy: String(adaptiveDoc.policy_id ?? "—"),
        recommended: recommendedPolicy(adaptiveDoc.advisor_recommendation),
        advice: adviceLabel(adaptiveDoc),
        gate: gateLabel(adaptiveDoc),
        staticF1,
        adaptiveF1,
        f1Different: staticF1 !== null && adaptiveF1 !== null && Math.abs(adaptiveF1 - staticF1) > 1e-9,
        latencyDelta: staticLatency !== null && adaptiveLatency !== null ? adaptiveLatency - staticLatency : null,
        staticHref: docHref(staticRecord.run_id, staticDoc.doc_id),
        adaptiveHref: docHref(adaptiveRecord.run_id, adaptiveDoc.doc_id),
      };
    });

    return {
      comparison,
      table,
      adaptiveKey,
      docCount,
      staticCondition: asRecord(conditions.static),
      adaptiveCondition: asRecord(conditions[adaptiveKey]),
      f1: readInterval(overall.exact_f1_delta),
      latency: readInterval(overall.latency_delta_ms),
      validation: readInterval(overall.validation_pass_rate_delta),
      checks: Object.entries(asRecord(comparison.claim_checks)).map(([key, value]) => {
        const check = asRecord(value);
        return { key, passed: check.pass === true, detail: check.detail };
      }),
      groups,
      groupsMatchOverall: groups.length > 0 && groups.every((group) => group.docCount === docCount),
      documents,
    };
  }, [evidence]);

  const visibleDocuments = useMemo(
    () => (view ? (onlyDifferent ? view.documents.filter((doc) => doc.f1Different) : view.documents) : []),
    [view, onlyDifferent],
  );

  const f1Pair = view ? metricPair(view.table, "exact_f1", view.adaptiveKey) : null;
  const latencyPair = view ? metricPair(view.table, "avg_latency_ms", view.adaptiveKey) : null;
  const validationPair = view ? metricPair(view.table, "validation_pass_rate", view.adaptiveKey) : null;
  const differentCount = view ? view.documents.filter((doc) => doc.f1Different).length : 0;

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-gradient-to-r from-slate-50 via-white to-emerald-50 p-6 dark:border-slate-800 dark:from-slate-900 dark:via-slate-900 dark:to-slate-900">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-3xl">
            <h1 className="text-2xl font-semibold text-slate-900 dark:text-white">Benchmark results</h1>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              Each benchmark processes the same labelled documents twice. Static always uses the default policy; adaptive
              lets AHMN choose a policy behind the safety gate. Differences on this page are adaptive minus static.
            </p>
          </div>
          <Link href="/dashboard/idpo/compare" className={SECONDARY_BUTTON}>
            Compare two runs
          </Link>
        </div>
      </section>

      <IdpoCard>
        <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
          <div className="w-full sm:w-auto">
            <label
              htmlFor="benchmark-run"
              className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400"
            >
              Benchmark run
            </label>
            <select
              id="benchmark-run"
              value={selectedRunId}
              disabled={runs.length === 0}
              onChange={(event) => setSelectedRunId(event.target.value)}
              className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 disabled:opacity-60 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 sm:w-[380px]"
            >
              {runsLoading && runs.length === 0 ? <option value="">Loading runs...</option> : null}
              {runGroups.map((group) => (
                <optgroup key={group.key} label={group.label}>
                  {group.runs.map((run) => (
                    <option key={run.benchmarkRunId} value={run.benchmarkRunId}>
                      {runLabel(run)}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          {selectedRun ? (
            <div className="min-w-0 flex-1 text-sm text-slate-600 dark:text-slate-300">
              <p>{runDescription(selectedRun)}</p>
              <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                <span className="font-mono">{selectedRun.benchmarkRunId}</span>
                {" · "}
                <a
                  href={`/api/benchmarks/${encodeURIComponent(selectedRun.benchmarkRunId)}`}
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-cyan-700 hover:underline dark:text-cyan-300"
                >
                  Raw report (JSON)
                </a>
              </p>
            </div>
          ) : null}
          {evidenceLoading && view ? (
            <p className="text-xs text-slate-500 dark:text-slate-400" role="status">
              Loading run...
            </p>
          ) : null}
        </div>
        {!runsLoading && runs.length === 0 && !error ? (
          <div className="mt-4 rounded-xl border border-dashed border-slate-300 px-4 py-5 text-sm text-slate-600 dark:border-slate-700 dark:text-slate-300">
            <p>No benchmark reports yet. Run a benchmark from the repository root to create one:</p>
            <p className="mt-2 font-mono text-xs text-slate-500 dark:text-slate-400">
              .venv\Scripts\python scripts\run_idpo_benchmark.py --pack datasets\probe_3.json --config
              configs\idpo_research_config.json
            </p>
          </div>
        ) : null}
      </IdpoCard>

      {error ? (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300"
        >
          <span>{error}</span>
          <button
            type="button"
            onClick={() => setReloadKey((key) => key + 1)}
            className="rounded-lg border border-rose-300 px-3 py-1 text-xs font-medium hover:bg-rose-100 dark:border-rose-700 dark:hover:bg-rose-900/40"
          >
            Try again
          </button>
        </div>
      ) : null}

      {!view && (runsLoading || evidenceLoading) ? (
        <div className="space-y-4" aria-hidden="true">
          <SkeletonBlock className="h-56" />
          <SkeletonBlock className="h-48" />
          <SkeletonBlock className="h-72" />
        </div>
      ) : null}

      {view && f1Pair && latencyPair && validationPair ? (
        <div className={`space-y-6 transition-opacity ${evidenceLoading ? "opacity-60" : ""}`}>
          <IdpoCard>
            <h2 className="text-base font-semibold text-slate-900 dark:text-white">What this run shows</h2>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              Paired differences over {view.docCount} documents with 95% bootstrap intervals. An interval that includes
              zero means this run cannot tell the two conditions apart.
            </p>
            <div className="mt-4 grid gap-3 lg:grid-cols-3">
              <OutcomeCard
                title="Accuracy (document F1)"
                value={view.f1 ? signed(view.f1.mean, 3) : "—"}
                verdict={verdictFor(view.f1, true, "Adaptive more accurate", "Adaptive less accurate")}
                interval={view.f1 ? `${signed(view.f1.low, 3)} to ${signed(view.f1.high, 3)}` : null}
                lines={
                  f1Pair.static === null && f1Pair.adaptive === null
                    ? ["This pack has no exact labels."]
                    : [
                        `Micro F1: ${formatMetric(f1Pair.static, "score")} static, ${formatMetric(f1Pair.adaptive, "score")} adaptive`,
                        `${String(view.comparison.exact_win_count ?? 0)} documents better, ${String(view.comparison.exact_loss_count ?? 0)} worse, ${String(view.comparison.exact_match_count ?? 0)} tied`,
                      ]
                }
              />
              <OutcomeCard
                title="Time per document"
                value={view.latency ? signed(view.latency.mean / 1000, 2, " s") : "—"}
                verdict={verdictFor(view.latency, false, "Adaptive faster", "Adaptive slower")}
                interval={
                  view.latency ? `${signed(view.latency.low / 1000, 2)} to ${signed(view.latency.high / 1000, 2)} s` : null
                }
                lines={[
                  `Average: ${formatMetric(latencyPair.static, "seconds")} static, ${formatMetric(latencyPair.adaptive, "seconds")} adaptive`,
                ]}
              />
              <OutcomeCard
                title="Validation pass rate"
                value={view.validation ? signed(view.validation.mean * 100, 0, " pts") : "—"}
                verdict={verdictFor(view.validation, true, "Adaptive passes more often", "Adaptive passes less often")}
                interval={
                  view.validation
                    ? `${signed(view.validation.low * 100, 0)} to ${signed(view.validation.high * 100, 0)} pts`
                    : null
                }
                lines={[
                  `Passed: ${formatMetric(validationPair.static, "rate")} static, ${formatMetric(validationPair.adaptive, "rate")} adaptive`,
                  "A pass means validation raised no issue.",
                ]}
              />
            </div>
            <p className="mt-4 text-xs text-slate-500 dark:text-slate-400">
              Figures come from the report saved with this run. The paper recomputed every run with the final scorer and
              10,000 bootstrap resamples (<span className="font-mono">paper/FINAL_EVIDENCE.md</span>), so some intervals
              and scores differ slightly.
            </p>
          </IdpoCard>

          <IdpoCard>
            <h2 className="text-base font-semibold text-slate-900 dark:text-white">How adaptive routing behaved</h2>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              Which policies each condition used, and what the safety gate did in the adaptive condition.
            </p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <Tile
                label="Policy changed by advice"
                value={`${String(view.comparison.policy_changed_count ?? 0)} of ${view.docCount}`}
              />
              <Tile
                label="Advice accepted"
                value={`${String(view.comparison.advice_accepted_count ?? 0)} of ${view.docCount}`}
              />
              <Tile
                label="Rollbacks"
                value={String(view.adaptiveCondition.rollback_count ?? 0)}
                hint="Policies the safety gate withdrew after they regressed."
              />
              <Tile
                label="Deferred to review"
                value={String(view.adaptiveCondition.defer_requested_count ?? 0)}
                hint="Documents the gate flagged for human review."
              />
            </div>
            <div className="mt-5 grid gap-6 md:grid-cols-2">
              <PolicyBars title="Static" distribution={view.staticCondition.policy_distribution} total={view.docCount} />
              <PolicyBars
                title="Adaptive"
                distribution={view.adaptiveCondition.policy_distribution}
                total={view.docCount}
              />
            </div>
            <p className="mt-4 text-xs text-slate-500 dark:text-slate-400">
              Advice source: {formatCounts(view.adaptiveCondition.advice_source_counts)}. Retrieval:{" "}
              {formatCounts(view.adaptiveCondition.retrieval_source_counts)}.
            </p>
          </IdpoCard>

          <div className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
            <IdpoCard>
              <h2 className="text-base font-semibold text-slate-900 dark:text-white">All metrics</h2>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[480px] text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                      <th className="px-2 py-2 font-medium">Metric</th>
                      <th className="px-2 py-2 text-right font-medium">Static</th>
                      <th className="px-2 py-2 text-right font-medium">Adaptive</th>
                      <th className="px-2 py-2 text-right font-medium">Difference</th>
                    </tr>
                  </thead>
                  <tbody>
                    {METRICS.map((metric) => {
                      const pair = metricPair(view.table, metric.key, view.adaptiveKey);
                      if (pair.static === null && pair.adaptive === null) {
                        return null;
                      }
                      return (
                        <tr key={metric.key} className="border-b border-slate-100 last:border-0 dark:border-slate-800">
                          <td className="px-2 py-2 text-slate-700 dark:text-slate-200">
                            {metric.label}
                            {metric.hint ? (
                              <span className="block text-xs text-slate-500 dark:text-slate-400">{metric.hint}</span>
                            ) : null}
                          </td>
                          <td className="px-2 py-2 text-right tabular-nums text-slate-600 dark:text-slate-300">
                            {formatMetric(pair.static, metric.kind)}
                          </td>
                          <td className="px-2 py-2 text-right tabular-nums text-slate-600 dark:text-slate-300">
                            {formatMetric(pair.adaptive, metric.kind)}
                          </td>
                          <td className="px-2 py-2 text-right tabular-nums text-slate-900 dark:text-white">
                            {formatMetricDelta(pair.static, pair.adaptive, metric.kind)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </IdpoCard>

            <IdpoCard>
              <h2 className="text-base font-semibold text-slate-900 dark:text-white">Run checks</h2>
              <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                Sanity checks recorded by the benchmark script. They confirm the run was real; they do not test whether
                adaptive is better.
              </p>
              <ul className="mt-3 space-y-3">
                {view.checks.map((check) => {
                  const passed = check.passed;
                  return (
                    <li key={check.key} className="flex gap-3">
                      <span
                        className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${
                          passed
                            ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300"
                            : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"
                        }`}
                      >
                        <Icon name={passed ? "check" : "minus"} className="h-3.5 w-3.5" />
                      </span>
                      <div className="min-w-0">
                        <p className="text-sm text-slate-900 dark:text-white">
                          {CHECK_LABELS[check.key] ?? check.key.replace(/_/g, " ")}
                          <span className="sr-only">{passed ? ": yes" : ": no"}</span>
                        </p>
                        <p className="mt-0.5 text-xs text-slate-500 [overflow-wrap:anywhere] dark:text-slate-400">
                          {formatCheckDetail(check.detail)}
                        </p>
                      </div>
                    </li>
                  );
                })}
                {view.checks.length === 0 ? (
                  <li className="text-sm text-slate-500 dark:text-slate-400">This report has no run checks.</li>
                ) : null}
              </ul>
            </IdpoCard>
          </div>

          {view.groups.length > 0 ? (
            <IdpoCard>
              <h2 className="text-base font-semibold text-slate-900 dark:text-white">By document tag</h2>
              {view.groupsMatchOverall ? (
                <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                  Every document in this pack carries all of these tags (
                  {view.groups.map((group) => group.tag.replace(/_/g, " ")).join(", ")}), so each tag gives the overall
                  result shown above.
                </p>
              ) : (
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full min-w-[720px] text-sm">
                    <thead>
                      <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                        <th className="px-2 py-2 font-medium">Tag</th>
                        <th className="px-2 py-2 text-right font-medium">Documents</th>
                        <th className="px-2 py-2 text-right font-medium">Micro F1, static</th>
                        <th className="px-2 py-2 text-right font-medium">Micro F1, adaptive</th>
                        <th className="px-2 py-2 text-right font-medium">Document F1 difference</th>
                        <th className="px-2 py-2 text-right font-medium">Time difference</th>
                      </tr>
                    </thead>
                    <tbody>
                      {view.groups.map((group) => (
                        <tr key={group.tag} className="border-b border-slate-100 last:border-0 dark:border-slate-800">
                          <td className="px-2 py-2 text-slate-900 dark:text-white">{group.tag.replace(/_/g, " ")}</td>
                          <td className="px-2 py-2 text-right tabular-nums text-slate-600 dark:text-slate-300">
                            {group.docCount}
                          </td>
                          <td className="px-2 py-2 text-right tabular-nums text-slate-600 dark:text-slate-300">
                            {formatMetric(group.f1.static, "score")}
                          </td>
                          <td className="px-2 py-2 text-right tabular-nums text-slate-600 dark:text-slate-300">
                            {formatMetric(group.f1.adaptive, "score")}
                          </td>
                          <td className="px-2 py-2 text-right tabular-nums text-slate-600 dark:text-slate-300">
                            {group.f1Interval
                              ? `${signed(group.f1Interval.mean, 3)} [${signed(group.f1Interval.low, 3)}, ${signed(group.f1Interval.high, 3)}]`
                              : "—"}
                          </td>
                          <td className="px-2 py-2 text-right tabular-nums text-slate-600 dark:text-slate-300">
                            {group.latencyInterval
                              ? `${signed(group.latencyInterval.mean / 1000, 2)} s [${signed(group.latencyInterval.low / 1000, 2)}, ${signed(group.latencyInterval.high / 1000, 2)}]`
                              : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </IdpoCard>
          ) : null}

          <IdpoCard>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold text-slate-900 dark:text-white">Documents</h2>
                <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                  One row per document. Open either condition to see its extracted fields and trace.
                </p>
              </div>
              <div
                className="inline-flex rounded-lg border border-slate-300 p-0.5 text-sm dark:border-slate-700"
                role="group"
                aria-label="Filter documents"
              >
                {[
                  { value: false, label: `All (${view.documents.length})` },
                  { value: true, label: `F1 differs (${differentCount})` },
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
              <table className="w-full min-w-[960px] text-sm">
                <thead>
                  <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                    <th className="px-2 py-2 font-medium">Document</th>
                    <th className="px-2 py-2 font-medium">Policy (static → adaptive)</th>
                    <th className="px-2 py-2 font-medium">AHMN recommended</th>
                    <th className="px-2 py-2 font-medium">Advice</th>
                    <th className="px-2 py-2 font-medium">Safety gate</th>
                    <th className="px-2 py-2 text-right font-medium">F1 static</th>
                    <th className="px-2 py-2 text-right font-medium">F1 adaptive</th>
                    <th className="px-2 py-2 text-right font-medium">Time difference</th>
                    <th className="px-2 py-2 font-medium">Open</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleDocuments.map((doc) => {
                    const policyChanged = doc.adaptivePolicy !== doc.staticPolicy;
                    const f1Tone =
                      doc.f1Different && doc.staticF1 !== null && doc.adaptiveF1 !== null
                        ? doc.adaptiveF1 > doc.staticF1
                          ? "text-emerald-700 dark:text-emerald-300"
                          : "text-amber-700 dark:text-amber-300"
                        : "text-slate-600 dark:text-slate-300";
                    return (
                      <tr key={doc.caseId} className="border-b border-slate-100 last:border-0 dark:border-slate-800">
                        <td className="px-2 py-2">
                          <p className="font-mono text-xs text-slate-900 dark:text-slate-100">{doc.caseId}</p>
                          {doc.tags.length > 0 ? (
                            <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                              {doc.tags.map((tag) => tag.replace(/_/g, " ")).join(", ")}
                            </p>
                          ) : null}
                        </td>
                        <td className="px-2 py-2 font-mono text-xs text-slate-600 dark:text-slate-300">
                          {doc.staticPolicy}
                          <span className="px-1 text-slate-400">→</span>
                          <span className={policyChanged ? "font-semibold text-slate-900 dark:text-white" : undefined}>
                            {doc.adaptivePolicy}
                          </span>
                        </td>
                        <td className="px-2 py-2 font-mono text-xs text-slate-600 dark:text-slate-300">{doc.recommended}</td>
                        <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{doc.advice}</td>
                        <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{doc.gate}</td>
                        <td className="px-2 py-2 text-right tabular-nums text-slate-600 dark:text-slate-300">
                          {formatMetric(doc.staticF1, "score")}
                        </td>
                        <td className={`px-2 py-2 text-right tabular-nums ${f1Tone}`}>{formatMetric(doc.adaptiveF1, "score")}</td>
                        <td className="px-2 py-2 text-right tabular-nums text-slate-600 dark:text-slate-300">
                          {doc.latencyDelta === null ? "—" : signed(doc.latencyDelta / 1000, 1, " s")}
                        </td>
                        <td className="whitespace-nowrap px-2 py-2 text-xs">
                          {doc.staticHref ? (
                            <Link href={doc.staticHref} className="font-medium text-cyan-700 hover:underline dark:text-cyan-300">
                              Static
                            </Link>
                          ) : null}
                          {doc.staticHref && doc.adaptiveHref ? <span className="px-1.5 text-slate-300 dark:text-slate-600">|</span> : null}
                          {doc.adaptiveHref ? (
                            <Link href={doc.adaptiveHref} className="font-medium text-cyan-700 hover:underline dark:text-cyan-300">
                              Adaptive
                            </Link>
                          ) : null}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {visibleDocuments.length === 0 ? (
                <p className="px-2 py-4 text-sm text-slate-500 dark:text-slate-400">
                  {onlyDifferent ? "Both conditions scored the same F1 on every document." : "This report lists no documents."}
                </p>
              ) : null}
            </div>
          </IdpoCard>
        </div>
      ) : null}
    </div>
  );
}
