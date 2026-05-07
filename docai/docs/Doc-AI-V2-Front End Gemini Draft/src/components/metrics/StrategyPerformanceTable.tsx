import { AlertTriangle } from "lucide-react";
import { Card, CardContent } from "@/components/ui";
import { mockStrategyLeaderboard } from "@/lib/mockData";
import { EvidenceStatusBadge, MockMetricBadge } from "./MetricsBadges";

const STRATEGY_STATUS_STYLES: Record<string, string> = {
  Promoted: "text-emerald-400",
  Testing: "text-cyan-400",
  Retired: "text-slate-500",
};

function reviewBurden(passRate: string): string {
  const n = parseFloat(passRate);
  if (n >= 85) return "Low";
  if (n >= 65) return "Medium";
  return "High";
}

function reviewBurdenClass(burden: string): string {
  if (burden === "Low") return "text-emerald-400";
  if (burden === "Medium") return "text-amber-400";
  return "text-red-400";
}

export function StrategyPerformanceTable() {
  return (
    <Card className="overflow-hidden border-white/5">
      <div className="bg-slate-900/60 px-5 py-2.5 border-b border-white/5 flex items-center justify-between">
        <span className="text-[10px] uppercase font-bold text-slate-400">
          Strategy Performance Summary
        </span>
        <MockMetricBadge />
      </div>
      <CardContent className="p-0">
        <div className="flex items-start gap-2 px-4 py-2.5 bg-amber-500/5 border-b border-amber-500/15">
          <AlertTriangle className="h-3.5 w-3.5 text-amber-400/60 mt-0.5 shrink-0" />
          <p className="text-[10px] text-amber-400/60">
            Mock only — not production ranking. Rankings require real review records and Expected
            Values.
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left border-collapse whitespace-nowrap">
            <thead className="bg-slate-900/80 border-b border-white/5 text-slate-500 uppercase text-[9px] tracking-wider">
              <tr>
                <th className="px-4 py-3 font-semibold">Extraction Strategy</th>
                <th className="px-4 py-3 font-semibold text-right">Documents</th>
                <th className="px-4 py-3 font-semibold text-right">Validation Pass %</th>
                <th className="px-4 py-3 font-semibold text-right">Recovery Success %</th>
                <th className="px-4 py-3 font-semibold">Review Burden</th>
                <th className="px-4 py-3 font-semibold">Evidence Status</th>
                <th className="px-4 py-3 font-semibold">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 bg-slate-800/10">
              {mockStrategyLeaderboard.map((s) => {
                const burden = reviewBurden(s.passRate);
                return (
                  <tr key={s.strategy} className="hover:bg-slate-800/40 transition-colors">
                    <td className="px-4 py-3">
                      <p className="text-xs font-medium text-slate-200">{s.family}</p>
                      <p className="text-[9px] font-mono text-slate-600 mt-0.5">{s.strategy}</p>
                    </td>
                    <td className="px-4 py-3 text-right text-xs font-mono text-slate-400">
                      {s.runs}
                    </td>
                    <td className="px-4 py-3 text-right text-xs font-mono text-slate-400">
                      {s.passRate}
                    </td>
                    <td className="px-4 py-3 text-right text-xs font-mono text-slate-400">
                      {s.recoveryRate}
                    </td>
                    <td className="px-4 py-3">
                      <span className={`text-xs font-semibold ${reviewBurdenClass(burden)}`}>
                        {burden}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <EvidenceStatusBadge status="Stub Only" />
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`text-[10px] font-semibold ${
                          STRATEGY_STATUS_STYLES[s.status] ?? "text-slate-400"
                        }`}
                      >
                        {s.status}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
