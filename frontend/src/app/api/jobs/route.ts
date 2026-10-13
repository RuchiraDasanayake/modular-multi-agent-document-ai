import { NextResponse } from "next/server";
import { createWorkspaceJob } from "@/server/jobs";
import { listAccessibleJobs } from "@/server/access";
import { requireUser } from "@/server/auth";
import { apiError } from "@/server/api/response";
import { syncActiveJobProgress } from "@/server/runner";
import { readJobValidationContext } from "@/server/review-context";
import type { JobExecutionMode, JobFieldConfig } from "@/types/idpo";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE_HEADERS = {
  "Cache-Control": "no-store, max-age=0",
};

function parseMode(value: unknown): JobExecutionMode | undefined {
  return value === "adaptive" || value === "strict" || value === "both" ? value : undefined;
}

function parseFieldConfig(value: unknown): JobFieldConfig[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const fields: JobFieldConfig[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const entry = item as Record<string, unknown>;
    const name = typeof entry.name === "string" ? entry.name.trim() : "";
    if (!name) {
      continue;
    }
    fields.push({
      name,
      description: typeof entry.description === "string" ? entry.description.trim() || undefined : undefined,
    });
  }
  return fields;
}

export async function GET(request: Request) {
  try {
    const user = await requireUser(request.headers);
    const jobs = listAccessibleJobs(user, 100).map((job) =>
      job.status === "queued" || job.status === "running" ? syncActiveJobProgress(job.jobId) : job,
    );
    for (const job of jobs) {
      const reviewContext = readJobValidationContext(job.jobId);
      if (reviewContext) {
        job.reviewContext = reviewContext;
      }
    }
    return NextResponse.json({ jobs }, { headers: NO_STORE_HEADERS });
  } catch (error) {
    return apiError(error, 500);
  }
}

export async function POST(request: Request) {
  try {
    const user = await requireUser(request.headers);
    const payload = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const job = createWorkspaceJob({
      ownerUserId: user.id,
      jobName: typeof payload.jobName === "string" ? payload.jobName : "",
      mode: parseMode(payload.mode) ?? "adaptive",
      fieldConfigCurrent: parseFieldConfig(payload.fieldConfigCurrent),
    });
    return NextResponse.json(job, { status: 201 });
  } catch (error) {
    return apiError(error, 400);
  }
}
