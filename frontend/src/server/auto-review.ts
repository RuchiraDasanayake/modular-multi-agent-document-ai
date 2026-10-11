import fs from "node:fs";
import path from "node:path";
import type { JobFieldConfig, JobStatus, ReviewStage } from "@/types/idpo";
import { readRunOcrText } from "@/server/artifacts";
import { loadRunnerConfig } from "@/server/config";
import type { ReviewFieldResult } from "@/server/review";
import { buildRequestedReviewRows } from "@/server/review";

type DetailRecord = Record<string, unknown>;

interface AutoReviewResult {
  fields: ReviewFieldResult[];
  reviewStage: ReviewStage | null;
  reviewConfidence: number | null;
}

interface ReviewerConfig {
  localModel: string;
  cloudModel: string;
  ollamaBaseUrl: string;
  openaiBaseUrl: string;
  openaiApiKey: string;
}

interface ReviewerOutput {
  confidence: number | null;
  fields: Array<{
    fieldKey: string;
    reviewState: string;
    correctedValue?: string | null;
    reviewNote?: string | null;
  }>;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function normalizeFieldKey(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, "_");
}

function clampConfidence(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  return Math.max(0, Math.min(1, Number(value.toFixed(4))));
}

function parseJsonFile(filePath: string): Record<string, unknown> {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf-8")) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function loadReviewerConfig(job: JobStatus): ReviewerConfig {
  const workspaceRoot = loadRunnerConfig().workspaceRoot;
  const configPath = path.join(workspaceRoot, "configs", "idpo_research_config.json");
  const config = parseJsonFile(configPath);
  const llm = asRecord(config.llm) ?? {};
  const settings = asRecord(job.settings) ?? {};

  return {
    localModel:
      (typeof settings.llmLocalModel === "string" && settings.llmLocalModel.trim()) ||
      (typeof llm.local_model === "string" && String(llm.local_model).trim()) ||
      "phi3:mini",
    cloudModel:
      (typeof settings.llmCloudModel === "string" && settings.llmCloudModel.trim()) ||
      (typeof llm.cloud_model === "string" && String(llm.cloud_model).trim()) ||
      "gpt-4o-mini",
    ollamaBaseUrl:
      (typeof llm.base_url === "string" && String(llm.base_url).trim()) ||
      "http://localhost:11434",
    openaiBaseUrl:
      (typeof llm.openai_api_url === "string" && String(llm.openai_api_url).trim()) ||
      process.env.OPENAI_API_URL?.trim() ||
      "https://api.openai.com/v1",
    openaiApiKey: process.env.OPENAI_API_KEY?.trim() || "",
  };
}

function extractJsonObject(text: string): string | null {
  const trimmed = text.trim();
  const fenced = trimmed.match(/```(?:json)?\s*([\s\S]+?)```/i);
  const candidate = fenced?.[1]?.trim() || trimmed;
  const start = candidate.indexOf("{");
  const end = candidate.lastIndexOf("}");
  if (start === -1 || end === -1 || end <= start) {
    return null;
  }
  return candidate.slice(start, end + 1);
}

function parseReviewerOutput(text: string): ReviewerOutput | null {
  const jsonText = extractJsonObject(text);
  if (!jsonText) {
    return null;
  }
  try {
    const parsed = JSON.parse(jsonText) as Record<string, unknown>;
    return {
      confidence: clampConfidence(parsed.confidence),
      fields: Array.isArray(parsed.fields)
        ? parsed.fields
            .map((item) => {
              const entry = asRecord(item);
              if (!entry || typeof entry.fieldKey !== "string" || typeof entry.reviewState !== "string") {
                return null;
              }
              return {
                fieldKey: entry.fieldKey,
                reviewState: entry.reviewState,
                correctedValue: typeof entry.correctedValue === "string" && entry.correctedValue.trim() ? entry.correctedValue.trim() : null,
                reviewNote: typeof entry.reviewNote === "string" && entry.reviewNote.trim() ? entry.reviewNote.trim() : null,
              };
            })
            .filter((item): item is NonNullable<typeof item> => item !== null)
        : [],
    };
  } catch {
    return null;
  }
}

function summarizeValidationIssues(detail: DetailRecord): string[] {
  const issues = Array.isArray(detail.validationIssues) ? detail.validationIssues : [];
  return issues
    .map((item) => {
      const entry = asRecord(item);
      const field = typeof entry?.field === "string" ? entry.field : "unknown";
      const issue = typeof entry?.issue === "string" ? entry.issue : "unknown issue";
      return `${field}: ${issue}`;
    })
    .slice(0, 12);
}

function renderAutoReviewPrompt(input: {
  rows: ReviewFieldResult[];
  detail: DetailRecord;
  fieldConfig: JobFieldConfig[];
  job: JobStatus;
  ocrText: string;
}): string {
  const metadata = asRecord(input.detail.metadata) ?? {};
  const context = asRecord(input.job.reviewContext?.current?.summary) ?? {};
  const fieldDescriptions = input.fieldConfig
    .map((field) => `${normalizeFieldKey(field.name)}: ${field.description?.trim() || "No extra note"}`)
    .join("\n");
  const extractedValues = input.rows
    .map((row) => `- ${row.fieldKey}: extracted="${row.extractedValue}" heuristic_state="${row.reviewState}" note="${row.reviewNote ?? ""}"`)
    .join("\n");
  const validationIssues = summarizeValidationIssues(input.detail).join("\n") || "No validation issues recorded.";
  const ocrText = input.ocrText.trim().slice(0, 12000) || "No OCR text recorded.";

  return [
    "You are reviewing extraction results for one document.",
    "Choose exactly one reviewState per field from: correct, wrong_value, missed_field, correctly_skipped, hallucinated_field.",
    "Return JSON only with keys: confidence and fields. Each field entry must contain fieldKey, reviewState, correctedValue, reviewNote.",
    "",
    `Job purpose: ${typeof context.jobPurpose === "string" ? context.jobPurpose : input.job.jobName || "Document extraction review"}`,
    `Known vendors: ${Array.isArray(context.knownVendors) && context.knownVendors.length > 0 ? context.knownVendors.join(", ") : "none"}`,
    `Field clarifications: ${Array.isArray(context.fieldClarifications) && context.fieldClarifications.length > 0 ? context.fieldClarifications.join(" | ") : "none"}`,
    `Validation notes: ${Array.isArray(context.validationNotes) && context.validationNotes.length > 0 ? context.validationNotes.join(" | ") : "none"}`,
    "",
    `Document type: ${typeof metadata.docType === "string" ? metadata.docType : "unknown"}`,
    `Vendor cluster: ${typeof metadata.vendorCluster === "string" ? metadata.vendorCluster : "unknown"}`,
    "",
    "Requested fields:",
    fieldDescriptions || "No field descriptions.",
    "",
    "Current extracted values:",
    extractedValues,
    "",
    "Validation issues:",
    validationIssues,
    "",
    "OCR text:",
    ocrText,
  ].join("\n");
}

function mergeReviewerFields(baseRows: ReviewFieldResult[], parsed: ReviewerOutput): ReviewFieldResult[] {
  const decisions = new Map(parsed.fields.map((field) => [normalizeFieldKey(field.fieldKey), field]));
  const allowedStates = new Set(["correct", "wrong_value", "missed_field", "correctly_skipped", "hallucinated_field"]);
  return baseRows.map((row) => {
    const decision = decisions.get(normalizeFieldKey(row.fieldKey));
    if (!decision || !allowedStates.has(decision.reviewState)) {
      return row;
    }
    return {
      ...row,
      reviewState: decision.reviewState as ReviewFieldResult["reviewState"],
      correctedValue: decision.correctedValue ?? row.correctedValue,
      reviewNote: decision.reviewNote ?? row.reviewNote,
    };
  });
}

async function callOllama(prompt: string, config: ReviewerConfig): Promise<ReviewerOutput | null> {
  const response = await fetch(`${config.ollamaBaseUrl.replace(/\/$/, "")}/api/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: config.localModel,
      prompt,
      stream: false,
      format: "json",
      options: {
        temperature: 0,
      },
    }),
  }).catch(() => null);

  if (!response?.ok) {
    return null;
  }

  const payload = (await response.json().catch(() => null)) as Record<string, unknown> | null;
  const raw = typeof payload?.response === "string" ? payload.response : "";
  return raw ? parseReviewerOutput(raw) : null;
}

async function callOpenAi(prompt: string, config: ReviewerConfig): Promise<ReviewerOutput | null> {
  if (!config.openaiApiKey) {
    return null;
  }

  const response = await fetch(`${config.openaiBaseUrl.replace(/\/$/, "")}/chat/completions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${config.openaiApiKey}`,
    },
    body: JSON.stringify({
      model: config.cloudModel,
      temperature: 0,
      response_format: { type: "json_object" },
      messages: [
        {
          role: "system",
          content: "You are a strict extraction reviewer. Return JSON only.",
        },
        {
          role: "user",
          content: prompt,
        },
      ],
    }),
  }).catch(() => null);

  if (!response?.ok) {
    return null;
  }

  const payload = (await response.json().catch(() => null)) as Record<string, unknown> | null;
  const choices = Array.isArray(payload?.choices) ? payload.choices : [];
  const first = asRecord(choices[0]);
  const message = asRecord(first?.message);
  const raw = typeof message?.content === "string" ? message.content : "";
  return raw ? parseReviewerOutput(raw) : null;
}

function shouldEscalate(result: ReviewerOutput | null): boolean {
  if (!result) {
    return true;
  }
  if (result.confidence != null && result.confidence < 0.8) {
    return true;
  }
  const uncertain = result.fields.some((field) => {
    const note = (field.reviewNote ?? "").toLowerCase();
    return note.includes("uncertain") || note.includes("unsure");
  });
  if (uncertain) {
    return true;
  }
  return result.fields.some((field) => field.reviewState !== "correct" && field.reviewState !== "correctly_skipped");
}

export async function autoReviewDocument(input: {
  job: JobStatus;
  runId: string;
  docId: string;
  detail: DetailRecord;
  fieldConfig: JobFieldConfig[];
}): Promise<AutoReviewResult> {
  const heuristicRows = buildRequestedReviewRows(input.detail, input.fieldConfig);
  const prompt = renderAutoReviewPrompt({
    rows: heuristicRows,
    detail: input.detail,
    fieldConfig: input.fieldConfig,
    job: input.job,
    ocrText: readRunOcrText(input.runId, input.docId),
  });
  const config = loadReviewerConfig(input.job);

  const local = await callOllama(prompt, config);
  if (local && !shouldEscalate(local)) {
    return {
      fields: mergeReviewerFields(heuristicRows, local),
      reviewStage: "local",
      reviewConfidence: local.confidence,
    };
  }

  const cloud = await callOpenAi(prompt, config);
  if (cloud) {
    return {
      fields: mergeReviewerFields(heuristicRows, cloud),
      reviewStage: "cloud",
      reviewConfidence: cloud.confidence,
    };
  }

  return {
    fields: heuristicRows,
    reviewStage: local ? "local" : null,
    reviewConfidence: local?.confidence ?? null,
  };
}
