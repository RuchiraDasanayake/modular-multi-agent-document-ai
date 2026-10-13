"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { IdpoCard } from "@/components/idpo/card";
import { api } from "@/lib/api";
import { idpoApi } from "@/lib/idpo-api";
import type { ProductAutoRun, ProductAutoSourceDocument } from "@/types/product-auto";
import type { ProductAutoRecipeRevision } from "@/types/product-auto-recipes";
import type { ProductAutoBriefField, ProductAutoBriefRevision, ProductAutoBriefSuggestion } from "@/types/product-auto-brief";

const FIELD_TYPES = ["string", "integer", "decimal", "boolean", "date", "array[object]"] as const;

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
  const [briefLoading, setBriefLoading] = useState(true);
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
    void idpoApi.listProductAutoRecipes(jobId).then((data) => {
      if (current) setApprovedRecipes(data.recipes.filter((recipe) => recipe.state === "approved_shadow"));
    }).catch(() => { if (current) setApprovedRecipes([]); });
    void api.me().then((user) => {
      if (current) setIsAdmin(user.role === "admin");
    }).catch(() => { if (current) setIsAdmin(false); });
    void idpoApi.getProductAutoBrief(jobId).then((data) => {
      if (!current) return;
      setBrief(data.brief);
      setBriefIntent(data.brief?.intent ?? "");
      setBriefFields(data.brief?.fields ?? []);
      setSampleFileIds(data.brief?.sample_sources.map((source) => source.file_id) ?? []);
      setStaleSampleFileIds(data.staleSampleFileIds);
    }).catch((cause) => {
      if (current) setError(cause instanceof Error ? cause.message : "Failed to load extraction setup.");
    }).finally(() => { if (current) setBriefLoading(false); });
    return () => { current = false; };
  }, [jobId]);

  useEffect(() => {
    if (!briefLoading && !brief && sampleFileIds.length === 0 && documents.length > 0) {
      setSampleFileIds([documents[0].fileId]);
    }
  }, [briefLoading, brief, sampleFileIds.length, documents]);

  const running = runs.some((run) => run.status === "running" || (run.status as string) === "queued");
  const modelActionBlocked = modelConfigured && !isAdmin;
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
  const reviewedCount = activeRun?.documents.filter((document) => document.reviewStatus === "completed" &&
    document.status !== "failed" && document.status !== "unsupported").length ?? 0;
  const batchReady = activeRun?.status === "success" && activeRun.selectedCount > 0 &&
    activeRun.documents.length === activeRun.selectedCount && reviewedCount === activeRun.selectedCount;
  const formDirty = !brief || JSON.stringify({ intent: briefIntent, fields: briefFields, samples: sampleFileIds }) !==
    JSON.stringify({ intent: brief.intent, fields: brief.fields,
      samples: brief.sample_sources.map((source) => source.file_id) });
  const confirmed = brief?.state === "confirmed" && !formDirty && staleSampleFileIds.length === 0;
  const matchingPreviews = confirmed ? runs.filter((run) => run.confirmedBrief?.phase === "preview" &&
    run.confirmedBrief.briefId === brief.brief_id && run.confirmedBrief.revision === brief.revision &&
    run.confirmedBrief.payloadSha256 === brief.payload_sha256) : [];
  const previewRun = matchingPreviews[0];
  const reviewedPreviewRun = matchingPreviews.find((run) => run.status === "success" &&
    run.documents.length > 0 && run.documents.every((document) => document.status === "needs_review" &&
      document.reviewStatus === "completed"));
  const remainingSelected = selected.filter((fileId) => !sampleFileIds.includes(fileId));

  function updateField(index: number, change: Partial<ProductAutoBriefField>) {
    setBriefFields((current) => current.map((field, fieldIndex) => fieldIndex === index
      ? { ...field, ...change } : field));
  }

  async function saveDraft() {
    setBriefBusy(true);
    setError("");
    try {
      const saved = await idpoApi.saveProductAutoBrief(jobId, brief?.revision ?? 0,
        briefIntent, briefFields, sampleFileIds);
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
    if (!brief || brief.state !== "draft" || formDirty) return;
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
    if (!brief) return;
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
      const run = await idpoApi.startProductAutoRun(jobId, fileIds, undefined, {
        expectedRevision: brief.revision, payloadSha256: brief.payload_sha256, phase,
        ...(phase === "batch" && reviewedPreviewRun ? { previewRunId: reviewedPreviewRun.runId } : {}),
      });
      setRuns((current) => [run, ...current]);
      setActiveRunId(run.runId);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not start extraction.");
    } finally { setStarting(false); }
  }

  async function start() {
    if (selected.length === 0) return;
    setStarting(true);
    setError("");
    try {
      const recipe = approvedRecipes.find((item) => item.recipe_id === selectedRecipeId);
      const run = await idpoApi.startProductAutoRun(jobId, selected, recipe
        ? { recipeId: recipe.recipe_id, expectedRevision: recipe.revision } : undefined);
      setRuns((current) => [run, ...current]);
      setActiveRunId(run.runId);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to start automatic extraction.");
    } finally {
      setStarting(false);
    }
  }

  async function downloadReviewedBatch() {
    if (!activeRun || !batchReady) return;
    const runId = activeRun.runId;
    setDownloadingRunId(runId);
    setError("");
    try {
      const blob = await idpoApi.downloadProductAutoReviewedBatch(jobId, runId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `docai-${runId}-reviewed-v1.jsonl`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not download the reviewed batch.");
      void idpoApi.listProductAutoRuns(jobId).then((data) => setRuns(data.runs)).catch(() => undefined);
    } finally { setDownloadingRunId(null); }
  }

  if (loading || briefLoading) return <div className="p-6 text-sm text-slate-500" aria-busy="true">Loading automatic extraction…</div>;

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div>
        <Link href={`/dashboard/idpo/jobs/${encodeURIComponent(jobId)}`} className="text-sm font-medium text-cyan-700 dark:text-cyan-300">← Back to job</Link>
        <h1 className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">Automatic schema extraction</h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600 dark:text-slate-300">
          Discover fields from each document or explicitly select an approved schema. Verify source evidence and review every proposed value.
        </p>
        {modelActionBlocked ? <p role="status" className="mt-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-200">
          This deployment allows only administrators to request paid model suggestions and extraction. You can save a draft, but an administrator must run its preview and batch.
        </p> : null}
      </div>

      {error ? <div role="alert" className="rounded-xl border border-rose-300 bg-rose-50 p-3 text-sm text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300">{error}</div> : null}

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
        <label className="mt-4 block text-sm font-medium text-slate-700 dark:text-slate-200">
          What should the result contain?
          <textarea value={briefIntent} onChange={(event) => setBriefIntent(event.target.value)} rows={3}
            maxLength={4000} placeholder="For example: extract the invoice number, final amount due, and payment date."
            className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-3 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-white" />
        </label>
        <div className="mt-4 flex items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Fields and meanings</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">Use a stable field ID and explain which value belongs in it.</p>
          </div>
          <button type="button" disabled={briefFields.length >= 24 || briefBusy} onClick={() => setBriefFields((current) =>
            [...current, { field_id: "", type: "string", description: "", example_values: [] }])}
            className="rounded-lg border border-cyan-500 px-3 py-2 text-sm font-medium text-cyan-700 hover:bg-cyan-50 disabled:opacity-50 dark:text-cyan-300">
            Add field
          </button>
        </div>
        {briefFields.length === 0 ? <p className="mt-3 text-sm text-slate-500">Add at least one typed field to confirm a schema.</p> : (
          <div className="mt-3 space-y-3">
            {briefFields.map((field, index) => (
              <div key={index} className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_180px_auto]">
                  <label className="text-xs font-medium text-slate-600 dark:text-slate-300">Field ID
                    <input value={field.field_id} maxLength={64} placeholder="invoice_total" onChange={(event) => updateField(index, { field_id: event.target.value })}
                      className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-white" />
                  </label>
                  <label className="text-xs font-medium text-slate-600 dark:text-slate-300">Type
                    <select value={field.type} onChange={(event) => updateField(index, { type: event.target.value as ProductAutoBriefField["type"] })}
                      className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-white">
                      {FIELD_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
                    </select>
                  </label>
                  <button type="button" onClick={() => setBriefFields((current) => current.filter((_, fieldIndex) => fieldIndex !== index))}
                    className="self-end rounded-lg px-2 py-2 text-sm text-rose-700 hover:bg-rose-50 dark:text-rose-300">Remove</button>
                </div>
                {field.type === "array[object]" ? <label className="mt-3 block text-xs font-medium text-slate-600 dark:text-slate-300">Repeated row group
                  <input value={field.group ?? ""} maxLength={64} placeholder="line_items" onChange={(event) => updateField(index, { group: event.target.value })}
                    className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-white" />
                </label> : null}
                <label className="mt-3 block text-xs font-medium text-slate-600 dark:text-slate-300">Meaning
                  <input value={field.description} maxLength={1000} placeholder="Final amount due after taxes and discounts"
                    onChange={(event) => updateField(index, { description: event.target.value })}
                    className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-white" />
                </label>
                <label className="mt-3 block text-xs font-medium text-slate-600 dark:text-slate-300">Example values (one per line, up to three)
                  <textarea value={field.example_values.join("\n")} rows={2} onChange={(event) => updateField(index,
                    { example_values: event.target.value.split(/\r?\n/).filter(Boolean) })}
                    className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-900 dark:text-white" />
                </label>
              </div>
            ))}
          </div>
        )}
        <div className="mt-5">
          <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Sample files</h3>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Choose 1–5 files that show the values you want. These files are previewed first.</p>
          {documents.length === 0 ? <p className="mt-2 text-sm text-slate-500">Upload files on the job page to continue.</p> : (
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
          <button type="button" onClick={() => void saveDraft()} disabled={briefBusy || suggesting || starting || running ||
            (!formDirty && staleSampleFileIds.length === 0) || sampleFileIds.length === 0 ||
            (!briefIntent.trim() && briefFields.length === 0)}
            className="rounded-lg border border-cyan-600 px-4 py-2 text-sm font-semibold text-cyan-700 hover:bg-cyan-50 disabled:opacity-50 dark:text-cyan-300">
            {briefBusy ? "Saving…" : brief?.state === "confirmed" ? "Save as new draft" : "Save draft"}
          </button>
          <button type="button" onClick={() => void confirmSchema()} disabled={briefBusy || suggesting || starting || running ||
            !brief || brief.state !== "draft" || formDirty || brief.fields.length === 0 ||
            brief.fields.some((field) => !field.description) || staleSampleFileIds.length > 0}
            className="rounded-lg bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700 disabled:opacity-50">
            Confirm field meanings
          </button>
          <button type="button" onClick={() => void suggestFields()} disabled={briefBusy || suggesting || starting || running ||
            !brief || brief.state !== "draft" || formDirty || staleSampleFileIds.length > 0 || !modelConfigured || !isAdmin}
            className="rounded-lg border border-cyan-600 px-4 py-2 text-sm font-semibold text-cyan-700 hover:bg-cyan-50 disabled:opacity-50 dark:text-cyan-300">
            {suggesting ? "Reading samples and suggesting…" : "Suggest fields with AI"}
          </button>
          {formDirty && brief ? <span className="text-xs text-amber-700 dark:text-amber-300">Save changes before confirming or previewing.</span> : null}
        </div>
        <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">
          AI suggestions use one server model call with bounded excerpts from your saved sample files. The call may incur provider cost. An administrator must run it. Suggestions remain editable and require your confirmation.
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
              disabled={briefBusy || suggesting || formDirty || brief?.revision !== suggestion.provenance.brief_revision ||
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
      </IdpoCard>

      {brief ? <IdpoCard>
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Preview, review, then apply</h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          Preview runs only on the confirmed sample files. Open each result below and complete its source-linked review before applying the same schema to the remaining files.
        </p>
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
            Apply to {remainingSelected.length} remaining files
          </button>
        </div>
        {previewRun ? <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
          Latest preview {previewRun.status}. {reviewedPreviewRun ? "A reviewed sample preview is ready for the batch." :
            "Review every preview document using the links in Runs below."}
        </p> : null}
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

      {!brief ? <IdpoCard>
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
      </IdpoCard> : null}

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
                {downloadingRunId === activeRun.runId ? "Preparing download…" : "Download reviewed batch"}
              </button>
              <p className="text-sm text-slate-600 dark:text-slate-300">
                {reviewedCount} of {activeRun.selectedCount} reviewed. JSONL has one structured result per document.
              </p>
            </div>
            <table className="w-full min-w-[600px] text-sm">
              <thead><tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-500 dark:border-slate-700"><th className="py-2 pr-3">Document</th><th className="py-2 pr-3">Status</th><th className="py-2 pr-3">Fields</th><th className="py-2 pr-3">Text matched</th><th className="py-2 pr-3">Human review</th></tr></thead>
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
