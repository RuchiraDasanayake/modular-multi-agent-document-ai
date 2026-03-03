import { NextResponse } from "next/server";
import { startRunJob } from "@/server/runner";
import { apiError } from "@/server/api/response";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface StartPayloadJson {
  commandId?: string;
  settings?: Record<string, unknown>;
  sourceRunId?: string;
}

type CustomField = { key: string; description?: string; pattern?: string };

function parseCustomFields(value: unknown): CustomField[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const parsed: CustomField[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const entry = item as Record<string, unknown>;
    const key = typeof entry.key === "string" ? entry.key.trim() : "";
    if (!key) {
      continue;
    }
    parsed.push({
      key,
      description: typeof entry.description === "string" ? entry.description : undefined,
      pattern: typeof entry.pattern === "string" ? entry.pattern : undefined,
    });
  }
  return parsed;
}

function parseBoolean(value: FormDataEntryValue | null, fallback = false): boolean {
  if (value === null) {
    return fallback;
  }
  const normalized = String(value).trim().toLowerCase();
  return normalized === "true" || normalized === "1" || normalized === "yes";
}

function parseNumber(value: FormDataEntryValue | null): number | undefined {
  if (value === null) {
    return undefined;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

export async function POST(request: Request) {
  try {
    const contentType = request.headers.get("content-type") ?? "";

    if (contentType.includes("application/json")) {
      const json = (await request.json()) as StartPayloadJson;
      const started = await startRunJob({
        commandId: json.commandId,
        settings: {
          configPath: typeof json.settings?.configPath === "string" ? json.settings.configPath : undefined,
          shadowMode: typeof json.settings?.shadowMode === "boolean" ? json.settings.shadowMode : false,
          shadowSampleRate:
            typeof json.settings?.shadowSampleRate === "number" ? (json.settings.shadowSampleRate as number) : undefined,
          policyPreference:
            typeof json.settings?.policyPreference === "string" ? (json.settings.policyPreference as string) : undefined,
          routingMode:
            json.settings?.routingMode === "auto" ||
            json.settings?.routingMode === "light" ||
            json.settings?.routingMode === "standard" ||
            json.settings?.routingMode === "heavy"
              ? (json.settings.routingMode as "auto" | "light" | "standard" | "heavy")
              : "auto",
          maxCostPerDoc:
            typeof json.settings?.maxCostPerDoc === "number" ? (json.settings.maxCostPerDoc as number) : undefined,
          escalationEnabled:
            typeof json.settings?.escalationEnabled === "boolean" ? (json.settings.escalationEnabled as boolean) : undefined,
          report: typeof json.settings?.report === "boolean" ? (json.settings.report as boolean) : true,
          customFields: parseCustomFields(json.settings?.customFields),
          llmLocalModel: typeof json.settings?.llmLocalModel === "string" ? (json.settings.llmLocalModel as string) : undefined,
          llmCloudModel: typeof json.settings?.llmCloudModel === "string" ? (json.settings.llmCloudModel as string) : undefined,
          llmDefaultMode:
            json.settings?.llmDefaultMode === "local" || json.settings?.llmDefaultMode === "cloud"
              ? (json.settings.llmDefaultMode as "local" | "cloud")
              : undefined,
          llmUseExtraction:
            typeof json.settings?.llmUseExtraction === "boolean" ? (json.settings.llmUseExtraction as boolean) : undefined,
          llmUseSummarization:
            typeof json.settings?.llmUseSummarization === "boolean"
              ? (json.settings.llmUseSummarization as boolean)
              : undefined,
          flagshipModel: typeof json.settings?.flagshipModel === "string" ? (json.settings.flagshipModel as string) : undefined,
        },
        files: [],
        sourceRunId: typeof json.sourceRunId === "string" ? json.sourceRunId : undefined,
      });
      return NextResponse.json(started, { status: 201 });
    }

    const form = await request.formData();

    const files = form
      .getAll("files")
      .filter((entry): entry is File => entry instanceof File && entry.size > 0);

    const settingsRaw = form.get("settings");
    const settings =
      typeof settingsRaw === "string" && settingsRaw.trim().length > 0
        ? (JSON.parse(settingsRaw) as Record<string, unknown>)
        : {
            configPath: form.get("configPath"),
            shadowMode: parseBoolean(form.get("shadowMode"), false),
            shadowSampleRate: parseNumber(form.get("shadowSampleRate")),
            policyPreference: form.get("policyPreference"),
            routingMode: form.get("routingMode"),
            maxCostPerDoc: parseNumber(form.get("maxCostPerDoc")),
            escalationEnabled: parseBoolean(form.get("escalationEnabled"), true),
            report: parseBoolean(form.get("report"), true),
          };

    const started = await startRunJob({
      commandId: typeof form.get("commandId") === "string" ? (form.get("commandId") as string) : undefined,
      settings: {
        configPath: typeof settings.configPath === "string" ? settings.configPath : undefined,
        shadowMode: typeof settings.shadowMode === "boolean" ? settings.shadowMode : false,
        shadowSampleRate: typeof settings.shadowSampleRate === "number" ? settings.shadowSampleRate : undefined,
        policyPreference: typeof settings.policyPreference === "string" ? settings.policyPreference : undefined,
        routingMode:
          settings.routingMode === "auto" ||
          settings.routingMode === "light" ||
          settings.routingMode === "standard" ||
          settings.routingMode === "heavy"
            ? (settings.routingMode as "auto" | "light" | "standard" | "heavy")
            : "auto",
        maxCostPerDoc: typeof settings.maxCostPerDoc === "number" ? settings.maxCostPerDoc : undefined,
        escalationEnabled: typeof settings.escalationEnabled === "boolean" ? settings.escalationEnabled : undefined,
        report: typeof settings.report === "boolean" ? settings.report : true,
        customFields: parseCustomFields(settings.customFields),
        llmLocalModel: typeof settings.llmLocalModel === "string" ? settings.llmLocalModel : undefined,
        llmCloudModel: typeof settings.llmCloudModel === "string" ? settings.llmCloudModel : undefined,
        llmDefaultMode:
          settings.llmDefaultMode === "local" || settings.llmDefaultMode === "cloud"
            ? (settings.llmDefaultMode as "local" | "cloud")
            : undefined,
        llmUseExtraction: typeof settings.llmUseExtraction === "boolean" ? settings.llmUseExtraction : undefined,
        llmUseSummarization: typeof settings.llmUseSummarization === "boolean" ? settings.llmUseSummarization : undefined,
        flagshipModel: typeof settings.flagshipModel === "string" ? settings.flagshipModel : undefined,
      },
      files,
      sourceRunId: typeof form.get("sourceRunId") === "string" ? (form.get("sourceRunId") as string) : undefined,
    });

    return NextResponse.json(started, { status: 201 });
  } catch (error) {
    return apiError(error, 400);
  }
}
