import Link from "next/link";
import { headers } from "next/headers";
import { notFound } from "next/navigation";
import { IdpoCard } from "@/components/idpo/card";
import { JobPolicyCreateForm } from "@/components/idpo/job-policy-create-form";
import { JobPolicyRuntimeToggle } from "@/components/idpo/job-policy-runtime-toggle";
import { getJobPolicyTemplates, getSuggestedJobPolicyMatching, listJobPolicies } from "@/server/policies";
import { requireJob } from "@/server/access";
import { requireUser } from "@/server/auth";

function formatF1(value: number | null): string {
  return typeof value === "number" ? value.toFixed(2) : "-";
}

function formatConfidence(value: number | null): string {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "-";
}

function formatSelection(value: {
  ahmnRouteCount: number;
  jobOverlayRouteCount: number;
  fallbackRouteCount: number;
  staticRouteCount: number;
}): string {
  const parts: string[] = [];
  if (value.ahmnRouteCount > 0) {
    parts.push(`${value.ahmnRouteCount} adaptive`);
  }
  if (value.jobOverlayRouteCount > 0) {
    parts.push(`${value.jobOverlayRouteCount} overlay`);
  }
  if (value.fallbackRouteCount > 0) {
    parts.push(`${value.fallbackRouteCount} fallback`);
  }
  if (value.staticRouteCount > 0) {
    parts.push(`${value.staticRouteCount} static`);
  }
  return parts.length > 0 ? parts.join(", ") : "-";
}

function formatWarmStart(warmStartCount: number, meanNeighborCount: number | null): string {
  if (warmStartCount === 0) {
    return "Not used";
  }
  if (typeof meanNeighborCount !== "number") {
    return `${warmStartCount} doc(s)`;
  }
  return `${warmStartCount} doc(s), avg ${meanNeighborCount.toFixed(1)} match`;
}

function formatFeedback(logged: number, pending: number): string {
  if (logged === 0 && pending === 0) {
    return "-";
  }
  return `${logged} logged, ${pending} pending`;
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

function availabilityTone(value: "active" | "active_extension" | "inactive" | "inactive_extension"): string {
  if (value === "inactive") {
    return "border-slate-300 bg-slate-100 text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300";
  }
  if (value === "inactive_extension") {
    return "border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-700/40 dark:bg-violet-900/20 dark:text-violet-300";
  }
  if (value === "active_extension") {
    return "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-700/40 dark:bg-emerald-900/20 dark:text-emerald-300";
  }
  return "border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-950/40 dark:text-slate-300";
}

export default async function JobPoliciesWorkspacePage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const resolved = await params;
  const jobId = decodeURIComponent(resolved.jobId);
  let isAdmin = false;
  try {
    const user = await requireUser(await headers());
    requireJob(jobId, user);
    isAdmin = user.role === "admin";
  } catch {
    notFound();
  }
  const workspace = listJobPolicies(jobId);
  const suggestedMatching = getSuggestedJobPolicyMatching(jobId);
  const policyTemplates = getJobPolicyTemplates(jobId);

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
          This is the job-level policy view. Review results from documents feed learning here. This is where you see
          which policies are working, which ones are fading, and which ones should be used more on the next run.
        </p>
        <p className="mt-2 max-w-4xl text-sm text-slate-600 dark:text-slate-300">
          Optional paid cloud policies are listed here as inactive extensions. They stay out of the active runtime bank
          until an admin turns them on for a job.
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
              Ranked from human-reviewed exact F1. AHMN confidence sits beside it as a learning signal, not as the score.
            </p>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400">Source: {workspace.sourcePath}</p>
        </div>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[1060px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                <th className="px-2 py-2">Rank</th>
                <th className="px-2 py-2">Policy</th>
                <th className="px-2 py-2">Runtime</th>
                <th className="px-2 py-2">Reviewed F1</th>
                <th className="px-2 py-2">AHMN confidence</th>
                <th className="px-2 py-2">Reviewed</th>
                <th className="px-2 py-2">Processed</th>
                <th className="px-2 py-2">State</th>
              </tr>
            </thead>
            <tbody>
              {workspace.leaderboard.map((policy) => (
                <tr key={`${policy.policyId}-leaderboard`} className="border-b border-slate-100 dark:border-slate-800">
                  <td className="px-2 py-3 font-medium text-slate-900 dark:text-white">#{policy.leaderboardRank ?? "-"}</td>
                  <td className="px-2 py-3">
                    <Link
                      href={`/dashboard/idpo/jobs/${encodeURIComponent(jobId)}/policies/${encodeURIComponent(policy.policyId)}`}
                      className="font-medium text-cyan-700 hover:text-cyan-800 dark:text-cyan-300 dark:hover:text-cyan-200"
                    >
                      {policy.policyId}
                    </Link>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                      <span>{policy.name}</span>
                      {policy.runtimeToggleAllowed ? (
                        <span className={`rounded-full border px-2 py-0.5 font-medium ${availabilityTone(policy.availability)}`}>
                          {policy.availability === "active_extension"
                            ? "cloud extension enabled"
                            : policy.availability === "inactive_extension"
                              ? "cloud extension disabled"
                              : policy.runtimeEnabled
                                ? "enabled"
                                : "disabled for this job"}
                        </span>
                      ) : null}
                    </div>
                  </td>
                  <td className="px-2 py-3">
                    {isAdmin ? <JobPolicyRuntimeToggle
                      jobId={jobId}
                      policyId={policy.policyId}
                      runtimeEnabled={policy.runtimeEnabled}
                      runtimeToggleAllowed={policy.runtimeToggleAllowed}
                    /> : <span className="text-xs text-slate-500">Admin only</span>}
                  </td>
                  <td className="px-2 py-3 text-slate-600 dark:text-slate-300">{formatF1(policy.meanExactF1)}</td>
                  <td className="px-2 py-3 text-slate-600 dark:text-slate-300">{formatConfidence(policy.ahmnConfidence)}</td>
                  <td className="px-2 py-3 text-slate-600 dark:text-slate-300">{policy.reviewedDocuments}</td>
                  <td className="px-2 py-3 text-slate-600 dark:text-slate-300">{policy.documentsProcessed}</td>
                  <td className="px-2 py-3">
                    <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${stateTone(policy.learningState)}`}>
                      {policy.learningState}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </IdpoCard>

      {isAdmin ? <IdpoCard>
        <details className="group">
          <summary className="flex cursor-pointer list-none items-start justify-between gap-4 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-left dark:border-slate-800 dark:bg-slate-950/40">
            <div>
              <h2 className="text-lg font-semibold text-slate-900 dark:text-white">New policy</h2>
              <p className="mt-1 max-w-3xl text-sm text-slate-600 dark:text-slate-300">
                Add a job-scoped policy only when the current bank is missing a real strategy.
              </p>
            </div>
            <span className="mt-1 text-xs font-medium text-cyan-700 transition group-open:rotate-45 dark:text-cyan-300">
              +
            </span>
          </summary>
          <div className="mt-4 max-w-3xl">
            <p className="mb-4 text-sm text-slate-600 dark:text-slate-300">
              Define how IDPO should run when this policy is selected, then add a few document hints so the system
              knows when to try it on the next run.
            </p>
            <JobPolicyCreateForm jobId={jobId} initialMatching={suggestedMatching} policyTemplates={policyTemplates} />
          </div>
        </details>
      </IdpoCard> : null}

      <IdpoCard>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Learning</h2>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              Keep learning here and nowhere else. This is the only place that shows Thompson Sampling, warm-start use,
              prior fading, and drift handling across the policies in this job.
            </p>
          </div>
        </div>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[1120px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-700 dark:text-slate-400">
                <th className="px-2 py-2">Policy</th>
                <th className="px-2 py-2">TS activity</th>
                <th className="px-2 py-2">RABI warm-start</th>
                <th className="px-2 py-2">RABI decay</th>
                <th className="px-2 py-2">DAAF drift</th>
                <th className="px-2 py-2">Review feedback</th>
              </tr>
            </thead>
            <tbody>
              {workspace.policies.map((policy) => (
                <tr key={`${policy.policyId}-learning`} className="border-b border-slate-100 dark:border-slate-800">
                  <td className="px-2 py-3">
                    <Link
                      href={`/dashboard/idpo/jobs/${encodeURIComponent(jobId)}/policies/${encodeURIComponent(policy.policyId)}`}
                      className="font-medium text-cyan-700 hover:text-cyan-800 dark:text-cyan-300 dark:hover:text-cyan-200"
                    >
                      {policy.policyId}
                    </Link>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                      <span>{policy.name}</span>
                      {policy.runtimeToggleAllowed ? (
                        <span className={`rounded-full border px-2 py-0.5 font-medium ${availabilityTone(policy.availability)}`}>
                          {policy.availability === "active_extension"
                            ? "cloud extension enabled"
                            : policy.availability === "inactive_extension"
                              ? "cloud extension disabled"
                              : policy.runtimeEnabled
                                ? "enabled"
                                : "disabled for this job"}
                        </span>
                      ) : null}
                    </div>
                  </td>
                  <td className="px-2 py-3 text-slate-600 dark:text-slate-300">{formatSelection(policy.learning)}</td>
                  <td className="px-2 py-3 text-slate-600 dark:text-slate-300">
                    {formatWarmStart(policy.learning.warmStartCount, policy.learning.meanNeighborCount)}
                  </td>
                  <td className="px-2 py-3 text-slate-600 capitalize dark:text-slate-300">{policy.learning.rabiDecayState}</td>
                  <td className="px-2 py-3 text-slate-600 capitalize dark:text-slate-300">{policy.learning.driftAwarenessState}</td>
                  <td className="px-2 py-3 text-slate-600 dark:text-slate-300">
                    {formatFeedback(policy.learning.reviewedLearningLoggedCount, policy.learning.reviewedLearningPendingCount)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </IdpoCard>
    </div>
  );
}
