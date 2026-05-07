import { AlertTriangle, CheckCircle } from "lucide-react";
import { Card, CardContent, Button } from "@/components/ui";
import { RunTypeBadge, MockBadge } from "./NewJobBadges";
import { mockDocumentQueue } from "@/lib/mockData";

interface StartRunStepProps {
  jobName: string;
  runType: "Training Run" | "Production Run";
  selectedSchemaId: string;
  ocrPreference: string;
  localModel: string;
  strategyMode: string;
  reviewOnLowConfidence: boolean;
  reviewOnValidationFailure: boolean;
  reviewOnRecoveryFailure: boolean;
}

const SCHEMA_NAMES: Record<string, string> = {
  s1: "Invoice Standard v1",
  s2: "Invoice Complex v2",
};

export default function StartRunStep({
  jobName,
  runType,
  selectedSchemaId,
  ocrPreference,
  localModel,
  strategyMode,
  reviewOnLowConfidence,
  reviewOnValidationFailure,
  reviewOnRecoveryFailure,
}: StartRunStepProps) {
  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2 mb-1">
          <CheckCircle className="h-4 w-4 opacity-70" />
          Start Run
        </h2>
        <p className="text-xs text-slate-500">Review the preflight summary before creating the job.</p>
      </div>

      <div className="flex items-start gap-3 px-4 py-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-400 text-xs font-medium">
        <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />
        <span>
          <span className="font-bold uppercase tracking-wider mr-1">Mock Only</span>
          — Backend execution is not connected. Job creation and run start are simulated.
        </span>
      </div>

      <Card className="glass-card border-white/5">
        <CardContent className="p-5 space-y-4">
          <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-3">
            Preflight Summary
          </p>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Job Name</p>
              <p className="text-sm font-medium text-slate-200">{jobName || "—"}</p>
            </div>
            <div>
              <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Run Type</p>
              <RunTypeBadge runType={runType} />
            </div>
            <div>
              <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">
                Extraction Schema
              </p>
              <p className="text-xs font-mono text-slate-300">
                {SCHEMA_NAMES[selectedSchemaId] ?? selectedSchemaId}
              </p>
            </div>
            <div>
              <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Documents</p>
              <p className="text-sm font-mono text-slate-200">{mockDocumentQueue.length}</p>
            </div>
            <div>
              <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">OCR</p>
              <p className="text-xs text-slate-300">{ocrPreference}</p>
            </div>
            <div>
              <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Local Model</p>
              <p className="text-xs font-mono text-slate-300">{localModel}</p>
            </div>
            <div>
              <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Strategy Mode</p>
              <p className="text-xs text-slate-300">{strategyMode}</p>
            </div>
            <div>
              <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">Review Triggers</p>
              <div className="flex flex-wrap gap-1 mt-1">
                {reviewOnLowConfidence && (
                  <span className="text-[9px] text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20">Low Confidence</span>
                )}
                {reviewOnValidationFailure && (
                  <span className="text-[9px] text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20">Validation Failure</span>
                )}
                {reviewOnRecoveryFailure && (
                  <span className="text-[9px] text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded border border-amber-500/20">Recovery Failure</span>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="flex items-center gap-3">
        <Button variant="outline" disabled className="text-slate-500 border-white/10 cursor-not-allowed flex items-center gap-2">
          <MockBadge />
          Create Job (Mock)
        </Button>
        <Button disabled className="text-slate-500 border border-white/10 bg-transparent cursor-not-allowed flex items-center gap-2">
          <MockBadge />
          Start Run (Mock)
        </Button>
      </div>
    </div>
  );
}
