import { ShieldCheck, ShieldAlert } from "lucide-react";
import { Card, CardContent } from "@/components/ui";
import { ValidationStatusBadge, StubBadge } from "./ReviewBadges";
import type { FrontendValidationReport } from "@/types/domain";

interface ValidationIssuesPanelProps {
  validationReport: FrontendValidationReport;
}

export default function ValidationIssuesPanel({ validationReport }: ValidationIssuesPanelProps) {
  const passed = validationReport.passStatus;

  return (
    <Card className={`border ${passed ? "border-white/5" : "border-red-500/20"} glass-card`}>
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
            {passed ? (
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-400 opacity-80" />
            ) : (
              <ShieldAlert className="h-3.5 w-3.5 text-red-400 opacity-80" />
            )}
            Validation Report
          </h3>
          <div className="flex items-center gap-2">
            <span
              className={`text-[10px] font-bold uppercase px-2 py-0.5 rounded ${
                passed
                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                  : "bg-red-500/10 text-red-400 border border-red-500/20"
              }`}
            >
              {passed ? "Pass" : "Fail"}
            </span>
            {validationReport.is_stub && <StubBadge />}
          </div>
        </div>

        <div className="mb-3">
          <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">
            Summary
          </p>
          <p className="text-xs text-slate-300">{validationReport.summary}</p>
        </div>

        {validationReport.issues.length === 0 ? (
          <p className="text-xs text-emerald-400/70 font-mono">No validation issues detected.</p>
        ) : (
          <div>
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">
              Issues ({validationReport.issues.length})
            </p>
            <ul className="space-y-2">
              {validationReport.issues.map((issue, i) => (
                <li
                  key={i}
                  className="flex items-start gap-3 p-2.5 rounded bg-slate-900/50 border border-white/5"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-mono text-xs text-slate-300">{issue.target}</span>
                      <ValidationStatusBadge status={issue.status} />
                    </div>
                    <p className="text-xs text-slate-400">{issue.message}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
