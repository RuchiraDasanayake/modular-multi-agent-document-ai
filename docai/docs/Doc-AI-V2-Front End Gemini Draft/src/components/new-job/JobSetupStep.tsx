import { Settings2 } from "lucide-react";
import { Card, CardContent, Input } from "@/components/ui";
import { RunTypeBadge } from "./NewJobBadges";

interface JobSetupStepProps {
  jobName: string;
  runType: "Training Run" | "Production Run";
  notes: string;
  onJobName: (v: string) => void;
  onRunType: (v: "Training Run" | "Production Run") => void;
  onNotes: (v: string) => void;
}

export default function JobSetupStep({
  jobName,
  runType,
  notes,
  onJobName,
  onRunType,
  onNotes,
}: JobSetupStepProps) {
  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2 mb-1">
          <Settings2 className="h-4 w-4 opacity-70" />
          Job Setup
        </h2>
        <p className="text-xs text-slate-500">Name this job and choose a run type.</p>
      </div>

      <Card className="glass-card border-white/5">
        <CardContent className="p-5 space-y-5">
          <div className="space-y-1.5">
            <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider">
              Job Name
            </label>
            <Input
              value={jobName}
              onChange={(e) => onJobName(e.target.value)}
              placeholder="e.g. November 2023 Invoices"
              className="text-sm border-white/10 bg-slate-900/50 text-slate-200 focus:border-cyan-500"
            />
          </div>

          <div className="space-y-1.5">
            <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider">
              Notes (optional)
            </label>
            <textarea
              value={notes}
              onChange={(e) => onNotes(e.target.value)}
              placeholder="Short description of this batch..."
              rows={2}
              className="w-full px-3 py-2 text-sm border border-white/10 bg-slate-900/50 rounded text-slate-200 focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500/50 outline-none resize-none transition-all"
            />
          </div>

          <div className="space-y-3">
            <label className="block text-[11px] font-bold text-slate-500 uppercase tracking-wider">
              Run Type
            </label>
            <div className="grid grid-cols-2 gap-4">
              {(["Training Run", "Production Run"] as const).map((rt) => {
                const active = runType === rt;
                const isTraining = rt === "Training Run";
                return (
                  <button
                    key={rt}
                    type="button"
                    onClick={() => onRunType(rt)}
                    className={`p-4 rounded-lg border text-left transition-all relative ${
                      active
                        ? isTraining
                          ? "border-cyan-500 bg-cyan-500/10 shadow-[0_0_15px_rgba(6,182,212,0.15)]"
                          : "border-emerald-500 bg-emerald-500/10 shadow-[0_0_15px_rgba(16,185,129,0.15)]"
                        : "border-white/10 bg-slate-900/50 hover:bg-slate-800/80"
                    }`}
                  >
                    {active && (
                      <div
                        className={`absolute top-2 right-2 w-2 h-2 rounded-full ${
                          isTraining
                            ? "bg-cyan-400 shadow-[0_0_5px_rgba(6,182,212,0.8)]"
                            : "bg-emerald-400 shadow-[0_0_5px_rgba(16,185,129,0.8)]"
                        }`}
                      />
                    )}
                    <RunTypeBadge runType={rt} />
                    <ul className="text-xs text-slate-400 space-y-1 list-disc pl-4 mt-3">
                      {isTraining ? (
                        <>
                          <li>Human review required</li>
                          <li>Corrections become Expected Values</li>
                          <li>Used for calibration batches</li>
                        </>
                      ) : (
                        <>
                          <li>Human review optional</li>
                          <li>Low-confidence docs enter review queue</li>
                          <li>Best for large-scale processing</li>
                        </>
                      )}
                    </ul>
                  </button>
                );
              })}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
