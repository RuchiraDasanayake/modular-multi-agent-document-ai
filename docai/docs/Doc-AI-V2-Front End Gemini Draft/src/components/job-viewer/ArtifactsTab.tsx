import { Archive, FileText } from "lucide-react";
import { Card, CardContent } from "@/components/ui";
import { ArtifactRow } from "./JobViewerBadges";
import {
  mockJobArtifacts,
  mockDocumentArtifactsByDocumentId,
  mockDocumentQueue,
} from "@/lib/mockData";

export default function ArtifactsTab() {
  return (
    <div className="space-y-6 animate-fade-in" style={{ animationDelay: "0.1s" }}>
      <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 pt-2 flex items-center">
        <Archive className="mr-2 h-4 w-4 opacity-80" />
        Run Artifacts
      </h2>
      <p className="text-[10px] text-amber-400/70 font-mono">
        Artifact names and summaries shown from mock fixtures. File download not implemented.
      </p>

      <Card className="overflow-hidden border-white/5">
        <div className="bg-slate-900/60 px-4 py-2 border-b border-white/5 text-[10px] uppercase font-bold text-slate-400">
          Job-Level Artifacts
        </div>
        <CardContent className="p-0">
          <table className="w-full text-sm text-left border-collapse">
            <thead className="bg-slate-900/80 border-b border-white/5 text-slate-500 uppercase text-[9px] tracking-wider">
              <tr>
                <th className="px-4 py-2">Artifact</th>
                <th className="px-4 py-2">Summary</th>
                <th className="px-4 py-2 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 bg-slate-800/10">
              <ArtifactRow
                name="job_context.json"
                summary={`Job: ${mockJobArtifacts.jobContext.jobId} · Run type: ${mockJobArtifacts.jobContext.runType} · ${mockJobArtifacts.jobContext.documentCount} docs`}
                isStub={!!mockJobArtifacts.jobContext.is_stub}
              />
              <ArtifactRow
                name="document_queue.json"
                summary={`${mockJobArtifacts.documentQueue.length} documents queued`}
              />
              <ArtifactRow
                name="metrics_report.json"
                summary={
                  mockJobArtifacts.metricsReport?.is_stub
                    ? "Stub metrics — not real performance data"
                    : "Metrics report"
                }
                isStub={!!mockJobArtifacts.metricsReport?.is_stub}
              />
              <ArtifactRow
                name="extracted_data_export.json"
                summary={`${mockJobArtifacts.extractedDataExport.documentCount} documents, stub output`}
                isStub={!!mockJobArtifacts.extractedDataExport.is_stub}
              />
              <ArtifactRow
                name="run_log.jsonl"
                summary={`${mockJobArtifacts.runLog.length} log events`}
              />
            </tbody>
          </table>
        </CardContent>
      </Card>

      {Object.entries(mockDocumentArtifactsByDocumentId).map(([docId, artifacts]) => {
        const filename = mockDocumentQueue.find((d) => d.documentId === docId)?.filename ?? docId;
        const ocrEngine = (artifacts.runPlan.ocrConfig.engine as string | undefined) ?? "—";
        return (
          <Card key={docId} className="overflow-hidden border-white/5">
            <div className="bg-slate-900/60 px-4 py-2 border-b border-white/5 text-[10px] uppercase font-bold text-slate-400 flex items-center gap-2">
              <FileText className="h-3 w-3 text-cyan-400/50" />
              Document: {filename}
              <span className="text-slate-600 font-mono font-normal normal-case">{docId}</span>
            </div>
            <CardContent className="p-0">
              <table className="w-full text-sm text-left border-collapse">
                <thead className="bg-slate-900/80 border-b border-white/5 text-slate-500 uppercase text-[9px] tracking-wider">
                  <tr>
                    <th className="px-4 py-2">Artifact</th>
                    <th className="px-4 py-2">Summary</th>
                    <th className="px-4 py-2 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5 bg-slate-800/10">
                  <ArtifactRow
                    name="document_profile.json"
                    summary={`Type: ${artifacts.documentProfile.detectedType} · Layout: ${artifacts.documentProfile.layoutType} · Quality: ${artifacts.documentProfile.qualityBin}`}
                    isStub={!!artifacts.documentProfile.is_stub}
                  />
                  <ArtifactRow
                    name="selected_policy.json"
                    summary={`Strategy: ${artifacts.selectedPolicy.strategyName} · By: ${artifacts.selectedPolicy.selectedBy}`}
                    isStub={!!artifacts.selectedPolicy.is_stub}
                  />
                  <ArtifactRow
                    name="run_plan.json"
                    summary={`Policy: ${artifacts.runPlan.policyId} · OCR: ${ocrEngine}`}
                    isStub={!!artifacts.runPlan.is_stub}
                  />
                  <ArtifactRow
                    name="ocr_output.json"
                    summary={`Engine: ${artifacts.ocrOutput.engineId} · Confidence: ${(artifacts.ocrOutput.confidence * 100).toFixed(0)}%`}
                    isStub={!!artifacts.ocrOutput.is_stub}
                  />
                  <ArtifactRow
                    name="extracted_output.json"
                    summary={`${artifacts.extractedOutput.fields.length} fields, ${artifacts.extractedOutput.tables.length} tables`}
                    isStub={!!artifacts.extractedOutput.is_stub}
                  />
                  <ArtifactRow
                    name="validation_report.json"
                    summary={`Pass: ${artifacts.validationReport.passStatus ? "Yes" : "No"} · ${artifacts.validationReport.summary} · ${artifacts.validationReport.issues.length} issues`}
                    isStub={!!artifacts.validationReport.is_stub}
                  />
                  <ArtifactRow
                    name="recovery_report.json"
                    summary={`Attempted: ${artifacts.recoveryReport.attempted ? "Yes" : "No"} · ${artifacts.recoveryReport.summary}`}
                    isStub={!!artifacts.recoveryReport.is_stub}
                  />
                  <ArtifactRow
                    name="final_output.json"
                    summary={`Quality: ${artifacts.finalOutput.qualitySummary} · ${artifacts.finalOutput.fields.length} fields`}
                    isStub={!!artifacts.finalOutput.is_stub}
                  />
                </tbody>
              </table>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
