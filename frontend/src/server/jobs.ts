import fs from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import type { JobStatus } from "@/types/idpo";
import { loadRunnerConfig } from "@/server/config";

const inMemoryJobs = new Map<string, JobStatus>();

function getJobFile(jobId: string): string {
  const config = loadRunnerConfig();
  return path.join(config.jobsDir, `${jobId}.json`);
}

function persistJob(job: JobStatus): void {
  const filePath = getJobFile(job.jobId);
  fs.writeFileSync(filePath, JSON.stringify(job, null, 2), "utf-8");
}

export function createJob(commandId: string, settings: Record<string, unknown>, uploadsPath: string): JobStatus {
  const job: JobStatus = {
    jobId: randomUUID().replace(/-/g, ""),
    status: "queued",
    startedAt: new Date().toISOString(),
    commandId,
    runId: null,
    runPath: null,
    logs: [],
    settings,
    uploadsPath,
  };

  inMemoryJobs.set(job.jobId, job);
  persistJob(job);
  return job;
}

export function appendJobLog(jobId: string, line: string): JobStatus {
  const job = getJob(jobId);
  if (!job) {
    throw new Error(`Job ${jobId} not found`);
  }

  const trimmed = line.trimEnd();
  if (trimmed.length > 0) {
    job.logs.push(trimmed);
    if (job.logs.length > 2000) {
      job.logs.splice(0, job.logs.length - 2000);
    }
  }

  inMemoryJobs.set(jobId, job);
  persistJob(job);
  return job;
}

export function updateJob(jobId: string, patch: Partial<JobStatus>): JobStatus {
  const current = getJob(jobId);
  if (!current) {
    throw new Error(`Job ${jobId} not found`);
  }

  const next: JobStatus = {
    ...current,
    ...patch,
    logs: patch.logs ?? current.logs,
    settings: patch.settings ?? current.settings,
  };

  inMemoryJobs.set(jobId, next);
  persistJob(next);
  return next;
}

export function setJobRunning(jobId: string): JobStatus {
  return updateJob(jobId, { status: "running" });
}

export function setJobSuccess(jobId: string, runId: string | null, runPath: string | null): JobStatus {
  return updateJob(jobId, {
    status: "success",
    runId,
    runPath,
    endedAt: new Date().toISOString(),
  });
}

export function setJobFailed(jobId: string, error: string): JobStatus {
  return updateJob(jobId, {
    status: "failed",
    error,
    endedAt: new Date().toISOString(),
  });
}

export function getJob(jobId: string): JobStatus | null {
  if (inMemoryJobs.has(jobId)) {
    return inMemoryJobs.get(jobId) ?? null;
  }

  const filePath = getJobFile(jobId);
  if (!fs.existsSync(filePath)) {
    return null;
  }

  try {
    const job = JSON.parse(fs.readFileSync(filePath, "utf-8")) as JobStatus;
    inMemoryJobs.set(jobId, job);
    return job;
  } catch {
    return null;
  }
}

export function listJobs(limit = 20): JobStatus[] {
  const config = loadRunnerConfig();
  const files = fs
    .readdirSync(config.jobsDir, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".json"))
    .map((entry) => path.join(config.jobsDir, entry.name))
    .sort((a, b) => {
      const aStat = fs.statSync(a);
      const bStat = fs.statSync(b);
      return bStat.mtimeMs - aStat.mtimeMs;
    })
    .slice(0, limit);

  return files
    .map((filePath) => {
      try {
        const job = JSON.parse(fs.readFileSync(filePath, "utf-8")) as JobStatus;
        inMemoryJobs.set(job.jobId, job);
        return job;
      } catch {
        return null;
      }
    })
    .filter((job): job is JobStatus => job !== null);
}
