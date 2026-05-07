import { RefreshCw } from "lucide-react";
import { Card, CardContent } from "@/components/ui";
import { StubBadge } from "./ReviewBadges";
import type { FrontendRecoveryReport } from "@/types/domain";

interface RecoveryAttemptsPanelProps {
  recoveryReport: FrontendRecoveryReport;
}

export default function RecoveryAttemptsPanel({ recoveryReport }: RecoveryAttemptsPanelProps) {
  return (
    <Card className="glass-card border-white/5">
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
            <RefreshCw className="h-3.5 w-3.5 opacity-70" />
            Recovery Report
          </h3>
          {recoveryReport.is_stub && <StubBadge />}
        </div>

        <div className="grid grid-cols-2 gap-3 mb-4">
          <div>
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">
              Attempted
            </p>
            <p
              className={`text-xs font-medium ${
                recoveryReport.attempted ? "text-emerald-400" : "text-slate-500"
              }`}
            >
              {recoveryReport.attempted ? "Yes" : "Not Attempted"}
            </p>
          </div>
          <div>
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">
              Summary
            </p>
            <p className="text-xs text-slate-300">{recoveryReport.summary}</p>
          </div>
        </div>

        {!recoveryReport.attempted ? (
          <p className="text-xs text-slate-500 font-mono">No recovery was attempted for this document.</p>
        ) : (
          <div className="space-y-3">
            {recoveryReport.recoveredItems.length > 0 && (
              <div>
                <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">
                  Recovered Items
                </p>
                <ul className="space-y-1">
                  {recoveryReport.recoveredItems.map((item, i) => (
                    <li key={i} className="flex items-center gap-2 text-xs">
                      <span className="text-emerald-400 shrink-0">✓</span>
                      <span className="text-emerald-300 font-mono">{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {recoveryReport.failedItems.length > 0 && (
              <div>
                <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">
                  Failed Items
                </p>
                <ul className="space-y-1">
                  {recoveryReport.failedItems.map((item, i) => (
                    <li key={i} className="flex items-center gap-2 text-xs">
                      <span className="text-red-400 shrink-0">✗</span>
                      <span className="text-red-300 font-mono">{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
