import { BrainCircuit } from "lucide-react";
import { Card, CardContent } from "@/components/ui";
import { StubBadge } from "./ReviewBadges";
import type { FrontendSelectedPolicy } from "@/types/domain";

interface ExtractionStrategyPanelProps {
  selectedPolicy: FrontendSelectedPolicy;
}

export default function ExtractionStrategyPanel({ selectedPolicy }: ExtractionStrategyPanelProps) {
  return (
    <Card className="glass-card border-white/5">
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
            <BrainCircuit className="h-3.5 w-3.5 opacity-70" />
            Extraction Strategy
          </h3>
          {selectedPolicy.is_stub && <StubBadge />}
        </div>

        <div className="space-y-3">
          <div>
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">
              Strategy Name
            </p>
            <p className="text-sm font-semibold text-cyan-400">{selectedPolicy.strategyName}</p>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">
                Selected By
              </p>
              <p className="text-xs font-mono text-slate-300">{selectedPolicy.selectedBy}</p>
            </div>
            <div>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">
                Internal Policy ID
              </p>
              <p className="text-xs font-mono text-slate-500">{selectedPolicy.policyId}</p>
            </div>
          </div>

          <div>
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">
              Selection Rationale
            </p>
            <ul className="space-y-1.5">
              {selectedPolicy.reasons.map((reason, i) => (
                <li key={i} className="flex items-start gap-2 text-xs text-slate-300">
                  <span className="text-cyan-400 mt-0.5 shrink-0">•</span>
                  {reason}
                </li>
              ))}
            </ul>
          </div>

          {selectedPolicy.disabledCandidates && selectedPolicy.disabledCandidates.length > 0 && (
            <div>
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">
                Disabled Candidates
              </p>
              <ul className="space-y-1.5">
                {selectedPolicy.disabledCandidates.map((c, i) => (
                  <li key={i} className="text-xs text-slate-400">
                    <span className="font-mono text-slate-500 mr-2">{c.policyId}</span>—{" "}
                    {c.reasonDisabled}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
