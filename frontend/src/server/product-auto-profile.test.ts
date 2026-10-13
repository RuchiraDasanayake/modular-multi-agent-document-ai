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
  const keys = ["IDPO_AUTO_OCR_ENGINE", "IDPO_AUTO_RESPONSE_FORMAT"];
  const previous = keys.map((key) => process.env[key]);
  try {
    process.env.IDPO_AUTO_OCR_ENGINE = "tesseract";
    process.env.IDPO_AUTO_RESPONSE_FORMAT = "strict_confirmed_values_v1";
    assert.equal(configuredExtractionProfile(true).responseFormat, "strict_confirmed_values_v1");
    assert.equal(configuredExtractionProfile(false).responseFormat, "plain_json");
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
