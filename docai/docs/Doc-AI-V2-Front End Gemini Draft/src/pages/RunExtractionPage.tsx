import { useState, useRef } from "react";
import { Upload, Play, FileText, CheckCircle, AlertCircle, Loader2, ChevronDown } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, Button, Badge } from "@/components/ui";
import { cn } from "@/lib/utils";
import {
  submitRun,
  getRunArtifacts,
  getDocumentJson,
  type RunResponse,
  type ArtifactListResponse,
} from "@/lib/docaiApi";

type Mode = "local_text" | "local_text_model" | "stub";

const MODE_LABELS: Record<Mode, string> = {
  local_text: "Local Text",
  local_text_model: "Local Text + Model",
  stub: "Stub (dev/test)",
};

const MODE_DESCRIPTIONS: Record<Mode, string> = {
  local_text: "KV extraction from plain text. No model inference.",
  local_text_model: "KV extraction merged with model candidates. Uses StubModelPlugin by default; set DOCAI_MODEL_PROVIDER=ollama on the server for real inference.",
  stub: "Returns placeholder data instantly. No real extraction.",
};

interface DocPayload {
  endpoint: "final-output" | "validation-report";
  data: unknown;
}

export default function RunExtractionPage() {
  const [mode, setMode] = useState<Mode>("local_text");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [runResult, setRunResult] = useState<RunResponse | null>(null);
  const [artifacts, setArtifacts] = useState<ArtifactListResponse | null>(null);
  const [docPayload, setDocPayload] = useState<DocPayload | null>(null);
  const [docLoading, setDocLoading] = useState<"final-output" | "validation-report" | null>(null);
  const [docError, setDocError] = useState<string | null>(null);
  const [modeOpen, setModeOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  async function handleSubmit() {
    if (!file) return;
    setLoading(true);
    setError(null);
    setRunResult(null);
    setArtifacts(null);
    setDocPayload(null);
    setDocError(null);
    try {
      const result = await submitRun(mode, file);
      setRunResult(result);
      try {
        const arts = await getRunArtifacts(result.run_id);
        setArtifacts(arts);
      } catch {
        // artifact listing is best-effort
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function fetchDocEndpoint(endpoint: "final-output" | "validation-report") {
    if (!runResult) return;
    setDocLoading(endpoint);
    setDocError(null);
    setDocPayload(null);
    try {
      const data = await getDocumentJson(runResult.run_id, "doc-0", endpoint);
      setDocPayload({ endpoint, data });
    } catch (err) {
      setDocError(err instanceof Error ? err.message : String(err));
    } finally {
      setDocLoading(null);
    }
  }

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold text-white tracking-tight">Run Extraction</h1>
        <p className="text-xs text-slate-400 mt-1">
          Submit a document to the DocAI v2 API. Results come from a real backend pipeline run.
        </p>
      </div>

      {/* Config card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-sm text-slate-200">Pipeline Configuration</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          {/* Mode selector */}
          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Pipeline Mode
            </label>
            <div className="relative">
              <button
                className="w-full flex items-center justify-between px-3 py-2 rounded-lg border border-white/10 bg-slate-900/50 text-sm text-slate-200 hover:bg-slate-800/60 transition-colors"
                onClick={() => setModeOpen((o) => !o)}
              >
                <span>{MODE_LABELS[mode]}</span>
                <ChevronDown className={cn("w-4 h-4 text-slate-400 transition-transform", modeOpen && "rotate-180")} />
              </button>
              {modeOpen && (
                <div className="absolute z-20 mt-1 w-full rounded-lg border border-white/10 bg-slate-900 shadow-xl overflow-hidden">
                  {(["local_text", "local_text_model", "stub"] as Mode[]).map((m) => (
                    <button
                      key={m}
                      className={cn(
                        "w-full text-left px-4 py-3 hover:bg-white/5 transition-colors",
                        m === mode && "bg-white/10"
                      )}
                      onClick={() => { setMode(m); setModeOpen(false); }}
                    >
                      <div className="text-sm font-semibold text-slate-200">{MODE_LABELS[m]}</div>
                      <div className="text-[11px] text-slate-500 mt-0.5">{MODE_DESCRIPTIONS[m]}</div>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <p className="text-[11px] text-slate-500">{MODE_DESCRIPTIONS[mode]}</p>
          </div>

          {/* File upload */}
          <div className="space-y-2">
            <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Document
            </label>
            <div
              className={cn(
                "border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-colors",
                file
                  ? "border-emerald-500/40 bg-emerald-500/5"
                  : "border-white/10 hover:border-white/20 hover:bg-white/5"
              )}
              onClick={() => fileInputRef.current?.click()}
            >
              {file ? (
                <div className="flex items-center justify-center gap-3">
                  <FileText className="w-5 h-5 text-emerald-400" />
                  <div className="text-left">
                    <p className="text-sm font-semibold text-slate-200">{file.name}</p>
                    <p className="text-[11px] text-slate-500">{(file.size / 1024).toFixed(1)} KB</p>
                  </div>
                </div>
              ) : (
                <>
                  <Upload className="w-7 h-7 text-slate-500 mx-auto mb-2" />
                  <p className="text-sm text-slate-400">Click to upload a document</p>
                  <p className="text-[11px] text-slate-600 mt-1">TXT, PDF, or image</p>
                </>
              )}
            </div>
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              accept=".txt,.pdf,.png,.jpg,.jpeg,.tiff,.tif"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) { setFile(f); setError(null); setRunResult(null); setArtifacts(null); setDocPayload(null); }
              }}
            />
          </div>

          {/* Submit */}
          <Button
            variant="primary"
            className="w-full h-9 text-sm"
            disabled={!file || loading}
            onClick={handleSubmit}
          >
            {loading ? (
              <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Running…</>
            ) : (
              <><Play className="w-4 h-4 mr-2" /> Run Extraction</>
            )}
          </Button>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <Card className="border-red-500/30 bg-red-500/5">
          <CardContent className="pt-4 flex gap-3">
            <AlertCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
            <div>
              <p className="text-sm font-semibold text-red-300">API Error</p>
              <p className="text-xs text-red-400/80 mt-1 font-mono break-all">{error}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Run result */}
      {runResult && (
        <Card className="border-emerald-500/20">
          <CardHeader>
            <div className="flex items-center gap-2">
              <CheckCircle className="w-4 h-4 text-emerald-400" />
              <CardTitle className="text-sm text-emerald-300">Run Complete</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <p className="text-slate-500 mb-1">Run ID</p>
                <p className="font-mono text-slate-200 break-all">{runResult.run_id}</p>
              </div>
              <div>
                <p className="text-slate-500 mb-1">Job ID</p>
                <p className="font-mono text-slate-200 break-all">{runResult.job_id}</p>
              </div>
              <div>
                <p className="text-slate-500 mb-1">Pipeline</p>
                <p className="font-mono text-slate-300">{runResult.generated_by}</p>
              </div>
              <div>
                <p className="text-slate-500 mb-1">Documents</p>
                <p className="text-slate-200">{runResult.completed_count} / {runResult.document_count} completed</p>
              </div>
            </div>

            <div className="flex flex-wrap gap-2">
              <Badge variant={runResult.is_stub ? "warning" : "success"}>
                {runResult.is_stub ? "stub output" : "real output"}
              </Badge>
              {runResult.policies_used.map((p) => (
                <Badge key={p} variant="secondary">{p}</Badge>
              ))}
            </div>

            {runResult.note && (
              <p className="text-[11px] text-slate-500 italic">{runResult.note}</p>
            )}

            {/* Artifact links */}
            <div className="pt-2 border-t border-white/10 space-y-2">
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                Document Artifacts (doc-0)
              </p>
              <div className="flex gap-2 flex-wrap">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={docLoading !== null}
                  onClick={() => fetchDocEndpoint("final-output")}
                >
                  {docLoading === "final-output" ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : null}
                  Final Output
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={docLoading !== null}
                  onClick={() => fetchDocEndpoint("validation-report")}
                >
                  {docLoading === "validation-report" ? <Loader2 className="w-3 h-3 mr-1 animate-spin" /> : null}
                  Validation Report
                </Button>
              </div>
              {docError && (
                <p className="text-[11px] text-red-400 font-mono">{docError}</p>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Doc payload viewer */}
      {docPayload && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-slate-300 capitalize">
              {docPayload.endpoint.replace("-", " ")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <pre className="text-[11px] text-slate-300 font-mono overflow-x-auto whitespace-pre-wrap break-all bg-slate-950/60 rounded-lg p-3 border border-white/5">
              {JSON.stringify(docPayload.data, null, 2)}
            </pre>
          </CardContent>
        </Card>
      )}

      {/* Artifact file list */}
      {artifacts && artifacts.artifact_count > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-slate-300">
              Artifact Files ({artifacts.artifact_count})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1">
              {artifacts.artifacts.map((a) => (
                <li key={a} className="text-[11px] font-mono text-slate-400 flex items-center gap-2">
                  <FileText className="w-3 h-3 text-slate-600 shrink-0" />
                  {a}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
