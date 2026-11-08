import fs from "node:fs";
import path from "node:path";
import { AccessError } from "@/server/auth";

type OcrProfile = { engine: "tesseract" } | {
  engine: "rapidocr"; python: string; timeoutSeconds: number; maxRssMiB: number; workDir: string;
};
export interface ExtractionProfile {
  version: 1 | 2 | 3 | 4;
  ocr: OcrProfile;
  responseFormat: "plain_json" | "strict_confirmed_values_v1" | "strict_confirmed_values_v2";
  longDocument?: "reject" | "bounded_text_segments_v1";
  visualDocument?: "disabled" | "bounded_visual_v1" | "bounded_visual_selective_v2" | "bounded_visual_selective_jpeg95_v1";
  localGeneration?: { temperature?: number; seed?: number; reasoning_effort?: "none" | "low" | "medium" | "high" };
}

const RAPID_ENV = ["IDPO_RAPIDOCR_PYTHON", "IDPO_RAPIDOCR_TIMEOUT_S",
  "IDPO_RAPIDOCR_MAX_RSS_MIB", "IDPO_RAPIDOCR_WORK_DIR"] as const;
const LOCAL_ENV = { temperature: "IDPO_LOCAL_TEMPERATURE", seed: "IDPO_LOCAL_SEED",
  reasoning_effort: "IDPO_LOCAL_REASONING_EFFORT" } as const;

function object(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function absolute(value: unknown): value is string {
  return typeof value === "string" && value.length <= 4096 && path.isAbsolute(value) &&
    !/[\u0000\r\n"]/.test(value);
}

function validLocalGeneration(value: unknown): value is NonNullable<ExtractionProfile["localGeneration"]> {
  return object(value) && Object.keys(value).length > 0 &&
    Object.keys(value).every((key) => Object.hasOwn(LOCAL_ENV, key)) &&
    (!("temperature" in value) || typeof value.temperature === "number" && Number.isFinite(value.temperature) &&
      value.temperature >= 0 && value.temperature <= 2) &&
    (!("seed" in value) || Number.isSafeInteger(value.seed) && Number(value.seed) >= 0 && Number(value.seed) <= 2147483647) &&
    (!("reasoning_effort" in value) || typeof value.reasoning_effort === "string" &&
      ["none", "low", "medium", "high"].includes(value.reasoning_effort));
}

function configuredLocalGeneration(): ExtractionProfile["localGeneration"] {
  let endpoint: URL;
  try { endpoint = new URL(process.env.IDPO_AUTO_API_BASE_URL || ""); } catch { return undefined; }
  if (endpoint.protocol !== "http:" || !["localhost", "127.0.0.1", "[::1]"].includes(endpoint.hostname)) return undefined;
  const controls: Record<string, unknown> = {};
  for (const [key, variable] of Object.entries(LOCAL_ENV)) {
    const raw = process.env[variable]?.trim();
    if (raw && (key === "seed" && !/^[0-9]+$/.test(raw) || key === "temperature" &&
      !/^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/.test(raw))) {
      throw new AccessError("Invalid local model generation settings.", 503);
    }
    if (raw) controls[key] = key === "reasoning_effort" ? raw : Number(raw);
  }
  if (!Object.keys(controls).length) return undefined;
  if (!validLocalGeneration(controls)) throw new AccessError("Invalid local model generation settings.", 503);
  return controls;
}

export function validExtractionProfile(value: unknown): value is ExtractionProfile {
  if (!object(value)) return false;
  const keys = value.version === 1 ? "ocr,responseFormat,version" :
    value.version === 2 ? "longDocument,ocr,responseFormat,version" :
    value.version === 3 ? "longDocument,ocr,responseFormat,version,visualDocument" :
    value.version === 4 ? "localGeneration,longDocument,ocr,responseFormat,version,visualDocument" : null;
  if (keys === null || Object.keys(value).sort().join() !== keys ||
    (value.version !== 1 && !["reject", "bounded_text_segments_v1"].includes(String(value.longDocument))) ||
    ((value.version === 3 || value.version === 4) && !["disabled", "bounded_visual_v1", "bounded_visual_selective_v2", "bounded_visual_selective_jpeg95_v1"].includes(String(value.visualDocument))) ||
    (value.version === 4 && !validLocalGeneration(value.localGeneration)) ||
    !["plain_json", "strict_confirmed_values_v1", "strict_confirmed_values_v2"].includes(String(value.responseFormat)) ||
    !object(value.ocr)) return false;
  const ocr = value.ocr;
  if (ocr.engine === "tesseract") return Object.keys(ocr).join() === "engine";
  return ocr.engine === "rapidocr" &&
    Object.keys(ocr).sort().join() === "engine,maxRssMiB,python,timeoutSeconds,workDir" &&
    absolute(ocr.python) && absolute(ocr.workDir) &&
    Number.isInteger(ocr.timeoutSeconds) && Number(ocr.timeoutSeconds) >= 1 && Number(ocr.timeoutSeconds) <= 180 &&
    Number.isInteger(ocr.maxRssMiB) && Number(ocr.maxRssMiB) >= 128 && Number(ocr.maxRssMiB) <= 2048;
}

/** Server configuration is resolved once, before staging or queue admission. */
export function configuredExtractionProfile(confirmedSchema: boolean): ExtractionProfile {
  const engine = process.env.IDPO_AUTO_OCR_ENGINE?.trim() || "tesseract";
  const responseFormat = process.env.IDPO_AUTO_RESPONSE_FORMAT?.trim() || "plain_json";
  const longDocument = process.env.IDPO_AUTO_LONG_DOCUMENT?.trim() || "reject";
  const visualDocument = process.env.IDPO_AUTO_VISUAL_DOCUMENT?.trim() || "disabled";
  if (!["plain_json", "strict_confirmed_values_v1", "strict_confirmed_values_v2"].includes(responseFormat)) {
    throw new AccessError("Invalid server response format profile.", 503);
  }
  if (!["reject", "bounded_text_segments_v1"].includes(longDocument)) {
    throw new AccessError("Invalid server long-document profile.", 503);
  }
  if (!["disabled", "bounded_visual_v1", "bounded_visual_selective_v2", "bounded_visual_selective_jpeg95_v1"].includes(visualDocument)) {
    throw new AccessError("Invalid server visual-document profile.", 503);
  }
  const number = (name: string, fallback: number): number => {
    const value = process.env[name] || String(fallback);
    return /^[1-9][0-9]*$/.test(value) ? Number(value) : NaN;
  };
  const localGeneration = configuredLocalGeneration();
  const profile = {
    version: localGeneration ? 4 : 3,
    ...(localGeneration ? { localGeneration } : {}),
    ocr: engine === "tesseract" ? { engine } : {
      engine, python: process.env.IDPO_RAPIDOCR_PYTHON || "",
      timeoutSeconds: number("IDPO_RAPIDOCR_TIMEOUT_S", 120),
      maxRssMiB: number("IDPO_RAPIDOCR_MAX_RSS_MIB", 1536),
      workDir: process.env.IDPO_RAPIDOCR_WORK_DIR || "",
    },
    responseFormat: confirmedSchema ? responseFormat : "plain_json",
    longDocument: confirmedSchema ? longDocument : "reject",
    visualDocument: confirmedSchema ? visualDocument : "disabled",
  };
  if (!validExtractionProfile(profile)) throw new AccessError("Invalid server extraction profile.", 503);
  if (profile.ocr.engine === "rapidocr") {
    try {
      if (!fs.statSync(profile.ocr.python).isFile() || !fs.statSync(profile.ocr.workDir).isDirectory()) throw new Error();
    } catch { throw new AccessError("The configured local OCR runtime or scratch directory is unavailable.", 503); }
  }
  return profile;
}

export function appendExtractionArguments(args: string[], profile?: ExtractionProfile): void {
  if (!profile) return; // Historical dispatches retain their original arguments.
  args.push("--ocr-engine", profile.ocr.engine);
  if (profile.ocr.engine === "rapidocr") args.push("--ocr-page-budget-s", String(profile.ocr.timeoutSeconds));
  if (profile.responseFormat !== "plain_json") args.push("--response-format-profile", profile.responseFormat);
  if (profile.longDocument === "bounded_text_segments_v1") args.push("--long-document-profile", profile.longDocument);
  if (profile.visualDocument && profile.visualDocument !== "disabled") args.push("--visual-document-profile", profile.visualDocument);
}

export function extractionEnvironment(base: NodeJS.ProcessEnv, profile?: ExtractionProfile): NodeJS.ProcessEnv {
  const env = { ...base };
  // Historical and Tesseract runs cannot inherit a later optional OCR configuration.
  for (const key of RAPID_ENV) delete env[key];
  for (const key of Object.values(LOCAL_ENV)) delete env[key];
  if (profile?.version === 4 && profile.localGeneration) {
    for (const [key, variable] of Object.entries(LOCAL_ENV)) {
      const value = profile.localGeneration[key as keyof typeof LOCAL_ENV];
      if (value !== undefined) env[variable] = String(value);
    }
  }
  if (profile?.ocr.engine === "rapidocr") {
    const ocr = profile.ocr;
    Object.assign(env, { IDPO_RAPIDOCR_PYTHON: ocr.python, IDPO_RAPIDOCR_TIMEOUT_S: String(ocr.timeoutSeconds),
      IDPO_RAPIDOCR_MAX_RSS_MIB: String(ocr.maxRssMiB), IDPO_RAPIDOCR_WORK_DIR: ocr.workDir });
  }
  return env;
}
