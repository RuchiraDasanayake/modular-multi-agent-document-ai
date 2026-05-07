import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { Card, CardContent } from "@/components/ui";
import type { JobOut } from "@/lib/docaiApi";
import { RunStatusBadge } from "./ProjectDashboardBadges";

interface RecentRunsTableProps {
  projectId: string | undefined;
  jobs: JobOut[];
}

export function RecentRunsTable({ projectId, jobs }: RecentRunsTableProps) {
  const recent = [...jobs]
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, 5);

  return (
    <Card className="overflow-hidden border-white/5">
      <div className="bg-slate-900/60 px-5 py-2.5 border-b border-white/5 flex items-center justify-between">
        <span className="text-[10px] uppercase font-bold text-slate-400">Recent Jobs</span>
        <Link
          to={`/projects/${projectId}/jobs`}
          className="text-[10px] text-cyan-400/60 hover:text-cyan-400 transition-colors"
        >
          View all jobs {"->"}
        </Link>
      </div>
      <CardContent className="p-0">
        <p className="px-5 py-2 text-[10px] text-slate-500 border-b border-white/5">
          Status shows the job record status from backend.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left border-collapse">
            <thead className="bg-slate-900/80 border-b border-white/5 text-slate-500 uppercase text-[9px] tracking-wider">
              <tr>
                <th className="px-5 py-3 font-semibold">Job</th>
                <th className="px-5 py-3 font-semibold">Job Type</th>
                <th className="px-5 py-3 font-semibold">Job Record Status</th>
                <th className="px-5 py-3 font-semibold text-right">Created</th>
                <th className="px-5 py-3 font-semibold text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 bg-slate-800/10">
              {recent.length === 0 && (
                <tr>
                  <td className="px-5 py-6 text-sm text-slate-500" colSpan={5}>
                    No jobs found for this project yet.
                  </td>
                </tr>
              )}
              {recent.map((job) => (
                <tr key={job.job_id} className="hover:bg-slate-800/40 transition-colors">
                  <td className="px-5 py-3">
                    <Link
                      to={`/projects/${projectId}/jobs/${job.job_id}`}
                      className="font-medium text-slate-200 hover:text-cyan-400 transition-colors text-sm"
                    >
                      {job.name}
                    </Link>
                    <p className="text-[10px] font-mono text-slate-600 mt-0.5">{job.schema_id}</p>
                  </td>
                  <td className="px-5 py-3">
                    <span className="text-xs text-slate-300 capitalize">{job.job_type}</span>
                  </td>
                  <td className="px-5 py-3">
                    <RunStatusBadge status={job.status} />
                  </td>
                  <td className="px-5 py-3 text-right text-xs font-mono text-slate-500 whitespace-nowrap">
                    {new Date(job.created_at).toLocaleString()}
                  </td>
                  <td className="px-5 py-3 text-right">
                    <Link
                      to={`/projects/${projectId}/jobs/${job.job_id}`}
                      className="inline-flex items-center gap-1 text-xs text-cyan-400/70 hover:text-cyan-400 transition-colors whitespace-nowrap"
                    >
                      View Job
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
