import { NextResponse } from "next/server";
import { getJob, mutateJob } from "@/server/jobs";
import { apiError } from "@/server/api/response";
import { syncActiveJobProgress } from "@/server/runner";
import { readJobValidationContext, updateJobValidationContextManualInput } from "@/server/review-context";
import type { JobExecutionMode, JobFieldConfig, JobValidationContextManualInput } from "@/types/idpo";

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
    const baseJob = getJob(jobId);
    const job =
      baseJob && (baseJob.status === "queued" || baseJob.status === "running")
        ? syncActiveJobProgress(jobId)
        : baseJob;
    if (!job) {
      return NextResponse.json({ error: "Job not found" }, { status: 404 });
    }
    const reviewContext = readJobValidationContext(jobId);
    if (reviewContext) {
      job.reviewContext = reviewContext;
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

function parseManualStringList(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }
  return value
    .filter((item): item is string => typeof item === "string")
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseReviewContextManualInput(value: unknown): JobValidationContextManualInput | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return undefined;
  }
  const record = value as Record<string, unknown>;
  return {
    jobPurpose: typeof record.jobPurpose === "string" ? record.jobPurpose.trim() || undefined : undefined,
    knownVendors: parseManualStringList(record.knownVendors),
    fieldClarifications: parseManualStringList(record.fieldClarifications),
    validationNotes: parseManualStringList(record.validationNotes),
  };
}

function parseSettingsPatch(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return undefined;
  }
  const record = value as Record<string, unknown>;
  const patch: Record<string, unknown> = {};

  if ("llmLocalModel" in record) {
    const model = typeof record.llmLocalModel === "string" ? record.llmLocalModel.trim() : "";
    patch.llmLocalModel = model || null;
  }

  return Object.keys(patch).length > 0 ? patch : undefined;
}

export async function PATCH(request: Request, { params }: Params) {
  try {
    const { jobId } = await params;
    const payload = (await request.json()) as Record<string, unknown>;
    let updated = mutateJob(jobId, (job) => {
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
      const settingsPatch = parseSettingsPatch(payload.settings);
      if (settingsPatch) {
        const nextSettings =
          job.settings && typeof job.settings === "object" && !Array.isArray(job.settings)
            ? { ...job.settings }
            : {};
        if ("llmLocalModel" in settingsPatch) {
          if (typeof settingsPatch.llmLocalModel === "string" && settingsPatch.llmLocalModel.trim()) {
            nextSettings.llmLocalModel = settingsPatch.llmLocalModel;
          } else {
            delete nextSettings.llmLocalModel;
          }
        }
        job.settings = nextSettings;
      }
      return job;
    });
    const reviewContextManualInput = parseReviewContextManualInput(payload.reviewContextManualInput);
    if (reviewContextManualInput) {
      updated.reviewContext = updateJobValidationContextManualInput(
        updated,
        updated.fieldConfigCurrent ?? [],
        reviewContextManualInput,
      );
    } else {
      const reviewContext = readJobValidationContext(jobId);
      if (reviewContext) {
        updated.reviewContext = reviewContext;
      }
    }
    return NextResponse.json(updated);
  } catch (error) {
    return apiError(error, 400);
  }
}
