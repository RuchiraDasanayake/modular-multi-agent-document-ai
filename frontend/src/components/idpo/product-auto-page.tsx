"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { IdpoCard } from "@/components/idpo/card";
import { idpoApi } from "@/lib/idpo-api";
import type { ProductAutoRun, ProductAutoSourceDocument } from "@/types/product-auto";

function statusClass(status: string): string {
  if (status === "processed" || status === "success" || status === "completed") return "text-emerald-700 dark:text-emerald-300";
  if (status === "failed" || status === "unsupported") return "text-rose-700 dark:text-rose-300";
  return "text-amber-700 dark:text-amber-300";
}

export function ProductAutoPage() {
  const { jobId: encodedJobId } = useParams<{ jobId: string }>();
  const jobId = decodeURIComponent(encodedJobId);
  const [documents, setDocuments] = useState<ProductAutoSourceDocument[]>([]);
  const [runs, setRuns] = useState<ProductAutoRun[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [available, setAvailable] = useState(false);
  const [modelConfigured, setModelConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let current = true;
    void idpoApi.listProductAutoRuns(jobId).then((data) => {
      if (!current) return;
      setDocuments(data.sourceFiles);
      setSelected(data.sourceFiles.filter((item) => item.selected).map((item) => item.fileId));
      setRuns(data.runs);
      setActiveRunId(data.runs[0]?.runId ?? null);
      setAvailable(data.available);
      setModelConfigured(data.modelConfigured);
    }).catch((cause) => {
      if (current) setError(cause instanceof Error ? cause.message : "Failed to load automatic extraction.");
    }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [jobId]);

  const running = runs.some((run) => run.status === "running");
  useEffect(() => {
    if (!running) return undefined;
    const timer = window.setInterval(() => {
      void idpoApi.listProductAutoRuns(jobId).then((data) => setRuns(data.runs)).catch((cause) => {
        setError(cause instanceof Error ? cause.message : "Failed to refresh run status.");
      });
    }, 2500);
    return () => window.clearInterval(timer);
  }, [jobId, running]);

  const activeRun = useMemo(() => runs.find((run) => run.runId === activeRunId) ?? runs[0] ?? null, [runs, activeRunId]);

  async function start() {
    if (selected.length === 0) return;
    setStarting(true);
    setError("");
    try {
      const run = await idpoApi.startProductAutoRun(jobId, selected);
      setRuns((current) => [run, ...current]);
      setActiveRunId(run.runId);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to start automatic extraction.");
    } finally {
      setStarting(false);
    }
  }

  if (loading) return <div className="p-6 text-sm text-slate-500" aria-busy="true">Loading automatic extraction…</div>;

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div>
        <Link href={`/dashboard/idpo/jobs/${encodeURIComponent(jobId)}`} className="text-sm font-medium text-cyan-700 dark:text-cyan-300">← Back to job</Link>
        <h1 className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">Automatic schema extraction</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600 dark:text-slate-300">
          Discover fields from each document, verify exact text evidence, then review proposed values. This workflow is opt in and keeps its results separate from research policy runs.
        </p>
      </div>

      {error ? <div role="alert" className="rounded-xl border border-rose-300 bg-rose-50 p-3 text-sm text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300">{error}</div> : null}

      <IdpoCard>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Run selected documents</h2>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              {modelConfigured ? "Server configured model proposals with local evidence checks." : "Local deterministic field discovery. Configure a server model for AI proposals."}
            </p>
          </div>
          <button type="button" onClick={() => void start()} disabled={!available || starting || running || selected.length === 0}
            className="rounded-xl bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-50">
            {starting ? "Starting…" : `Extract ${selected.length} selected`}
          </button>
        </div>
        {!available ? <p className="mt-3 text-sm text-amber-700 dark:text-amber-300">This deployment has no automatic extraction runner configured.</p> : null}
        {documents.length === 0 ? <p className="mt-4 text-sm text-slate-500">Upload documents on the job page first.</p> : (
          <div className="mt-4 grid gap-2 sm:grid-cols-2">
            {documents.map((document) => (
              <label key={document.fileId} className="flex min-w-0 items-center gap-2 rounded-lg border border-slate-200 p-2 text-sm dark:border-slate-700">
                <input type="checkbox" checked={selected.includes(document.fileId)} disabled={running || starting}
                  onChange={(event) => setSelected((current) => event.target.checked ? [...current, document.fileId] : current.filter((id) => id !== document.fileId))} />
                <span className="truncate text-slate-800 dark:text-slate-200" title={document.fileName}>{document.fileName}</span>
              </label>
            ))}
          </div>
        )}
      </IdpoCard>

      <IdpoCard>
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Runs</h2>
        {runs.length === 0 ? <p className="mt-3 text-sm text-slate-500">No automatic extraction runs yet.</p> : (
          <div className="mt-3 flex flex-wrap gap-2">
            {runs.map((run) => (
              <button key={run.runId} type="button" onClick={() => setActiveRunId(run.runId)}
                className={`rounded-lg border px-3 py-2 text-left text-xs dark:border-slate-700 ${activeRun?.runId === run.runId ? "border-cyan-500 bg-cyan-50 dark:bg-cyan-900/20" : "border-slate-200"}`}>
                <span className="font-mono">{run.runId.slice(0, 13)}</span>
                <span className={`ml-2 font-semibold ${statusClass(run.status)}`}>{run.status}</span>
                <span className="ml-2 text-slate-500">{run.selectedCount} files</span>
              </button>
            ))}
          </div>
        )}
        {activeRun?.status === "running" ? <p className="mt-4 text-sm text-amber-700 dark:text-amber-300">Extracting. Results will appear when the run completes.</p> : null}
        {activeRun?.status === "failed" ? <p role="alert" className="mt-4 text-sm text-rose-700 dark:text-rose-300">{activeRun.error ?? "Extraction failed."}</p> : null}
        {activeRun?.status === "success" ? (
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[600px] text-sm">
              <thead><tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-500 dark:border-slate-700"><th className="py-2 pr-3">Document</th><th className="py-2 pr-3">Status</th><th className="py-2 pr-3">Fields</th><th className="py-2 pr-3">Accepted</th><th className="py-2 pr-3">Human review</th></tr></thead>
              <tbody>{activeRun.documents.map((document) => (
                <tr key={document.docId} className="border-b border-slate-100 dark:border-slate-800">
                  <td className="py-2 pr-3"><Link className="font-medium text-cyan-700 hover:underline dark:text-cyan-300" href={`/dashboard/idpo/jobs/${encodeURIComponent(jobId)}/auto/${encodeURIComponent(activeRun.runId)}/docs/${encodeURIComponent(document.docId)}`}>{document.fileName}</Link></td>
                  <td className={`py-2 pr-3 ${statusClass(document.status)}`}>{document.status.replaceAll("_", " ")}</td>
                  <td className="py-2 pr-3">{document.fieldCount}</td>
                  <td className="py-2 pr-3">{document.acceptedCount}</td>
                  <td className={`py-2 pr-3 ${statusClass(document.reviewStatus)}`}>{document.reviewStatus}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        ) : null}
      </IdpoCard>
    </div>
  );
}
