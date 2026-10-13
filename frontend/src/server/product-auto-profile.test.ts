import assert from "node:assert/strict";
import os from "node:os";
import test from "node:test";
import { appendExtractionArguments, configuredExtractionProfile, extractionEnvironment,
  validExtractionProfile, type ExtractionProfile } from "./product-auto-profile";

test("extraction profile validates bounds and excludes unknown configuration", () => {
  const profile: ExtractionProfile = { version: 1, responseFormat: "plain_json",
    ocr: { engine: "rapidocr", python: process.execPath, workDir: os.tmpdir(), timeoutSeconds: 120, maxRssMiB: 1536 } };
  assert.equal(validExtractionProfile(profile), true);
  for (const patch of [{ timeoutSeconds: 181 }, { maxRssMiB: 127 }, { python: "relative.exe" },
    { workDir: "relative" }, { timeoutSeconds: 0.5 }, { key: "not-permitted" }]) {
    assert.equal(validExtractionProfile({ ...profile, ocr: { ...profile.ocr, ...patch } }), false);
  }
  assert.equal(validExtractionProfile({ ...profile, responseFormat: "unknown" }), false);
  assert.equal(validExtractionProfile({ ...profile, secret: "unexpected" }), false);
});

test("only explicit confirmed schemas use configured strict output", () => {
  const keys = ["IDPO_AUTO_OCR_ENGINE", "IDPO_AUTO_RESPONSE_FORMAT", "IDPO_AUTO_LONG_DOCUMENT", "IDPO_AUTO_VISUAL_DOCUMENT"];
  const previous = keys.map((key) => process.env[key]);
  try {
    process.env.IDPO_AUTO_OCR_ENGINE = "tesseract";
    process.env.IDPO_AUTO_RESPONSE_FORMAT = "strict_confirmed_values_v1";
    process.env.IDPO_AUTO_LONG_DOCUMENT = "bounded_text_segments_v1";
    process.env.IDPO_AUTO_VISUAL_DOCUMENT = "bounded_visual_v1";
    assert.equal(configuredExtractionProfile(true).responseFormat, "strict_confirmed_values_v1");
    assert.equal(configuredExtractionProfile(false).responseFormat, "plain_json");
    assert.equal(configuredExtractionProfile(true).longDocument, "bounded_text_segments_v1");
    assert.equal(configuredExtractionProfile(false).longDocument, "reject");
    assert.equal(configuredExtractionProfile(true).visualDocument, "bounded_visual_v1");
    assert.equal(configuredExtractionProfile(false).visualDocument, "disabled");
    process.env.IDPO_AUTO_VISUAL_DOCUMENT = "unbounded";
    assert.throws(() => configuredExtractionProfile(true), /visual-document/);
    process.env.IDPO_AUTO_VISUAL_DOCUMENT = "disabled";
    process.env.IDPO_AUTO_RESPONSE_FORMAT = "bad";
    assert.throws(() => configuredExtractionProfile(false), /response format/);
    process.env.IDPO_AUTO_RESPONSE_FORMAT = "plain_json";
    process.env.IDPO_AUTO_OCR_ENGINE = "other-engine";
    assert.throws(() => configuredExtractionProfile(true), /extraction profile/);
  } finally {
    keys.forEach((key, index) => {
      if (previous[index] === undefined) delete process.env[key]; else process.env[key] = previous[index];
    });
  }
});

test("long-document policy is versioned and validated independently of output format", () => {
  const base = { version: 2, responseFormat: "plain_json", ocr: { engine: "tesseract" } };
  assert.equal(validExtractionProfile(base), false);
  assert.equal(validExtractionProfile({ ...base, longDocument: "truncate" }), false);
  const profile: ExtractionProfile = { version: 2, responseFormat: "plain_json",
    ocr: { engine: "tesseract" }, longDocument: "bounded_text_segments_v1" };
  assert.equal(validExtractionProfile(profile), true);
  assert.equal(validExtractionProfile({ ...profile, version: 1 }), false);
  const args: string[] = [];
  appendExtractionArguments(args, profile);
  assert.deepEqual(args, ["--ocr-engine", "tesseract", "--long-document-profile", "bounded_text_segments_v1"]);
});

test("visual routing is sealed only in version three and never inherited by older profiles", () => {
  const profile: ExtractionProfile = { version: 3, ocr: { engine: "tesseract" },
    responseFormat: "plain_json", longDocument: "reject", visualDocument: "bounded_visual_v1" };
  assert.equal(validExtractionProfile(profile), true);
  assert.equal(validExtractionProfile({ ...profile, version: 2 }), false);
  assert.equal(validExtractionProfile({ ...profile, version: 1 }), false);
  assert.equal(validExtractionProfile({ ...profile, visualDocument: undefined }), false);
  assert.equal(validExtractionProfile({ ...profile, visualDocument: "unbounded" }), false);
  const args: string[] = [];
  appendExtractionArguments(args, profile);
  assert.deepEqual(args, ["--ocr-engine", "tesseract", "--visual-document-profile", "bounded_visual_v1"]);
  for (const old of [
    { version: 1, ocr: { engine: "tesseract" }, responseFormat: "plain_json" },
    { version: 2, ocr: { engine: "tesseract" }, responseFormat: "plain_json", longDocument: "reject" },
  ] as ExtractionProfile[]) {
    assert.equal(validExtractionProfile(old), true);
    const oldArgs: string[] = [];
    appendExtractionArguments(oldArgs, old);
    assert.deepEqual(oldArgs, ["--ocr-engine", "tesseract"]);
  }
});

test("sealed extraction arguments and environment override later process configuration", () => {
  const profile: ExtractionProfile = { version: 1, responseFormat: "strict_confirmed_values_v1",
    ocr: { engine: "rapidocr", python: process.execPath, workDir: os.tmpdir(), timeoutSeconds: 90, maxRssMiB: 1024 } };
  const args: string[] = [];
  appendExtractionArguments(args, profile);
  assert.deepEqual(args, ["--ocr-engine", "rapidocr", "--ocr-page-budget-s", "90",
    "--response-format-profile", "strict_confirmed_values_v1"]);
  const base: NodeJS.ProcessEnv = { NODE_ENV: "test", IDPO_RAPIDOCR_PYTHON: "changed",
    IDPO_RAPIDOCR_TIMEOUT_S: "1", ICORE_API_KEY: "test-credential" };
  const env = extractionEnvironment(base, profile);
  assert.equal(env.IDPO_RAPIDOCR_PYTHON, process.execPath);
  assert.equal(env.IDPO_RAPIDOCR_TIMEOUT_S, "90");
  assert.equal(env.ICORE_API_KEY, "test-credential");
  for (const old of [undefined, { version: 1, responseFormat: "plain_json", ocr: { engine: "tesseract" } } as ExtractionProfile]) {
    assert.equal(extractionEnvironment(base, old).IDPO_RAPIDOCR_PYTHON, undefined);
  }
  const legacy: string[] = [];
  appendExtractionArguments(legacy);
  assert.deepEqual(legacy, []);
  assert.equal(base.IDPO_RAPIDOCR_PYTHON, "changed", "does not mutate inherited environment");
});

test("selective visual routing is an explicit sealed profile without changing historical visual runs", () => {
  const profile: ExtractionProfile = { version: 3, ocr: { engine: "tesseract" },
    responseFormat: "strict_confirmed_values_v1", longDocument: "bounded_text_segments_v1",
    visualDocument: "bounded_visual_selective_v2" };
  assert.equal(validExtractionProfile(profile), true);
  const args: string[] = [];
  appendExtractionArguments(args, profile);
  assert.deepEqual(args.slice(-2), ["--visual-document-profile", "bounded_visual_selective_v2"]);
  assert.equal(validExtractionProfile({ ...profile, visualDocument: "bounded_visual_v1" }), true);
});

test("keyed strict v2 is explicit, sealed, and does not reinterpret v1 dispatches", () => {
  const v2: ExtractionProfile = { version: 3, ocr: { engine: "tesseract" },
    responseFormat: "strict_confirmed_values_v2", longDocument: "bounded_text_segments_v1",
    visualDocument: "bounded_visual_selective_v2" };
  assert.equal(validExtractionProfile(v2), true);
  const args: string[] = [];
  appendExtractionArguments(args, v2);
  assert.deepEqual(args, ["--ocr-engine", "tesseract", "--response-format-profile", "strict_confirmed_values_v2",
    "--long-document-profile", "bounded_text_segments_v1", "--visual-document-profile", "bounded_visual_selective_v2"]);
  const v1: ExtractionProfile = { ...v2, responseFormat: "strict_confirmed_values_v1" };
  assert.equal(validExtractionProfile(v1), true);
  const oldArgs: string[] = [];
  appendExtractionArguments(oldArgs, v1);
  assert.equal(oldArgs[3], "strict_confirmed_values_v1");
  const previous = process.env.IDPO_AUTO_RESPONSE_FORMAT;
  const previousOcr = process.env.IDPO_AUTO_OCR_ENGINE;
  try {
    process.env.IDPO_AUTO_OCR_ENGINE = "tesseract";
    process.env.IDPO_AUTO_RESPONSE_FORMAT = "strict_confirmed_values_v2";
    assert.equal(configuredExtractionProfile(true).responseFormat, "strict_confirmed_values_v2");
    assert.equal(configuredExtractionProfile(false).responseFormat, "plain_json");
  } finally {
    if (previous === undefined) delete process.env.IDPO_AUTO_RESPONSE_FORMAT;
    else process.env.IDPO_AUTO_RESPONSE_FORMAT = previous;
    if (previousOcr === undefined) delete process.env.IDPO_AUTO_OCR_ENGINE;
    else process.env.IDPO_AUTO_OCR_ENGINE = previousOcr;
  }
});
