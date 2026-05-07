import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import { Card, CardContent } from "@/components/ui";
import { JobOut } from "@/lib/docaiApi";
import { JobStatusBadge } from "./JobStatusBadge";
import { RunTypeBadge } from "./RunTypeBadge";

interface JobsTableProps {
  jobs: JobOut[];
  projectId: string | undefined;
}

export function JobsTable({ jobs, projectId }: JobsTableProps) {
  if (jobs.length === 0) {
    return (
      <Card className="p-8 text-center text-slate-400">
        No jobs yet. Create one to get started.
      </Card>
    );
  }

  return (
    <Card className="overflow-hidden border-white/5">
      <div className="bg-slate-900/60 px-5 py-2.5 border-b border-white/5 flex items-center justify-between">
        <span className="text-[10px] uppercase font-bold text-slate-400">All Jobs</span>
        <span className="text-[10px] font-mono text-slate-500 normal-case">
          {jobs.length} jobs
        </span>
      </div>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm text-left border-collapse">
            <thead className="bg-slate-900/80 border-b border-white/5 text-slate-500 uppercase text-[9px] tracking-wider">
              <tr>
                <th className="px-5 py-3 font-semibold">Job</th>
                <th className="px-5 py-3 font-semibold">Run Type</th>
                <th className="px-5 py-3 font-semibold">Status</th>
                <th className="px-5 py-3 font-semibold text-right">Schema</th>
                <th className="px-5 py-3 font-semibold text-right">Created</th>
                <th className="px-5 py-3 font-semibold text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5 bg-slate-800/10">
              {jobs.map((job) => (
                <tr key={job.job_id} className="hover:bg-slate-800/40 transition-colors">
                  <td className="px-5 py-3">
                    <Link
                      to={`/projects/${projectId}/jobs/${job.job_id}`}
                      className="font-medium text-slate-200 hover:text-cyan-400 transition-colors text-sm"
                    >
                      {job.name}
                    </Link>
                  </td>
                  <td className="px-5 py-3">
                    <RunTypeBadge runType={job.job_type === "production" ? "Production Run" : "Training Run"} />
                  </td>
                  <td className="px-5 py-3">
                    <JobStatusBadge status={job.status} />
                  </td>
                  <td className="px-5 py-3 text-right text-xs font-mono text-slate-400">
                    {job.schema_id}
                  </td>
                  <td className="px-5 py-3 text-right text-xs font-mono text-slate-500">
                    {new Date(job.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-5 py-3 text-right">
                    <Link
                      to={`/projects/${projectId}/jobs/${job.job_id}`}
                      className="inline-flex items-center gap-1 text-xs text-cyan-400/70 hover:text-cyan-400 transition-colors whitespace-nowrap"
                    >
                      View
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
