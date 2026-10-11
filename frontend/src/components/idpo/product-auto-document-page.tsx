"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { IdpoCard } from "@/components/idpo/card";
import { idpoApi } from "@/lib/idpo-api";
import type { ProductAutoAddedFieldInput, ProductAutoDocumentDetail, ProductAutoReviewDecision, ProductAutoReviewField, ProductAutoScalarType } from "@/types/product-auto";

type Draft = Record<string, { decision: ProductAutoReviewDecision | ""; corrected_value: string; note: string }>;
type AddedDraft = ProductAutoAddedFieldInput & { clientId: string };

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return "No value proposed";
  if (typeof value === "string") return value || "Empty string";
  return JSON.stringify(value);
}

export function ProductAutoDocumentPage() {
  const params = useParams<{ jobId: string; runId: string; docId: string }>();
  const jobId = decodeURIComponent(params.jobId);
  const runId = decodeURIComponent(params.runId);
  const docId = decodeURIComponent(params.docId);
  const [detail, setDetail] = useState<ProductAutoDocumentDetail | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const [addedDraft, setAddedDraft] = useState<AddedDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    let current = true;
    void idpoApi.getProductAutoDocument(jobId, runId, docId).then((data) => {
      if (!current) return;
      setDetail(data);
      const reviews = new Map(data.review?.fields.map((field) => [field.field_id, field]) ?? []);
      setDraft(Object.fromEntries(data.candidate.proposed_schema.map((field) => {
        const review = reviews.get(field.field_id);
        return [field.field_id, { decision: review?.decision ?? "", corrected_value: review?.corrected_value ?? "", note: review?.note ?? "" }];
      })));
      setAddedDraft((data.review?.added_fields ?? []).map((field) => ({ ...field, value: String(field.value), clientId: field.field_id })));
    }).catch((cause) => {
      if (current) setError(cause instanceof Error ? cause.message : "Failed to load extraction result.");
    }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [jobId, runId, docId]);

  function updateDraft(fieldId: string, patch: Partial<Draft[string]>) {
    setDraft((current) => ({ ...current, [fieldId]: { ...current[fieldId], ...patch } }));
    setMessage("");
  }

  function updateAdded(clientId: string, patch: Partial<AddedDraft>) {
    setAddedDraft((current) => current.map((field) => field.clientId === clientId ? { ...field, ...patch } : field));
    setMessage("");
  }

  async function save() {
    if (!detail) return;
    const fields: ProductAutoReviewField[] = detail.candidate.proposed_schema.flatMap((field) => {
      const row = draft[field.field_id];
      if (!row?.decision) return [];
      return [{ field_id: field.field_id, decision: row.decision,
        corrected_value: row.decision === "corrected" ? row.corrected_value : null,
        note: row.note || null }];
    });
    setSaving(true);
    setError("");
    try {
      const addedFields: ProductAutoAddedFieldInput[] = addedDraft.map(({ field_id, type, value, note }) => ({ field_id, type, value, note }));
      const result = await idpoApi.saveProductAutoReview(jobId, runId, docId, detail.review?.revision ?? 0, fields, addedFields);
      const refreshed = await idpoApi.getProductAutoDocument(jobId, runId, docId);
      setDetail(refreshed);
      setAddedDraft((refreshed.review?.added_fields ?? []).map((field) => ({ ...field, value: String(field.value), clientId: field.field_id })));
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
  const values = new Map(candidate.extracted_values.map((item) => [item.field_id, item]));
  const originalUrl = `/api/jobs/${encodeURIComponent(jobId)}/docs/${encodeURIComponent(detail.fileId)}/content`;
  const previewable = /\.(pdf|png|jpe?g|txt|json)$/i.test(detail.fileName);

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div>
        <Link href={`/dashboard/idpo/jobs/${encodeURIComponent(jobId)}/auto`} className="text-sm font-medium text-cyan-700 dark:text-cyan-300">← Automatic extraction runs</Link>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="break-all text-2xl font-semibold text-slate-900 dark:text-white">{detail.fileName}</h1>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">Document status: {candidate.document_status.replaceAll("_", " ")} · Human review: {detail.review?.status ?? "unreviewed"}</p>
          </div>
          <a href={originalUrl} target="_blank" rel="noopener noreferrer" className="rounded-xl border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800">Open original</a>
        </div>
      </div>

      {error ? <div role="alert" className="rounded-xl border border-rose-300 bg-rose-50 p-3 text-sm text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300">{error}</div> : null}
      {message ? <div role="status" className="rounded-xl border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-700 dark:border-emerald-700/40 dark:bg-emerald-900/20 dark:text-emerald-300">{message}</div> : null}

      <div className="grid gap-5 lg:grid-cols-2 lg:items-start">
      <IdpoCard className="lg:sticky lg:top-6">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Original document</h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">Compare each proposed value and quote against the uploaded source.</p>
        {previewable ? (
          <iframe
            title={`Original document: ${detail.fileName}`}
            src={originalUrl}
            sandbox="allow-downloads"
            loading="lazy"
            referrerPolicy="no-referrer"
            className="mt-4 h-[60vh] min-h-[380px] w-full rounded-xl border border-slate-200 bg-white dark:border-slate-700"
          />
        ) : (
          <p className="mt-4 rounded-xl border border-slate-200 p-4 text-sm text-slate-600 dark:border-slate-700 dark:text-slate-300">
            This file type has no in-page preview. Open the original to inspect it.
          </p>
        )}
      </IdpoCard>

      <IdpoCard>
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Proposed schema and values</h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">Accepted values have exact text evidence. Other values need review or are missing.</p>
        {candidate.proposed_schema.length === 0 ? (
          <p className="mt-4 text-sm text-amber-700 dark:text-amber-300">No fields were proposed. Inspect the source and add any missed scalar fields below.</p>
        ) : (
          <div className="mt-4 space-y-4">
            {candidate.proposed_schema.map((field) => {
              const value = values.get(field.field_id);
              const reviewed = detail.review?.fields.find((item) => item.field_id === field.field_id);
              const row = draft[field.field_id] ?? { decision: "", corrected_value: "", note: "" };
              return (
                <section key={field.field_id} className="rounded-xl border border-slate-200 p-4 dark:border-slate-700">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <h3 className="font-medium text-slate-900 dark:text-white">{field.field_id.replaceAll("_", " ")}</h3>
                      <p className="text-xs text-slate-500 dark:text-slate-400">{field.type}{field.group ? ` · ${field.group}` : ""}</p>
                    </div>
                    <span className={`text-xs font-semibold ${value?.status === "accepted" ? "text-emerald-700 dark:text-emerald-300" : "text-amber-700 dark:text-amber-300"}`}>
                      {value?.status?.replaceAll("_", " ") ?? "no value"}
                    </span>
                  </div>
                  <p className="mt-3 break-words text-sm text-slate-800 dark:text-slate-200">{displayValue(value?.value)}</p>
                  {reviewed ? (
                    <p className="mt-2 break-words text-xs font-medium text-violet-700 dark:text-violet-300">
                      Human review: {reviewed.decision.replaceAll("_", " ")}{reviewed.corrected_value ? ` · ${reviewed.corrected_value}` : ""}
                    </p>
                  ) : null}
                  {value?.evidence ? (
                    <div className="mt-3 rounded-lg border-l-4 border-cyan-500 bg-cyan-50 p-3 text-sm dark:bg-cyan-900/20">
                      <div className="text-xs font-medium text-cyan-800 dark:text-cyan-200">Evidence · page {value.evidence.page}</div>
                      <blockquote className="mt-1 whitespace-pre-wrap break-words text-slate-700 dark:text-slate-200">{value.evidence.quote}</blockquote>
                    </div>
                  ) : <p className="mt-2 text-xs text-slate-500 dark:text-slate-400">No verified source span.</p>}
                  <div className="mt-4 grid gap-3 md:grid-cols-[220px,minmax(0,1fr)]">
                    <label className="text-sm text-slate-700 dark:text-slate-200">Human decision
                      <select value={row.decision} onChange={(event) => updateDraft(field.field_id, { decision: event.target.value as ProductAutoReviewDecision | "" })}
                        className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-2 dark:border-slate-700 dark:bg-slate-950">
                        <option value="">Not reviewed</option>
                        <option value="correct">Correct</option>
                        <option value="incorrect">Incorrect value</option>
                        <option value="corrected">Corrected value</option>
                        <option value="not_present">Field not present (remove)</option>
                        <option value="remove">Remove spurious field</option>
                      </select>
                    </label>
                    {row.decision === "corrected" ? <label className="text-sm text-slate-700 dark:text-slate-200">Correct value
                      <input value={row.corrected_value} onChange={(event) => updateDraft(field.field_id, { corrected_value: event.target.value })}
                        className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-2 py-2 dark:border-slate-700 dark:bg-slate-950" />
                    </label> : null}
                  </div>
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
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Added values come from your document review. They have no machine evidence span.</p>
            </div>
            <button type="button" onClick={() => setAddedDraft((current) => [...current, { clientId: crypto.randomUUID(), field_id: "", type: "string", value: "", note: "" }])}
              className="rounded-lg border border-cyan-600 px-3 py-2 text-sm font-medium text-cyan-700 hover:bg-cyan-50 dark:text-cyan-300 dark:hover:bg-cyan-900/20">Add field</button>
          </div>
          <div className="mt-3 space-y-3">
            {addedDraft.map((field) => (
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
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <button type="button" onClick={() => void save()} disabled={saving}
            className="rounded-xl bg-cyan-600 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700 disabled:opacity-50">{saving ? "Saving…" : "Save human review"}</button>
          <span className="text-xs text-slate-500 dark:text-slate-400">A review is complete when every proposed field has a decision. This adjudicates this document only; it does not approve a reusable recipe.</span>
        </div>
      </IdpoCard>
      </div>

      <IdpoCard>
        <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Corrected structured result</h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">Derived from the preserved machine candidate and latest saved review. Revision {detail.correctedResult.review_revision}; {detail.correctedResult.review_status}.</p>
        <pre className="mt-3 max-h-96 overflow-auto rounded-lg bg-slate-950 p-4 text-xs text-slate-100">{JSON.stringify(detail.correctedResult, null, 2)}</pre>
      </IdpoCard>

      {detail.auditTrail.length > 0 ? (
        <IdpoCard>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Review history</h2>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">Each save is recorded with the reviewer, time, original machine value, and decision.</p>
          <ol className="mt-4 space-y-3">
            {detail.auditTrail.map((event) => (
              <li key={event.audit_event_id} className="rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-700">
                <div className="font-medium text-slate-900 dark:text-white">Revision {event.revision} · {new Date(event.created_at).toLocaleString()}</div>
                <div className="text-xs text-slate-500 dark:text-slate-400">Reviewer {event.reviewer_user_id}</div>
                <ul className="mt-2 space-y-1 text-slate-700 dark:text-slate-200">
                  {event.review_fields.map((field) => {
                    const machine = event.machine_fields.find((item) => item.field_id === field.field_id);
                    return <li key={field.field_id} className="break-words">
                      <span className="font-medium">{field.field_id}</span>: {displayValue(machine?.value)} → {field.decision.replaceAll("_", " ")}{field.corrected_value ? `: ${field.corrected_value}` : ""}
                    </li>;
                  })}
                  {(event.review_added_fields ?? event.review_snapshot.added_fields ?? []).map((field) => (
                    <li key={`added-${field.field_id}`} className="break-words"><span className="font-medium">{field.field_id}</span>: added {field.type} value {displayValue(field.value)}</li>
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
