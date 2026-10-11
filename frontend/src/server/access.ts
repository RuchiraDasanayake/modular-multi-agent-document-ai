import { AccessError, type AuthenticatedUser } from "@/server/auth";
import { getJob, listJobs } from "@/server/jobs";
import type { JobStatus } from "@/types/idpo";

export function canAccessJob(job: JobStatus, user: AuthenticatedUser): boolean {
  // Jobs created before ownership was recorded remain available to admins only.
  return user.role === "admin" || job.ownerUserId === user.id;
}

export function requireJob(jobId: string, user: AuthenticatedUser): JobStatus {
  const job = getJob(jobId);
  if (!job || !canAccessJob(job, user)) throw new AccessError("Job not found.", 404);
  return job;
}

export function listAccessibleJobs(user: AuthenticatedUser, limit = 50): JobStatus[] {
  return listJobs(Number.MAX_SAFE_INTEGER).filter((job) => canAccessJob(job, user)).slice(0, limit);
}

export function accessibleRunIds(user: AuthenticatedUser): Set<string> {
  const runIds = new Set<string>();
  for (const job of listAccessibleJobs(user, Number.MAX_SAFE_INTEGER)) {
    if (job.runId) runIds.add(job.runId);
    if (job.latestRunId) runIds.add(job.latestRunId);
    for (const run of job.runs ?? []) {
      if (run.runId) runIds.add(run.runId);
    }
    for (const document of job.documents ?? []) {
      if (document.latestRunId) runIds.add(document.latestRunId);
      for (const outcome of document.outcomes) {
        if (outcome.runId) runIds.add(outcome.runId);
      }
    }
  }
  return runIds;
}

export function canAccessRun(runId: string, user: AuthenticatedUser): boolean {
  return user.role === "admin" || accessibleRunIds(user).has(runId);
}

export function requireRun(runId: string, user: AuthenticatedUser): void {
  if (!canAccessRun(runId, user)) throw new AccessError("Run not found.", 404);
}
