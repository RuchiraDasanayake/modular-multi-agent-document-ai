import { Card, CardContent } from "@/components/ui";
import { mockRunProgression } from "@/lib/mockData";
import { EvidenceStatusBadge, MockMetricBadge } from "./MetricsBadges";
import { RunTypeBadge } from "@/components/jobs/RunTypeBadge";

function deriveEvidenceStatus(docs: number, reviewed: number): string {
  if (docs === 0) return "Stub Only";
  if (reviewed === 0) return "Stub Only";
  if (reviewed >= docs) return "Review Required";
  return "Stub Only";
}

export function RunProgressionTable() {
  return (
    <Card className="overflow-hidden border-white/5">
      <div className="bg-slate-900/60 px-5 py-2.5 border-b border-white/5 flex items-center justify-between">
        <span className="text-[10px] uppercase font-bold text-slate-400">Run Progression</span>
        <MockMetricBadge />
      </div>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left border-collapse whitespace-nowrap">
            <thead className="bg-slate-900/80 border-b border-white/5 text-slate-500 uppercase text-[9px] tracking-wider">
              <tr>
                <th className="px-4 py-3 font-semibold">Run</th>
                <th className="px-4 py-3 font-semibold">Run Type</th>
                <th className="px-4 py-3 font-semibold text-right">Documents</th>
                <th className="px-4 py-3 font-semibold text-right">Reviewed</th>
                <th className="px-4 py-3 font-semibold text-right">Validation Pass %</th>
                <th className="px-4 py-3 font-semibold text-right">Recovery Success %</th>
                <th className="px-4 py-3 font-semibold">Best Extraction Strategy</th>
                <th className="px-4 py-3 font-semibold">Evidence Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 bg-slate-800/10">
              {mockRunProgression.map((run, i) => (
                <tr key={i} className="hover:bg-slate-800/40 transition-colors">
                  <td className="px-4 py-3 font-medium text-slate-200 text-xs">{run.run}</td>
                  <td className="px-4 py-3">
                    <RunTypeBadge runType={run.type} />
                  </td>
                  <td className="px-4 py-3 text-right text-xs font-mono text-slate-300">{run.docs}</td>
                  <td className="px-4 py-3 text-right text-xs font-mono text-slate-400">{run.reviewed}</td>
                  <td className="px-4 py-3 text-right text-xs font-mono text-slate-400">
                    <span className="text-slate-500">{run.passRate}</span>
                  </td>
                  <td className="px-4 py-3 text-right text-xs font-mono text-slate-500">
                    {run.recoveryRate}
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-[10px] font-mono text-slate-400">{run.bestPolicy}</span>
                  </td>
                  <td className="px-4 py-3">
                    <EvidenceStatusBadge
                      status={deriveEvidenceStatus(run.docs, run.reviewed)}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="px-4 py-2.5 border-t border-white/5 bg-slate-900/30">
          <p className="text-[10px] font-mono text-slate-600">
            F1 Score column removed — real F1 requires reviewed Expected Values and backend scoring.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
