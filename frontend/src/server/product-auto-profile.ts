import fs from "node:fs";
import path from "node:path";
import { AccessError } from "@/server/auth";

type OcrProfile = { engine: "tesseract" } | {
  engine: "rapidocr"; python: string; timeoutSeconds: number; maxRssMiB: number; workDir: string;
};
export interface ExtractionProfile {
  version: 1 | 2;
  ocr: OcrProfile;
  responseFormat: "plain_json" | "strict_confirmed_values_v1";
  longDocument?: "reject" | "bounded_text_segments_v1";
}

const RAPID_ENV = ["IDPO_RAPIDOCR_PYTHON", "IDPO_RAPIDOCR_TIMEOUT_S",
  "IDPO_RAPIDOCR_MAX_RSS_MIB", "IDPO_RAPIDOCR_WORK_DIR"] as const;

function object(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function absolute(value: unknown): value is string {
  return typeof value === "string" && value.length <= 4096 && path.isAbsolute(value) &&
    !/[\u0000\r\n"]/.test(value);
}

export function validExtractionProfile(value: unknown): value is ExtractionProfile {
  if (!object(value) || (value.version === 1 ? Object.keys(value).sort().join() !== "ocr,responseFormat,version" :
    value.version !== 2 || Object.keys(value).sort().join() !== "longDocument,ocr,responseFormat,version" ||
    !["reject", "bounded_text_segments_v1"].includes(String(value.longDocument))) ||
    !["plain_json", "strict_confirmed_values_v1"].includes(String(value.responseFormat)) ||
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
  if (!["plain_json", "strict_confirmed_values_v1"].includes(responseFormat)) {
    throw new AccessError("Invalid server response format profile.", 503);
  }
  if (!["reject", "bounded_text_segments_v1"].includes(longDocument)) {
    throw new AccessError("Invalid server long-document profile.", 503);
  }
  const number = (name: string, fallback: number): number => {
    const value = process.env[name] || String(fallback);
    return /^[1-9][0-9]*$/.test(value) ? Number(value) : NaN;
  };
  const profile = {
    version: 2,
    ocr: engine === "tesseract" ? { engine } : {
      engine, python: process.env.IDPO_RAPIDOCR_PYTHON || "",
      timeoutSeconds: number("IDPO_RAPIDOCR_TIMEOUT_S", 120),
      maxRssMiB: number("IDPO_RAPIDOCR_MAX_RSS_MIB", 1536),
      workDir: process.env.IDPO_RAPIDOCR_WORK_DIR || "",
    },
    responseFormat: confirmedSchema ? responseFormat : "plain_json",
    longDocument: confirmedSchema ? longDocument : "reject",
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
}

export function extractionEnvironment(base: NodeJS.ProcessEnv, profile?: ExtractionProfile): NodeJS.ProcessEnv {
  const env = { ...base };
  // Historical and Tesseract runs cannot inherit a later optional OCR configuration.
  for (const key of RAPID_ENV) delete env[key];
  if (profile?.ocr.engine === "rapidocr") {
    const ocr = profile.ocr;
    Object.assign(env, { IDPO_RAPIDOCR_PYTHON: ocr.python, IDPO_RAPIDOCR_TIMEOUT_S: String(ocr.timeoutSeconds),
      IDPO_RAPIDOCR_MAX_RSS_MIB: String(ocr.maxRssMiB), IDPO_RAPIDOCR_WORK_DIR: ocr.workDir });
  }
  return env;
}
