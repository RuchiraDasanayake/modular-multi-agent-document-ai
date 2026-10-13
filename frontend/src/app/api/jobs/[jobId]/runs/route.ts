import { NextResponse } from "next/server";
import { startJobRuns } from "@/server/runner";
import { requireJob } from "@/server/access";
import { AccessError, requireUser, type AuthenticatedUser } from "@/server/auth";
import { listJobPolicies } from "@/server/policies";
import { apiError } from "@/server/api/response";
import type { JobFieldConfig } from "@/types/idpo";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface Params {
  params: Promise<{ jobId: string }>;
}

type CustomField = { key: string; description?: string };
type ApiKeys = { openai?: string };

function requireSafeViewerRun(user: AuthenticatedUser, jobId: string, settings: Record<string, unknown>): void {
  if (user.role === "admin") return;
  const hasValue = (key: string) => typeof settings[key] === "string" && Boolean((settings[key] as string).trim());
  const unsafeSettings =
    (hasValue("configPath") && settings.configPath !== "configs/idpo_research_config.json") ||
    hasValue("llmLocalModel") || hasValue("llmCloudModel") || hasValue("flagshipModel") ||
    settings.llmDefaultMode === "cloud" || settings.autoInstallLocalModel === true ||
    settings.escalationEnabled === true || settings.shadowMode === true ||
    (typeof settings.maxCostPerDoc === "number" && settings.maxCostPerDoc > 0) ||
    (typeof settings.apiKeys === "object" && settings.apiKeys !== null && Object.keys(settings.apiKeys).length > 0);
  if (unsafeSettings) throw new AccessError("Admin access is required for model, cloud, escalation, and resource settings.", 403);

  const cloudPolicyEnabled = listJobPolicies(jobId).policies.some((policy) => {
    const extraction = policy.actions.extraction;
    return policy.runtimeEnabled && (
      policy.availability === "active_extension" ||
      (extraction && typeof extraction === "object" && "model_tier" in extraction
        && typeof extraction.model_tier === "string" && extraction.model_tier !== "local")
    );
  });
  if (cloudPolicyEnabled) throw new AccessError("Admin access is required to run cloud policies.", 403);
}

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
    const user = await requireUser(request.headers);
    const { jobId } = await params;
    requireJob(jobId, user);
    const payload = (await request.json()) as Record<string, unknown>;
    const settings =
      payload.settings && typeof payload.settings === "object" && !Array.isArray(payload.settings)
        ? (payload.settings as Record<string, unknown>)
        : {};
    requireSafeViewerRun(user, jobId, settings);
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
        escalationEnabled: user.role === "admin"
          ? typeof settings.escalationEnabled === "boolean" ? settings.escalationEnabled : undefined
          : false,
        report: typeof settings.report === "boolean" ? settings.report : true,
        customFields: parseCustomFields(settings.customFields),
        llmLocalModel: typeof settings.llmLocalModel === "string" ? settings.llmLocalModel : undefined,
        llmCloudModel: typeof settings.llmCloudModel === "string" ? settings.llmCloudModel : undefined,
        llmDefaultMode: user.role === "admin"
          ? settings.llmDefaultMode === "local" || settings.llmDefaultMode === "cloud"
            ? settings.llmDefaultMode
            : undefined
          : "local",
        forceLocalOnly: user.role !== "admin",
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
