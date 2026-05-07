import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AlertCircle, Download } from "lucide-react";
import { Button, Card, CardContent } from "@/components/ui";
import {
  getDocumentJson,
  getLatestReviewRecord,
  listRunDocuments,
  DocumentOut,
  RunDocumentOut,
  ReviewRecordOut,
} from "@/lib/docaiApi";

interface DocumentWithResults {
  document_id: string;
  filename: string;
  status: string;
  final_output: unknown;
  latest_review: ReviewRecordOut | null;
  final_output_error: string | null;
  is_stub: boolean;
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

function readIsStub(payload: unknown): boolean {
  if (typeof payload !== "object" || payload === null || !("is_stub" in payload)) return false;
  const value = (payload as { is_stub?: unknown }).is_stub;
  return typeof value === "boolean" ? value : false;
}

function extractFieldNames(payload: unknown): Set<string> {
  if (typeof payload !== "object" || payload === null) return new Set();
  const rootFields = (payload as { fields?: unknown }).fields;
  const nestedFinalOutput = (payload as { final_output?: unknown }).final_output;
  const nestedFields =
    typeof nestedFinalOutput === "object" && nestedFinalOutput !== null
      ? (nestedFinalOutput as { fields?: unknown }).fields
      : undefined;
  const fields = rootFields ?? nestedFields;
  if (!Array.isArray(fields)) return new Set();
  return new Set(
    fields
      .map((f) =>
        typeof f === "object" && f !== null ? formatFieldCell((f as { field_name?: unknown }).field_name) : "-",
      )
      .filter((f) => f !== "-"),
  );
}

function getFieldValue(payload: unknown, fieldName: string): string {
  if (typeof payload !== "object" || payload === null) return "-";
  const rootFields = (payload as { fields?: unknown }).fields;
  const nestedFinalOutput = (payload as { final_output?: unknown }).final_output;
  const nestedFields =
    typeof nestedFinalOutput === "object" && nestedFinalOutput !== null
      ? (nestedFinalOutput as { fields?: unknown }).fields
      : undefined;
  const fields = rootFields ?? nestedFields;
  if (!Array.isArray(fields)) return "-";
  const field = fields.find(
    (f) => typeof f === "object" && f !== null && formatFieldCell((f as { field_name?: unknown }).field_name) === fieldName,
  );
  if (!field || typeof field !== "object") return "-";
  return formatFieldCell((field as { value?: unknown }).value);
}

interface ResultsTableTabProps {
  selectedRunId: string | null;
  documents: DocumentOut[];
  project_id: string | undefined;
  job_id: string | undefined;
}

export default function ResultsTableTab({
  selectedRunId,
  documents,
  project_id,
  job_id,
}: ResultsTableTabProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resultsData, setResultsData] = useState<DocumentWithResults[]>([]);

  const fieldNames = useMemo(
    () => {
      const names = new Set<string>();
      resultsData.forEach((doc) => {
        extractFieldNames(doc.final_output).forEach((name) => names.add(name));
      });
      return Array.from(names).sort();
    },
    [resultsData],
  );

  const hasStub = useMemo(() => resultsData.some((doc) => doc.is_stub), [resultsData]);

  useEffect(() => {
    if (!selectedRunId) {
      setResultsData([]);
      setError(null);
      setLoading(false);
      return;
    }

    const loadResults = async () => {
      setLoading(true);
      setError(null);
      try {
        const runDocs = await listRunDocuments(selectedRunId);

        const results: DocumentWithResults[] = [];
        for (const runDoc of runDocs) {
          const doc = documents.find((d) => d.document_id === runDoc.document_id);
          const docName = doc?.original_filename || runDoc.document_id;

          let finalOutputPayload: unknown = null;
          let finalOutputError: string | null = null;
          try {
            finalOutputPayload = await getDocumentJson(selectedRunId, runDoc.document_id, "final-output");
          } catch (e) {
            finalOutputError = e instanceof Error ? e.message : "Failed to load final output";
          }

          let latestReview: ReviewRecordOut | null = null;
          try {
            latestReview = await getLatestReviewRecord(selectedRunId, runDoc.document_id);
          } catch {
            // 404 or error is expected if not reviewed yet
          }

          results.push({
            document_id: runDoc.document_id,
            filename: docName,
            status: runDoc.status,
            final_output: finalOutputPayload,
            latest_review: latestReview,
            final_output_error: finalOutputError,
            is_stub: readIsStub(finalOutputPayload),
          });
        }

        setResultsData(results);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load results");
      } finally {
        setLoading(false);
      }
    };

    void loadResults();
  }, [selectedRunId, documents]);

  function exportCsv() {
    if (resultsData.length === 0) return;

    const headers = ["Document ID", "Filename", "Status", "Review Status", ...fieldNames];
    const rows: string[][] = [];

    resultsData.forEach((doc) => {
      const values = [
        doc.document_id,
        doc.filename,
        doc.status,
        doc.latest_review?.review_status ?? "not reviewed",
      ];
      fieldNames.forEach((fieldName) => {
        values.push(getFieldValue(doc.final_output, fieldName));
      });
      rows.push(values);
    });

    // Escape CSV values
    const escapedHeaders = headers.map((h) => `"${h.replace(/"/g, '""')}"`).join(",");
    const escapedRows = rows
      .map((row) => row.map((v) => `"${v.replace(/"/g, '""')}"`).join(","))
      .join("\n");
    const csv = `${escapedHeaders}\n${escapedRows}`;

    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.setAttribute("href", url);
    link.setAttribute("download", "results.csv");
    link.style.visibility = "hidden";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  function exportJson() {
    if (resultsData.length === 0) return;

    const exportData = resultsData.map((doc) => {
      const row: Record<string, unknown> = {
        document_id: doc.document_id,
        filename: doc.filename,
        status: doc.status,
        review_status: doc.latest_review?.review_status ?? "not reviewed",
      };
      fieldNames.forEach((fieldName) => {
        row[fieldName] = getFieldValue(doc.final_output, fieldName);
      });
      return row;
    });

    const json = JSON.stringify(exportData, null, 2);
    const blob = new Blob([json], { type: "application/json;charset=utf-8;" });
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.setAttribute("href", url);
    link.setAttribute("download", "results.json");
    link.style.visibility = "hidden";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  }

  if (!selectedRunId) {
    return (
      <Card className="border border-amber-500/30 bg-amber-500/10">
        <CardContent className="p-4 text-sm text-amber-300">
          Select a run in the Runs tab to view structured results.
        </CardContent>
      </Card>
    );
  }

  if (loading) {
    return (
      <Card className="p-6 text-center text-slate-400">
        Loading results for {resultsData.length} document(s)...
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="border border-red-500/30 bg-red-500/10 p-4">
        <p className="text-red-300 text-sm">{error}</p>
      </Card>
    );
  }

  if (resultsData.length === 0) {
    return (
      <Card className="p-6 text-sm text-slate-400">
        No documents in this run.
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {hasStub && (
        <Card className="border-amber-500/30 bg-amber-500/10">
          <CardContent className="p-4 flex items-start gap-3">
            <AlertCircle className="h-5 w-5 text-amber-400 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-semibold text-amber-300">Stub Runtime Output</p>
              <p className="text-xs text-amber-200">One or more results contain stub output. Use for testing only.</p>
            </div>
          </CardContent>
        </Card>
      )}

      <Card className="overflow-hidden border-white/5">
        <CardContent className="p-4">
          <div className="flex justify-between items-center mb-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Results ({resultsData.length} document{resultsData.length !== 1 ? "s" : ""})
            </h3>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={exportCsv}>
                <Download className="mr-1.5 h-4 w-4" />
                Export CSV
              </Button>
              <Button variant="outline" size="sm" onClick={exportJson}>
                <Download className="mr-1.5 h-4 w-4" />
                Export JSON
              </Button>
            </div>
          </div>

          <div className="overflow-x-auto rounded-lg border border-white/5">
            <table className="w-full text-sm text-left border-collapse">
              <thead className="bg-slate-900/80 border-b border-white/5 text-slate-400 uppercase text-[10px] tracking-wider">
                <tr>
                  <th className="px-4 py-3 font-semibold">Document ID</th>
                  <th className="px-4 py-3 font-semibold">Filename</th>
                  <th className="px-4 py-3 font-semibold">Status</th>
                  <th className="px-4 py-3 font-semibold">Review Status</th>
                  {fieldNames.map((fieldName) => (
                    <th key={fieldName} className="px-4 py-3 font-semibold">
                      {fieldName}
                    </th>
                  ))}
                  <th className="px-4 py-3 font-semibold text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 bg-slate-800/30">
                {resultsData.map((doc) => (
                  <tr key={doc.document_id} className="hover:bg-slate-800/50 transition-colors">
                    <td className="px-4 py-3 text-slate-300 font-mono text-xs">{doc.document_id}</td>
                    <td className="px-4 py-3 text-slate-200 text-xs">{doc.filename}</td>
                    <td className="px-4 py-3 text-slate-200 text-xs">{doc.status}</td>
                    <td className="px-4 py-3 text-slate-200 text-xs">
                      {doc.final_output_error ? (
                        <span className="text-red-300">error</span>
                      ) : (
                        doc.latest_review?.review_status ?? "not reviewed"
                      )}
                    </td>
                    {fieldNames.map((fieldName) => (
                      <td key={`${doc.document_id}-${fieldName}`} className="px-4 py-3 text-slate-200 text-xs">
                        {doc.final_output_error ? "-" : getFieldValue(doc.final_output, fieldName)}
                      </td>
                    ))}
                    <td className="px-4 py-3 text-right">
                      <Button variant="ghost" size="sm" asChild className="hover:text-cyan-400">
                        <Link to={`/projects/${project_id}/jobs/${job_id}/document/${doc.document_id}`}>
                          Open Review
                        </Link>
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
