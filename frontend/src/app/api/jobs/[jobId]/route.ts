import { NextResponse } from "next/server";
import { getJob, mutateJob } from "@/server/jobs";
import { apiError } from "@/server/api/response";
import type { JobExecutionMode, JobFieldConfig } from "@/types/idpo";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const NO_STORE_HEADERS = {
  "Cache-Control": "no-store, max-age=0",
};

interface Params {
  params: Promise<{ jobId: string }>;
}

export async function GET(_: Request, { params }: Params) {
  try {
    const { jobId } = await params;
    const job = getJob(jobId);
    if (!job) {
      return NextResponse.json({ error: "Job not found" }, { status: 404 });
    }
    return NextResponse.json(job, { headers: NO_STORE_HEADERS });
  } catch (error) {
    return apiError(error, 400);
  }
}

function parseMode(value: unknown): JobExecutionMode | undefined {
  return value === "adaptive" || value === "strict" || value === "both" ? value : undefined;
}

function parseFieldConfig(value: unknown): JobFieldConfig[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
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

export async function PATCH(request: Request, { params }: Params) {
  try {
    const { jobId } = await params;
    const payload = (await request.json()) as Record<string, unknown>;
    const updated = mutateJob(jobId, (job) => {
      if (typeof payload.jobName === "string") {
        job.jobName = payload.jobName.trim();
      }
      const mode = parseMode(payload.mode);
      if (mode) {
        job.mode = mode;
      }
      const fieldConfig = parseFieldConfig(payload.fieldConfigCurrent);
      if (fieldConfig) {
        job.fieldConfigCurrent = fieldConfig;
      }
      if (Array.isArray(payload.selectedFileIds)) {
        const selected = new Set(
          payload.selectedFileIds.filter((value): value is string => typeof value === "string"),
        );
        for (const document of job.documents ?? []) {
          document.selected = selected.has(document.fileId);
        }
      }
      return job;
    });
    return NextResponse.json(updated);
  } catch (error) {
    return apiError(error, 400);
  }
}
