import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ChevronLeft, Download, AlertCircle, ExternalLink } from "lucide-react";
import { Button, Card, CardContent } from "@/components/ui";
import {
  getDocument,
  getDocumentFileUrl,
  listRuns,
  listRunDocuments,
  getDocumentJson,
  DocumentOut,
  RunOut,
  RunDocumentOut,
} from "@/lib/docaiApi";
import ReviewPanel from "@/components/job-viewer/ReviewPanel";

interface FinalOutputField {
  field_name?: string;
  value?: string;
  normalized_value?: string;
  confidence?: string;
  evidence_text?: string;
  validation_status?: string;
}

interface ValidationReportView {
  pass_status: string;
  summary: string;
  field_issues: string[];
  table_issues: string[];
  document_issues: string[];
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

function readFinalOutputFields(payload: unknown): FinalOutputField[] {
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
    .map((field) => (typeof field === "object" && field !== null ? (field as FinalOutputField) : null))
    .filter((f): f is FinalOutputField => !!f);
}

function readValidationReport(payload: unknown): ValidationReportView {
  const empty: ValidationReportView = {
    pass_status: "-",
    summary: "-",
    field_issues: [],
    table_issues: [],
    document_issues: [],
  };
  if (typeof payload !== "object" || payload === null) return empty;

  const nested = (payload as { validation_report?: unknown }).validation_report;
  const report = typeof nested === "object" && nested !== null ? (nested as Record<string, unknown>) : (payload as Record<string, unknown>);
  const toList = (value: unknown): string[] => (Array.isArray(value) ? value.map((entry) => formatFieldCell(entry)) : []);

  return {
    pass_status: formatFieldCell(report.pass_status),
    summary: formatFieldCell(report.summary),
    field_issues: toList(report.field_issues),
    table_issues: toList(report.table_issues),
    document_issues: toList(report.document_issues),
  };
}


function getPreviewType(fileType?: string): "image" | "pdf" | "text" | "unsupported" {
  const normalized = (fileType || "").toLowerCase();
  if (normalized.startsWith("image/")) return "image";
  if (normalized === "application/pdf") return "pdf";
  if (normalized === "text/plain") return "text";
  return "unsupported";
}

export default function DocumentReviewPage() {
  const { project_id, job_id, doc_id } = useParams();

  // Document metadata
  const [document, setDocument] = useState<DocumentOut | null>(null);
  const [docLoading, setDocLoading] = useState(true);
  const [docError, setDocError] = useState<string | null>(null);

  // Run list and filtering
  const [runs, setRuns] = useState<RunOut[]>([]);
  const [runsLoading, setRunsLoading] = useState(true);
  const [runsError, setRunsError] = useState<string | null>(null);
  const [relevantRuns, setRelevantRuns] = useState<RunOut[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  // Run documents for selected run
  const [runDocuments, setRunDocuments] = useState<RunDocumentOut[]>([]);
  const [runDocumentsError, setRunDocumentsError] = useState<string | null>(null);

  // Final output and validation
  const [finalOutput, setFinalOutput] = useState<unknown>(null);
  const [validationReport, setValidationReport] = useState<unknown>(null);
  const [artifactLoading, setArtifactLoading] = useState(false);
  const [artifactError, setArtifactError] = useState<string | null>(null);

  // Load document metadata
  useEffect(() => {
    if (!doc_id) {
      setDocError("Document ID is missing from route");
      setDocLoading(false);
      return;
    }

    const loadDoc = async () => {
      setDocLoading(true);
      setDocError(null);
      try {
        const docData = await getDocument(doc_id);
        setDocument(docData);
      } catch (e) {
        setDocError(e instanceof Error ? e.message : "Failed to load document");
      } finally {
        setDocLoading(false);
      }
    };

    void loadDoc();
  }, [doc_id]);

  // Load runs and filter by document
  useEffect(() => {
    if (!job_id) {
      setRunsError("Job ID is missing from route");
      setRunsLoading(false);
      return;
    }

    const loadRuns = async () => {
      setRunsLoading(true);
      setRunsError(null);
      try {
        const runData = await listRuns(job_id);
        setRuns(runData);

        // Filter runs that contain this document
        const runsWithDoc: RunOut[] = [];
        for (const run of runData) {
          try {
            const runDocs = await listRunDocuments(run.run_id);
            if (runDocs.some((rd) => rd.document_id === doc_id)) {
              runsWithDoc.push(run);
            }
          } catch {
            // Skip runs we can't inspect
          }
        }
        setRelevantRuns(runsWithDoc);
        if (runsWithDoc.length > 0) {
          setSelectedRunId(runsWithDoc[0].run_id);
        }
      } catch (e) {
        setRunsError(e instanceof Error ? e.message : "Failed to load runs");
      } finally {
        setRunsLoading(false);
      }
    };

    void loadRuns();
  }, [job_id, doc_id]);

  // Load run documents when run is selected
  useEffect(() => {
    if (!selectedRunId) {
      setRunDocuments([]);
      setRunDocumentsError(null);
      return;
    }

    const loadRunDocs = async () => {
      setRunDocumentsError(null);
      try {
        const docs = await listRunDocuments(selectedRunId);
        setRunDocuments(docs);
      } catch (e) {
        setRunDocumentsError(e instanceof Error ? e.message : "Failed to load run documents");
      }
    };

    void loadRunDocs();
  }, [selectedRunId]);

  // Load artifacts when run is selected
  useEffect(() => {
    if (!selectedRunId || !doc_id) {
      setFinalOutput(null);
      setValidationReport(null);
      return;
    }

    const loadArtifacts = async () => {
      setArtifactLoading(true);
      setArtifactError(null);
      try {
        const [finalOut, validReport] = await Promise.all([
          getDocumentJson(selectedRunId, doc_id, "final-output"),
          getDocumentJson(selectedRunId, doc_id, "validation-report"),
        ]);
        setFinalOutput(finalOut);
        setValidationReport(validReport);
      } catch (e) {
        setArtifactError(e instanceof Error ? e.message : "Failed to load artifacts");
      } finally {
        setArtifactLoading(false);
      }
    };

    void loadArtifacts();
  }, [selectedRunId, doc_id]);

  if (docLoading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Card className="p-8 text-center">
          <p className="text-slate-400">Loading document...</p>
        </Card>
      </div>
    );
  }

  if (docError || !document) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <Card className="p-8 text-center border-red-500/30 bg-red-500/10">
          <p className="text-red-400">{docError || "Document not found"}</p>
        </Card>
      </div>
    );
  }

  const selectedRun = relevantRuns.find((r) => r.run_id === selectedRunId);
  const isStub = readIsStub(finalOutput);
  const fields = readFinalOutputFields(finalOutput);
  const validationData = readValidationReport(validationReport);
  const fileUrl = getDocumentFileUrl(document.document_id);
  const fileType = (document.file_type || "").toLowerCase();
  const previewType = getPreviewType(fileType);
  const downloadName = document.original_filename || document.document_id;

  return (
    <div className="flex-1 flex flex-col overflow-hidden relative z-10">
      {/* Header */}
      <header className="px-6 py-4 border-b border-white/10 glass-panel flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2 text-sm">
          <Button variant="ghost" size="sm" className="px-1 hover:text-cyan-400" asChild>
            <Link to={`/projects/${project_id}/jobs/${job_id}`}>
              <ChevronLeft className="h-4 w-4" />
            </Link>
          </Button>
          <span className="text-slate-500 font-mono text-xs">Jobs / {job_id} /</span>
          <span className="font-semibold text-slate-200">{document.original_filename}</span>
        </div>
        <a href={fileUrl} download={downloadName}>
          <Button variant="outline" size="sm">
            <Download className="mr-1.5 h-4 w-4" />
            Download
          </Button>
        </a>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* Left: Document metadata + run selector */}
        <section className="w-2/5 border-r border-white/10 bg-slate-950/50 overflow-y-auto flex flex-col p-5 gap-4">
          {/* Document Metadata */}
          <Card className="glass-card border-white/5 shrink-0">
            <CardContent className="p-4">
              <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-3">
                Document
              </h3>
              <div className="space-y-2 text-xs">
                <div>
                  <p className="text-slate-500 font-bold mb-0.5">ID</p>
                  <p className="font-mono text-slate-300">{document.document_id}</p>
                </div>
                <div>
                  <p className="text-slate-500 font-bold mb-0.5">Filename</p>
                  <p className="text-slate-300">{document.original_filename}</p>
                </div>
                <div>
                  <p className="text-slate-500 font-bold mb-0.5">Type</p>
                  <p className="text-slate-300">{document.file_type || "-"}</p>
                </div>
                <div>
                  <p className="text-slate-500 font-bold mb-0.5">Hash</p>
                  <p className="font-mono text-slate-400 text-[9px]">{document.file_hash ? document.file_hash.slice(0, 16) + "..." : "-"}</p>
                </div>
                <div>
                  <p className="text-slate-500 font-bold mb-0.5">Status</p>
                  <p className="text-slate-300">{document.status}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card className="glass-card border-white/5 shrink-0">
            <CardContent className="p-4 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  Original Document
                </h3>
                <span className="text-[10px] text-slate-500">{document.file_type || "Unknown type"}</span>
              </div>

              <div className="h-96 rounded border border-white/10 bg-slate-900/40 overflow-hidden">
                {previewType === "image" && (
                  <img
                    src={fileUrl}
                    alt={downloadName}
                    className="h-full w-full object-contain"
                  />
                )}

                {previewType === "pdf" && (
                  <object data={fileUrl} type="application/pdf" className="h-full w-full">
                    <div className="h-full w-full flex items-center justify-center p-4 text-xs text-slate-400 text-center">
                      PDF preview unavailable in this browser. Open or download the original file.
                    </div>
                  </object>
                )}

                {previewType === "text" && (
                  <div className="h-full w-full flex items-center justify-center p-4 text-xs text-slate-400 text-center">
                    Text preview is available by opening the original file.
                  </div>
                )}

                {previewType === "unsupported" && (
                  <div className="h-full w-full flex items-center justify-center p-4 text-xs text-slate-400 text-center">
                    Preview is not available for this file type.
                  </div>
                )}
              </div>

              <div className="flex gap-2">
                <Button variant="outline" size="sm" asChild>
                  <a href={fileUrl} target="_blank" rel="noreferrer">
                    <ExternalLink className="mr-1.5 h-4 w-4" />
                    Open Original
                  </a>
                </Button>
                <Button variant="outline" size="sm" asChild>
                  <a href={fileUrl} download={downloadName}>
                    <Download className="mr-1.5 h-4 w-4" />
                    Download
                  </a>
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Run Selector */}
          <Card className="glass-card border-white/5 shrink-0">
            <CardContent className="p-4">
              <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-3">
                Select Run
              </h3>
              {runsLoading ? (
                <p className="text-xs text-slate-400">Loading runs...</p>
              ) : runsError ? (
                <p className="text-xs text-red-400">{runsError}</p>
              ) : relevantRuns.length === 0 ? (
                <p className="text-xs text-slate-400">No runs found for this document</p>
              ) : (
                <div className="space-y-2">
                  {relevantRuns.map((run) => (
                    <button
                      key={run.run_id}
                      onClick={() => setSelectedRunId(run.run_id)}
                      className={`w-full text-left p-2 rounded text-xs transition-colors ${
                        selectedRunId === run.run_id
                          ? "bg-cyan-500/20 border border-cyan-500/50 text-cyan-300"
                          : "bg-slate-800/50 border border-white/5 text-slate-300 hover:bg-slate-700/50"
                      }`}
                    >
                      <div className="font-mono text-[9px] opacity-70">{run.run_id.slice(0, 12)}</div>
                      <div className="font-medium">{run.status}</div>
                      <div className="text-[9px] opacity-70">
                        {run.completed_at ? new Date(run.completed_at).toLocaleString() : "Not completed"}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </section>

        {/* Right: Review panels */}
        <section className="flex-1 overflow-y-auto p-6 space-y-5 bg-slate-900/60 backdrop-blur">
          {selectedRunId && (
            <>
              {/* Stub warning */}
              {isStub && (
                <Card className="border-amber-500/30 bg-amber-500/10">
                  <CardContent className="p-4 flex items-start gap-3">
                    <AlertCircle className="h-5 w-5 text-amber-400 shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm font-semibold text-amber-300">Stub Runtime Output</p>
                      <p className="text-xs text-amber-200">This is stub extraction output, not real. Use for testing only.</p>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Loading indicator */}
              {artifactLoading && (
                <Card className="p-4 text-center text-slate-400 text-sm">
                  Loading extraction results...
                </Card>
              )}

              {artifactError && (
                <Card className="p-4 text-center text-red-400 text-sm border-red-500/30 bg-red-500/10">
                  {artifactError}
                </Card>
              )}

              {!artifactLoading && !artifactError && (
                <>
                  {/* Extracted Fields */}
                  {fields.length > 0 && (
                    <Card className="border-white/5">
                      <CardContent className="p-4">
                        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">
                          Extracted Fields
                        </h3>
                        <div className="overflow-x-auto">
                          <table className="w-full text-xs text-left">
                            <thead className="text-slate-400 border-b border-white/5">
                              <tr>
                                <th className="pb-2 font-semibold">Field</th>
                                <th className="pb-2 font-semibold">Value</th>
                                <th className="pb-2 font-semibold">Confidence</th>
                                <th className="pb-2 font-semibold">Status</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-white/5">
                              {fields.map((field, i) => (
                                <tr key={i} className="hover:bg-white/5">
                                  <td className="py-2 text-slate-300">{formatFieldCell(field.field_name)}</td>
                                  <td className="py-2 text-slate-300">{formatFieldCell(field.value)}</td>
                                  <td className="py-2 text-slate-400">{formatFieldCell(field.confidence)}</td>
                                  <td className="py-2 text-slate-400">{formatFieldCell(field.validation_status)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </CardContent>
                    </Card>
                  )}

                  {/* Validation Evidence */}
                  {validationData.pass_status !== "-" && (
                    <Card className="border-white/5">
                      <CardContent className="p-4">
                        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3">
                          Validation Report
                        </h3>
                        <div className="space-y-3 text-xs">
                          <div>
                            <p className="text-slate-500 font-bold mb-1">Status</p>
                            <p className="text-slate-300">{validationData.pass_status}</p>
                          </div>
                          <div>
                            <p className="text-slate-500 font-bold mb-1">Summary</p>
                            <p className="text-slate-300">{validationData.summary}</p>
                          </div>
                          {validationData.field_issues.length > 0 && (
                            <div>
                              <p className="text-slate-500 font-bold mb-1">Field Issues</p>
                              <ul className="list-disc list-inside text-slate-300 space-y-1">
                                {validationData.field_issues.map((issue, i) => (
                                  <li key={i}>{issue}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      </CardContent>
                    </Card>
                  )}

                  {/* Review Panel */}
                  {runDocumentsError && (
                    <Card className="p-4 text-red-400 text-sm border-red-500/30 bg-red-500/10">
                      {runDocumentsError}
                    </Card>
                  )}
                  {!runDocumentsError && !runDocuments.some((rd) => rd.document_id === doc_id) && (
                    <Card className="p-4 text-amber-400 text-sm border-amber-500/30 bg-amber-500/10">
                      This document is not attached to the selected run.
                    </Card>
                  )}
                  {runDocuments.some((rd) => rd.document_id === doc_id) && (
                    <ReviewPanel
                      selectedRunId={selectedRunId}
                      runDocuments={runDocuments.filter((rd) => rd.document_id === doc_id)}
                      documentNameById={new Map([[document.document_id, document.original_filename]])}
                      runDocumentsLoading={false}
                      runDocumentsError={null}
                    />
                  )}
                </>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}
