import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { Card, CardContent } from "@/components/ui";
import { mockJobsList } from "@/lib/mockData";
import { RunStatusBadge } from "./ProjectDashboardBadges";
import { RunTypeBadge } from "@/components/jobs/RunTypeBadge";

function StrategyChips({ strategies }: { strategies: string[] }) {
  if (strategies.length === 0) return <span className="text-slate-600 text-xs">—</span>;
  const visible = strategies.slice(0, 2);
  const overflow = strategies.length - 2;
  return (
    <div className="flex flex-wrap gap-1">
      {visible.map((s) => (
        <span
          key={s}
          className="text-[9px] font-mono text-slate-400 bg-slate-800/60 border border-white/5 px-1.5 py-0.5 rounded leading-tight"
        >
          {s}
        </span>
      ))}
      {overflow > 0 && <span className="text-[9px] text-slate-500 self-center">+{overflow}</span>}
    </div>
  );
}

interface RecentRunsTableProps {
  projectId: string | undefined;
}

export function RecentRunsTable({ projectId }: RecentRunsTableProps) {
  const recent = [...mockJobsList]
    .sort((a, b) => b.lastUpdated.localeCompare(a.lastUpdated))
    .slice(0, 5);

  return (
    <Card className="overflow-hidden border-white/5">
      <div className="bg-slate-900/60 px-5 py-2.5 border-b border-white/5 flex items-center justify-between">
        <span className="text-[10px] uppercase font-bold text-slate-400">Recent Runs</span>
        <Link
          to={`/projects/${projectId}/jobs`}
          className="text-[10px] text-cyan-400/60 hover:text-cyan-400 transition-colors"
        >
          View all jobs →
        </Link>
      </div>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left border-collapse">
            <thead className="bg-slate-900/80 border-b border-white/5 text-slate-500 uppercase text-[9px] tracking-wider">
              <tr>
                <th className="px-5 py-3 font-semibold">Job</th>
                <th className="px-5 py-3 font-semibold">Run Type</th>
                <th className="px-5 py-3 font-semibold">Status</th>
                <th className="px-5 py-3 font-semibold text-right">Documents</th>
                <th className="px-5 py-3 font-semibold text-right">Needs Review</th>
                <th className="px-5 py-3 font-semibold">Extraction Strategies</th>
                <th className="px-5 py-3 font-semibold text-right">Last Updated</th>
                <th className="px-5 py-3 font-semibold text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 bg-slate-800/10">
              {recent.map((job) => (
                <tr key={job.id} className="hover:bg-slate-800/40 transition-colors">
                  <td className="px-5 py-3">
                    <Link
                      to={`/projects/${projectId}/jobs/${job.id}`}
                      className="font-medium text-slate-200 hover:text-cyan-400 transition-colors text-sm"
                    >
                      {job.name}
                    </Link>
                    <p className="text-[10px] font-mono text-slate-600 mt-0.5">{job.schema}</p>
                  </td>
                  <td className="px-5 py-3">
                    <RunTypeBadge runType={job.runType} />
                  </td>
                  <td className="px-5 py-3">
                    <RunStatusBadge status={job.status} />
                  </td>
                  <td className="px-5 py-3 text-right text-xs font-mono text-slate-300">
                    {job.documentCount}
                  </td>
                  <td className="px-5 py-3 text-right text-xs font-mono">
                    {job.needsReviewCount > 0 ? (
                      <span className="text-amber-400">{job.needsReviewCount}</span>
                    ) : (
                      <span className="text-slate-600">—</span>
                    )}
                  </td>
                  <td className="px-5 py-3 max-w-[180px]">
                    <StrategyChips strategies={job.strategies} />
                  </td>
                  <td className="px-5 py-3 text-right text-xs font-mono text-slate-500 whitespace-nowrap">
                    {job.lastUpdated}
                  </td>
                  <td className="px-5 py-3 text-right">
                    <Link
                      to={`/projects/${projectId}/jobs/${job.id}`}
                      className="inline-flex items-center gap-1 text-xs text-cyan-400/70 hover:text-cyan-400 transition-colors whitespace-nowrap"
                    >
                      View Run Console
                      <ChevronRight className="h-3 w-3 shrink-0" />
                    </Link>
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
