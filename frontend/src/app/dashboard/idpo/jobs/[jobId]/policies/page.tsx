import Link from "next/link";
import { IdpoCard } from "@/components/idpo/card";
import { JobPolicyCreateForm } from "@/components/idpo/job-policy-create-form";
import { listJobPolicies } from "@/server/policies";

function formatDate(value: string | null): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function formatF1(value: number | null): string {
  return typeof value === "number" ? value.toFixed(2) : "-";
}

function stateTone(value: string): string {
  switch (value) {
    case "promoted":
      return "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-700/40 dark:bg-emerald-900/20 dark:text-emerald-300";
    case "demoted":
      return "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-700/40 dark:bg-rose-900/20 dark:text-rose-300";
    case "watch":
      return "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-700/40 dark:bg-amber-900/20 dark:text-amber-300";
    case "candidate":
      return "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-700/40 dark:bg-sky-900/20 dark:text-sky-300";
    default:
      return "border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-950/40 dark:text-slate-300";
  }
}

export default async function JobPoliciesWorkspacePage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const resolved = await params;
  const jobId = decodeURIComponent(resolved.jobId);
  const workspace = listJobPolicies(jobId);

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <Link
          href={`/dashboard/idpo/jobs/${encodeURIComponent(jobId)}`}
          className="text-xs text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"
        >
          Back to job
        </Link>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold text-slate-900 dark:text-white">Policy workspace</h1>
          <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-medium text-slate-700 dark:border-slate-700 dark:bg-slate-950/40 dark:text-slate-200">
            job {jobId}
          </span>
        </div>
        <p className="mt-2 max-w-4xl text-sm text-slate-600 dark:text-slate-300">
          This is the job-scoped policy bank. Track which policies are performing well, which are being demoted, and add
          custom policies that become available on the next run.
        </p>
        <div className="mt-4 grid gap-3 md:grid-cols-4">
          <IdpoCard className="p-4">
            <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Policies in job</div>
            <div className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{workspace.policies.length}</div>
          </IdpoCard>
          <IdpoCard className="p-4">
            <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Custom policies</div>
            <div className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">{workspace.customPolicyCount}</div>
          </IdpoCard>
          <IdpoCard className="p-4">
            <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Promoted</div>
            <div className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">
              {workspace.policies.filter((policy) => policy.learningState === "promoted").length}
            </div>
          </IdpoCard>
          <IdpoCard className="p-4">
            <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Demoted</div>
            <div className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">
              {workspace.policies.filter((policy) => policy.learningState === "demoted").length}
            </div>
          </IdpoCard>
        </div>
      </section>

      <IdpoCard>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Leaderboard</h2>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              Reviewed exact F1 first, then usage count. This is job-local evidence, not global memory.
            </p>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400">Source: {workspace.sourcePath}</p>
        </div>
        <div className="mt-4 grid gap-4 lg:grid-cols-3">
          {workspace.leaderboard.slice(0, 6).map((policy, index) => (
            <Link
              key={policy.policyId}
              href={`/dashboard/idpo/jobs/${encodeURIComponent(jobId)}/policies/${encodeURIComponent(policy.policyId)}`}
              className="rounded-2xl border border-slate-200 bg-slate-50 p-4 hover:border-cyan-300 hover:bg-cyan-50/50 dark:border-slate-800 dark:bg-slate-950/40 dark:hover:border-cyan-700/40 dark:hover:bg-cyan-950/10"
            >
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm font-semibold text-slate-900 dark:text-white">
                  {index + 1}. {policy.name}
                </span>
                <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${stateTone(policy.learningState)}`}>
                  {policy.learningState}
                </span>
              </div>
              <div className="mt-2 text-xs text-slate-500 dark:text-slate-400">{policy.policyId}</div>
              <div className="mt-4 grid grid-cols-3 gap-3 text-sm">
                <div>
                  <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">F1</div>
                  <div className="mt-1 font-medium text-slate-900 dark:text-white">{formatF1(policy.meanExactF1)}</div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Processed</div>
                  <div className="mt-1 font-medium text-slate-900 dark:text-white">{policy.documentsProcessed}</div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">Reviewed</div>
                  <div className="mt-1 font-medium text-slate-900 dark:text-white">{policy.reviewedDocuments}</div>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </IdpoCard>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(340px,0.9fr)]">
        <IdpoCard>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Policy table</h2>
              <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
                Track source, learning state, reviewed F1, and how many documents each policy touched in this job.
              </p>
            </div>
          </div>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[980px] text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                  <th className="px-2 py-2">Policy</th>
                  <th className="px-2 py-2">Source</th>
                  <th className="px-2 py-2">State</th>
                  <th className="px-2 py-2">Reviewed F1</th>
                  <th className="px-2 py-2">Processed</th>
                  <th className="px-2 py-2">Reviewed</th>
                  <th className="px-2 py-2">Failed</th>
                  <th className="px-2 py-2">Last used</th>
                </tr>
              </thead>
              <tbody>
                {workspace.policies.map((policy) => (
                  <tr key={policy.policyId} className="border-b border-slate-100 dark:border-slate-800">
                    <td className="px-2 py-3">
                      <Link
                        href={`/dashboard/idpo/jobs/${encodeURIComponent(jobId)}/policies/${encodeURIComponent(policy.policyId)}`}
                        className="font-medium text-cyan-700 hover:text-cyan-800 dark:text-cyan-300 dark:hover:text-cyan-200"
                      >
                        {policy.policyId}
                      </Link>
                      <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{policy.name}</div>
                    </td>
                    <td className="px-2 py-3 capitalize text-slate-600 dark:text-slate-300">{policy.source}</td>
                    <td className="px-2 py-3">
                      <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${stateTone(policy.learningState)}`}>
                        {policy.learningState}
                      </span>
                    </td>
                    <td className="px-2 py-3 text-slate-600 dark:text-slate-300">{formatF1(policy.meanExactF1)}</td>
                    <td className="px-2 py-3 text-slate-600 dark:text-slate-300">{policy.documentsProcessed}</td>
                    <td className="px-2 py-3 text-slate-600 dark:text-slate-300">{policy.reviewedDocuments}</td>
                    <td className="px-2 py-3 text-slate-600 dark:text-slate-300">{policy.documentsFailed}</td>
                    <td className="px-2 py-3 text-slate-600 dark:text-slate-300">{formatDate(policy.lastUsedAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </IdpoCard>

        <IdpoCard>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Add custom policy</h2>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
            Add a job-scoped policy. It will be merged into the job policy bank and become available on the next run.
          </p>
          <div className="mt-4">
            <JobPolicyCreateForm jobId={jobId} />
          </div>
        </IdpoCard>
      </div>
    </div>
  );
}
