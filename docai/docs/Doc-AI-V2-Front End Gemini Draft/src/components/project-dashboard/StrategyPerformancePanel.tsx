import { AlertTriangle } from "lucide-react";
import { Card, CardContent } from "@/components/ui";
import { mockStrategyLeaderboard } from "@/lib/mockData";
import { MockMetricBadge } from "./ProjectDashboardBadges";

const STRATEGY_STATUS_STYLES: Record<string, string> = {
  Promoted: "text-emerald-400",
  Testing: "text-cyan-400",
  Retired: "text-slate-500",
};

export function StrategyPerformancePanel() {
  return (
    <Card className="border-white/5 overflow-hidden">
      <CardContent className="p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
            Strategy Performance Summary
          </h3>
          <MockMetricBadge />
        </div>

        <div className="flex items-start gap-2 px-3 py-2 rounded bg-amber-500/5 border border-amber-500/15 mb-4">
          <AlertTriangle className="h-3.5 w-3.5 text-amber-400/70 mt-0.5 shrink-0" />
          <p className="text-[10px] text-amber-400/70">
            Metrics are stub data only. Do not treat as production performance.
          </p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left border-collapse">
            <thead className="bg-slate-900/60 border-b border-white/5 text-slate-500 uppercase text-[9px] tracking-wider">
              <tr>
                <th className="px-3 py-2 font-semibold">Extraction Strategy</th>
                <th className="px-3 py-2 font-semibold text-right">Runs</th>
                <th className="px-3 py-2 font-semibold text-right">Validation Pass</th>
                <th className="px-3 py-2 font-semibold text-right">Recovery Rate</th>
                <th className="px-3 py-2 font-semibold">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {mockStrategyLeaderboard.map((s) => (
                <tr key={s.strategy} className="hover:bg-slate-800/30 transition-colors">
                  <td className="px-3 py-2.5">
                    <p className="text-xs font-medium text-slate-200">{s.family}</p>
                    <p className="text-[9px] font-mono text-slate-600 mt-0.5">{s.strategy}</p>
                  </td>
                  <td className="px-3 py-2.5 text-right text-xs font-mono text-slate-400">
                    {s.runs}
                  </td>
                  <td className="px-3 py-2.5 text-right text-xs font-mono text-slate-400">
                    {s.passRate}
                  </td>
                  <td className="px-3 py-2.5 text-right text-xs font-mono text-slate-400">
                    {s.recoveryRate}
                  </td>
                  <td className="px-3 py-2.5">
                    <span
                      className={`text-[10px] font-semibold ${
                        STRATEGY_STATUS_STYLES[s.status] ?? "text-slate-400"
                      }`}
                    >
                      {s.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
