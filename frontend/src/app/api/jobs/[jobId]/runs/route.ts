import { NextResponse } from "next/server";
import { startJobRuns } from "@/server/runner";
import { apiError } from "@/server/api/response";
import type { JobFieldConfig } from "@/types/idpo";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ jobId: string }>;
}

type CustomField = { key: string; description?: string };
type ApiKeys = { openai?: string };

function parseCustomFields(value: unknown): CustomField[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const fields: CustomField[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const entry = item as Record<string, unknown>;
    const key = typeof entry.key === "string" ? entry.key.trim() : "";
    if (!key) {
      continue;
    }
    fields.push({
      key,
      description: typeof entry.description === "string" ? entry.description.trim() || undefined : undefined,
    });
  }
  return fields;
}

function parseApiKeys(value: unknown): ApiKeys | undefined {
  if (!value || typeof value !== "object") {
    return undefined;
  }
  const keys = value as Record<string, unknown>;
  const openai = typeof keys.openai === "string" ? keys.openai.trim() : "";
  return openai ? { openai } : undefined;
}

export async function POST(request: Request, { params }: Params) {
  try {
    const { jobId } = await params;
    const payload = (await request.json()) as Record<string, unknown>;
    const settings =
      payload.settings && typeof payload.settings === "object" && !Array.isArray(payload.settings)
        ? (payload.settings as Record<string, unknown>)
        : {};
    const selectedFileIds = Array.isArray(payload.selectedFileIds)
      ? payload.selectedFileIds.filter((value): value is string => typeof value === "string")
      : [];
    const mode = payload.mode === "strict" || payload.mode === "both" ? payload.mode : "adaptive";
    const fieldConfigCurrent: JobFieldConfig[] | undefined = Array.isArray(payload.fieldConfigCurrent) ? [] : undefined;
    const rawFieldConfig = Array.isArray(payload.fieldConfigCurrent) ? payload.fieldConfigCurrent : null;
    if (fieldConfigCurrent && rawFieldConfig) {
      for (const item of rawFieldConfig) {
        if (!item || typeof item !== "object") {
          continue;
        }
        const entry = item as Record<string, unknown>;
        const name = typeof entry.name === "string" ? entry.name.trim() : "";
        if (!name) {
          continue;
        }
        fieldConfigCurrent.push({
          name,
          description: typeof entry.description === "string" ? entry.description.trim() || undefined : undefined,
        });
      }
    }

    const started = await startJobRuns({
      jobId,
      selectedFileIds,
      mode,
      jobName: typeof payload.jobName === "string" ? payload.jobName : undefined,
      fieldConfigCurrent,
      settings: {
        configPath: typeof settings.configPath === "string" ? settings.configPath : undefined,
        adaptiveMode:
          settings.adaptiveMode === "static" || settings.adaptiveMode === "adaptive_safe"
            ? settings.adaptiveMode
            : mode === "strict"
              ? "static"
              : "adaptive_safe",
        shadowMode: typeof settings.shadowMode === "boolean" ? settings.shadowMode : false,
        shadowSampleRate: typeof settings.shadowSampleRate === "number" ? settings.shadowSampleRate : undefined,
        maxCostPerDoc: typeof settings.maxCostPerDoc === "number" ? settings.maxCostPerDoc : undefined,
        escalationEnabled: typeof settings.escalationEnabled === "boolean" ? settings.escalationEnabled : undefined,
        report: typeof settings.report === "boolean" ? settings.report : true,
        customFields: parseCustomFields(settings.customFields),
        llmLocalModel: typeof settings.llmLocalModel === "string" ? settings.llmLocalModel : undefined,
        llmCloudModel: typeof settings.llmCloudModel === "string" ? settings.llmCloudModel : undefined,
        llmDefaultMode:
          settings.llmDefaultMode === "local" || settings.llmDefaultMode === "cloud"
            ? settings.llmDefaultMode
            : undefined,
        llmUseExtraction: typeof settings.llmUseExtraction === "boolean" ? settings.llmUseExtraction : undefined,
        llmUseSummarization:
          typeof settings.llmUseSummarization === "boolean" ? settings.llmUseSummarization : undefined,
        flagshipModel: typeof settings.flagshipModel === "string" ? settings.flagshipModel : undefined,
        autoInstallLocalModel:
          typeof settings.autoInstallLocalModel === "boolean" ? settings.autoInstallLocalModel : undefined,
        apiKeys: parseApiKeys(settings.apiKeys),
      },
    });

    return NextResponse.json(started, { status: 201 });
  } catch (error) {
    return apiError(error, 400);
  }
}
