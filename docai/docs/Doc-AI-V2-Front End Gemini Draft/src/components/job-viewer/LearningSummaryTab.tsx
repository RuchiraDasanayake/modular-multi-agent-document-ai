import { AlertTriangle } from "lucide-react";
import { Card, CardContent, Badge } from "@/components/ui";
import { mockJobContext, mockDocumentQueue, mockJobLearningSummary } from "@/lib/mockData";

export default function LearningSummaryTab() {
  const completedDocs = mockDocumentQueue.filter((d) => d.reviewStatus === "Completed");

  return (
    <div className="space-y-6 animate-fade-in" style={{ animationDelay: "0.1s" }}>
      <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-400 text-xs font-medium">
        <AlertTriangle className="h-4 w-4 shrink-0" />
        <span>
          <span className="font-bold uppercase tracking-wider mr-1">
            Mock Only — Future Evidence Summary
          </span>
          — No real learning has occurred. This section shows stub observations from the current run
          only.
        </span>
      </div>

      <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400">Learning Summary</h2>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardContent className="p-4">
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">
              Reviewed Documents
            </p>
            <p className="text-xl font-bold text-slate-100">{completedDocs.length}</p>
            <p className="text-[10px] text-slate-500 mt-1">of {mockJobContext.documentCount} total</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">
              Expected Values
            </p>
            <p className="text-xl font-bold text-slate-400">—</p>
            <p className="text-[10px] text-slate-500 mt-1">Not yet defined for this run</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-1">
              Strategies Observed
            </p>
            <p className="text-xl font-bold text-slate-100">{mockJobLearningSummary.policiesUsed.length}</p>
            <p className="text-[10px] text-slate-500 mt-1">from this run</p>
          </CardContent>
        </Card>
      </div>

      <Card className="overflow-hidden border-white/5">
        <div className="bg-slate-900/60 px-4 py-2 border-b border-white/5 text-[10px] uppercase font-bold text-slate-400">
          Strategy Observations (Stub)
        </div>
        <CardContent className="p-0">
          <table className="w-full text-sm text-left border-collapse">
            <thead className="bg-slate-900/80 border-b border-white/5 text-slate-500 uppercase text-[9px] tracking-wider">
              <tr>
                <th className="px-4 py-3">Strategy</th>
                <th className="px-4 py-3">Docs</th>
                <th className="px-4 py-3">Pass Rate</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 bg-slate-800/10">
              {mockJobLearningSummary.performance.map((p, i) => (
                <tr key={i} className="hover:bg-slate-800/40 transition-colors">
                  <td className="px-4 py-3 text-slate-300 text-xs font-medium">{p.policy}</td>
                  <td className="px-4 py-3 text-slate-400 text-xs font-mono">{p.docs}</td>
                  <td className="px-4 py-3 text-emerald-400 font-mono text-xs">{p.passRate}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card className="overflow-hidden border-white/5">
        <CardContent className="p-4">
          <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">
            Common Failed Fields (Stub)
          </p>
          <div className="flex flex-wrap gap-2">
            {mockJobLearningSummary.commonFailedFields.map((field, i) => (
              <Badge key={i} variant="outline" className="border-amber-500/30 bg-amber-500/10 text-amber-400">
                {field}
              </Badge>
            ))}
          </div>
        </CardContent>
      </Card>

      <p className="text-[10px] text-slate-500 font-mono">
        Recommendations and strategy mutation controls are not available until real expected values
        are reviewed and approved.
      </p>
    </div>
  );
}
