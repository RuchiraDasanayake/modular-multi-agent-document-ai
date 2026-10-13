"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { IdpoCard } from "@/components/idpo/card";
import { idpoApi } from "@/lib/idpo-api";
import { productAutoOutcomeCopy } from "./product-auto-outcome";
import { isVisualProposal, machineProposalLabel, pdfSourcePageUrl, sourceTextPanelCopy, visualLinkedCellsReviewable } from "./product-auto-visual-review";
import type { ProductAutoAddedFieldInput, ProductAutoAddedLinkedFieldInput, ProductAutoAddedScalarFieldInput, ProductAutoDocumentDetail, ProductAutoEvidence, ProductAutoLinkedCell, ProductAutoLinkedCorrectionRow, ProductAutoReviewDecision, ProductAutoReviewField, ProductAutoScalarType } from "@/types/product-auto";

type Draft = Record<string, { decision: ProductAutoReviewDecision | ""; corrected_value: string; note: string }>;
type AddedScalarDraft = ProductAutoAddedScalarFieldInput & { clientId: string };
type AddedLinkedDraft = ProductAutoAddedLinkedFieldInput & { clientId: string };
type AddedDraft = AddedScalarDraft | AddedLinkedDraft;

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return "No value proposed";
  if (typeof value === "string") return value || "Empty string";
  return JSON.stringify(value);
}

function linkedCells(value: unknown): ProductAutoLinkedCell[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is ProductAutoLinkedCell => item && typeof item === "object" &&
    Number.isInteger(item.row) && typeof item.value === "string" &&
    (item.status === "accepted" || item.status === "needs_review")).sort((left, right) => left.row - right.row);
}

function nativeContext(detail: ProductAutoDocumentDetail, evidence: ProductAutoEvidence): string | null {
  const parsed = detail.parsedDocument;
  const unit = parsed?.units[evidence.page - 1];
  if (!unit) return null;
  const cell = parsed?.tables.flatMap((table) => table.cells).find((item) => item.anchors.some((anchor) =>
    anchor.unit_id === unit.unit_id && anchor.text_span &&
    anchor.text_span[0] <= evidence.start && evidence.end <= anchor.text_span[1]));
  const locator = cell?.anchors.find((anchor) => anchor.unit_id === unit.unit_id)?.native_locator;
  if (!locator) return unit.label ?? unit.unit_id;
  try {
    const value = JSON.parse(locator) as Record<string, unknown>;
    const row = typeof value.row === "number" ? value.row + 1 : null;
    const column = typeof value.column === "number" ? value.column + 1 : null;
    if (value.kind === "xlsx_cell" && typeof value.address === "string") {
      return `${unit.label ?? "Sheet"} · cell ${value.address}${value.formula === true ? " (formula, not evaluated)" : ""}`;
    }
    if (value.kind === "docx_table_cell" && typeof value.table_index === "number" && row && column) {
      return `Word table ${value.table_index + 1} · row ${row}, column ${column}`;
    }
    if (value.kind === "pptx_table_cell" && typeof value.shape_id === "number" && row && column) {
      return `Slide ${value.slide}, table shape ${value.shape_id} · row ${row}, column ${column}`;
    }
    if ((value.kind === "html_dom_cell" || value.kind === "eml_html_cell") && typeof value.xpath === "string") {
      return `${unit.label ?? unit.unit_id} · DOM cell ${value.xpath}`;
    }
  } catch { /* A malformed locator leaves the source unit label available. */ }
  return unit.label ?? unit.unit_id;
}

function linkedCorrectionRows(value: string | null | undefined, machine: unknown): ProductAutoLinkedCorrectionRow[] {
  if (value) {
    try {
      const parsed: unknown = JSON.parse(value);
      if (Array.isArray(parsed)) return parsed.filter((item): item is ProductAutoLinkedCorrectionRow =>
        item && typeof item === "object" && Number.isInteger(item.row) && typeof item.value === "string");
    } catch { /* fall back to machine rows */ }
  }
  return linkedCells(machine).map(({ row, value: cellValue }) => ({ row, value: cellValue }));
}

function addedDrafts(detail: ProductAutoDocumentDetail): AddedDraft[] {
  return (detail.review?.added_fields ?? []).map((field): AddedDraft => field.type === "array[object]"
    ? { field_id: field.field_id, type: field.type, group: field.group, note: field.note,
      value: field.value.map((cell) => ({ row: cell.row, value: cell.value,
        ...(cell.human_source_page ? { human_source_page: cell.human_source_page } :
          { evidence: { page: cell.evidence?.page ?? detail.sourcePages[0]?.page ?? 1,
            quote: cell.evidence?.quote ?? "" } }) })), clientId: field.field_id }
    : { field_id: field.field_id, type: field.type, value: String(field.value), note: field.note,
      ...(field.human_source_page ? { human_source_page: field.human_source_page } :
        { evidence: { page: field.evidence?.page ?? detail.sourcePages[0]?.page ?? 1,
          quote: field.evidence?.quote ?? "" } }), clientId: field.field_id });
}

export function ProductAutoDocumentPage() {
  const params = useParams<{ jobId: string; runId: string; docId: string }>();
  const jobId = decodeURIComponent(params.jobId);
  const runId = decodeURIComponent(params.runId);
  const docId = decodeURIComponent(params.docId);
  const [detail, setDetail] = useState<ProductAutoDocumentDetail | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [addedDraft, setAddedDraft] = useState<AddedDraft[]>([]);
  const [linkedDraft, setLinkedDraft] = useState<Record<string, ProductAutoLinkedCorrectionRow[]>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [reportedActiveMinutes, setReportedActiveMinutes] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [sourcePage, setSourcePage] = useState<number | null>(null);

  useEffect(() => {
    let current = true;
    void idpoApi.getProductAutoDocument(jobId, runId, docId).then((data) => {
      if (!current) return;
      setDetail(data);
      setSourcePage(null);
      const reviews = new Map(data.review?.fields.map((field) => [field.field_id, field]) ?? []);
      setDraft(Object.fromEntries(data.candidate.proposed_schema.map((field) => {
        const review = reviews.get(field.field_id);
        return [field.field_id, { decision: review?.decision ?? "", corrected_value: review?.corrected_value ?? "", note: review?.note ?? "" }];
      })));
      const machine = new Map(data.candidate.extracted_values.map((value) => [value.field_id, value.value]));
      setLinkedDraft(Object.fromEntries(data.candidate.proposed_schema.filter((field) => field.type === "array[object]")
        .map((field) => [field.field_id, linkedCorrectionRows(reviews.get(field.field_id)?.corrected_value,
          machine.get(field.field_id))])));
      setAddedDraft(addedDrafts(data));
      setReportedActiveMinutes("");
    }).catch((cause) => {
      if (current) setError(cause instanceof Error ? cause.message : "Failed to load extraction result.");
    }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [jobId, runId, docId]);

  function updateDraft(fieldId: string, patch: Partial<Draft[string]>) {
    setDraft((current) => ({ ...current, [fieldId]: { ...current[fieldId], ...patch } }));
    setMessage("");
  }

  function updateAdded(clientId: string, patch: Partial<AddedScalarDraft>) {
    setAddedDraft((current) => current.map((field) => field.clientId === clientId && field.type !== "array[object]"
      ? { ...field, ...patch } : field));
    setMessage("");
  }

  function updateAddedLinked(clientId: string, patch: Partial<AddedLinkedDraft>) {
    setAddedDraft((current) => current.map((field) => field.clientId === clientId && field.type === "array[object]"
      ? { ...field, ...patch } : field));
    setMessage("");
  }

  function updateAddedLinkedCell(clientId: string, index: number, patch: Partial<AddedLinkedDraft["value"][number]>) {
    setAddedDraft((current) => current.map((field) => field.clientId === clientId && field.type === "array[object]"
      ? { ...field, value: field.value.map((cell, cellIndex) => cellIndex === index ? { ...cell, ...patch } : cell) }
      : field));
    setMessage("");
  }

  function addAddedLinkedCell(clientId: string) {
    setAddedDraft((current) => current.map((field) => {
      if (field.clientId !== clientId || field.type !== "array[object]" || field.value.length >= 128) return field;
      const used = new Set(field.value.map((cell) => cell.row));
      const row = Array.from({ length: 128 }, (_, index) => index).find((index) => !used.has(index));
      return row === undefined ? field : { ...field, value: [...field.value, { row, value: "",
        ...(detail?.visualRoute === "visual"
          ? { human_source_page: { kind: "human_observed_page" as const, page: detail.sourcePages[0]?.page ?? 1 } }
          : { evidence: { page: detail?.sourcePages[0]?.page ?? 1, quote: "" } }) }] };
    }));
    setMessage("");
  }

  function removeAddedLinkedCell(clientId: string, index: number) {
    setAddedDraft((current) => current.map((field) => field.clientId === clientId && field.type === "array[object]"
      ? { ...field, value: field.value.filter((_, cellIndex) => cellIndex !== index) } : field));
    setMessage("");
  }

  function updateLinked(fieldId: string, index: number, patch: Partial<ProductAutoLinkedCorrectionRow>) {
    setLinkedDraft((current) => ({ ...current, [fieldId]: (current[fieldId] ?? []).map((cell, cellIndex) =>
      cellIndex === index ? { ...cell, ...patch } : cell) }));
    setMessage("");
  }

  function addLinked(fieldId: string) {
    setLinkedDraft((current) => {
      const cells = current[fieldId] ?? [];
      const used = new Set(cells.map((cell) => cell.row));
      const row = Array.from({ length: 128 }, (_, index) => index).find((index) => !used.has(index));
      return row === undefined ? current : { ...current, [fieldId]: [...cells, { row, value: "" }].sort((a, b) => a.row - b.row) };
    });
    setMessage("");
  }

  function removeLinked(fieldId: string, index: number) {
    setLinkedDraft((current) => ({ ...current, [fieldId]: (current[fieldId] ?? []).filter((_, cellIndex) => cellIndex !== index) }));
    setMessage("");
  }

  async function save() {
    if (!detail) return;
    const fields: ProductAutoReviewField[] = detail.candidate.proposed_schema.flatMap((field) => {
      const row = draft[field.field_id];
      if (!row?.decision) return [];
      return [{ field_id: field.field_id, decision: row.decision,
        corrected_value: row.decision === "corrected"
          ? field.type === "array[object]" ? JSON.stringify((linkedDraft[field.field_id] ?? [])
            .map(({ row: rowIndex, value }) => ({ row: rowIndex, value }))) : row.corrected_value
          : null,
        note: row.note || null }];
    });
    setSaving(true);
    setError("");
    try {
      const addedFields: ProductAutoAddedFieldInput[] = addedDraft.map((field) => field.type === "array[object]"
        ? { field_id: field.field_id, type: field.type, group: field.group, value: field.value, note: field.note }
        : { field_id: field.field_id, type: field.type, value: field.value,
          ...(field.human_source_page ? { human_source_page: field.human_source_page } : { evidence: field.evidence }),
          note: field.note });
      const result = await idpoApi.saveProductAutoReview(jobId, runId, docId, detail.review?.revision ?? 0,
        fields, addedFields, reportedActiveMinutes);
      const refreshed = await idpoApi.getProductAutoDocument(jobId, runId, docId);
      setDetail(refreshed);
      setAddedDraft(addedDrafts(refreshed));
      setReportedActiveMinutes("");
      setMessage(result.review.status === "completed" ? "Human review completed." : "Partial human review saved.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Failed to save review.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <div className="p-6 text-sm text-slate-500" aria-busy="true">Loading extraction result…</div>;
  if (!detail) return <div role="alert" className="p-6 text-sm text-rose-700">{error || "Document result not found."}</div>;

  const { candidate } = detail;
  const outcome = productAutoOutcomeCopy(candidate.document_status, detail.outcomeReason, detail.sourcePages.length);
  const values = new Map(candidate.extracted_values.map((item) => [item.field_id, item]));
  const removedProposals = candidate.proposed_schema.filter((field) =>
    draft[field.field_id]?.decision === "remove" || draft[field.field_id]?.decision === "not_present").length;
  const atFieldLimit = candidate.proposed_schema.length - removedProposals + addedDraft.length >= 24;
  const originalUrl = `/api/jobs/${encodeURIComponent(jobId)}/docs/${encodeURIComponent(detail.fileId)}/content`;
  const exportUrl = `/api/jobs/${encodeURIComponent(jobId)}/auto/${encodeURIComponent(runId)}/docs/${encodeURIComponent(docId)}/export`;
  const previewable = /\.(pdf|png|jpe?g|txt|json)$/i.test(detail.fileName);
  const nativeFormat = /\.(docx|xlsx|pptx|html|eml)$/i.test(detail.fileName);
  const sourceTextCopy = sourceTextPanelCopy(detail.visualRoute, Boolean(detail.parsedDocument), detail.sourcePages);
  const selectedPageUrl = sourcePage === null ? null :
    pdfSourcePageUrl(originalUrl, detail.fileName, sourcePage, detail.sourcePages);

  function showSourcePage(page: number) {
    if (!detail) return;
    const target = pdfSourcePageUrl(originalUrl, detail.fileName, page, detail.sourcePages);
    if (target) setSourcePage(page);
    document.getElementById("original-source")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div>
        <Link href={`/dashboard/idpo/jobs/${encodeURIComponent(jobId)}/auto`} className="text-sm font-medium text-cyan-700 dark:text-cyan-300">← Automatic extraction runs</Link>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="break-all text-2xl font-semibold text-slate-900 dark:text-white">{detail.fileName}</h1>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">Document status: {candidate.document_status.replaceAll("_", " ")} · Human review: {detail.correctedResult.review_status}</p>
          </div>
          <a href={originalUrl} target="_blank" rel="noopener noreferrer" className="rounded-xl border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800">{nativeFormat ? "Download original" : "Open original"}</a>
        </div>
      </div>

      {error ? <div role="alert" className="rounded-xl border border-rose-300 bg-rose-50 p-3 text-sm text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300">{error}</div> : null}
      {message ? <div role="status" className="rounded-xl border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-700 dark:border-emerald-700/40 dark:bg-emerald-900/20 dark:text-emerald-300">{message}</div> : null}

      <div className="grid gap-5 lg:grid-cols-2 lg:items-start">
      <IdpoCard className="lg:sticky lg:top-6">
        <h2 id="original-source" className="text-lg font-semibold text-slate-900 dark:text-white">Original document</h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{sourceTextCopy.introduction}</p>
        {selectedPageUrl ? <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">Showing PDF page {sourcePage}. <a className="text-cyan-700 underline dark:text-cyan-300" href={selectedPageUrl} target="_blank" rel="noopener noreferrer">Open this page in a new tab</a></p> : null}
        {previewable ? (
          <iframe
            title={`Original document: ${detail.fileName}`}
            src={selectedPageUrl ?? originalUrl}
            sandbox="allow-downloads"
            loading="lazy"
            referrerPolicy="no-referrer"
            className="mt-4 h-[60vh] min-h-[380px] w-full rounded-xl border border-slate-200 bg-white dark:border-slate-700"
          />
        ) : (
          <p className="mt-4 rounded-xl border border-slate-200 p-4 text-sm text-slate-600 dark:border-slate-700 dark:text-slate-300">
            This file type has no in-page preview. Download the original to inspect it.
          </p>
        )}
        <details className="mt-4 rounded-xl border border-slate-200 p-3 dark:border-slate-700">
          <summary className="cursor-pointer text-sm font-medium text-slate-700 dark:text-slate-200">{sourceTextCopy.summary}</summary>
          {detail.parsedDocument ? <p className="mt-2 text-xs text-slate-600 dark:text-slate-300">Native cell addresses point into the unchanged uploaded file. Embedded images, slide notes and email attachments are not read. No cell pixel boxes or field meaning are verified.</p> : null}
          {sourceTextCopy.emptyMessage ? <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">{sourceTextCopy.emptyMessage}</p> : null}
          <div className="mt-3 max-h-80 space-y-3 overflow-auto">
            {detail.sourcePages.map((page) => <section key={page.page}>
              <h3 className="text-xs font-semibold text-slate-700 dark:text-slate-200">{detail.parsedDocument?.units[page.page - 1]?.label ?? `Page ${page.page}`}</h3>
              <pre className="mt-1 whitespace-pre-wrap break-words text-xs text-slate-600 dark:text-slate-300">{page.text || "No text extracted."}</pre>
            </section>)}
          </div>
        </details>
      </IdpoCard>

      {outcome ? <IdpoCard>
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">{outcome.title}</h2>
        <p role="alert" className="mt-3 text-sm font-medium text-rose-700 dark:text-rose-300">{outcome.cause}</p>
        <p className="mt-3 text-sm text-slate-700 dark:text-slate-200">{outcome.action}</p>
        <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">{outcome.sourceNote}</p>
      </IdpoCard> : <IdpoCard>
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Proposed schema and values</h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">Text matched means the value occurs in the extracted text. Image-derived proposals have page hints, not verified pixel locations. Check the original document and field meaning before approving either.</p>
        {detail.visualRoute === "visual" ? <p className="mt-2 text-sm font-medium text-amber-700 dark:text-amber-300">
          Image-derived extraction — review required. This visual route does not produce reusable recipe evidence, even when all proposed values are corrected or confirmed.
        </p> : null}
        {candidate.proposed_schema.length === 0 ? (
          <p className="mt-4 text-sm text-amber-700 dark:text-amber-300">No fields were proposed. Inspect the source and add missed scalar fields or linked columns below.</p>
        ) : (
          <div className="mt-4 space-y-4">
            {candidate.proposed_schema.map((field) => {
              const value = values.get(field.field_id);
              const reviewed = detail.review?.fields.find((item) => item.field_id === field.field_id);
              const row = draft[field.field_id] ?? { decision: "", corrected_value: "", note: "" };
              const linked = field.type === "array[object]";
              const machineCells = linked ? linkedCells(value?.value) : [];
              const fullyGrounded = machineCells.length > 0 && machineCells.every((cell) => cell.status === "accepted" && cell.evidence);
              const visualProposal = isVisualProposal(value);
              const visualLinkedReviewable = visualProposal && visualLinkedCellsReviewable(machineCells, detail.sourcePages);
              return (
                <section key={field.field_id} className="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <h3 className="font-medium text-slate-900 dark:text-white">{field.field_id.replaceAll("_", " ")}</h3>
                      <p className="text-xs text-slate-500 dark:text-slate-400">{field.type}{field.group ? ` · ${field.group}` : ""}</p>
                    </div>
                    <span className={`text-xs font-semibold ${value?.status === "accepted" ? "text-emerald-700 dark:text-emerald-300" : "text-amber-700 dark:text-amber-300"}`}>
                      {machineProposalLabel(value)}
                    </span>
                  </div>
                  {linked ? (
                    <div className="mt-3 overflow-x-auto">
                      <table className="w-full min-w-[560px] text-left text-xs text-slate-700 dark:text-slate-200">
                        <thead><tr className="border-b border-slate-200 dark:border-slate-700">
                          <th className="px-2 py-2">Row</th><th className="px-2 py-2">Proposed cell</th>
                          <th className="px-2 py-2">Status</th><th className="px-2 py-2">Source quote</th>
                        </tr></thead>
                        <tbody>{machineCells.map((cell) => <tr key={cell.row} className="border-b border-slate-100 align-top dark:border-slate-800">
                          <td className="px-2 py-2 tabular-nums">{cell.row + 1}</td>
                          <td className="px-2 py-2 break-words">{cell.value}</td>
                          <td className="px-2 py-2">{cell.visual_grounding_verified === false ? "Image-derived — review required" :
                            cell.status === "accepted" ? "Text matched" : cell.status.replaceAll("_", " ")}</td>
                          <td className="px-2 py-2 break-words">{cell.evidence
                            ? <><span className="font-medium">{detail.parsedDocument?.units[cell.evidence.page - 1]?.label ?? `Page ${cell.evidence.page}`}:</span> <q>{cell.evidence.quote}</q>
                              {cell.evidence.kind === "text_match" ? <span className="mt-1 block text-amber-700 dark:text-amber-300">OCR text match; image position and meaning require review.</span> : null}
                              {nativeContext(detail, cell.evidence) ? <code className="mt-1 block break-all text-[11px]">{nativeContext(detail, cell.evidence)}</code> : null}</>
                            : cell.visual_page ? <><button type="button" onClick={() => showSourcePage(cell.visual_page!)} className="font-medium text-cyan-700 underline dark:text-cyan-300">Page {cell.visual_page} · inspect original</button>
                              <span className="mt-1 block text-amber-700 dark:text-amber-300">No verified pixel location or OCR span</span></>
                              : <span className="text-amber-700 dark:text-amber-300">No verified source span</span>}</td>
                        </tr>)}</tbody>
                      </table>
                      {machineCells.length === 0 ? <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">No linked cells proposed.</p> : null}
                    </div>
                  ) : <p className="mt-3 break-words text-sm text-slate-800 dark:text-slate-200">{displayValue(value?.value)}</p>}
                  {!linked && visualProposal && value?.visual_pages ? <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">
                    Image-derived — review required. Check {value.visual_pages.map((page, index) => <span key={page}>{index > 0 ? ", " : ""}<button type="button" onClick={() => showSourcePage(page)} className="underline">page {page}</button></span>)} in the original document; no pixel location is verified.
                  </p> : null}
                  {reviewed ? (
                    <p className="mt-2 break-words text-xs font-medium text-violet-700 dark:text-violet-300">
                      Human review: {reviewed.decision.replaceAll("_", " ")}{reviewed.corrected_value
                        ? linked ? " · edited linked rows" : ` · ${reviewed.corrected_value}` : ""}
                    </p>
                  ) : null}
                  {!linked && value?.evidence ? (
                    <div className="mt-3 rounded-lg border-l-4 border-cyan-500 bg-cyan-50 p-3 text-sm dark:bg-cyan-900/20">
                      <div className="text-xs font-medium text-cyan-800 dark:text-cyan-200">{value.evidence.kind === "text_match" ? "OCR text match · image still requires review" : "Evidence"} · {detail.parsedDocument?.units[value.evidence.page - 1]?.label ?? `page ${value.evidence.page}`}</div>
                      {nativeContext(detail, value.evidence) ? <code className="mt-1 block break-all text-[11px]">{nativeContext(detail, value.evidence)}</code> : null}
                      <blockquote className="mt-1 whitespace-pre-wrap break-words text-slate-700 dark:text-slate-200">{value.evidence.quote}</blockquote>
                    </div>
                  ) : !linked ? <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">No verified source span.</p> : null}
                  <div className="mt-4 grid gap-3 md:grid-cols-[220px,minmax(0,1fr)]">
                    <label className="text-sm text-slate-700 dark:text-slate-200">Human decision
                      <select value={row.decision} onChange={(event) => updateDraft(field.field_id, { decision: event.target.value as ProductAutoReviewDecision | "" })}
                        className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-2 dark:border-slate-700 dark:bg-slate-950">
                        <option value="">Not reviewed</option>
                        <option value="correct" disabled={linked && !fullyGrounded && !visualLinkedReviewable}>{visualProposal ? "Verified from original image" : "Correct"}</option>
                        <option value="incorrect">Incorrect value</option>
                        <option value="corrected">{linked ? "Correct linked rows" : "Corrected value"}</option>
                        <option value="not_present">Field not present (remove)</option>
                        <option value="remove">Remove spurious field</option>
                      </select>
                    </label>
                    {row.decision === "corrected" && !linked ? <label className="text-sm text-slate-700 dark:text-slate-200">Correct value
                      <input value={row.corrected_value} onChange={(event) => updateDraft(field.field_id, { corrected_value: event.target.value })}
                        className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-2 dark:border-slate-700 dark:bg-slate-950" />
                    </label> : null}
                  </div>
                  {visualLinkedReviewable ? <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">
                    “Verified from original image” confirms every proposed cell in this column after you inspect the original. The page hints do not prove the values or row alignment.
                  </p> : null}
                  {linked && row.decision === "corrected" ? (
                    <div className="mt-3 rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                      <p className="text-xs text-slate-600 dark:text-slate-300">Edit the linked cells by row number. These are human corrections; inspect the original source before saving.</p>
                      <div className="mt-2 overflow-x-auto"><table className="w-full min-w-[400px] text-left text-xs">
                        <thead><tr><th className="p-2">Row</th><th className="p-2">Corrected cell value</th><th className="p-2">Action</th></tr></thead>
                        <tbody>{(linkedDraft[field.field_id] ?? []).map((cell, index) => <tr key={index}>
                          <td className="p-2"><input type="number" min={1} max={128} aria-label={`Corrected row number ${index + 1}`}
                            value={cell.row < 0 ? "" : cell.row + 1}
                            onChange={(event) => updateLinked(field.field_id, index,
                              { row: event.target.value === "" ? -1 : Number(event.target.value) - 1 })}
                            className="w-20 rounded-lg border border-slate-300 bg-white px-2 py-1 tabular-nums dark:border-slate-700 dark:bg-slate-950" /></td>
                          <td className="p-2"><input aria-label={`Row ${cell.row + 1} corrected value`} value={cell.value}
                            onChange={(event) => updateLinked(field.field_id, index, { value: event.target.value })}
                            maxLength={500} className="w-full rounded-lg border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-950" /></td>
                          <td className="p-2"><button type="button" onClick={() => removeLinked(field.field_id, index)}
                            className="text-rose-700 hover:underline dark:text-rose-300">Remove</button></td>
                        </tr>)}</tbody>
                      </table></div>
                      <button type="button" onClick={() => addLinked(field.field_id)} disabled={(linkedDraft[field.field_id] ?? []).length >= 128}
                        className="mt-2 rounded-lg border border-cyan-600 px-3 py-1 text-xs font-medium text-cyan-700 disabled:opacity-50 dark:text-cyan-300">Add row</button>
                    </div>
                  ) : null}
                  <label className="mt-3 block text-sm text-slate-700 dark:text-slate-200">Review note
                    <textarea value={row.note} onChange={(event) => updateDraft(field.field_id, { note: event.target.value })} rows={2} maxLength={2000}
                      className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-2 dark:border-slate-700 dark:bg-slate-950" />
                  </label>
                </section>
              );
            })}
          </div>
        )}
        <div className="mt-5 border-t border-slate-200 pt-5 dark:border-slate-700">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="font-semibold text-slate-900 dark:text-white">Missed scalar fields</h3>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{detail.visualRoute === "visual"
                ? "Inspect the original image, then record the page where you observed each added value. This is a human observation, not verified OCR or pixel evidence."
                : "Each value needs a page and an exact quote from the OCR text. The typed value must appear in that quote."}</p>
            </div>
            <button type="button" disabled={atFieldLimit || detail.sourcePages.length === 0}
              onClick={() => setAddedDraft((current) => [...current, { clientId: crypto.randomUUID(), field_id: "", type: "string", value: "",
                ...(detail.visualRoute === "visual"
                  ? { human_source_page: { kind: "human_observed_page" as const, page: detail.sourcePages[0]?.page ?? 1 } }
                  : { evidence: { page: detail.sourcePages[0]?.page ?? 1, quote: "" } }), note: "" }])}
              className="rounded-lg border border-cyan-600 px-3 py-2 text-sm font-medium text-cyan-700 hover:bg-cyan-50 disabled:cursor-not-allowed disabled:opacity-50 dark:text-cyan-300 dark:hover:bg-cyan-900/20">Add field</button>
          </div>
          <div className="mt-3 space-y-3">
            {addedDraft.filter((field): field is AddedScalarDraft => field.type !== "array[object]").map((field) => (
              <div key={field.clientId} className="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
                <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr),130px]">
                  <label className="text-sm text-slate-700 dark:text-slate-200">Field ID
                    <input value={field.field_id} onChange={(event) => updateAdded(field.clientId, { field_id: event.target.value })} placeholder="invoice_number" maxLength={64}
                      className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-2 dark:border-slate-700 dark:bg-slate-950" />
                  </label>
                  <label className="text-sm text-slate-700 dark:text-slate-200">Type
                    <select value={field.type} onChange={(event) => updateAdded(field.clientId, { type: event.target.value as ProductAutoScalarType, value: "" })}
                      className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-2 dark:border-slate-700 dark:bg-slate-950">
                      <option value="string">Text</option><option value="integer">Integer</option><option value="decimal">Decimal</option><option value="boolean">Boolean</option><option value="date">Date</option>
                    </select>
                  </label>
                </div>
                <label className="mt-3 block text-sm text-slate-700 dark:text-slate-200">Value
                  {field.type === "boolean" ? (
                    <select value={field.value} onChange={(event) => updateAdded(field.clientId, { value: event.target.value })}
                      className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-2 dark:border-slate-700 dark:bg-slate-950">
                      <option value="">Select a value</option><option value="true">True</option><option value="false">False</option>
                    </select>
                  ) : (
                    <input value={field.value} onChange={(event) => updateAdded(field.clientId, { value: event.target.value })} maxLength={10000}
                      inputMode={field.type === "integer" ? "numeric" : field.type === "decimal" ? "decimal" : "text"}
                      className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-2 dark:border-slate-700 dark:bg-slate-950" />
                  )}
                </label>
                {field.human_source_page ? <div className="mt-3 flex flex-wrap items-end gap-3">
                  <label className="text-sm text-slate-700 dark:text-slate-200">Observed in original image · page
                    <select value={field.human_source_page.page} onChange={(event) => updateAdded(field.clientId,
                      { human_source_page: { kind: "human_observed_page", page: Number(event.target.value) } })}
                      className="mt-1 block rounded-lg border border-slate-300 bg-white px-2 py-2 dark:border-slate-700 dark:bg-slate-950">
                      {detail.sourcePages.map((page) => <option key={page.page} value={page.page}>{page.page}</option>)}
                    </select>
                  </label>
                  <button type="button" onClick={() => showSourcePage(field.human_source_page!.page)}
                    className="text-sm text-cyan-700 underline dark:text-cyan-300">View source page</button>
                </div> : <div className="mt-3 grid gap-3 sm:grid-cols-[110px,minmax(0,1fr)]">
                  <label className="text-sm text-slate-700 dark:text-slate-200">OCR page
                    <select value={field.evidence?.page ?? detail.sourcePages[0]?.page ?? 1} onChange={(event) => updateAdded(field.clientId,
                      { evidence: { page: Number(event.target.value), quote: field.evidence?.quote ?? "" } })}
                      className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-2 dark:border-slate-700 dark:bg-slate-950">
                      {detail.sourcePages.map((page) => <option key={page.page} value={page.page}>{page.page}</option>)}
                    </select>
                  </label>
                  <label className="text-sm text-slate-700 dark:text-slate-200">Exact OCR quote
                    <textarea value={field.evidence?.quote ?? ""} onChange={(event) => updateAdded(field.clientId,
                      { evidence: { page: field.evidence?.page ?? detail.sourcePages[0]?.page ?? 1, quote: event.target.value } })} rows={2} maxLength={500}
                      className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-2 dark:border-slate-700 dark:bg-slate-950" />
                  </label>
                </div>}
                <label className="mt-3 block text-sm text-slate-700 dark:text-slate-200">Review note
                  <textarea value={field.note ?? ""} onChange={(event) => updateAdded(field.clientId, { note: event.target.value })} rows={2} maxLength={2000}
                    className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-2 dark:border-slate-700 dark:bg-slate-950" />
                </label>
                <button type="button" onClick={() => setAddedDraft((current) => current.filter((item) => item.clientId !== field.clientId))}
                  className="mt-2 text-sm font-medium text-rose-700 hover:underline dark:text-rose-300">Remove added field</button>
              </div>
            ))}
          </div>
        </div>
        <div className="mt-5 border-t border-slate-200 pt-5 dark:border-slate-700">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h3 className="font-semibold text-slate-900 dark:text-white">Missed linked columns</h3>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{detail.visualRoute === "visual"
                ? "Give related columns the same group and row numbers. Inspect each cell in the original image and record its page; these are reviewer observations, not machine-verified evidence. Image-derived results cannot seed a reusable recipe."
                : "Give related columns the same group and row numbers. Every cell needs a page and a unique exact OCR quote containing its value. A recipe needs at least two columns aligned on each row."}</p>
            </div>
            <button type="button" disabled={atFieldLimit || detail.sourcePages.length === 0}
              onClick={() => setAddedDraft((current) => [...current, { clientId: crypto.randomUUID(), field_id: "",
                type: "array[object]", group: "line_items", value: [{ row: 0, value: "",
                  ...(detail.visualRoute === "visual"
                    ? { human_source_page: { kind: "human_observed_page" as const, page: detail.sourcePages[0]?.page ?? 1 } }
                    : { evidence: { page: detail.sourcePages[0]?.page ?? 1, quote: "" } }) }], note: "" }])}
              className="rounded-lg border border-cyan-600 px-3 py-2 text-sm font-medium text-cyan-700 hover:bg-cyan-50 disabled:cursor-not-allowed disabled:opacity-50 dark:text-cyan-300 dark:hover:bg-cyan-900/20">Add linked column</button>
          </div>
          <div className="mt-3 space-y-3">
            {addedDraft.filter((field): field is AddedLinkedDraft => field.type === "array[object]").map((field) => (
              <div key={field.clientId} className="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="text-sm text-slate-700 dark:text-slate-200">Column field ID
                    <input value={field.field_id} onChange={(event) => updateAddedLinked(field.clientId, { field_id: event.target.value })}
                      placeholder="item_name" maxLength={64}
                      className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-2 dark:border-slate-700 dark:bg-slate-950" />
                  </label>
                  <label className="text-sm text-slate-700 dark:text-slate-200">Linked group
                    <input value={field.group} onChange={(event) => updateAddedLinked(field.clientId, { group: event.target.value })}
                      placeholder="line_items" maxLength={64}
                      className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-2 dark:border-slate-700 dark:bg-slate-950" />
                  </label>
                </div>
                <div className="mt-3 overflow-x-auto"><table className="w-full min-w-[680px] text-left text-xs">
                  <thead><tr><th className="p-2">Row</th><th className="p-2">Cell value</th><th className="p-2">Source page</th><th className="p-2">Source reference</th><th className="p-2">Action</th></tr></thead>
                  <tbody>{field.value.map((cell, index) => <tr key={index} className="align-top">
                    <td className="p-2"><input type="number" min={1} max={128} aria-label={`${field.field_id || "New column"} row number ${index + 1}`}
                      value={cell.row < 0 ? "" : cell.row + 1}
                      onChange={(event) => updateAddedLinkedCell(field.clientId, index,
                        { row: event.target.value === "" ? -1 : Number(event.target.value) - 1 })}
                      className="w-20 rounded-lg border border-slate-300 bg-white px-2 py-1 tabular-nums dark:border-slate-700 dark:bg-slate-950" /></td>
                    <td className="p-2"><input aria-label={`${field.field_id || "New column"} row ${index + 1} value`} value={cell.value}
                      onChange={(event) => updateAddedLinkedCell(field.clientId, index, { value: event.target.value })}
                      maxLength={500} className="w-full rounded-lg border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-950" /></td>
                    <td className="p-2"><select value={cell.human_source_page?.page ?? cell.evidence?.page ?? detail.sourcePages[0]?.page ?? 1}
                      aria-label={`${field.field_id || "New column"} row ${index + 1} ${cell.human_source_page ? "observed image" : "OCR"} page`}
                      onChange={(event) => updateAddedLinkedCell(field.clientId, index, cell.human_source_page
                        ? { human_source_page: { kind: "human_observed_page", page: Number(event.target.value) } }
                        : { evidence: { page: Number(event.target.value), quote: cell.evidence?.quote ?? "" } })}
                      className="rounded-lg border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-950">
                      {detail.sourcePages.map((page) => <option key={page.page} value={page.page}>{page.page}</option>)}
                    </select></td>
                    <td className="p-2">{cell.human_source_page ? <button type="button"
                      onClick={() => showSourcePage(cell.human_source_page!.page)}
                      className="text-cyan-700 underline dark:text-cyan-300">Observed in original image · view page</button>
                      : <textarea value={cell.evidence?.quote ?? ""}
                        aria-label={`${field.field_id || "New column"} row ${index + 1} exact OCR quote`}
                        onChange={(event) => updateAddedLinkedCell(field.clientId, index,
                          { evidence: { page: cell.evidence?.page ?? detail.sourcePages[0]?.page ?? 1,
                            quote: event.target.value } })}
                        rows={2} maxLength={500} className="w-full rounded-lg border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-950" />}</td>
                    <td className="p-2"><button type="button" onClick={() => removeAddedLinkedCell(field.clientId, index)}
                      className="text-rose-700 hover:underline dark:text-rose-300">Remove</button></td>
                  </tr>)}</tbody>
                </table></div>
                <button type="button" onClick={() => addAddedLinkedCell(field.clientId)} disabled={field.value.length >= 128}
                  className="mt-2 rounded-lg border border-cyan-600 px-3 py-1 text-xs font-medium text-cyan-700 disabled:opacity-50 dark:text-cyan-300">Add cell</button>
                <label className="mt-3 block text-sm text-slate-700 dark:text-slate-200">Review note
                  <textarea value={field.note ?? ""} onChange={(event) => updateAddedLinked(field.clientId, { note: event.target.value })}
                    rows={2} maxLength={2000} className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-2 dark:border-slate-700 dark:bg-slate-950" />
                </label>
                <button type="button" onClick={() => setAddedDraft((current) => current.filter((item) => item.clientId !== field.clientId))}
                  className="mt-2 text-sm font-medium text-rose-700 hover:underline dark:text-rose-300">Remove linked column</button>
              </div>
            ))}
          </div>
        </div>
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <button type="button" onClick={() => void save()} disabled={saving}
            className="rounded-xl bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700 disabled:opacity-50">{saving ? "Saving…" : "Save human review"}</button>
          <span className="text-xs text-slate-500 dark:text-slate-400">A review is complete when every proposed field has a decision and added fields have source references. Image page references become approved only with a completed human review; image-derived results cannot seed a reusable recipe.</span>
        </div>
        <label className="mt-4 block max-w-xs text-sm text-slate-700 dark:text-slate-200">Active minutes spent on this save (optional, self-reported)
          <input type="number" min="0.1" max="240" step="0.1" inputMode="decimal"
            value={reportedActiveMinutes} onChange={(event) => setReportedActiveMinutes(event.target.value)}
            className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-2 dark:border-slate-700 dark:bg-slate-950" />
          <span className="mt-1 block text-xs text-slate-500 dark:text-slate-400">Count only your active work since the previous save. Exclude breaks; leave blank if unknown.</span>
        </label>
      </IdpoCard>}
      </div>

      {!outcome ? <IdpoCard>
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Corrected structured result</h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">Derived from the preserved machine candidate and latest saved review. Revision {detail.correctedResult.review_revision}; {detail.correctedResult.review_status}. Existing image-derived linked cells retain their machine status. Added values with a reviewer-observed page record a human decision, not OCR or pixel verification.</p>
        {detail.correctedResult.review_status === "completed" ? (
          <a href={exportUrl} className="mt-3 inline-block rounded-xl bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700">
            Download reviewed JSON
          </a>
        ) : <p className="mt-3 text-sm text-amber-700 dark:text-amber-300">Complete the review to download a structured result.</p>}
        <pre className="mt-3 max-h-96 overflow-auto rounded-lg bg-slate-950 p-4 text-xs text-slate-100">{JSON.stringify(detail.correctedResult, null, 2)}</pre>
      </IdpoCard> : null}

      {detail.auditTrail.length > 0 ? (
        <IdpoCard>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Review history</h2>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">Each save is recorded with the reviewer, time, original machine value, and decision.</p>
          <ol className="mt-4 space-y-3">
            {detail.auditTrail.map((event) => (
              <li key={event.audit_event_id} className="rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-700">
                <div className="font-medium text-slate-900 dark:text-white">Revision {event.revision} · {new Date(event.created_at).toLocaleString()}</div>
                <div className="text-xs text-slate-500 dark:text-slate-400">Reviewer {event.reviewer_user_id}
                  {event.reported_active_review_seconds === undefined ? " · no effort reported" :
                    ` · self-reported active work for this save: ${event.reported_active_review_seconds} seconds`}</div>
                <ul className="mt-2 space-y-1 text-slate-700 dark:text-slate-200">
                  {event.review_fields.map((field) => {
                    const machine = event.machine_fields.find((item) => item.field_id === field.field_id);
                    return <li key={field.field_id} className="break-words">
                      <span className="font-medium">{field.field_id}</span>: {displayValue(machine?.value)} → {field.decision.replaceAll("_", " ")}{field.corrected_value ? `: ${field.corrected_value}` : ""}
                    </li>;
                  })}
                  {(event.review_added_fields ?? event.review_snapshot.added_fields ?? []).map((field) => field.type === "array[object]" ? (
                    <li key={`added-${field.field_id}`} className="break-words">
                      <span className="font-medium">{field.field_id}</span>: added linked column in {field.group}
                      <ul className="ml-4 list-disc">{field.value.map((cell) => <li key={cell.row}>
                        Row {cell.row + 1}: {cell.value}{cell.human_source_page
                          ? ` · reviewer observed original image page ${cell.human_source_page.page}`
                          : cell.evidence ? <> · OCR page {cell.evidence.page}: <q>{cell.evidence.quote}</q></> : " · no source reference"}
                      </li>)}</ul>
                    </li>
                  ) : (
                    <li key={`added-${field.field_id}`} className="break-words"><span className="font-medium">{field.field_id}</span>: added {field.type} value {displayValue(field.value)}
                      {field.human_source_page ? ` · reviewer observed original image page ${field.human_source_page.page}` :
                        field.evidence ? <> · OCR page {field.evidence.page}: <q>{field.evidence.quote}</q></> : " · no source reference"}</li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
        </IdpoCard>
      ) : null}
    </div>
  );
}
