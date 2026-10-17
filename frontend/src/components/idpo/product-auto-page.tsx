"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { IdpoCard } from "@/components/idpo/card";
import { ProductFileUpload } from "@/components/idpo/product-file-upload";
import { productAutoReviewReadiness } from "@/components/idpo/product-auto-review-readiness";
import { ProductAutoRunRefresh } from "@/components/idpo/product-auto-run-refresh";
import { api } from "@/lib/api";
import { idpoApi } from "@/lib/idpo-api";
import { clearPendingProductAutoRunRequest, pendingProductAutoRunRequest,
  reserveProductAutoRunRequest, type PendingProductAutoRunRequest,
  type ProductAutoRunPayload } from "@/lib/product-auto-run-request";
import type { ProductAutoRun, ProductAutoSourceDocument } from "@/types/product-auto";
import type { ProductAutoRecipeRevision } from "@/types/product-auto-recipes";
import type { ProductAutoBriefField, ProductAutoBriefRevision, ProductAutoBriefSuggestion } from "@/types/product-auto-brief";

const FIELD_TYPES = ["string", "integer", "decimal", "boolean", "date", "array[object]"] as const;
type BriefLoadState = { jobId: string; status: "loading" | "ready" | "error"; error?: string };

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
  const [isAdmin, setIsAdmin] = useState(false);
  const [approvedRecipes, setApprovedRecipes] = useState<ProductAutoRecipeRevision[]>([]);
  const [brief, setBrief] = useState<ProductAutoBriefRevision | null>(null);
  const [briefLoad, setBriefLoad] = useState<BriefLoadState>({ jobId, status: "loading" });
  const [briefLoadAttempt, setBriefLoadAttempt] = useState(0);
  const [briefIntent, setBriefIntent] = useState("");
  const [briefFields, setBriefFields] = useState<ProductAutoBriefField[]>([]);
  const [sampleFileIds, setSampleFileIds] = useState<string[]>([]);
  const [staleSampleFileIds, setStaleSampleFileIds] = useState<string[]>([]);
  const [briefBusy, setBriefBusy] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [suggestion, setSuggestion] = useState<ProductAutoBriefSuggestion | null>(null);
  const [selectedRecipeId, setSelectedRecipeId] = useState("");
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [downloadingRunId, setDownloadingRunId] = useState<string | null>(null);
  const [exportMessage, setExportMessage] = useState<{ runId: string; text: string } | null>(null);
  const [error, setError] = useState("");
  const [pendingRunRequest, setPendingRunRequest] = useState<PendingProductAutoRunRequest | null>(null);
  const [pendingRunChecked, setPendingRunChecked] = useState(false);
  const [reviewRefreshing, setReviewRefreshing] = useState(false);
  const [reviewRefreshError, setReviewRefreshError] = useState("");
  const runRefresh = useRef(new ProductAutoRunRefresh(setRuns, setReviewRefreshing));
  const briefReady = briefLoad.jobId === jobId && briefLoad.status === "ready";
  const briefLoading = briefLoad.jobId !== jobId || briefLoad.status === "loading";

  useEffect(() => {
    const refresh = runRefresh.current;
    refresh.invalidate();
    setReviewRefreshing(false);
    setReviewRefreshError("");
    return () => refresh.invalidate();
  }, [jobId]);

  useEffect(() => {
    setPendingRunChecked(false);
    try { setPendingRunRequest(pendingProductAutoRunRequest(window.sessionStorage, jobId)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not read the previous extraction request."); }
  }, [jobId]);

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
    void idpoApi.listProductAutoRecipes(jobId).then((data) => {
      if (current) setApprovedRecipes(data.recipes.filter((recipe) => recipe.state === "approved_shadow"));
    }).catch(() => { if (current) setApprovedRecipes([]); });
    void api.me().then((user) => {
      if (current) setIsAdmin(user.role === "admin");
    }).catch(() => { if (current) setIsAdmin(false); });
    return () => { current = false; };
  }, [jobId]);

  useEffect(() => {
    let current = true;
    setBriefLoad({ jobId, status: "loading" });
    void idpoApi.getProductAutoBrief(jobId).then((data) => {
      if (!current) return;
      setBrief(data.brief);
      setBriefIntent(data.brief?.intent ?? "");
      setBriefFields(data.brief?.fields ?? []);
      setSampleFileIds(data.brief?.sample_sources.map((source) => source.file_id) ?? []);
      setStaleSampleFileIds(data.staleSampleFileIds);
      setBriefLoad({ jobId, status: "ready" });
    }).catch((cause) => {
      if (current) setBriefLoad({ jobId, status: "error",
        error: cause instanceof Error ? cause.message : "Failed to load extraction setup." });
    });
    return () => { current = false; };
  }, [jobId, briefLoadAttempt]);

  useEffect(() => {
    if (briefReady && !brief && sampleFileIds.length === 0 && documents.length > 0) {
      setSampleFileIds([documents[0].fileId]);
    }
  }, [briefReady, brief, sampleFileIds.length, documents]);

  const running = runs.some((run) => run.status === "running" || (run.status as string) === "queued");
  const modelActionBlocked = modelConfigured && !isAdmin;
  async function refreshFiles() {
    const data = await idpoApi.listProductAutoRuns(jobId);
    setDocuments(data.sourceFiles);
    setSelected((current) => Array.from(new Set([...current,
      ...data.sourceFiles.filter((file) => file.selected && !documents.some((old) => old.fileId === file.fileId))
        .map((file) => file.fileId)])));
  }
  const refreshRunStatuses = useCallback(async () => {
    try {
      await runRefresh.current.refresh(async () => (await idpoApi.listProductAutoRuns(jobId)).runs,
        () => setReviewRefreshError(""));
    } catch (cause) {
      setReviewRefreshError(cause instanceof Error ? cause.message : "Could not refresh review status.");
    }
  }, [jobId]);

  useEffect(() => {
    const refreshWhenVisible = () => {
      if (document.visibilityState === "visible") void refreshRunStatuses();
    };
    window.addEventListener("focus", refreshWhenVisible);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      window.removeEventListener("focus", refreshWhenVisible);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, [refreshRunStatuses]);

  useEffect(() => {
    if (!running) return undefined;
    const timer = window.setInterval(() => {
      void refreshRunStatuses();
    }, 2500);
    return () => window.clearInterval(timer);
  }, [refreshRunStatuses, running]);

  const activeRun = useMemo(() => runs.find((run) => run.runId === activeRunId) ?? runs[0] ?? null, [runs, activeRunId]);
  const { reviewedCount, batchReady } = productAutoReviewReadiness(activeRun);
  const formDirty = !brief || JSON.stringify({ intent: briefIntent, fields: briefFields, samples: sampleFileIds }) !==
    JSON.stringify({ intent: brief.intent, fields: brief.fields,
      samples: brief.sample_sources.map((source) => source.file_id) });
  const confirmed = briefReady && brief?.state === "confirmed" && !formDirty && staleSampleFileIds.length === 0;
  const matchingPreviews = confirmed ? runs.filter((run) => run.confirmedBrief?.phase === "preview" &&
    run.confirmedBrief.briefId === brief.brief_id && run.confirmedBrief.revision === brief.revision &&
    run.confirmedBrief.payloadSha256 === brief.payload_sha256) : [];
  const previewRun = matchingPreviews[0];
  const reviewedPreviewRun = matchingPreviews.find((run) => productAutoReviewReadiness(run).previewReady);
  const remainingSelected = selected.filter((fileId) => !sampleFileIds.includes(fileId));
  const repeatsBatchFiles = confirmed && runs.some((run) => run.confirmedBrief?.phase === "batch" &&
    run.confirmedBrief.briefId === brief.brief_id && run.confirmedBrief.revision === brief.revision &&
    run.confirmedBrief.payloadSha256 === brief.payload_sha256 &&
    run.documents.some((document) => remainingSelected.includes(document.fileId)));

  function updateField(index: number, change: Partial<ProductAutoBriefField>) {
    setBriefFields((current) => current.map((field, fieldIndex) => fieldIndex === index
      ? { ...field, ...change } : field));
  }

  function addTableColumn() {
    setBriefFields((current) => {
      const mostRecentTableField = [...current].reverse().find((field) => field.type === "array[object]");
      return [...current, { field_id: "", type: "array[object]",
        group: mostRecentTableField?.group?.trim() || "line_items", description: "", example_values: [] }];
    });
  }

  async function saveDraft() {
    if (!briefReady) return;
    setBriefBusy(true);
    setError("");
    try {
      const fields = briefFields.map((field) => ({ ...field,
        example_values: field.example_values.map((example) => example.trim()).filter(Boolean) }));
      if (fields.some((field) => field.example_values.length > 3)) {
        throw new Error("Each field may have at most three examples. Remove extra examples before saving.");
      }
      const saved = await idpoApi.saveProductAutoBrief(jobId, brief?.revision ?? 0,
        briefIntent, fields, sampleFileIds);
      setBrief(saved.brief);
      setBriefIntent(saved.brief.intent);
      setBriefFields(saved.brief.fields);
      setSampleFileIds(saved.brief.sample_sources.map((source) => source.file_id));
      setStaleSampleFileIds([]);
      setSuggestion(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save extraction setup.");
    } finally { setBriefBusy(false); }
  }

  async function suggestFields() {
    if (!briefReady || !brief || brief.state !== "draft" || formDirty) return;
    setSuggesting(true);
    setSuggestion(null);
    setError("");
    try {
      const result = await idpoApi.suggestProductAutoBrief(jobId, brief.revision, brief.payload_sha256);
      setSuggestion(result);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not suggest fields from the sample files.");
    } finally { setSuggesting(false); }
  }

  async function confirmSchema() {
    if (!briefReady || !brief) return;
    setBriefBusy(true);
    setError("");
    try {
      const confirmedBrief = await idpoApi.confirmProductAutoBrief(jobId, brief.revision, brief.payload_sha256);
      setBrief(confirmedBrief.brief);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not confirm the schema.");
    } finally { setBriefBusy(false); }
  }

  async function startConfirmedRun(phase: "preview" | "batch") {
    if (!brief || !confirmed) return;
    const fileIds = phase === "preview" ? brief.sample_sources.map((source) => source.file_id) : remainingSelected;
    if (fileIds.length === 0) return;
    setStarting(true);
    setError("");
    try {
      const selection = {
        expectedRevision: brief.revision, payloadSha256: brief.payload_sha256, phase,
        ...(phase === "batch" && reviewedPreviewRun ? { previewRunId: reviewedPreviewRun.runId } : {}),
      };
      const run = await startWithRequestReceipt({ selectedFileIds: fileIds, confirmedBrief: selection });
      setRuns((current) => [run, ...current]);
      setActiveRunId(run.runId);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not start extraction.");
    } finally { setStarting(false); }
  }

  async function start() {
    if (!briefReady || selected.length === 0) return;
    setStarting(true);
    setError("");
    try {
      const recipe = approvedRecipes.find((item) => item.recipe_id === selectedRecipeId);
      const run = await startWithRequestReceipt({ selectedFileIds: selected, ...(recipe
        ? { approvedRecipe: { recipeId: recipe.recipe_id, expectedRevision: recipe.revision } } : {}) });
      setRuns((current) => [run, ...current]);
      setActiveRunId(run.runId);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to start automatic extraction.");
    } finally {
      setStarting(false);
    }
  }

  async function startWithRequestReceipt(payload: ProductAutoRunPayload): Promise<ProductAutoRun> {
    if (!briefReady) throw new Error("Load extraction setup before starting extraction.");
    const finishAdmission = runRefresh.current.beginAdmission();
    try {
      let stored: PendingProductAutoRunRequest;
      try {
        stored = reserveProductAutoRunRequest(window.sessionStorage, jobId, payload);
      } catch (cause) {
        if (cause instanceof Error) throw cause;
        throw new Error("Browser session storage is required to safely start extraction.");
      }
      setPendingRunRequest(stored);
      setPendingRunChecked(false);
      const run = await idpoApi.startProductAutoRun(jobId, payload.selectedFileIds,
        payload.approvedRecipe, payload.confirmedBrief, stored.key);
      clearPendingProductAutoRunRequest(window.sessionStorage, jobId, stored.key);
      setPendingRunRequest(null);
      return run;
    } finally {
      finishAdmission();
    }
  }

  async function checkPendingRunRequest() {
    if (!pendingRunRequest) return;
    setError("");
    try {
      await runRefresh.current.refresh(async () => (await idpoApi.listProductAutoRuns(jobId)).runs, (runs) => {
        const matched = runs.find((run) => run.idempotencyKey === pendingRunRequest.key);
        if (matched) {
          clearPendingProductAutoRunRequest(window.sessionStorage, jobId, pendingRunRequest.key);
          setPendingRunRequest(null);
          setPendingRunChecked(false);
          setActiveRunId(matched.runId);
        } else {
          setPendingRunChecked(true);
          setError("No accepted run is listed for the prior request yet. Retrying the same request keeps its key; a separate attempt may incur another model call.");
        }
      });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not check extraction runs.");
    }
  }

  function allowSeparateRunRequest() {
    if (!pendingRunRequest || !pendingRunChecked) return;
    clearPendingProductAutoRunRequest(window.sessionStorage, jobId, pendingRunRequest.key);
    setPendingRunRequest(null);
    setPendingRunChecked(false);
    setError("The prior request was not retried. A new extraction request may incur another model call.");
  }

  async function downloadReviewedBatch(copy = false) {
    if (!activeRun || !batchReady || downloadingRunId !== null) return;
    const runId = activeRun.runId;
    setDownloadingRunId(runId);
    setError("");
    setExportMessage(null);
    try {
      const blob = await idpoApi.downloadProductAutoReviewedBatch(jobId, runId);
      if (copy) {
        try {
          await navigator.clipboard.writeText(await blob.text());
          setExportMessage({ runId, text: "Reviewed batch JSONL copied." });
        } catch {
          setExportMessage({ runId, text: "Clipboard access is unavailable. Use Download reviewed batch." });
        }
        return;
      }
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `docai-${runId}-reviewed-v1.jsonl`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
      setExportMessage({ runId, text: "Download requested. If your browser blocks the file, use Copy reviewed JSONL." });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not download the reviewed batch.");
      void refreshRunStatuses();
    } finally { setDownloadingRunId(null); }
  }

  if (loading || briefLoading) return <div className="p-6 text-sm text-slate-500" aria-busy="true">Loading automatic extraction…</div>;

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div>
        <Link href="/dashboard/idpo/jobs" className="text-sm font-medium text-cyan-700 dark:text-cyan-300">← All jobs</Link>
        <h1 className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">Extract documents</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600 dark:text-slate-300">
          Upload files, describe the information you need, and confirm the field meanings. Preview a sample before processing the batch, then review and export.
        </p>
        {modelActionBlocked ? <p role="status" className="mt-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-200">
          This deployment allows only administrators to request paid model suggestions and extraction. You can save a draft, but an administrator must run its preview and batch.
        </p> : null}
      </div>

      {error ? <div role="alert" className="rounded-xl border border-rose-300 bg-rose-50 p-3 text-sm text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300">{error}</div> : null}
      {briefLoad.status === "error" ? <IdpoCard>
        <p role="alert" className="text-sm text-rose-700 dark:text-rose-300">{briefLoad.error}</p>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">Extraction setup could not be loaded. Load the saved schema before editing fields or starting extraction.</p>
        <button type="button" onClick={() => setBriefLoadAttempt((attempt) => attempt + 1)}
          className="mt-3 rounded-lg border border-cyan-600 px-3 py-2 text-sm font-medium text-cyan-700 dark:text-cyan-300">
          Retry loading extraction setup
        </button>
      </IdpoCard> : null}
      <IdpoCard>
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Files</h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{documents.length} {documents.length === 1 ? "file" : "files"} in this job. Uploading does not start extraction.</p>
        <ProductFileUpload key={jobId} jobId={jobId} disabled={starting || running || briefBusy || suggesting} onUploaded={refreshFiles} />
      </IdpoCard>
      {pendingRunRequest && !starting ? <IdpoCard>
        <p className="text-sm font-semibold text-amber-800 dark:text-amber-200">An extraction start may already have been accepted.</p>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">Check runs or retry the same selection and schema. The saved request key prevents a repeated paid attempt after a lost response.</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" onClick={() => void checkPendingRunRequest()} disabled={starting}
            className="rounded-lg border border-cyan-600 px-3 py-2 text-sm font-medium text-cyan-700 disabled:opacity-50 dark:text-cyan-300">Check runs</button>
          {pendingRunChecked ? <button type="button" onClick={allowSeparateRunRequest} disabled={starting}
            className="rounded-lg border border-amber-600 px-3 py-2 text-sm font-medium text-amber-800 disabled:opacity-50 dark:text-amber-200">Start a separate attempt</button> : null}
        </div>
      </IdpoCard> : null}

      <IdpoCard>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Set up your extraction</h2>
            <p className="mt-1 max-w-3xl text-sm text-slate-600 dark:text-slate-300">
              Describe the result, name the fields, and choose up to five sample files. Confirm the field meanings before previewing.
            </p>
          </div>
          {brief ? <span className="rounded-full border border-slate-300 px-3 py-1 text-xs font-medium text-slate-600 dark:border-slate-700 dark:text-slate-300">
            {brief.state === "confirmed" ? `Confirmed revision ${brief.revision}` : `Draft revision ${brief.revision}`}
          </span> : null}
        </div>
        <fieldset disabled={!briefReady || briefBusy || suggesting || starting || running}
          aria-busy={briefBusy || suggesting || starting} aria-label="Extraction setup" className="min-w-0">
        <label className="mt-4 block text-sm font-medium text-slate-700 dark:text-slate-200">
          What should the result contain?
          <textarea value={briefIntent} onChange={(event) => setBriefIntent(event.target.value)} rows={3}
            maxLength={4000} placeholder="For example: extract the invoice number, final amount due, and payment date."
            className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-3 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-white" />
        </label>
        <div className="mt-4 flex items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Fields and meanings</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">Use a stable field ID and explain which value belongs in it. Table columns share a repeated row group.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" disabled={briefFields.length >= 24 || briefBusy} onClick={() => setBriefFields((current) =>
              [...current, { field_id: "", type: "string", description: "", example_values: [] }])}
              className="rounded-lg border border-cyan-500 px-3 py-2 text-sm font-medium text-cyan-700 hover:bg-cyan-50 disabled:opacity-50 dark:text-cyan-300">
              Add field
            </button>
            <button type="button" disabled={briefFields.length >= 24 || briefBusy} onClick={addTableColumn}
              className="rounded-lg border border-cyan-500 px-3 py-2 text-sm font-medium text-cyan-700 hover:bg-cyan-50 disabled:opacity-50 dark:text-cyan-300">
              Add table column
            </button>
          </div>
        </div>
        {briefFields.length === 0 ? <p className="mt-3 text-sm text-slate-500">Add at least one typed field to confirm a schema.</p> : (
          <div className="mt-3 space-y-3">
            {briefFields.map((field, index) => (
              <div key={index} className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_180px_auto]">
                  <div>
                    <label htmlFor={`${jobId}-field-${index}-id`} className="text-xs font-medium text-slate-600 dark:text-slate-300">Field ID</label>
                    <input id={`${jobId}-field-${index}-id`} value={field.field_id} maxLength={64} placeholder="invoice_total" onChange={(event) => updateField(index, { field_id: event.target.value })}
                      className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-white" />
                  </div>
                  <div>
                    <label htmlFor={`${jobId}-field-${index}-type`} className="text-xs font-medium text-slate-600 dark:text-slate-300">Type</label>
                    <select id={`${jobId}-field-${index}-type`} value={field.type} onChange={(event) => updateField(index, { type: event.target.value as ProductAutoBriefField["type"] })}
                      className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-white">
                      {FIELD_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
                    </select>
                  </div>
                  <button type="button" onClick={() => setBriefFields((current) => current.filter((_, fieldIndex) => fieldIndex !== index))}
                    className="self-end rounded-lg px-2 py-2 text-sm text-rose-700 hover:bg-rose-50 dark:text-rose-300">Remove</button>
                </div>
                {field.type === "array[object]" ? <div className="mt-3">
                  <label htmlFor={`${jobId}-field-${index}-group`} className="text-xs font-medium text-slate-600 dark:text-slate-300">Repeated row group</label>
                  <input id={`${jobId}-field-${index}-group`} value={field.group ?? ""} maxLength={64} placeholder="line_items" onChange={(event) => updateField(index, { group: event.target.value })}
                    className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-white" />
                </div> : null}
                <div className="mt-3">
                  <label htmlFor={`${jobId}-field-${index}-meaning`} className="text-xs font-medium text-slate-600 dark:text-slate-300">Meaning</label>
                  <input id={`${jobId}-field-${index}-meaning`} value={field.description} maxLength={1000} placeholder="Final amount due after taxes and discounts"
                    onChange={(event) => updateField(index, { description: event.target.value })}
                    className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-white" />
                </div>
                <div className="mt-3">
                  <label htmlFor={`${jobId}-field-${index}-examples`} className="text-xs font-medium text-slate-600 dark:text-slate-300">Example values (one per line, up to three)</label>
                  <textarea id={`${jobId}-field-${index}-examples`} value={field.example_values.join("\n")} rows={2} onChange={(event) => updateField(index,
                    { example_values: event.target.value.split(/\r?\n/) })}
                    className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-white" />
                </div>
              </div>
            ))}
          </div>
        )}
        <div className="mt-5">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Sample files</h3>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Choose 1–5 files that show the values you want. These files are previewed first.</p>
          {documents.length === 0 ? <p className="mt-2 text-sm text-slate-500">Upload files above to choose a sample.</p> : (
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              {documents.map((document) => <label key={document.fileId} className="flex min-w-0 items-center gap-2 rounded-lg border border-slate-200 p-2 text-sm dark:border-slate-700">
                <input type="checkbox" checked={sampleFileIds.includes(document.fileId)}
                  disabled={!sampleFileIds.includes(document.fileId) && sampleFileIds.length >= 5}
                  onChange={(event) => setSampleFileIds((current) => event.target.checked
                    ? [...current, document.fileId] : current.filter((id) => id !== document.fileId))} />
                <span className="truncate" title={document.fileName}>{document.fileName}</span>
              </label>)}
            </div>
          )}
          {staleSampleFileIds.length > 0 ? <p role="alert" className="mt-2 text-sm text-rose-700 dark:text-rose-300">
            A sample changed or is missing. Save a new draft from the current files before previewing.
          </p> : null}
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <button type="button" onClick={() => void saveDraft()} disabled={!briefReady || briefBusy || suggesting || starting || running ||
            (!formDirty && staleSampleFileIds.length === 0) || sampleFileIds.length === 0 ||
            (!briefIntent.trim() && briefFields.length === 0)}
            className="rounded-lg border border-cyan-600 px-4 py-2 text-sm font-semibold text-cyan-700 hover:bg-cyan-50 disabled:opacity-50 dark:text-cyan-300">
            {briefBusy ? "Saving…" : brief?.state === "confirmed" ? "Save as new draft" : "Save draft"}
          </button>
          <button type="button" onClick={() => void confirmSchema()} disabled={!briefReady || briefBusy || suggesting || starting || running ||
            !brief || brief.state !== "draft" || formDirty || brief.fields.length === 0 ||
            brief.fields.some((field) => !field.description) || staleSampleFileIds.length > 0}
            className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700 disabled:opacity-50">
            Confirm field meanings
          </button>
          <button type="button" onClick={() => void suggestFields()} disabled={!briefReady || briefBusy || suggesting || starting || running ||
            !brief || brief.state !== "draft" || formDirty || staleSampleFileIds.length > 0 || !modelConfigured || !isAdmin}
            className="rounded-lg border border-cyan-600 px-4 py-2 text-sm font-semibold text-cyan-700 hover:bg-cyan-50 disabled:opacity-50 dark:text-cyan-300">
            {suggesting ? "Reading samples and suggesting…" : "Suggest fields with AI"}
          </button>
          {formDirty && brief ? <span className="text-xs text-amber-700 dark:text-amber-300">Save changes before confirming or previewing.</span> : null}
        </div>
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
          AI suggestions use one server model call with bounded excerpts from your saved sample files. The call may incur provider cost. An administrator must run it. Suggestions remain editable and require your confirmation. A new extraction run may also incur provider cost.
        </p>
        {suggestion ? <div className="mt-4 rounded-xl border border-cyan-300 bg-cyan-50 p-4 dark:border-cyan-700 dark:bg-cyan-950/30">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h3 className="font-semibold text-slate-900 dark:text-white">AI draft from {suggestion.provenance.samples.length} samples</h3>
              <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
                {suggestion.fields.length} proposed fields · {suggestion.provenance.model_id} · output cap {suggestion.provenance.max_output_tokens} tokens
                {suggestion.provenance.prompt_tokens !== null ? ` · ${suggestion.provenance.prompt_tokens} input tokens` : ""}
                {suggestion.provenance.completion_tokens !== null ? ` · ${suggestion.provenance.completion_tokens} output tokens` : ""}
              </p>
            </div>
            <button type="button" onClick={() => setBriefFields(suggestion.fields)}
              disabled={!briefReady || briefBusy || suggesting || formDirty || brief?.revision !== suggestion.provenance.brief_revision ||
                brief?.payload_sha256 !== suggestion.provenance.brief_payload_sha256}
              className="rounded-lg bg-cyan-600 px-3 py-2 text-sm font-semibold text-white hover:bg-cyan-700 disabled:opacity-50">
              Use these fields in draft
            </button>
          </div>
          <ul className="mt-3 space-y-1 text-sm text-slate-700 dark:text-slate-200">
            {suggestion.fields.map((field) => <li key={field.field_id}><span className="font-mono font-medium">{field.field_id}</span> · {field.description} ({field.type})</li>)}
          </ul>
          {suggestion.clarification_questions.length > 0 ? <div className="mt-3 text-sm text-slate-700 dark:text-slate-200">
            <p className="font-semibold">Clarify before confirmation</p>
            <ul className="mt-1 list-disc space-y-1 pl-5">{suggestion.clarification_questions.map((question) => <li key={question}>{question}</li>)}</ul>
            <p className="mt-1 text-xs">Answer by editing the intent or field meanings, then save the draft.</p>
          </div> : null}
          <p className="mt-3 text-xs text-slate-600 dark:text-slate-300">Source receipts: {suggestion.provenance.samples.map((sample) =>
            `${documents.find((document) => document.fileId === sample.file_id)?.fileName ?? sample.file_id} (${sample.parser_id}, ${sample.excerpt_chars} characters${sample.truncated ? ", truncated" : ""}, SHA ${sample.source_sha256.slice(0, 12)})`).join(" · ")}</p>
        </div> : null}
        </fieldset>
      </IdpoCard>

      {brief ? <IdpoCard>
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Preview, review, then apply</h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          Preview runs only on the confirmed sample files. Open each result and complete its source-linked review before applying the same schema to the remaining files.
        </p>
        {confirmed && brief ? <section aria-labelledby="confirmed-preview-schema" className="mt-4 rounded-lg border border-slate-200 p-3 dark:border-slate-700">
          <h3 id="confirmed-preview-schema" className="text-sm font-semibold text-slate-900 dark:text-white">
            Confirmed schema for preview · revision {brief.revision}
          </h3>
          <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
            Sample files: {brief.sample_sources.map((source) =>
              documents.find((document) => document.fileId === source.file_id)?.fileName ?? source.file_id).join(", ")}
          </p>
          <ul className="mt-3 max-h-64 space-y-2 overflow-y-auto text-sm">
            {brief.fields.map((field) => <li key={field.field_id} className="rounded-md bg-slate-50 p-2 dark:bg-slate-900">
              <p className="font-medium text-slate-900 dark:text-white">
                <span className="font-mono">{field.field_id}</span> <span className="font-normal text-slate-500 dark:text-slate-400">({field.type}{field.group ? ` · ${field.group}` : ""})</span>
              </p>
              <p className="mt-1 text-slate-700 dark:text-slate-200">{field.description}</p>
              {field.example_values.length > 0 ? <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">Examples: {field.example_values.join(", ")}</p> : null}
            </li>)}
          </ul>
          <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">
            In review, compare each proposed value with this meaning and the original document. A text match alone does not establish the correct value.
          </p>
        </section> : null}
        {!modelConfigured ? <p className="mt-3 text-sm text-amber-700 dark:text-amber-300">A server model is required for this schema. Ask an administrator to configure one.</p> : null}
        {!available ? <p className="mt-3 text-sm text-amber-700 dark:text-amber-300">The extraction runner is unavailable on this deployment.</p> : null}
        <div className="mt-4 flex flex-wrap gap-3">
          <button type="button" disabled={!confirmed || !available || !modelConfigured || modelActionBlocked || running || starting || briefBusy}
            onClick={() => void startConfirmedRun("preview")}
            className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700 disabled:opacity-50">
            {starting ? "Starting…" : previewRun ? "Run preview again" : "Preview sample files"}
          </button>
          <button type="button" disabled={!confirmed || !reviewedPreviewRun || remainingSelected.length === 0 ||
            !available || !modelConfigured || modelActionBlocked || running || starting || briefBusy} onClick={() => void startConfirmedRun("batch")}
            className="rounded-lg border border-cyan-600 px-4 py-2 text-sm font-semibold text-cyan-700 hover:bg-cyan-50 disabled:opacity-50 dark:text-cyan-300">
            Extract {remainingSelected.length} selected {remainingSelected.length === 1 ? "file" : "files"}
          </button>
        </div>
        {repeatsBatchFiles ? <p className="mt-3 text-sm text-amber-700 dark:text-amber-300">
          Some selected files already have batch results for this schema. Open those results below before starting another run, which may incur another model charge.
        </p> : null}
        {previewRun ? <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
          Latest preview {previewRun.status}. {reviewedPreviewRun ? "A reviewed sample preview is ready for the batch." :
            "Review every preview result before applying the schema to other files."}
        </p> : null}
        {previewRun && previewRun.documents.length > 0 ? <div className="mt-3">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Preview results</h3>
          <ol className="mt-2 space-y-1 text-sm">
            {previewRun.documents.map((document, index) => <li key={document.docId}>
              <Link className="font-medium text-cyan-700 hover:underline dark:text-cyan-300"
                href={`/dashboard/idpo/jobs/${encodeURIComponent(jobId)}/auto/${encodeURIComponent(previewRun.runId)}/docs/${encodeURIComponent(document.docId)}`}>
                Review result {index + 1}: {document.fileName}
              </Link>
              <span className="ml-2 text-slate-600 dark:text-slate-300">{document.reviewStatus.replaceAll("_", " ")}</span>
            </li>)}
          </ol>
        </div> : null}
        {confirmed ? <div className="mt-4 grid gap-2 sm:grid-cols-2">
          {documents.filter((document) => !sampleFileIds.includes(document.fileId)).map((document) =>
            <label key={document.fileId} className="flex min-w-0 items-center gap-2 rounded-lg border border-slate-200 p-2 text-sm dark:border-slate-700">
              <input type="checkbox" checked={selected.includes(document.fileId)} disabled={running || starting}
                onChange={(event) => setSelected((current) => event.target.checked
                  ? [...current, document.fileId] : current.filter((id) => id !== document.fileId))} />
              <span className="truncate" title={document.fileName}>{document.fileName}</span>
            </label>)}
        </div> : null}
      </IdpoCard> : null}

      {briefReady && !brief ? <IdpoCard>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Run selected documents</h2>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              {modelConfigured ? "Server configured model proposals with local evidence checks." : "Local deterministic field discovery. Configure a server model for AI proposals."}
            </p>
          </div>
          <button type="button" onClick={() => void start()} disabled={!available || modelActionBlocked || starting || running || selected.length === 0}
            className="rounded-xl bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-50">
            {starting ? "Starting…" : `Extract ${selected.length} selected`}
          </button>
        </div>
        {!available ? <p className="mt-3 text-sm text-amber-700 dark:text-amber-300">This deployment has no automatic extraction runner configured.</p> : null}
        {approvedRecipes.length > 0 ? (
          <label className="mt-4 block max-w-md text-sm font-medium text-slate-700 dark:text-slate-200">
            Schema for this run
            <select value={selectedRecipeId} disabled={running || starting || !modelConfigured}
              onChange={(event) => setSelectedRecipeId(event.target.value)}
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-white">
              <option value="">Discover fields from each document</option>
              {approvedRecipes.map((recipe) => (
                <option key={recipe.recipe_id} value={recipe.recipe_id}>
                  {recipe.family_name} · revision {recipe.revision}
                </option>
              ))}
            </select>
            {selectedRecipeId ? <span className="mt-1 block font-normal text-slate-500">This choice is explicit for the selected files. Results still require review.</span> : null}
          </label>
        ) : null}
        {documents.length === 0 ? <p className="mt-4 text-sm text-slate-500">Upload files above to get started.</p> : (
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
      </IdpoCard> : null}

      <IdpoCard>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Runs</h2>
          <button type="button" onClick={() => void refreshRunStatuses()} disabled={reviewRefreshing}
            className="rounded-lg border border-cyan-600 px-3 py-2 text-sm font-medium text-cyan-700 disabled:opacity-50 dark:text-cyan-300">
            {reviewRefreshing ? "Refreshing…" : "Refresh review status"}
          </button>
        </div>
        {reviewRefreshError ? <p role="alert" className="mt-2 text-sm text-rose-700 dark:text-rose-300">{reviewRefreshError}</p> : null}
        {runs.length === 0 ? <p className="mt-3 text-sm text-slate-500">No automatic extraction runs yet.</p> : (
          <div className="mt-3 flex flex-wrap gap-2">
            {runs.map((run) => (
              <button key={run.runId} type="button" onClick={() => setActiveRunId(run.runId)}
                className={`rounded-lg border px-3 py-2 text-left text-xs dark:border-slate-700 ${activeRun?.runId === run.runId ? "border-cyan-500 bg-cyan-50 dark:bg-cyan-900/20" : "border-slate-200"}`}>
                <span className="font-mono">{run.runId.slice(0, 13)}</span>
                <span className={`ml-2 font-semibold ${statusClass(run.status)}`}>{run.status}</span>
                <span className="ml-2 text-slate-500">{run.selectedCount} files</span>
                {run.approvedRecipe ? <span className="ml-2 text-slate-500">{run.approvedRecipe.familyName} r{run.approvedRecipe.revision}</span> : null}
                {run.confirmedBrief ? <span className="ml-2 text-slate-500">{run.confirmedBrief.phase} · schema r{run.confirmedBrief.revision}</span> : null}
              </button>
            ))}
          </div>
        )}
        {(activeRun?.status as string) === "queued" ? <p className="mt-4 text-sm text-amber-700 dark:text-amber-300">Queued. Extraction will start when a worker is available.</p> : null}
        {activeRun?.status === "running" ? <p className="mt-4 text-sm text-amber-700 dark:text-amber-300">Extracting. Results will appear when the run completes.</p> : null}
        {activeRun?.status === "failed" ? <p role="alert" className="mt-4 text-sm text-rose-700 dark:text-rose-300">{activeRun.error ?? "Extraction failed."}</p> : null}
        {activeRun?.status === "success" ? (
          <div className="mt-4 overflow-x-auto">
            <div className="mb-3 flex flex-wrap items-center gap-3">
              <button type="button" onClick={() => void downloadReviewedBatch()}
                disabled={!batchReady || downloadingRunId !== null}
                className="rounded-lg bg-cyan-700 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-800 disabled:cursor-not-allowed disabled:opacity-50">
                {downloadingRunId === activeRun.runId ? "Preparing export…" : "Download reviewed batch"}
              </button>
              <button type="button" onClick={() => void downloadReviewedBatch(true)}
                disabled={!batchReady || downloadingRunId !== null}
                className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700">
                Copy reviewed JSONL
              </button>
              <p className="text-sm text-slate-600 dark:text-slate-300">
                {reviewedCount} of {activeRun.documents.length} results reviewed across {activeRun.selectedCount} selected {activeRun.selectedCount === 1 ? "file" : "files"}. JSONL has one structured result per document.
              </p>
            </div>
            {exportMessage?.runId === activeRun.runId ? <p role="status" className="mb-3 text-sm text-slate-600 dark:text-slate-300">{exportMessage.text}</p> : null}
            <table className="w-full min-w-[600px] text-sm">
              <thead><tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-500 dark:border-slate-700"><th className="py-2 pr-3">Document</th><th className="py-2 pr-3">Original proposal</th><th className="py-2 pr-3">Proposed fields</th><th className="py-2 pr-3">Text matched</th><th className="py-2 pr-3">Human review</th></tr></thead>
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
      <details className="rounded-xl border border-slate-200 p-4 dark:border-slate-800">
        <summary className="cursor-pointer text-sm font-medium text-slate-600 dark:text-slate-300">Advanced job settings</summary>
        <Link href={`/dashboard/idpo/jobs/${encodeURIComponent(jobId)}`} className="mt-3 inline-block text-sm text-cyan-700 hover:underline dark:text-cyan-300">Rename job and open research pipeline</Link>
      </details>
    </div>
  );
}
