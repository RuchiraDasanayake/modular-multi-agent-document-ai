import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Download } from "lucide-react";
import { Button, Card, CardContent } from "@/components/ui";
import {
  ArtifactListResponse,
  attachDocumentToRun,
  createRun,
  DocumentOut,
  ExecuteRunResponse,
  executeRun,
  getDocumentJson,
  getJob,
  getRun,
  getRunArtifacts,
  JobOut,
  listDocuments,
  listRunDocuments,
  listRuns,
  RunDocumentOut,
  RunOut,
} from "@/lib/docaiApi";
import ResultsTableTab from "@/components/job-viewer/ResultsTableTab";
import LearningSummaryTab from "@/components/job-viewer/LearningSummaryTab";

type Tab = "overview" | "queue" | "runs" | "results" | "artifacts" | "learning";
type ArtifactEndpoint = "final-output" | "validation-report";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "queue", label: "Document Queue" },
  { id: "runs", label: "Runs" },
  { id: "results", label: "Results" },
  { id: "artifacts", label: "Artifacts" },
  { id: "learning", label: "Learning Samples" },
];

type DocumentWithOptionalSize = DocumentOut & {
  file_size?: number | string | null;
  size_bytes?: number | string | null;
};

type RunWithOptionalUpdatedAt = RunOut & {
  updated_at?: string | null;
};

type LoadedArtifact = {
  documentId: string;
  endpoint: ArtifactEndpoint;
  loading: boolean;
  error: string | null;
  data: unknown;
};

function formatTimestamp(value?: string | null): string {
  if (!value) return "-";
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return value;
  return new Date(parsed).toLocaleString();
}

function formatSize(bytes?: number): string {
  if (bytes === undefined || !Number.isFinite(bytes) || bytes < 0) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function parseDocSize(doc: DocumentOut): number | undefined {
  const candidate =
    (doc as DocumentWithOptionalSize).file_size ?? (doc as DocumentWithOptionalSize).size_bytes;
  if (typeof candidate === "number") return candidate;
  if (typeof candidate === "string") {
    const parsed = Number(candidate);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}

function truncateHash(hash?: string | null): string {
  if (!hash) return "-";
  return hash.length > 16 ? `${hash.slice(0, 8)}...${hash.slice(-8)}` : hash;
}

function readIsStub(payload: unknown): boolean | null {
  if (typeof payload !== "object" || payload === null || !("is_stub" in payload)) return null;
  const value = (payload as { is_stub?: unknown }).is_stub;
  return typeof value === "boolean" ? value : null;
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


type ValidationReportView = {
  pass_status: string;
  summary: string;
  field_issues: string[];
  table_issues: string[];
  document_issues: string[];
  artifact_paths: string[];
};

function readValidationReport(payload: unknown): ValidationReportView {
  const empty: ValidationReportView = { pass_status: "-", summary: "-", field_issues: [], table_issues: [], document_issues: [], artifact_paths: [] };
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
    artifact_paths: toList(report.artifact_paths),
  };
}

function routingSourceLabel(source: RunDocumentOut["routing_source"]): string {
  return source === "document_override" ? "Document override" : "Run default";
}


export default function JobViewerPage() {
  const { project_id, job_id } = useParams();
  const [activeTab, setActiveTab] = useState<Tab>("overview");
  const [job, setJob] = useState<JobOut | null>(null);
  const [documents, setDocuments] = useState<DocumentOut[]>([]);
  const [runs, setRuns] = useState<RunOut[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [selectedRun, setSelectedRun] = useState<RunOut | null>(null);
  const [runDetailLoading, setRunDetailLoading] = useState(false);
  const [runDetailError, setRunDetailError] = useState<string | null>(null);
  const [runDocuments, setRunDocuments] = useState<RunDocumentOut[]>([]);
  const [runDocumentsLoading, setRunDocumentsLoading] = useState(false);
  const [runDocumentsError, setRunDocumentsError] = useState<string | null>(null);
  const [artifactList, setArtifactList] = useState<ArtifactListResponse | null>(null);
  const [artifactListLoading, setArtifactListLoading] = useState(false);
  const [artifactListError, setArtifactListError] = useState<string | null>(null);
  const [loadedArtifact, setLoadedArtifact] = useState<LoadedArtifact | null>(null);

  const [createRunMode, setCreateRunMode] = useState("stub");
  const [createRunLoading, setCreateRunLoading] = useState(false);
  const [createRunError, setCreateRunError] = useState<string | null>(null);
  const [createRunStep, setCreateRunStep] = useState<string | null>(null);
  const [executeResult, setExecuteResult] = useState<ExecuteRunResponse | null>(null);
  const [executingRunId, setExecutingRunId] = useState<string | null>(null);

  const resolvedProjectId = project_id ?? job?.project_id;
  const documentNameById = useMemo(
    () => new Map(documents.map((doc) => [doc.document_id, doc.original_filename])),
    [documents],
  );

  useEffect(() => {
    if (!job_id) {
      setError("Job ID is missing from route");
      setLoading(false);
      return;
    }
    void loadJobViewerData(job_id);
  }, [job_id]);

  useEffect(() => {
    if (!selectedRunId) {
      setSelectedRun(null);
      setRunDocuments([]);
      setArtifactList(null);
      setLoadedArtifact(null);
      setRunDetailError(null);
      setRunDocumentsError(null);
      setArtifactListError(null);
      return;
    }
    void loadSelectedRunEvidence(selectedRunId);
  }, [selectedRunId]);

  async function loadJobViewerData(selectedJobId: string) {
    setLoading(true);
    setError(null);
    try {
      const [jobData, documentData, runData] = await Promise.all([
        getJob(selectedJobId),
        listDocuments(selectedJobId),
        listRuns(selectedJobId),
      ]);
      setJob(jobData);
      setDocuments(documentData);
      setRuns(runData);
      if (selectedRunId && !runData.some((run) => run.run_id === selectedRunId)) {
        setSelectedRunId(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load job details");
    } finally {
      setLoading(false);
    }
  }

  async function loadSelectedRunEvidence(runId: string) {
    setRunDetailLoading(true);
    setRunDocumentsLoading(true);
    setArtifactListLoading(true);
    setRunDetailError(null);
    setRunDocumentsError(null);
    setArtifactListError(null);
    setLoadedArtifact(null);

    const [runResult, docsResult, artifactResult] = await Promise.allSettled([
      getRun(runId),
      listRunDocuments(runId),
      getRunArtifacts(runId),
    ]);

    if (runResult.status === "fulfilled") {
      setSelectedRun(runResult.value);
    } else {
      setSelectedRun(null);
      setRunDetailError(runResult.reason instanceof Error ? runResult.reason.message : "Failed to load run detail.");
    }
    setRunDetailLoading(false);

    if (docsResult.status === "fulfilled") {
      setRunDocuments(docsResult.value);
    } else {
      setRunDocuments([]);
      setRunDocumentsError(docsResult.reason instanceof Error ? docsResult.reason.message : "Failed to load run documents.");
    }
    setRunDocumentsLoading(false);

    if (artifactResult.status === "fulfilled") {
      setArtifactList(artifactResult.value);
    } else {
      setArtifactList(null);
      setArtifactListError(artifactResult.reason instanceof Error ? artifactResult.reason.message : "Failed to load artifact list.");
    }
    setArtifactListLoading(false);
  }

  async function loadArtifactPayload(documentId: string, endpoint: ArtifactEndpoint) {
    if (!selectedRunId) return;
    setLoadedArtifact({ documentId, endpoint, loading: true, error: null, data: null });
    try {
      const payload = await getDocumentJson(selectedRunId, documentId, endpoint);
      setLoadedArtifact({ documentId, endpoint, loading: false, error: null, data: payload });
    } catch (e) {
      setLoadedArtifact({
        documentId,
        endpoint,
        loading: false,
        error: e instanceof Error ? e.message : "Failed to load artifact payload.",
        data: null,
      });
    }
  }

  async function handleCreateAndExecuteRun() {
    if (!job_id || documents.length === 0) return;
    setCreateRunError(null);
    setCreateRunLoading(true);
    setCreateRunStep("Creating run...");
    setExecuteResult(null);
    try {
      const newRun = await createRun(job_id, createRunMode);

      setCreateRunStep(`Attaching ${documents.length} document(s)...`);
      await Promise.all(documents.map((doc: DocumentOut) => attachDocumentToRun(newRun.run_id, doc.document_id)));

      setCreateRunStep("Executing run...");
      const result = await executeRun(newRun.run_id, true);
      setExecuteResult(result);

      await loadJobViewerData(job_id);
      setSelectedRunId(newRun.run_id);
      setActiveTab("results");
    } catch (e) {
      setCreateRunError(e instanceof Error ? e.message : "Failed to create or execute run");
    } finally {
      setCreateRunLoading(false);
      setCreateRunStep(null);
    }
  }

  async function handleExecuteRun(runId: string) {
    setExecutingRunId(runId);
    setExecuteResult(null);
    try {
      const runDocs = await listRunDocuments(runId);
      const unattached = documents.filter((d: DocumentOut) => !runDocs.some((rd) => rd.document_id === d.document_id));
      if (unattached.length > 0) {
        await Promise.all(unattached.map((doc: DocumentOut) => attachDocumentToRun(runId, doc.document_id)));
      }
      const result = await executeRun(runId, true);
      setExecuteResult(result);
      if (job_id) await loadJobViewerData(job_id);
      setSelectedRunId(runId);
      setActiveTab("results");
    } catch (e) {
      setCreateRunError(e instanceof Error ? e.message : "Failed to execute run");
    } finally {
      setExecutingRunId(null);
    }
  }

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden relative z-10">
      <header className="px-6 py-4 border-b border-white/10 glass-panel flex items-center justify-between shrink-0">
        <div>
          <div className="flex items-center gap-2 text-[10px] font-bold text-slate-500 mb-1 uppercase tracking-wider">
            <Link
              to={resolvedProjectId ? `/projects/${resolvedProjectId}/jobs` : "/projects"}
              className="hover:text-cyan-400 transition-colors"
            >
              Jobs
            </Link>
            <span>/</span>
            <span>{job?.job_id ?? job_id}</span>
          </div>
          <h1 className="text-xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
            {job?.name ?? "Job Viewer"}
          </h1>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" disabled title="Not wired to backend yet">
            <Download className="mr-1.5 h-4 w-4" />
            Export (Not Wired)
          </Button>
        </div>
      </header>

      <div className="px-6 border-b border-white/10 glass-panel pt-2">
        <nav className="flex gap-6 overflow-x-auto scrollbar-hide">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`pb-3 text-sm font-medium border-b-2 transition-all whitespace-nowrap ${
                activeTab === tab.id
                  ? "border-cyan-400 text-cyan-400 shadow-[0_4px_15px_rgba(6,182,212,0.5)]"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      <div className="flex-1 overflow-y-auto p-6 relative">
        <div className="max-w-5xl mx-auto space-y-6">
          {loading && <Card className="p-8 text-center text-slate-400">Loading job metadata, documents, and runs...</Card>}

          {!loading && error && (
            <Card className="border border-red-500/30 bg-red-500/10 p-4">
              <p className="text-red-300 text-sm">{error}</p>
              <div className="mt-3">
                <Button variant="outline" size="sm" onClick={() => job_id && void loadJobViewerData(job_id)}>
                  Retry
                </Button>
              </div>
            </Card>
          )}

          {!loading && !error && !job && <Card className="p-6 text-sm text-slate-300">Job not found.</Card>}

          {!loading && !error && job && activeTab === "overview" && (
            <div className="space-y-4">
              <Card className="overflow-hidden border-white/5">
                <CardContent className="p-5 grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div><p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Job ID</p><p className="text-sm font-mono text-slate-300">{job.job_id}</p></div>
                  <div><p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Project ID</p><p className="text-sm font-mono text-slate-300">{job.project_id}</p></div>
                  <div><p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Schema ID</p><p className="text-sm font-mono text-slate-300">{job.schema_id}</p></div>
                  <div><p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Job Type</p><p className="text-sm text-slate-200">{job.job_type}</p></div>
                  <div><p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Status</p><p className="text-sm text-slate-200">{job.status}</p></div>
                  <div><p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Created</p><p className="text-sm text-slate-200">{formatTimestamp(job.created_at)}</p></div>
                </CardContent>
              </Card>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Card><CardContent className="p-4"><p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Documents in Queue</p><p className="text-lg font-bold text-slate-100">{documents.length}</p></CardContent></Card>
                <Card><CardContent className="p-4"><p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">Runs</p><p className="text-lg font-bold text-slate-100">{runs.length}</p></CardContent></Card>
              </div>
            </div>
          )}

          {!loading && !error && job && activeTab === "queue" && (
            <Card className="overflow-hidden border-white/5">
              <CardContent className="p-0">
                {documents.length === 0 ? (
                  <div className="p-6 text-sm text-slate-400">No documents registered for this job yet.</div>
                ) : (
                  <table className="w-full text-sm text-left border-collapse">
                    <thead className="bg-slate-900/80 border-b border-white/5 text-slate-400 uppercase text-[10px] tracking-wider">
                      <tr>
                        <th className="px-4 py-3 font-semibold">Document ID</th>
                        <th className="px-4 py-3 font-semibold">Filename</th>
                        <th className="px-4 py-3 font-semibold">MIME/Type</th>
                        <th className="px-4 py-3 font-semibold">Size</th>
                        <th className="px-4 py-3 font-semibold">Hash</th>
                        <th className="px-4 py-3 font-semibold">Status</th>
                        <th className="px-4 py-3 font-semibold">Created</th>
                        <th className="px-4 py-3 font-semibold text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5 bg-slate-800/30">
                      {documents.map((doc) => (
                        <tr key={doc.document_id} className="hover:bg-slate-800/50 transition-colors">
                          <td className="px-4 py-3 text-slate-300 font-mono text-xs">{doc.document_id}</td>
                          <td className="px-4 py-3 text-slate-200 text-xs">{doc.original_filename}</td>
                          <td className="px-4 py-3 text-slate-400 text-xs">{doc.file_type || "-"}</td>
                          <td className="px-4 py-3 text-slate-400 text-xs">{formatSize(parseDocSize(doc))}</td>
                          <td className="px-4 py-3 text-slate-400 font-mono text-xs" title={doc.file_hash || "-"}>{truncateHash(doc.file_hash)}</td>
                          <td className="px-4 py-3 text-slate-200 text-xs">{doc.status}</td>
                          <td className="px-4 py-3 text-slate-400 text-xs">{formatTimestamp(doc.created_at)}</td>
                          <td className="px-4 py-3 text-right">
                            <Button variant="ghost" size="sm" asChild className="hover:text-cyan-400">
                              <Link to={`/projects/${resolvedProjectId}/jobs/${job_id}/document/${doc.document_id}`}>
                                Review
                              </Link>
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </CardContent>
            </Card>
          )}

          {!loading && !error && job && activeTab === "runs" && (
            <>
              <Card className="border-white/5">
                <CardContent className="p-4 space-y-3">
                  <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">New Extraction Run</p>
                  {documents.length === 0 && (
                    <p className="text-xs text-amber-400">Upload documents in the Document Queue before creating a run.</p>
                  )}
                  {documents.length > 0 && (
                    <div className="flex items-end gap-3">
                      <div className="flex-1">
                        <label className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">
                          Extraction Mode
                        </label>
                        <select
                          value={createRunMode}
                          onChange={(e) => setCreateRunMode(e.target.value)}
                          disabled={createRunLoading}
                          className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-slate-200"
                        >
                          <option value="stub">Stub (Testing)</option>
                          <option value="practice">Practice</option>
                          <option value="production">Production</option>
                        </select>
                      </div>
                      <button
                        onClick={() => void handleCreateAndExecuteRun()}
                        disabled={createRunLoading}
                        className="px-4 py-2 bg-cyan-600 hover:bg-cyan-700 disabled:bg-slate-600 text-white text-sm font-medium rounded transition-colors whitespace-nowrap"
                      >
                        {createRunLoading ? (createRunStep ?? "Working...") : `Create & Execute (${documents.length} doc${documents.length !== 1 ? "s" : ""})`}
                      </button>
                    </div>
                  )}
                  {createRunError && <p className="text-xs text-red-300">{createRunError}</p>}
                  {executeResult && (
                    <div className="rounded border border-cyan-500/30 bg-cyan-500/10 p-3 space-y-1 text-xs">
                      <p className="font-semibold text-cyan-300">Run complete</p>
                      <p className="text-slate-300">Documents: {executeResult.completed_count}/{executeResult.document_count}</p>
                      {executeResult.execution_errors.length > 0 && (
                        <p className="text-red-300">Errors: {executeResult.execution_errors.join("; ")}</p>
                      )}
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card className="overflow-hidden border-white/5">
                <CardContent className="p-0">
                  {runs.length === 0 ? (
                    <div className="p-6 text-sm text-slate-400">No runs created for this job yet.</div>
                  ) : (
                    <table className="w-full text-sm text-left border-collapse">
                      <thead className="bg-slate-900/80 border-b border-white/5 text-slate-400 uppercase text-[10px] tracking-wider">
                        <tr>
                          <th className="px-4 py-3 font-semibold">Run ID</th>
                          <th className="px-4 py-3 font-semibold">Mode</th>
                          <th className="px-4 py-3 font-semibold">Run Type</th>
                          <th className="px-4 py-3 font-semibold">Status</th>
                          <th className="px-4 py-3 font-semibold">Created</th>
                          <th className="px-4 py-3 font-semibold">Updated</th>
                          <th className="px-4 py-3 font-semibold">Action</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/5 bg-slate-800/30">
                        {runs.map((run) => (
                          <tr key={run.run_id} className={selectedRunId === run.run_id ? "bg-cyan-500/10" : "hover:bg-slate-800/50 transition-colors"}>
                            <td className="px-4 py-3 text-slate-300 font-mono text-xs">{run.run_id}</td>
                            <td className="px-4 py-3 text-slate-400 text-xs">{run.mode || "-"}</td>
                            <td className="px-4 py-3 text-slate-200 text-xs">{run.run_type}</td>
                            <td className="px-4 py-3 text-slate-200 text-xs">{run.status}</td>
                            <td className="px-4 py-3 text-slate-400 text-xs">{formatTimestamp(run.created_at)}</td>
                            <td className="px-4 py-3 text-slate-400 text-xs">{formatTimestamp((run as RunWithOptionalUpdatedAt).updated_at ?? run.completed_at)}</td>
                            <td className="px-4 py-3">
                              <div className="flex gap-2">
                                <Button variant="outline" size="sm" onClick={() => setSelectedRunId(run.run_id)}>
                                  {selectedRunId === run.run_id ? "Selected" : "Inspect"}
                                </Button>
                                {run.status !== "completed" && (
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => void handleExecuteRun(run.run_id)}
                                    disabled={executingRunId === run.run_id}
                                    className="text-cyan-400 border-cyan-500/50 hover:bg-cyan-500/10"
                                  >
                                    {executingRunId === run.run_id ? "Running..." : "Execute"}
                                  </Button>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </CardContent>
              </Card>

              <Card className="border-white/5">
                <CardContent className="p-4 space-y-3">
                  <p className="text-[10px] font-bold text-cyan-400 uppercase tracking-wider">Backend evidence view</p>
                  {!selectedRunId && <p className="text-sm text-slate-400">Select a run to inspect metadata and run-document mappings.</p>}
                  {selectedRunId && runDetailLoading && <p className="text-sm text-slate-400">Loading run detail...</p>}
                  {selectedRunId && runDetailError && <p className="text-sm text-red-300">{runDetailError}</p>}
                  {selectedRunId && selectedRun && !runDetailLoading && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                      {[
                        ["run_id", selectedRun.run_id],
                        ["status", selectedRun.status],
                        ["mode", selectedRun.mode || "-"],
                        ["run_type", selectedRun.run_type],
                        ["created_at", formatTimestamp(selectedRun.created_at)],
                        ["completed_at", formatTimestamp(selectedRun.completed_at)],
                        ["artifact_root", selectedRun.artifact_root || "-"],
                      ].map(([label, value]) => (
                        <div key={label} className={label === "artifact_root" ? "md:col-span-2" : ""}>
                          <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">{label}</p>
                          <p className="text-slate-200 font-mono break-all">{value}</p>
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="pt-2 border-t border-white/5">
                    <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">Attached Run Documents</p>
                    {runDocumentsLoading && <p className="text-sm text-slate-400">Loading run documents...</p>}
                    {!runDocumentsLoading && runDocumentsError && <p className="text-sm text-red-300">{runDocumentsError}</p>}
                    {!runDocumentsLoading && !runDocumentsError && selectedRunId && runDocuments.length === 0 && <p className="text-sm text-slate-400">No documents attached to this run.</p>}
                    {!runDocumentsLoading && !runDocumentsError && runDocuments.length > 0 && (
                      <ul className="space-y-2">
                        {runDocuments.map((rd) => (
                          <li key={rd.run_document_id} className="text-xs text-slate-300 border border-white/10 rounded p-2">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-mono">{documentNameById.get(rd.document_id) || rd.document_id}</span>
                              <span className="text-slate-500">document_id: {rd.document_id}</span>
                              <span className="text-slate-500">status: {rd.status}</span>
                            </div>
                            <div className="mt-1 grid grid-cols-1 md:grid-cols-2 gap-1 text-[11px]">
                              <p className="text-slate-400">
                                <span className="font-semibold text-slate-500">schema_id:</span>{" "}
                                {rd.schema_id || "—"}
                              </p>
                              <p className="text-slate-400">
                                <span className="font-semibold text-slate-500">mode:</span>{" "}
                                {rd.mode || "—"}
                              </p>
                              <p className="text-slate-400 flex items-center gap-2">
                                <span className="font-semibold text-slate-500">routing source:</span>
                                <span
                                  className={`inline-flex items-center px-1.5 py-0.5 rounded border ${
                                    rd.routing_source === "document_override"
                                      ? "border-cyan-500/40 text-cyan-300 bg-cyan-500/10"
                                      : "border-slate-500/40 text-slate-300 bg-slate-700/30"
                                  }`}
                                >
                                  {routingSourceLabel(rd.routing_source)}
                                </span>
                              </p>
                              <p className="text-slate-400">
                                <span className="font-semibold text-slate-500">routing reason:</span>{" "}
                                {rd.routing_reason || "—"}
                              </p>
                            </div>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </CardContent>
              </Card>

              {selectedRunId && selectedRun?.status === "completed" && (
                <Card className="border-cyan-500/20 bg-cyan-500/5">
                  <CardContent className="p-4 flex items-center justify-between">
                    <p className="text-sm text-cyan-300">Run complete. View extracted results in the Results tab.</p>
                    <Button variant="outline" size="sm" onClick={() => setActiveTab("results")} className="text-cyan-400 border-cyan-500/50">
                      View Results
                    </Button>
                  </CardContent>
                </Card>
              )}
            </>
          )}

          {!loading && !error && job && activeTab === "artifacts" && (
            <div className="space-y-4">
              <Card className="border-cyan-500/20 bg-cyan-500/5">
                <CardContent className="p-4 space-y-1">
                  <p className="text-sm font-semibold text-cyan-300">Backend evidence view</p>
                  <p className="text-xs text-slate-300">Some artifact payloads are not exposed by API yet.</p>
                  <p className="text-xs text-slate-400">Run events are not exposed by API yet.</p>
                  <p className="text-xs text-slate-400">Indexed metrics are not exposed by API yet.</p>
                  <p className="text-xs text-slate-400">Arbitrary artifact JSON content is not exposed by API yet.</p>
                  <p className="text-xs text-slate-400">Learning/AHMN is not wired yet.</p>
                </CardContent>
              </Card>
              {!selectedRunId && <Card className="border border-amber-500/30 bg-amber-500/10"><CardContent className="p-4 text-sm text-amber-300">Select a run in the Runs tab to inspect artifacts.</CardContent></Card>}
              {selectedRunId && (
                <>
                  <Card className="border-white/5">
                    <CardContent className="p-4 space-y-2">
                      <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Artifact Filenames</p>
                      <p className="text-xs text-slate-400 font-mono">run_id: {selectedRunId}</p>
                      {artifactListLoading && <p className="text-sm text-slate-400">Loading artifact list...</p>}
                      {!artifactListLoading && artifactListError && <p className="text-sm text-red-300">{artifactListError}</p>}
                      {!artifactListLoading && !artifactListError && artifactList && (
                        <>
                          <p className="text-xs text-slate-300">artifact_count: <span className="font-mono">{artifactList.artifact_count}</span></p>
                          {artifactList.artifact_count === 0 ? <p className="text-sm text-slate-400">No artifact files found.</p> : (
                            <ul className="space-y-1">{artifactList.artifacts.map((a) => <li key={a} className="text-xs font-mono text-slate-300 break-all">{a}</li>)}</ul>
                          )}
                        </>
                      )}
                    </CardContent>
                  </Card>

                  <Card className="border-white/5">
                    <CardContent className="p-4 space-y-3">
                      <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Load Final Output / Validation Report</p>
                      {runDocumentsLoading && <p className="text-sm text-slate-400">Loading run documents...</p>}
                      {!runDocumentsLoading && runDocumentsError && <p className="text-sm text-red-300">{runDocumentsError}</p>}
                      {!runDocumentsLoading && !runDocumentsError && runDocuments.length === 0 && <p className="text-sm text-slate-400">No run documents available.</p>}
                      {!runDocumentsLoading && !runDocumentsError && runDocuments.length > 0 && (
                        <div className="space-y-2">
                          {runDocuments.map((rd) => {
                            const active = loadedArtifact?.documentId === rd.document_id;
                            return (
                              <div key={rd.run_document_id} className="border border-white/10 rounded p-3">
                                <p className="text-xs font-mono text-slate-200 break-all">{documentNameById.get(rd.document_id) || rd.document_id}</p>
                                <p className="text-[11px] text-slate-500 font-mono">document_id: {rd.document_id} | status: {rd.status}</p>
                                <div className="flex gap-2 mt-2">
                                  <Button variant="outline" size="sm" onClick={() => void loadArtifactPayload(rd.document_id, "final-output")}>Load Final Output</Button>
                                  <Button variant="outline" size="sm" onClick={() => void loadArtifactPayload(rd.document_id, "validation-report")}>Load Validation Report</Button>
                                </div>
                                {active && loadedArtifact?.loading && <p className="text-xs text-slate-400 mt-2">Loading selected payload...</p>}
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </CardContent>
                  </Card>

                  {loadedArtifact && (
                    <Card className="border-white/5">
                      <CardContent className="p-4 space-y-2">
                        <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                          {loadedArtifact.endpoint === "final-output" ? "final_output.json" : "validation_report.json"}
                        </p>
                        <p className="text-xs text-slate-400 font-mono">document_id: {loadedArtifact.documentId}</p>
                        {!loadedArtifact.loading && loadedArtifact.error && <p className="text-xs text-red-300">Error: {loadedArtifact.error}</p>}
                        {!loadedArtifact.loading && !loadedArtifact.error && (
                          <>
                            {readIsStub(loadedArtifact.data) !== null && <p className="text-xs text-amber-300 font-semibold">is_stub: {String(readIsStub(loadedArtifact.data))}</p>}
                            {readIsStub(loadedArtifact.data) === true && (
                              <div className="rounded border border-amber-500/40 bg-amber-500/10 p-3 space-y-1">
                                <p className="text-xs font-semibold text-amber-300">Stub runtime output - not real extraction.</p>
                                <p className="text-[11px] text-amber-200/90">
                                  This payload is useful for verifying the runtime spine and artifact flow only.
                                </p>
                              </div>
                            )}
                            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Raw artifact payload</p>
                            <pre className="text-[11px] text-slate-300 font-mono overflow-x-auto whitespace-pre-wrap break-all bg-slate-950/60 rounded-lg p-3 border border-white/5">{JSON.stringify(loadedArtifact.data, null, 2)}</pre>
                          </>
                        )}
                      </CardContent>
                    </Card>
                  )}
                </>
              )}
            </div>
          )}

          {!loading && !error && job && activeTab === "results" && (
            <ResultsTableTab
              selectedRunId={selectedRunId}
              documents={documents}
              project_id={resolvedProjectId}
              job_id={job_id}
            />
          )}

          {!loading && !error && job && activeTab === "learning" && (
            <LearningSummaryTab selectedRunId={selectedRunId} />
          )}
        </div>
      </div>
    </div>
  );
}
