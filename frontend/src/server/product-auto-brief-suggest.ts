import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { createHash, randomUUID } from "node:crypto";
import { requireJob } from "@/server/access";
import { AccessError, requireAdmin, type AuthenticatedUser } from "@/server/auth";
import { getCommandConfig, loadRunnerConfig } from "@/server/config";
import { currentProductAutoBriefSampleFiles, requireCurrentProductAutoBrief,
  validateProductAutoBriefFields } from "@/server/product-auto-brief";
import type { ProductAutoBriefField, ProductAutoBriefSuggestion } from "@/types/product-auto-brief";

const SHA256 = /^[a-f0-9]{64}$/;
const MAX_REQUEST_BYTES = 48 * 1024;
const MAX_OUTPUT_BYTES = 64 * 1024;
const MAX_SOURCE_BYTES = 20 * 1024 * 1024;
const HELPER_TIMEOUT_MS = 120_000;

type HelperInput = {
  contract_version: 1;
  brief_revision: number;
  brief_payload_sha256: string;
  intent: string;
  existing_fields: { field_id: string; type: string; description: string; example_values: string[] }[];
  samples: { file_id: string; source_sha256: string; path: string }[];
  model: { id: string; base_url: string };
};

type HelperDiagnostic = {
  stage: string; code: string; finish_reason?: string | null;
  prompt_tokens?: number | null; completion_tokens?: number | null;
  sdk_attempts?: number | null; raw_reply_sha256?: string | null;
  helper_output_sha256?: string | null;
};

type AttemptContext = {
  id: string; jobId: string; directory: string; receiptFile: string; rawReplyPath: string | null;
};

class SuggestionHelperFailure extends Error {
  constructor(readonly diagnostic: HelperDiagnostic) { super("Schema suggestion helper failed."); }
}

function safeDiagnostic(raw: string): HelperDiagnostic {
  try {
    const parsed: unknown = JSON.parse(raw.trim().split(/\r?\n/).at(-1) ?? "");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error();
    const value = parsed as Record<string, unknown>;
    const bounded = (text: unknown) => typeof text === "string" && /^[A-Za-z0-9_]{1,64}$/.test(text);
    const count = (number: unknown) => number === null ||
      (typeof number === "number" && Number.isSafeInteger(number) && number >= 0 && number <= 10_000_000);
    if (!bounded(value.stage) || !bounded(value.code) ||
      value.finish_reason !== undefined && value.finish_reason !== null && !bounded(value.finish_reason) ||
      !count(value.prompt_tokens ?? null) || !count(value.completion_tokens ?? null) ||
      !count(value.sdk_attempts ?? null) ||
      value.raw_reply_sha256 !== undefined && value.raw_reply_sha256 !== null &&
      (typeof value.raw_reply_sha256 !== "string" || !SHA256.test(value.raw_reply_sha256))) throw new Error();
    return { stage: value.stage as string, code: value.code as string,
      finish_reason: value.finish_reason as string | null | undefined,
      prompt_tokens: value.prompt_tokens as number | null | undefined,
      completion_tokens: value.completion_tokens as number | null | undefined,
      sdk_attempts: value.sdk_attempts as number | null | undefined,
      raw_reply_sha256: value.raw_reply_sha256 as string | null | undefined };
  } catch { return { stage: "helper", code: "unknown_failure" }; }
}

function providerReplyHash(output: unknown): string | null {
  if (!output || typeof output !== "object" || Array.isArray(output)) return null;
  const provenance = (output as Record<string, unknown>).provenance;
  if (!provenance || typeof provenance !== "object" || Array.isArray(provenance)) return null;
  const hash = (provenance as Record<string, unknown>).raw_reply_sha256;
  return typeof hash === "string" && SHA256.test(hash) ? hash : null;
}

function writeAttemptReceipt(attempt: AttemptContext, input: HelperInput,
  status: "started" | "failed" | "completed", diagnostic: HelperDiagnostic): void {
  const receipt = {
    contract_version: 1, attempt_id: attempt.id, job_id: attempt.jobId,
    brief_revision: input.brief_revision, brief_payload_sha256: input.brief_payload_sha256,
    model_id: input.model.id, sample_sources: input.samples.map((sample) => ({
      file_id: sample.file_id, source_sha256: sample.source_sha256 })),
    status, ...diagnostic, raw_reply_saved: Boolean(attempt.rawReplyPath && fs.existsSync(attempt.rawReplyPath)),
    updated_at: new Date().toISOString(),
  };
  const temporary = `${attempt.receiptFile}.${randomUUID()}.tmp`;
  fs.writeFileSync(temporary, JSON.stringify(receipt, null, 2), { flag: "wx", mode: 0o600 });
  fs.renameSync(temporary, attempt.receiptFile);
}

function configuredModel(): HelperInput["model"] {
  const id = process.env.IDPO_AUTO_MODEL?.trim();
  const baseUrl = process.env.IDPO_AUTO_API_BASE_URL?.trim();
  if (!id || id.length > 128 || !baseUrl || baseUrl.length > 2048) {
    throw new AccessError("A server model must be configured for AI field suggestions.", 503);
  }
  let url: URL;
  try { url = new URL(baseUrl); }
  catch { throw new AccessError("The server model URL is invalid.", 503); }
  const local = url.protocol === "http:" && ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
  if (!(url.protocol === "https:" || local) || !url.hostname || url.username || url.password || url.search || url.hash) {
    throw new AccessError("The server model URL is invalid.", 503);
  }
  if (!local && !process.env.ICORE_API_KEY?.trim()) {
    throw new AccessError("The server model key is missing.", 503);
  }
  return { id, base_url: baseUrl };
}

function helperDirectory(jobId: string, ownerId: string): string {
  const ownerHash = createHash("sha256").update(ownerId).digest("hex");
  return path.join(path.dirname(loadRunnerConfig().runsDir), "frontend", "auto_briefs", ownerHash, jobId, "suggestions");
}

async function runDraftHelper(input: HelperInput, _jobId: string, _ownerId: string,
  attempt: AttemptContext): Promise<unknown> {
  const command = getCommandConfig("idpo_process_auto");
  const file = path.join(attempt.directory, `${attempt.id}.request.json`);
  const bytes = Buffer.from(JSON.stringify({ ...input,
    ...(attempt.rawReplyPath ? { raw_reply_path: attempt.rawReplyPath } : {}) }), "utf8");
  if (bytes.length > MAX_REQUEST_BYTES) throw new AccessError("The sample request is too large.", 400);
  fs.writeFileSync(file, bytes, { flag: "wx", mode: 0o600 });
  try {
    const digest = createHash("sha256").update(bytes).digest("hex");
    const output = await new Promise<string>((resolve, reject) => {
      const child = spawn(command.program, ["-m", "idpo.product_auto.brief_draft", "--request-file", file,
        "--request-sha256", digest], {
        cwd: command.cwd, env: { ...process.env, ...command.env }, windowsHide: true,
        stdio: ["ignore", "pipe", "pipe"], shell: false,
      });
      let stdout = "";
      let stderr = "";
      let settled = false;
      const finish = (error?: Error, value?: string) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        if (error) reject(error); else resolve(value ?? "");
      };
      const timer = setTimeout(() => {
        child.kill();
        finish(new SuggestionHelperFailure({ stage: "helper", code: "timeout" }));
      }, HELPER_TIMEOUT_MS);
      child.stdout.setEncoding("utf8");
      child.stdout.on("data", (chunk: string) => {
        stdout += chunk;
        if (Buffer.byteLength(stdout, "utf8") > MAX_OUTPUT_BYTES) {
          child.kill();
          finish(new SuggestionHelperFailure({ stage: "helper", code: "output_limit" }));
        }
      });
      child.stderr.setEncoding("utf8");
      child.stderr.on("data", (chunk: string) => {
        stderr += chunk;
        if (Buffer.byteLength(stderr, "utf8") > 8192) {
          child.kill();
          finish(new SuggestionHelperFailure({ stage: "helper", code: "stderr_limit" }));
        }
      });
      child.on("error", () => finish(new SuggestionHelperFailure({ stage: "helper", code: "start_failed" })));
      child.on("close", (code) => code === 0 ? finish(undefined, stdout) :
        finish(new SuggestionHelperFailure(safeDiagnostic(stderr))));
    });
    try { return JSON.parse(output) as unknown; }
    catch { throw new SuggestionHelperFailure({ stage: "helper", code: "invalid_stdout" }); }
  } finally {
    fs.rmSync(file, { force: true });
  }
}

function validateSuggestion(value: unknown, input: HelperInput): ProductAutoBriefSuggestion {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid schema suggestion.");
  const result = value as Record<string, unknown>;
  if (Object.keys(result).sort().join() !== "clarification_questions,fields,provenance") {
    throw new Error("Invalid schema suggestion.");
  }
  const fields = validateProductAutoBriefFields(result.fields);
  if (fields.length < 1 || fields.length > 12 || fields.some((field) => !field.description)) {
    throw new Error("Invalid schema suggestion fields.");
  }
  const questions = result.clarification_questions;
  if (!Array.isArray(questions) || questions.length > 5 || questions.some((question) =>
    typeof question !== "string" || !question.trim() || question !== question.trim() ||
    [...question].length > 200 || /[\u0000-\u001f\u007f]/u.test(question))) {
    throw new Error("Invalid schema suggestion questions.");
  }
  const p = result.provenance;
  if (!p || typeof p !== "object" || Array.isArray(p)) throw new Error("Invalid schema suggestion provenance.");
  const receipt = p as Record<string, unknown>;
  const samples = receipt.samples;
  if (receipt.brief_revision !== input.brief_revision || receipt.brief_payload_sha256 !== input.brief_payload_sha256 ||
    typeof receipt.prompt_sha256 !== "string" || !SHA256.test(receipt.prompt_sha256) ||
    !receipt.model || typeof receipt.model !== "object" || Array.isArray(receipt.model) ||
    (receipt.model as Record<string, unknown>).id !== input.model.id ||
    !Array.isArray(samples) || samples.length !== input.samples.length ||
    samples.some((sample, index) => !sample || typeof sample !== "object" ||
      (sample as Record<string, unknown>).file_id !== input.samples[index].file_id ||
      (sample as Record<string, unknown>).source_sha256 !== input.samples[index].source_sha256 ||
      typeof (sample as Record<string, unknown>).parser_id !== "string" ||
      !/^[a-zA-Z0-9_.-]{1,80}$/.test((sample as Record<string, unknown>).parser_id as string) ||
      typeof (sample as Record<string, unknown>).truncated !== "boolean" ||
      typeof (sample as Record<string, unknown>).excerpt_chars !== "number" ||
      !Number.isInteger((sample as Record<string, unknown>).excerpt_chars) ||
      ((sample as Record<string, unknown>).excerpt_chars as number) < 1 ||
      ((sample as Record<string, unknown>).excerpt_chars as number) > 1800) ||
    receipt.max_output_tokens !== 1800 || typeof receipt.input_chars !== "number" ||
    !Number.isInteger(receipt.input_chars) || receipt.input_chars < 1 || receipt.input_chars > 24000 ||
    (receipt.sdk_attempts !== null && receipt.sdk_attempts !== 1)) {
    throw new Error("Invalid schema suggestion provenance.");
  }
  const nonnegative = (number: unknown) => number === null ||
    (typeof number === "number" && Number.isFinite(number) && number >= 0);
  if (!nonnegative(receipt.prompt_tokens) || !nonnegative(receipt.completion_tokens) ||
    !nonnegative(receipt.latency_ms)) throw new Error("Invalid model usage receipt.");
  return { fields: fields as ProductAutoBriefField[], clarification_questions: questions as string[],
    provenance: {
      brief_revision: input.brief_revision, brief_payload_sha256: input.brief_payload_sha256,
      samples: samples.map((sample) => {
        const receipt = sample as Record<string, unknown>;
        return { file_id: receipt.file_id as string, source_sha256: receipt.source_sha256 as string,
          parser_id: receipt.parser_id as string, excerpt_chars: receipt.excerpt_chars as number,
          truncated: receipt.truncated as boolean };
      }), model_id: input.model.id,
      prompt_sha256: receipt.prompt_sha256 as string, input_chars: receipt.input_chars as number,
      max_output_tokens: 1800, prompt_tokens: receipt.prompt_tokens as number | null,
      completion_tokens: receipt.completion_tokens as number | null,
      latency_ms: receipt.latency_ms as number | null,
    } };
}

export async function suggestProductAutoBrief(jobId: string, user: AuthenticatedUser, rawRequest: unknown,
  helper: (input: HelperInput, jobId: string, ownerId: string, attempt: AttemptContext) => Promise<unknown> = runDraftHelper,
): Promise<ProductAutoBriefSuggestion> {
  const job = requireJob(jobId, user);
  requireAdmin(user);
  if (!job.ownerUserId) throw new AccessError("An owned job is required for schema suggestions.", 409);
  if (!rawRequest || typeof rawRequest !== "object" || Array.isArray(rawRequest) ||
    Object.keys(rawRequest).sort().join() !== "expectedPayloadSha256,expectedRevision") {
    throw new AccessError("Pin the saved draft revision to request a suggestion.", 400);
  }
  const request = rawRequest as Record<string, unknown>;
  if (typeof request.expectedRevision !== "number" || !Number.isSafeInteger(request.expectedRevision) ||
    request.expectedRevision < 1 || typeof request.expectedPayloadSha256 !== "string" ||
    !SHA256.test(request.expectedPayloadSha256)) {
    throw new AccessError("Pin the saved draft revision to request a suggestion.", 400);
  }
  const brief = requireCurrentProductAutoBrief(jobId, request.expectedRevision, request.expectedPayloadSha256);
  if (brief.state !== "draft") throw new AccessError("Save a new draft before requesting AI suggestions.", 409);
  const model = configuredModel();
  const samples = currentProductAutoBriefSampleFiles(jobId, brief.revision, brief.payload_sha256);
  for (const sample of samples) {
    let size: number;
    try { size = fs.statSync(sample.path).size; }
    catch { throw new AccessError("A sample source is unavailable in this job.", 409); }
    if (size > MAX_SOURCE_BYTES) {
      throw new AccessError("Sample source exceeds the 20 MB suggestion limit.", 400);
    }
  }
  const input: HelperInput = {
    contract_version: 1, brief_revision: brief.revision, brief_payload_sha256: brief.payload_sha256,
    intent: brief.intent, samples, model,
    existing_fields: brief.fields.slice(0, 12).map((field) => ({ field_id: field.field_id,
      type: field.type, description: field.description.slice(0, 200),
      example_values: field.example_values.map((value) => value.slice(0, 80)) })),
  };
  const directory = helperDirectory(jobId, job.ownerUserId);
  fs.mkdirSync(directory, { recursive: true });
  const attemptId = randomUUID();
  const attempt: AttemptContext = { id: attemptId, jobId, directory,
    receiptFile: path.join(directory, `${attemptId}.diagnostic.json`),
    rawReplyPath: process.env.IDPO_AUTO_SUGGEST_CAPTURE_RAW === "1"
      ? path.join(directory, `${attemptId}.reply.txt`) : null };
  writeAttemptReceipt(attempt, input, "started", { stage: "helper", code: "started" });
  let raw: unknown;
  try { raw = await helper(input, jobId, job.ownerUserId, attempt); }
  catch (error) {
    const diagnostic = error instanceof SuggestionHelperFailure ? error.diagnostic :
      { stage: "helper", code: "unknown_failure" };
    writeAttemptReceipt(attempt, input, "failed", diagnostic);
    throw new AccessError(`AI field suggestion failed (reference ${attemptId}).`, 502);
  }
  let suggestion: ProductAutoBriefSuggestion;
  try { suggestion = validateSuggestion(raw, input); }
  catch {
    const output = JSON.stringify(raw) ?? "undefined";
    writeAttemptReceipt(attempt, input, "failed", { stage: "node_validation", code: "invalid_suggestion",
      raw_reply_sha256: providerReplyHash(raw),
      helper_output_sha256: createHash("sha256").update(output).digest("hex") });
    throw new AccessError(`The model returned an invalid field suggestion (reference ${attemptId}).`, 502);
  }
  try { requireCurrentProductAutoBrief(jobId, brief.revision, brief.payload_sha256); }
  catch {
    writeAttemptReceipt(attempt, input, "failed", { stage: "postflight", code: "source_or_revision_changed" });
    throw new AccessError("Extraction brief or sample source changed. Reload before continuing.", 409);
  }
  writeAttemptReceipt(attempt, input, "completed", { stage: "complete", code: "ok",
    prompt_tokens: suggestion.provenance.prompt_tokens,
    completion_tokens: suggestion.provenance.completion_tokens, sdk_attempts: 1,
    raw_reply_sha256: providerReplyHash(raw) });
  return suggestion;
}
