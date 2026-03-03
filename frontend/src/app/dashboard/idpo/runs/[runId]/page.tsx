"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { idpoApi } from "@/lib/idpo-api";
import { IdpoCard } from "@/components/idpo/card";
import { StatusBadge } from "@/components/idpo/status-badge";
import { JsonViewer } from "@/components/idpo/json-viewer";
import type {
  DocumentSummary,
  JobStatus,
  ProvenanceEvent,
  RunFileInfo,
  RunOverview,
  ShadowComparison,
} from "@/types/idpo";

const tabs = [
  "Overview",
  "Documents",
  "Extraction",
  "Validation & Guardrails",
  "Recovery & Escalation",
  "Provenance",
  "Shadow Mode",
  "Retrieval/Answering",
] as const;

type TabName = (typeof tabs)[number];

function formatNumber(value: number | null | undefined, digits = 2) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return value.toFixed(digits);
}

export default function RunDetailPage() {
  const params = useParams<{ runId: string }>();
  const runId = decodeURIComponent(params.runId);

  const [activeTab, setActiveTab] = useState<TabName>("Overview");
  const [overview, setOverview] = useState<RunOverview | null>(null);
  const [docs, setDocs] = useState<DocumentSummary[]>([]);
  const [files, setFiles] = useState<RunFileInfo[]>([]);
  const [provenance, setProvenance] = useState<{ events: ProvenanceEvent[]; stageCounts: Record<string, number>; files: Record<string, string | null> } | null>(null);
  const [metrics, setMetrics] = useState<Record<string, unknown>>({});
  const [shadow, setShadow] = useState<{ enabled: boolean; comparisons: ShadowComparison[]; policySummaries: Record<string, unknown>[] } | null>(null);
  const [selectedDocId, setSelectedDocId] = useState<string>("");
  const [selectedDoc, setSelectedDoc] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [rerunJob, setRerunJob] = useState<JobStatus | null>(null);

  const load = async () => {
    setLoading(true);
    const [runOverview, runDocs, runFiles, runProv, runMetrics, runShadow] = await Promise.all([
      idpoApi.runOverview(runId),
      idpoApi.runDocs(runId),
      idpoApi.runFiles(runId),
      idpoApi.runProvenance(runId),
      idpoApi.runMetrics(runId),
      idpoApi.runShadow(runId),
    ]);

    setOverview(runOverview);
    setDocs(runDocs.docs);
    setFiles(runFiles.files);
    setProvenance(runProv);
    setMetrics(runMetrics);
    setShadow(runShadow);

    const initialDocId = runDocs.docs[0]?.docId ?? "";
    setSelectedDocId((prev) => prev || initialDocId);
    setLoading(false);
  };

  useEffect(() => {
    load().catch((err) => {
      setError(err instanceof Error ? err.message : "Failed to load run details");
      setLoading(false);
    });
  }, [runId]);

  useEffect(() => {
    if (!selectedDocId) {
      setSelectedDoc(null);
      return;
    }

    idpoApi
      .runDoc(runId, selectedDocId)
      .then((doc) => setSelectedDoc(doc))
      .catch(() => setSelectedDoc(null));
  }, [runId, selectedDocId]);

  const extractionFields = useMemo(() => {
    const fields = selectedDoc?.fields;
    return Array.isArray(fields) ? fields : [];
  }, [selectedDoc]);

  const validationIssues = useMemo(() => {
    const issues = selectedDoc?.validationIssues;
    return Array.isArray(issues) ? issues : [];
  }, [selectedDoc]);

  const recoveryAttempts = useMemo(() => {
    const attempts = selectedDoc?.recoveryAttempts;
    return Array.isArray(attempts) ? attempts : [];
  }, [selectedDoc]);

  const guardrailFindings = useMemo(() => {
    const findings = selectedDoc?.guardrailFindings;
    return Array.isArray(findings) ? findings : [];
  }, [selectedDoc]);

  const runMetrics = (metrics.metrics as Record<string, number>) ?? {};

  const retrievalFiles = files.filter((file) => file.path.startsWith("retrieve/") || file.path.startsWith("answer/") || file.path.startsWith("index/"));

  const downloadPath = async (relativePath: string) => {
    const response = await idpoApi.runFile(runId, relativePath);
    const text = response.type === "json" ? JSON.stringify(response.content, null, 2) : String(response.content ?? "");
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = relativePath.split("/").pop() ?? "artifact.txt";
    link.click();
    URL.revokeObjectURL(url);
  };

  const rerunPolicy = async (policyId: string) => {
    try {
      setError("");
      const job = await idpoApi.rerunWithPolicy(runId, policyId);
      setRerunJob(job);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to trigger rerun");
    }
  };

  if (loading) {
    return <div className="text-sm text-slate-600 dark:text-slate-300">Loading run details...</div>;
  }

  if (error && !overview) {
    return (
      <div className="rounded-xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300">
        {error}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-gradient-to-r from-slate-50 via-white to-cyan-50 p-6 dark:border-slate-800 dark:from-slate-900 dark:via-slate-900 dark:to-slate-900">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <Link href="/dashboard/idpo" className="text-xs text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white">
              Back to IDPO dashboard
            </Link>
            <h1 className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">Run {runId}</h1>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              Canonical and shadow artifacts with provenance, recovery, escalation, and policy safety metrics.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge value={overview?.run.status ?? "unknown"} />
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700 dark:bg-slate-800 dark:text-slate-200">
              {overview?.run.docCount ?? 0} docs
            </span>
          </div>
        </div>
      </section>

      {error ? (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300">
          {error}
        </div>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {tabs.map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setActiveTab(tab)}
            className={`rounded-lg px-3 py-1.5 text-sm ${
              activeTab === tab
                ? "bg-slate-900 text-white dark:bg-brand-600"
                : "border border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {activeTab === "Overview" ? (
        <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
          <IdpoCard>
            <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Docs</p>
            <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{overview?.documents.length ?? 0}</p>
          </IdpoCard>
          <IdpoCard>
            <p className="text-xs uppercase text-slate-500 dark:text-slate-400">P95 Latency</p>
            <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{formatNumber(overview?.p95LatencyMs)} ms</p>
          </IdpoCard>
          <IdpoCard>
            <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Estimated Cost</p>
            <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{formatNumber(overview?.estimatedCost)}</p>
          </IdpoCard>
          <IdpoCard>
            <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Validation Pass</p>
            <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">
              {overview?.validationPassRate !== null && overview?.validationPassRate !== undefined
                ? `${(overview.validationPassRate * 100).toFixed(1)}%`
                : "-"}
            </p>
          </IdpoCard>
          <IdpoCard>
            <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Escalations</p>
            <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{overview?.escalationsCount ?? 0}</p>
          </IdpoCard>
          <IdpoCard>
            <p className="text-xs uppercase text-slate-500 dark:text-slate-400">Retries</p>
            <p className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{overview?.retriesCount ?? 0}</p>
          </IdpoCard>

          <IdpoCard className="md:col-span-3 xl:col-span-6">
            <h3 className="text-base font-semibold text-slate-900 dark:text-white">Metrics Snapshot</h3>
            <div className="mt-3 grid gap-2 md:grid-cols-3 lg:grid-cols-4">
              {Object.entries(runMetrics).map(([key, value]) => (
                <div key={key} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-700 dark:bg-slate-800/60">
                  <p className="text-[11px] uppercase tracking-wide text-slate-500 dark:text-slate-400">{key}</p>
                  <p className="mt-1 text-sm font-medium text-slate-900 dark:text-white">{typeof value === "number" ? value.toFixed(3) : String(value)}</p>
                </div>
              ))}
              {Object.keys(runMetrics).length === 0 ? (
                <p className="text-sm text-slate-500 dark:text-slate-400">No metrics artifact found.</p>
              ) : null}
            </div>
          </IdpoCard>
        </div>
      ) : null}

      {activeTab === "Documents" ? (
        <IdpoCard>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                  <th className="px-2 py-2">Doc ID</th>
                  <th className="px-2 py-2">Type</th>
                  <th className="px-2 py-2">Vendor</th>
                  <th className="px-2 py-2">Complexity</th>
                  <th className="px-2 py-2">Route</th>
                  <th className="px-2 py-2">Latency</th>
                  <th className="px-2 py-2">Validation</th>
                  <th className="px-2 py-2">Escalated</th>
                  <th className="px-2 py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {docs.map((doc) => (
                  <tr key={doc.docId} className="border-b border-slate-100 dark:border-slate-800">
                    <td className="px-2 py-2 font-medium text-slate-900 dark:text-slate-100">{doc.docId}</td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{doc.docType ?? "-"}</td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{doc.vendorCluster ?? "-"}</td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{doc.complexityBin ?? "-"}</td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{doc.routeBin ?? "-"}</td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{formatNumber(doc.latencyMs)} ms</td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{doc.validationIssueCount}</td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{doc.escalated ? "yes" : "no"}</td>
                    <td className="px-2 py-2">
                      <Link
                        href={`/dashboard/idpo/runs/${runId}/docs/${doc.docId}`}
                        className="rounded-lg border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
                      >
                        Open Doc
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </IdpoCard>
      ) : null}

      {activeTab === "Extraction" ? (
        <IdpoCard>
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <label className="text-sm text-slate-700 dark:text-slate-200">Select Document</label>
            <select
              value={selectedDocId}
              onChange={(event) => setSelectedDocId(event.target.value)}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
            >
              {docs.map((doc) => (
                <option key={doc.docId} value={doc.docId}>
                  {doc.docId}
                </option>
              ))}
            </select>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full min-w-[860px] text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                  <th className="px-2 py-2">Field</th>
                  <th className="px-2 py-2">Value</th>
                  <th className="px-2 py-2">Confidence</th>
                  <th className="px-2 py-2">Type</th>
                  <th className="px-2 py-2">Method</th>
                  <th className="px-2 py-2">Evidence</th>
                </tr>
              </thead>
              <tbody>
                {extractionFields.map((field) => {
                  const item = field as Record<string, unknown>;
                  const evidence = item.evidence as Record<string, unknown> | undefined;
                  return (
                    <tr key={`${String(item.key)}_${String(item.value)}`} className="border-b border-slate-100 dark:border-slate-800">
                      <td className="px-2 py-2 font-medium text-slate-900 dark:text-slate-100">{String(item.key)}</td>
                      <td className="px-2 py-2 text-slate-700 dark:text-slate-200">{String(item.value ?? "")}</td>
                      <td className="px-2 py-2 text-slate-700 dark:text-slate-200">{formatNumber(Number(item.confidence ?? 0), 3)}</td>
                      <td className="px-2 py-2">
                        <StatusBadge value={String(item.confidence_type ?? "unknown")} />
                      </td>
                      <td className="px-2 py-2 text-slate-700 dark:text-slate-200">{String(item.extraction_method ?? "unknown")}</td>
                      <td className="px-2 py-2 text-xs text-slate-600 dark:text-slate-300">
                        {evidence?.span ? JSON.stringify(evidence.span) : "-"} {evidence?.page ? `(p${String(evidence.page)})` : ""}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {extractionFields.length === 0 ? (
              <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">No extraction fields found for this document.</p>
            ) : null}
          </div>

          <div className="mt-4">
            <JsonViewer title="Raw Document Payload" value={selectedDoc ?? {}} />
          </div>
        </IdpoCard>
      ) : null}

      {activeTab === "Validation & Guardrails" ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <IdpoCard>
            <h3 className="text-base font-semibold text-slate-900 dark:text-white">Validation Errors</h3>
            <div className="mt-3 space-y-2">
              {validationIssues.map((issue, idx) => {
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
              {validationIssues.length === 0 ? <p className="text-sm text-slate-500 dark:text-slate-400">No validation errors.</p> : null}
            </div>
          </IdpoCard>

          <IdpoCard>
            <h3 className="text-base font-semibold text-slate-900 dark:text-white">Guardrail Findings</h3>
            <div className="mt-3 space-y-2">
              {guardrailFindings.map((finding, idx) => {
                const item = finding as Record<string, unknown>;
                return (
                  <div key={`${String(item.rule)}_${idx}`} className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-medium text-slate-900 dark:text-white">{String(item.rule)}</p>
                      <StatusBadge value={String(item.result ?? "unknown")} />
                    </div>
                    <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">{String(item.message ?? "")}</p>
                  </div>
                );
              })}
              {guardrailFindings.length === 0 ? <p className="text-sm text-slate-500 dark:text-slate-400">No guardrail artifact found.</p> : null}
            </div>
          </IdpoCard>
        </div>
      ) : null}

      {activeTab === "Recovery & Escalation" ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <IdpoCard>
            <h3 className="text-base font-semibold text-slate-900 dark:text-white">Field-Level Recovery Attempts</h3>
            <div className="mt-3 space-y-2">
              {recoveryAttempts.map((attempt, idx) => {
                const item = attempt as Record<string, unknown>;
                return (
                  <div key={`${String(item.field)}_${idx}`} className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-medium text-slate-900 dark:text-white">{String(item.field)}</p>
                      <StatusBadge value={Boolean(item.success) ? "ready" : "failed"} />
                    </div>
                    <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
                      attempt {String(item.attempt ?? "1")} via {String(item.strategy ?? "unknown")}
                    </p>
                  </div>
                );
              })}
              {recoveryAttempts.length === 0 ? <p className="text-sm text-slate-500 dark:text-slate-400">No recovery attempts found.</p> : null}
            </div>
          </IdpoCard>

          <IdpoCard>
            <h3 className="text-base font-semibold text-slate-900 dark:text-white">Escalation</h3>
            <div className="mt-3 rounded-xl border border-slate-200 p-4 dark:border-slate-700">
              <p className="text-sm text-slate-700 dark:text-slate-200">
                Escalated: <strong>{String((selectedDoc?.escalation as Record<string, unknown> | undefined)?.escalated ? "yes" : "no")}</strong>
              </p>
              <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
                Reason: {String((selectedDoc?.escalation as Record<string, unknown> | undefined)?.reason ?? "-")}
              </p>
              <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
                Target: {String((selectedDoc?.escalation as Record<string, unknown> | undefined)?.targetModel ?? "-")}
              </p>
              <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
                Cost Est.: {formatNumber(Number((selectedDoc?.escalation as Record<string, unknown> | undefined)?.costEstimate ?? 0), 3)}
              </p>
              <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
                Latency Est.: {formatNumber(Number((selectedDoc?.escalation as Record<string, unknown> | undefined)?.latencyEstimateMs ?? 0), 1)} ms
              </p>
            </div>
          </IdpoCard>
        </div>
      ) : null}

      {activeTab === "Provenance" ? (
        <IdpoCard>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-base font-semibold text-slate-900 dark:text-white">Provenance Timeline</h3>
            <div className="flex gap-2">
              {provenance?.files.events ? (
                <button
                  type="button"
                  onClick={() => downloadPath(provenance.files.events as string)}
                  className="rounded-lg border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  Export events.jsonl
                </button>
              ) : null}
              {provenance?.files.graph ? (
                <button
                  type="button"
                  onClick={() => downloadPath(provenance.files.graph as string)}
                  className="rounded-lg border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
                >
                  Export graph.json
                </button>
              ) : null}
            </div>
          </div>

          <div className="mb-4 flex flex-wrap gap-2">
            {Object.entries(provenance?.stageCounts ?? {}).map(([stage, count]) => (
              <span
                key={stage}
                className="rounded-full border border-slate-300 px-2 py-1 text-xs text-slate-700 dark:border-slate-600 dark:text-slate-200"
              >
                {stage}: {count}
              </span>
            ))}
          </div>

          <div className="max-h-[460px] overflow-auto rounded-xl border border-slate-200 dark:border-slate-700">
            <table className="w-full min-w-[920px] text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400">
                  <th className="px-2 py-2">Time</th>
                  <th className="px-2 py-2">Stage</th>
                  <th className="px-2 py-2">Event</th>
                  <th className="px-2 py-2">Agent</th>
                  <th className="px-2 py-2">Doc</th>
                  <th className="px-2 py-2">Latency</th>
                  <th className="px-2 py-2">Cost</th>
                </tr>
              </thead>
              <tbody>
                {(provenance?.events ?? []).map((event) => (
                  <tr key={event.eventId} className="border-b border-slate-100 dark:border-slate-800">
                    <td className="px-2 py-2 text-xs text-slate-600 dark:text-slate-300">{new Date(event.timestamp * 1000).toLocaleTimeString()}</td>
                    <td className="px-2 py-2">
                      <StatusBadge value={event.stage} />
                    </td>
                    <td className="px-2 py-2 text-slate-700 dark:text-slate-200">{event.eventType}</td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{event.agent}</td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{event.docId ?? "-"}</td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{formatNumber(event.latencyMs)} ms</td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{formatNumber(event.costUnits, 3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </IdpoCard>
      ) : null}

      {activeTab === "Shadow Mode" ? (
        <IdpoCard>
          <div className="mb-4 flex items-center justify-between gap-2">
            <h3 className="text-base font-semibold text-slate-900 dark:text-white">Canonical vs Shadow Comparison</h3>
            <StatusBadge value={shadow?.enabled ? "ready" : "unknown"} />
          </div>

          <div className="mb-4 grid gap-3 md:grid-cols-3">
            {(shadow?.policySummaries ?? []).map((summary) => {
              const item = summary as Record<string, unknown>;
              return (
                <div key={String(item.policyId)} className="rounded-xl border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800/50">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-slate-900 dark:text-white">{String(item.policyId)}</p>
                    <button
                      type="button"
                      onClick={() => rerunPolicy(String(item.policyId))}
                      className="rounded-md border border-slate-300 px-2 py-1 text-[11px] text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
                    >
                      Rerun with policy
                    </button>
                  </div>
                  <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">Docs compared: {String(item.docsCompared ?? 0)}</p>
                  <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">Avg latency delta: {formatNumber(Number(item.avgLatencyDeltaMs ?? 0))} ms</p>
                  <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">Avg quality delta: {formatNumber(Number(item.avgQualityDelta ?? 0), 4)}</p>
                </div>
              );
            })}
            {(shadow?.policySummaries ?? []).length === 0 ? (
              <p className="text-sm text-slate-500 dark:text-slate-400">No shadow comparisons found.</p>
            ) : null}
          </div>

          {rerunJob ? (
            <div className="mb-4 rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-700">
              Rerun job {rerunJob.jobId.slice(0, 10)} started. Track in dashboard jobs panel.
            </div>
          ) : null}

          <div className="overflow-x-auto">
            <table className="w-full min-w-[980px] text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                  <th className="px-2 py-2">Doc</th>
                  <th className="px-2 py-2">Policy</th>
                  <th className="px-2 py-2">Canonical Latency</th>
                  <th className="px-2 py-2">Shadow Latency</th>
                  <th className="px-2 py-2">Quality Delta</th>
                  <th className="px-2 py-2">Retrieval Delta</th>
                </tr>
              </thead>
              <tbody>
                {(shadow?.comparisons ?? []).map((row, idx) => (
                  <tr key={`${row.docId}_${row.policyId}_${idx}`} className="border-b border-slate-100 dark:border-slate-800">
                    <td className="px-2 py-2 text-slate-700 dark:text-slate-200">{row.docId}</td>
                    <td className="px-2 py-2 text-slate-700 dark:text-slate-200">{row.policyId}</td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{formatNumber(row.canonicalLatencyMs)} ms</td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">{formatNumber(row.shadowLatencyMs)} ms</td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">
                      {formatNumber(
                        row.shadowQualityProxy !== null && row.canonicalQualityProxy !== null
                          ? row.shadowQualityProxy - row.canonicalQualityProxy
                          : null,
                        4,
                      )}
                    </td>
                    <td className="px-2 py-2 text-slate-600 dark:text-slate-300">
                      {formatNumber(
                        row.shadowRetrievalProxy !== null && row.canonicalRetrievalProxy !== null
                          ? row.shadowRetrievalProxy - row.canonicalRetrievalProxy
                          : null,
                        4,
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </IdpoCard>
      ) : null}

      {activeTab === "Retrieval/Answering" ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <IdpoCard>
            <h3 className="text-base font-semibold text-slate-900 dark:text-white">Retrieval & Answer Artifacts</h3>
            <div className="mt-3 max-h-[420px] space-y-2 overflow-auto">
              {retrievalFiles.map((file) => (
                <div key={file.path} className="flex items-center justify-between gap-2 rounded-lg border border-slate-200 px-3 py-2 dark:border-slate-700">
                  <div>
                    <p className="text-xs font-medium text-slate-800 dark:text-slate-200">{file.path}</p>
                    <p className="text-[11px] text-slate-500 dark:text-slate-400">{(file.size / 1024).toFixed(1)} KB</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => downloadPath(file.path)}
                    className="rounded-md border border-slate-300 px-2 py-1 text-xs text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800"
                  >
                    Open
                  </button>
                </div>
              ))}
              {retrievalFiles.length === 0 ? (
                <p className="text-sm text-slate-500 dark:text-slate-400">No retrieval or answer artifacts found in this run.</p>
              ) : null}
            </div>
          </IdpoCard>

          <IdpoCard>
            <JsonViewer title="Metrics + Queue + Policy Safety" value={metrics} />
          </IdpoCard>
        </div>
      ) : null}
    </div>
  );
}
