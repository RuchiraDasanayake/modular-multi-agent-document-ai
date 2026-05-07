import { useEffect, useState } from "react";
import { Button, Card, CardContent } from "@/components/ui";
import {
  createReviewRecord,
  DocumentOut,
  getDocumentJson,
  listReviewRecords,
  getLatestReviewRecord,
  ReviewDecision,
  ReviewRecordCreate,
  ReviewRecordOut,
  RunDocumentOut,
} from "@/lib/docaiApi";

type ReviewFieldRow = {
  field_name: string;
  extracted_value: string;
  evidence_text: string;
  validation_status: string;
  decision: ReviewDecision;
  corrected_value: string;
};

type MissedFieldRow = {
  field_name: string;
  corrected_value: string;
};

function formatTimestamp(value?: string | null): string {
  if (!value) return "-";
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return value;
  return new Date(parsed).toLocaleString();
}

function formatFieldCell(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "string") return value.length > 0 ? value : "-";
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function readIsStub(payload: unknown): boolean | null {
  if (typeof payload !== "object" || payload === null || !("is_stub" in payload)) return null;
  const value = (payload as { is_stub?: unknown }).is_stub;
  return typeof value === "boolean" ? value : null;
}

function readFinalOutputReviewRows(payload: unknown): ReviewFieldRow[] {
  if (typeof payload !== "object" || payload === null) return [];
  const rootFields = (payload as { fields?: unknown }).fields;
  const nestedFinalOutput = (payload as { final_output?: unknown }).final_output;
  const nestedFields =
    typeof nestedFinalOutput === "object" && nestedFinalOutput !== null
      ? (nestedFinalOutput as { fields?: unknown }).fields
      : undefined;
  const fields = rootFields ?? nestedFields;
  if (!Array.isArray(fields)) return [];

  return fields
    .map((field) => (typeof field === "object" && field !== null ? (field as Record<string, unknown>) : null))
    .filter((field): field is Record<string, unknown> => !!field)
    .map((field) => ({
      field_name: formatFieldCell(field.field_name) === "-" ? "" : formatFieldCell(field.field_name),
      extracted_value: formatFieldCell(field.value),
      evidence_text: formatFieldCell(field.evidence_text),
      validation_status: formatFieldCell(field.validation_status),
      decision: "correct" as ReviewDecision,
      corrected_value: "",
    }))
    .filter((row) => row.field_name.trim().length > 0);
}

interface ReviewPanelProps {
  selectedRunId: string | null;
  runDocuments: RunDocumentOut[];
  documentNameById: Map<string, string>;
  runDocumentsLoading: boolean;
  runDocumentsError: string | null;
}

export default function ReviewPanel({
  selectedRunId,
  runDocuments,
  documentNameById,
  runDocumentsLoading,
  runDocumentsError,
}: ReviewPanelProps) {
  const [reviewDocumentId, setReviewDocumentId] = useState<string | null>(null);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [reviewLoadError, setReviewLoadError] = useState<string | null>(null);
  const [reviewPayload, setReviewPayload] = useState<unknown>(null);
  const [reviewRows, setReviewRows] = useState<ReviewFieldRow[]>([]);
  const [missedFieldRows, setMissedFieldRows] = useState<MissedFieldRow[]>([]);
  const [reviewNote, setReviewNote] = useState("");
  const [reviewSubmitLoading, setReviewSubmitLoading] = useState(false);
  const [reviewSubmitError, setReviewSubmitError] = useState<string | null>(null);
  const [reviewSubmitMessage, setReviewSubmitMessage] = useState<string | null>(null);
  const [reviewHistoryLoading, setReviewHistoryLoading] = useState(false);
  const [reviewHistoryError, setReviewHistoryError] = useState<string | null>(null);
  const [reviewHistory, setReviewHistory] = useState<ReviewRecordOut[]>([]);
  const [latestReviewRecord, setLatestReviewRecord] = useState<ReviewRecordOut | null>(null);

  useEffect(() => {
    setReviewDocumentId(null);
    setReviewPayload(null);
    setReviewRows([]);
    setReviewLoadError(null);
    setReviewSubmitError(null);
    setReviewSubmitMessage(null);
    setReviewHistory([]);
    setLatestReviewRecord(null);
  }, [selectedRunId]);

  async function loadReviewHistory(documentId: string) {
    if (!selectedRunId) return;
    setReviewHistoryLoading(true);
    setReviewHistoryError(null);
    try {
      const [history, latest] = await Promise.all([
        listReviewRecords(selectedRunId, documentId),
        getLatestReviewRecord(selectedRunId, documentId),
      ]);
      setReviewHistory(history);
      setLatestReviewRecord(latest);
    } catch (e) {
      setReviewHistory([]);
      setLatestReviewRecord(null);
      setReviewHistoryError(e instanceof Error ? e.message : "Failed to load correction history.");
    } finally {
      setReviewHistoryLoading(false);
    }
  }

  async function loadReviewDocument(documentId: string) {
    if (!selectedRunId) return;
    setReviewDocumentId(documentId);
    setReviewLoading(true);
    setReviewLoadError(null);
    setReviewSubmitError(null);
    setReviewSubmitMessage(null);
    try {
      const payload = await getDocumentJson(selectedRunId, documentId, "final-output");
      setReviewPayload(payload);
      setReviewRows(readFinalOutputReviewRows(payload));
      setMissedFieldRows([]);
      setReviewNote("");
      await loadReviewHistory(documentId);
    } catch (e) {
      setReviewPayload(null);
      setReviewRows([]);
      setMissedFieldRows([]);
      setReviewHistory([]);
      setLatestReviewRecord(null);
      setReviewLoadError(e instanceof Error ? e.message : "Failed to load final output for review.");
    } finally {
      setReviewLoading(false);
    }
  }

  function updateReviewDecision(index: number, decision: ReviewDecision) {
    setReviewRows((prev) =>
      prev.map((row, idx) =>
        idx === index ? { ...row, decision, corrected_value: decision === "wrong_value" ? row.corrected_value : "" } : row,
      ),
    );
  }

  function updateReviewCorrectedValue(index: number, correctedValue: string) {
    setReviewRows((prev) =>
      prev.map((row, idx) => (idx === index ? { ...row, corrected_value: correctedValue } : row)),
    );
  }

  async function saveReviewRecord() {
    if (!selectedRunId || !reviewDocumentId) return;
    setReviewSubmitError(null);
    setReviewSubmitMessage(null);

    const errors: string[] = [];
    const corrections: ReviewRecordCreate["corrections"] = [];

    reviewRows.forEach((row) => {
      const fieldName = row.field_name.trim();
      if (!fieldName) {
        errors.push("Each review row must include a field_name.");
        return;
      }
      if (row.decision === "wrong_value") {
        const correctedValue = row.corrected_value.trim();
        if (!correctedValue) {
          errors.push(`wrong_value requires corrected_value for field "${fieldName}".`);
          return;
        }
        corrections.push({ field_name: fieldName, decision: row.decision, corrected_value: correctedValue });
        return;
      }
      corrections.push({ field_name: fieldName, decision: row.decision });
    });

    missedFieldRows.forEach((row) => {
      const fieldName = row.field_name.trim();
      const correctedValue = row.corrected_value.trim();
      if (!fieldName && !correctedValue) return;
      if (!fieldName || !correctedValue) {
        errors.push("missed_field requires both field_name and corrected_value.");
        return;
      }
      corrections.push({ field_name: fieldName, decision: "missed_field", corrected_value: correctedValue });
    });

    if (errors.length > 0) {
      setReviewSubmitError(errors.join(" "));
      return;
    }

    const hasCorrection = corrections.some(
      (correction) =>
        correction.decision === "wrong_value" ||
        correction.decision === "missed_field" ||
        correction.decision === "hallucinated_field",
    );

    const payload: ReviewRecordCreate = {
      reviewer_id: "local_operator",
      review_status: hasCorrection ? "corrected" : "reviewed",
      review_note: reviewNote.trim() || undefined,
      corrections,
    };

    setReviewSubmitLoading(true);
    try {
      await createReviewRecord(selectedRunId, reviewDocumentId, payload);
      await loadReviewHistory(reviewDocumentId);
      setReviewSubmitMessage("Review saved. Corrections recorded.");
    } catch (e) {
      setReviewSubmitError(e instanceof Error ? e.message : "Failed to save review record.");
    } finally {
      setReviewSubmitLoading(false);
    }
  }

  if (!selectedRunId) {
    return (
      <Card className="border border-amber-500/30 bg-amber-500/10">
        <CardContent className="p-4 text-sm text-amber-300">
          Select a run in the Runs tab to review extraction evidence.
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card className="border-white/5">
        <CardContent className="p-4 space-y-3">
          <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Load Final Output for Review</p>
          <p className="text-xs text-slate-400 font-mono">run_id: {selectedRunId}</p>
          {runDocumentsLoading && <p className="text-sm text-slate-400">Loading run documents...</p>}
          {runDocumentsError && <p className="text-sm text-red-300">{runDocumentsError}</p>}
          {!runDocumentsLoading && !runDocumentsError && runDocuments.length === 0 && (
            <p className="text-sm text-slate-400">No run documents available.</p>
          )}
          {!runDocumentsLoading && !runDocumentsError && runDocuments.length > 0 && (
            <div className="space-y-2">
              {runDocuments.map((rd) => {
                const active = reviewDocumentId === rd.document_id;
                return (
                  <div key={rd.run_document_id} className="border border-white/10 rounded p-3">
                    <p className="text-xs font-mono text-slate-200 break-all">{documentNameById.get(rd.document_id) || rd.document_id}</p>
                    <p className="text-[11px] text-slate-500 font-mono">document_id: {rd.document_id} | status: {rd.status}</p>
                    <div className="mt-2"><Button variant="outline" size="sm" onClick={() => void loadReviewDocument(rd.document_id)}>Load Final Output for Review</Button></div>
                    {active && reviewLoading && <p className="text-xs text-slate-400 mt-2">Loading final_output.json...</p>}
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {reviewDocumentId && reviewPayload && (
        <Card className="border-white/5">
          <CardContent className="p-4 space-y-3">
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Human Review Evidence</p>
            <p className="text-xs text-slate-400 font-mono">document_id: {reviewDocumentId}</p>
            {readIsStub(reviewPayload) === true && (
              <div className="rounded border border-amber-500/40 bg-amber-500/10 p-3 space-y-1">
                <p className="text-xs font-semibold text-amber-300">Stub runtime output — review records saved here are workflow tests, not real extraction assessment.</p>
              </div>
            )}
            {reviewRows.length === 0 ? (
              <p className="text-sm text-slate-400">No extracted fields found in final_output.fields for this document.</p>
            ) : (
              <div className="space-y-4">
                <div className="overflow-x-auto rounded-lg border border-white/5">
                  <table className="w-full text-sm text-left border-collapse">
                    <thead className="bg-slate-900/80 border-b border-white/5 text-slate-400 uppercase text-[10px] tracking-wider">
                      <tr>
                        <th className="px-4 py-3 font-semibold">field_name</th>
                        <th className="px-4 py-3 font-semibold">extracted_value</th>
                        <th className="px-4 py-3 font-semibold">evidence_text</th>
                        <th className="px-4 py-3 font-semibold">validation_status</th>
                        <th className="px-4 py-3 font-semibold">decision</th>
                        <th className="px-4 py-3 font-semibold">corrected_value</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5 bg-slate-800/30">
                      {reviewRows.map((row, idx) => (
                        <tr key={`${row.field_name}-${idx}`} className="hover:bg-slate-800/50 transition-colors">
                          <td className="px-4 py-3 text-slate-300 text-xs">{row.field_name}</td>
                          <td className="px-4 py-3 text-slate-200 text-xs">{row.extracted_value}</td>
                          <td className="px-4 py-3 text-slate-200 text-xs">{row.evidence_text}</td>
                          <td className="px-4 py-3 text-slate-200 text-xs">{row.validation_status}</td>
                          <td className="px-4 py-3">
                            <select
                              value={row.decision}
                              onChange={(e) => updateReviewDecision(idx, e.target.value as ReviewDecision)}
                              className="bg-slate-700 border border-slate-600 rounded px-2 py-1 text-xs text-slate-200"
                            >
                              <option value="correct">correct</option>
                              <option value="wrong_value">wrong_value</option>
                              <option value="hallucinated_field">hallucinated_field</option>
                              <option value="correctly_skipped">correctly_skipped</option>
                            </select>
                          </td>
                          <td className="px-4 py-3">
                            <input
                              type="text"
                              value={row.corrected_value}
                              onChange={(e) => updateReviewCorrectedValue(idx, e.target.value)}
                              disabled={row.decision !== "wrong_value"}
                              className="bg-slate-700 border border-slate-600 rounded px-2 py-1 text-xs text-slate-200 w-full disabled:opacity-50"
                              placeholder={row.decision === "wrong_value" ? "Enter corrected value" : ""}
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="border-t border-white/5 pt-4">
                  <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">Add Missed Field</p>
                  <div className="flex gap-2 items-end">
                    <div className="flex-1">
                      <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">field_name</label>
                      <input
                        type="text"
                        value={missedFieldRows.length > 0 ? missedFieldRows[0].field_name : ""}
                        onChange={(e) => setMissedFieldRows([{ field_name: e.target.value, corrected_value: missedFieldRows[0]?.corrected_value || "" }])}
                        className="bg-slate-700 border border-slate-600 rounded px-2 py-1 text-xs text-slate-200 w-full"
                        placeholder="Enter field name"
                      />
                    </div>
                    <div className="flex-1">
                      <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">corrected_value</label>
                      <input
                        type="text"
                        value={missedFieldRows.length > 0 ? missedFieldRows[0].corrected_value : ""}
                        onChange={(e) => setMissedFieldRows([{ field_name: missedFieldRows[0]?.field_name || "", corrected_value: e.target.value }])}
                        className="bg-slate-700 border border-slate-600 rounded px-2 py-1 text-xs text-slate-200 w-full"
                        placeholder="Enter corrected value"
                      />
                    </div>
                    <div className="text-xs text-slate-400">decision: missed_field</div>
                  </div>
                </div>

                <div className="border-t border-white/5 pt-4 space-y-3">
                  <div>
                    <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Review Note (Optional)</label>
                    <textarea
                      value={reviewNote}
                      onChange={(e) => setReviewNote(e.target.value)}
                      className="bg-slate-700 border border-slate-600 rounded px-2 py-1 text-xs text-slate-200 w-full"
                      rows={2}
                      placeholder="Optional notes about this review"
                    />
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => void saveReviewRecord()}
                      disabled={reviewSubmitLoading}
                    >
                      {reviewSubmitLoading ? "Saving..." : "Save Review Record"}
                    </Button>
                  </div>
                  {reviewSubmitError && <p className="text-xs text-red-300">{reviewSubmitError}</p>}
                  {reviewSubmitMessage && <p className="text-xs text-green-300">{reviewSubmitMessage}</p>}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {reviewDocumentId && (
        <Card className="border-white/5">
          <CardContent className="p-4 space-y-3">
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Review History</p>
            <p className="text-xs text-slate-400 font-mono">document_id: {reviewDocumentId}</p>
            {reviewHistoryLoading && <p className="text-sm text-slate-400">Loading review history...</p>}
            {reviewHistoryError && <p className="text-sm text-red-300">{reviewHistoryError}</p>}
            {!reviewHistoryLoading && !reviewHistoryError && (
              <>
                {latestReviewRecord && (
                  <div className="space-y-2">
                    <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Latest Review Record</p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                      <div><p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">review_id</p><p className="text-slate-200 font-mono break-all">{latestReviewRecord.review_id}</p></div>
                      <div><p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">review_status</p><p className="text-slate-200">{latestReviewRecord.review_status}</p></div>
                      <div><p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">reviewer_id</p><p className="text-slate-200">{latestReviewRecord.reviewer_id || "-"}</p></div>
                      <div><p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">created_at</p><p className="text-slate-200">{formatTimestamp(latestReviewRecord.created_at)}</p></div>
                      <div className="md:col-span-2"><p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">corrections</p><p className="text-slate-200">{latestReviewRecord.corrections.length} corrections</p></div>
                      {latestReviewRecord.review_note && (
                        <div className="md:col-span-2"><p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">review_note</p><p className="text-slate-200 break-all">{latestReviewRecord.review_note}</p></div>
                      )}
                    </div>
                  </div>
                )}
                {reviewHistory.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">All Review Records ({reviewHistory.length})</p>
                    <div className="space-y-1">
                      {reviewHistory.map((record) => (
                        <div key={record.review_id} className="border border-white/10 rounded p-2 text-xs">
                          <p className="font-mono text-slate-300">{record.review_id}</p>
                          <p className="text-slate-400">status: {record.review_status} | reviewer: {record.reviewer_id || "-"} | corrections: {record.corrections.length} | {formatTimestamp(record.created_at)}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {reviewHistory.length === 0 && !latestReviewRecord && <p className="text-sm text-slate-400">No review records found for this document.</p>}
              </>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
