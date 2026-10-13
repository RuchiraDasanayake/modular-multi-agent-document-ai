import fs from "node:fs";
import path from "node:path";
import { createHash, randomUUID } from "node:crypto";
import { spawn } from "node:child_process";
import { AccessError } from "@/server/auth";
import { getCommandConfig, loadRunnerConfig } from "@/server/config";
import { getJobOrThrow } from "@/server/jobs";
import { requireCurrentProductAutoBrief } from "@/server/product-auto-brief";
import { claimProductAutoRunRequestReceipt, readProductAutoRunRequestReceipt,
  validProductAutoRunRequestKey } from "@/server/product-auto-run-requests";
import { productExecutionQueue, QueueAdmissionError, type ProductDispatch } from "@/server/product-execution-queue";
import { appendExtractionArguments, configuredExtractionProfile, extractionEnvironment,
  validExtractionProfile, type ExtractionProfile } from "@/server/product-auto-profile";
import type { ProductAutoBriefRevision } from "@/types/product-auto-brief";
import type {
  ProductAutoAddedField,
  ProductAutoAddedLinkedCell,
  ProductAutoAuditEvent,
  ProductAutoCandidate,
  ProductAutoCorrectedResult,
  ProductAutoDocumentDetail,
  ProductAutoEvidence,
  ProductAutoHumanSourcePage,
  ProductAutoLinkedCell,
  ProductAutoLinkedCorrectionRow,
  ProductAutoParsedDocument,
  ProductAutoReview,
  ProductAutoReviewDecision,
  ProductAutoReviewField,
  ProductAutoReviewedExport,
  ProductAutoRun,
  ProductAutoRunDocument,
  ProductAutoScalarType,
} from "@/types/product-auto";

const SAFE_ID = /^[a-zA-Z0-9_-]{1,100}$/;
const MAX_REVIEW_NOTE = 2000;
const MAX_CORRECTION = 10000;
const MAX_LINKED_CORRECTION = 300000;
const MAX_LINKED_ROWS = 128;
const MAX_SCHEMA_FIELDS = 24;
const MAX_ADDED_FIELDS = MAX_SCHEMA_FIELDS;
const MAX_ADDED_QUOTE = 500;
const SCHEMA_FIELD_ID = /^[\p{L}][\p{L}\p{N}_]{0,63}$/u;
const SCHEMA_TYPES = new Set(["string", "integer", "decimal", "boolean", "date", "array[object]"]);
const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);
const DEFAULT_MODEL_MAX_OUTPUT_TOKENS = 8192;
const MAX_MODEL_MAX_OUTPUT_TOKENS = 16384;
const DEFAULT_MODEL_TIMEOUT_S = 180;
const MAX_MODEL_TIMEOUT_S = 600;
const MAX_REVIEWED_BATCH_DOCUMENTS = 5000;
const MAX_REVIEWED_BATCH_BYTES = 64 * 1024 * 1024;
const HEARTBEAT_INTERVAL_MS = 15_000;
const LEASE_TIMEOUT_MS = 5 * 60_000;
const RECOVERY_INTERVAL_MS = 30_000;
const activeHeartbeats = new Map<string, NodeJS.Timeout>();
const instanceId: string = (() => {
  const holder = globalThis as typeof globalThis & { __productAutoInstanceId?: string };
  holder.__productAutoInstanceId ??= randomUUID();
  return holder.__productAutoInstanceId;
})();

interface SelectedFile {
  fileId: string;
  fileName: string;
  storedName: string;
  sha256: string;
}

interface RunRecord {
  runId: string;
  jobId: string;
  idempotencyKey?: string;
  status: "queued" | "running" | "success" | "failed";
  createdAt: string;
  endedAt?: string;
  serverInstanceId: string;
  queueDispatch?: { ownerId: string; sha256: string };
  selectedFiles: SelectedFile[];
  approvedRecipe?: {
    recipeId: string; revision: number; auditEventId: string; ownerUserId: string;
    familyName: string; snapshotSha256: string;
  };
  confirmedBrief?: {
    briefId: string; revision: number; auditEventId: string; ownerUserId: string; jobId: string;
    payloadSha256: string; snapshotSha256: string; phase: "preview" | "batch"; previewRunId?: string;
  };
  documents: Array<ProductAutoRunDocument & { machineResultSha256?: string }>;
  error?: string;
}

interface RunLease {
  ownerInstanceId: string;
  heartbeatAt: string;
  expiresAt: string;
}

function requireSafeId(value: string): void {
  if (!SAFE_ID.test(value)) throw new AccessError("Run or document not found.", 404);
}

function storageRoot(): string {
  return path.dirname(loadRunnerConfig().runsDir);
}

function runFile(jobId: string, runId: string): string {
  requireSafeId(jobId);
  requireSafeId(runId);
  return path.join(storageRoot(), "frontend", "auto_runs", jobId, `${runId}.json`);
}

function terminalFile(jobId: string, runId: string): string {
  return runFile(jobId, runId).replace(/\.json$/, ".terminal.json");
}

function leaseFile(jobId: string, runId: string): string {
  return runFile(jobId, runId).replace(/\.json$/, ".lease.json");
}

function outputDir(runId: string): string {
  requireSafeId(runId);
  return path.join(storageRoot(), "product_runs", runId);
}

function stagedInputDir(runId: string): string {
  requireSafeId(runId);
  const root = path.resolve(storageRoot(), "frontend", "auto_inputs");
  const target = path.resolve(root, runId);
  if (path.dirname(target) !== root) throw new Error("Invalid staging directory.");
  return target;
}

function stagedRecipeFile(runId: string): string {
  return path.join(path.dirname(stagedInputDir(runId)), `${runId}.recipe.json`);
}

function stagedSchemaFile(runId: string): string {
  return path.join(path.dirname(stagedInputDir(runId)), `${runId}.schema.json`);
}

function dispatchFile(jobId: string, runId: string): string {
  return runFile(jobId, runId).replace(/\.json$/, ".dispatch.json");
}

interface ModelBudget {
  maxOutputTokens: number;
  timeoutSeconds: number;
}

interface PreparedDispatch {
  version: 1 | 2 | 3;
  ownerId: string;
  jobId: string;
  runId: string;
  commandSha256: string;
  inputManifestSha256: string;
  model?: string;
  baseUrl?: string;
  modelBudget?: ModelBudget;
  extractionProfile?: ExtractionProfile;
}

function validModelBudget(value: unknown): value is ModelBudget {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const budget = value as Record<string, unknown>;
  return Object.keys(budget).sort().join() === "maxOutputTokens,timeoutSeconds" &&
    Number.isSafeInteger(budget.maxOutputTokens) && (budget.maxOutputTokens as number) >= 1 &&
    (budget.maxOutputTokens as number) <= MAX_MODEL_MAX_OUTPUT_TOKENS &&
    Number.isSafeInteger(budget.timeoutSeconds) && (budget.timeoutSeconds as number) >= 1 &&
    (budget.timeoutSeconds as number) <= MAX_MODEL_TIMEOUT_S;
}

function configuredModelBudget(): ModelBudget {
  const bounded = (name: string, fallback: number, maximum: number): number => {
    const raw = process.env[name];
    if (raw === undefined || raw === "") return fallback;
    if (!/^[1-9][0-9]*$/.test(raw)) throw new AccessError(`Invalid server model budget: ${name}.`, 503);
    const number = Number(raw);
    if (!Number.isSafeInteger(number) || number > maximum) {
      throw new AccessError(`Invalid server model budget: ${name}.`, 503);
    }
    return number;
  };
  return {
    maxOutputTokens: bounded("IDPO_AUTO_MAX_OUTPUT_TOKENS", DEFAULT_MODEL_MAX_OUTPUT_TOKENS,
      MAX_MODEL_MAX_OUTPUT_TOKENS),
    timeoutSeconds: bounded("IDPO_AUTO_TIMEOUT_S", DEFAULT_MODEL_TIMEOUT_S, MAX_MODEL_TIMEOUT_S),
  };
}

function appendModelArguments(args: string[], model?: string, baseUrl?: string, budget?: ModelBudget): void {
  if (!model || !baseUrl) return;
  args.push("--model", model, "--api-base-url", baseUrl);
  if (budget) args.push("--max-tokens", String(budget.maxOutputTokens),
    "--timeout-s", String(budget.timeoutSeconds));
}

function commandSha256(): string {
  // Environment values may contain credentials: persist only their digest.
  return createHash("sha256").update(JSON.stringify(getCommandConfig("idpo_process_auto"))).digest("hex");
}

function inputManifestSha256(record: Pick<RunRecord, "selectedFiles" | "approvedRecipe" | "confirmedBrief">): string {
  return createHash("sha256").update(JSON.stringify({ selectedFiles: record.selectedFiles,
    approvedRecipe: record.approvedRecipe ?? null, confirmedBrief: record.confirmedBrief ?? null })).digest("hex");
}

function recipeReceipt(record: RunRecord): Record<string, string | number> | null {
  const recipe = record.approvedRecipe;
  return recipe ? {
    recipe_id: recipe.recipeId, revision: recipe.revision,
    audit_event_id: recipe.auditEventId, snapshot_sha256: recipe.snapshotSha256,
  } : null;
}

function matchesRecipeReceipt(value: unknown, record: RunRecord): boolean {
  const expected = recipeReceipt(record);
  if (expected === null) return value == null;
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const actual = value as Record<string, unknown>;
  return Object.keys(actual).length === Object.keys(expected).length &&
    Object.entries(expected).every(([key, wanted]) => actual[key] === wanted);
}

function confirmedSchemaReceipt(record: RunRecord): Record<string, string | number> | null {
  const brief = record.confirmedBrief;
  return brief ? {
    brief_id: brief.briefId, revision: brief.revision, audit_event_id: brief.auditEventId,
    payload_sha256: brief.payloadSha256, snapshot_sha256: brief.snapshotSha256,
  } : null;
}

function matchesConfirmedSchemaReceipt(value: unknown, record: RunRecord): boolean {
  const expected = confirmedSchemaReceipt(record);
  if (expected === null) return value == null;
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const actual = value as Record<string, unknown>;
  return Object.keys(actual).length === Object.keys(expected).length &&
    Object.entries(expected).every(([key, wanted]) => actual[key] === wanted);
}

function auditDir(jobId: string, runId: string, docId: string): string {
  requireSafeId(docId);
  return path.join(storageRoot(), "frontend", "auto_reviews", jobId, runId, "events", docId);
}

function writeJsonAtomic(filePath: string, value: unknown): void {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const temporary = `${filePath}.${randomUUID()}.tmp`;
  try {
    fs.writeFileSync(temporary, JSON.stringify(value, null, 2), "utf8");
    fs.renameSync(temporary, filePath);
  } finally {
    if (fs.existsSync(temporary)) fs.unlinkSync(temporary);
  }
}

function parseJsonObject(filePath: string): Record<string, unknown> {
  let parsed: unknown;
  try {
    parsed = JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    throw new Error("Invalid extraction artifact.");
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Invalid extraction artifact.");
  }
  return parsed as Record<string, unknown>;
}

function parseJsonLines(filePath: string): Record<string, unknown>[] {
  return fs.readFileSync(filePath, "utf8").split(/\r?\n/).filter(Boolean).map((line) => {
    let value: unknown;
    try {
      value = JSON.parse(line);
    } catch {
      throw new Error("Invalid extraction artifact.");
    }
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new Error("Invalid extraction artifact.");
    }
    return value as Record<string, unknown>;
  });
}

function readRunRecord(jobId: string, runId: string): RunRecord {
  const filePath = runFile(jobId, runId);
  if (!fs.existsSync(filePath)) throw new AccessError("Run not found.", 404);
  const base = parseJsonObject(filePath) as unknown as RunRecord;
  if (base.jobId !== jobId || base.runId !== runId) throw new Error("Invalid run record.");
  const terminal = terminalFile(jobId, runId);
  if (!fs.existsSync(terminal)) return base;
  const completed = parseJsonObject(terminal) as unknown as RunRecord;
  if (completed.jobId !== jobId || completed.runId !== runId ||
    !["success", "failed"].includes(completed.status)) throw new Error("Invalid run terminal record.");
  return completed;
}

function saveRunRecord(record: RunRecord): void {
  writeJsonAtomic(runFile(record.jobId, record.runId), record);
}

function publishTerminalRecord(record: RunRecord): boolean {
  const target = terminalFile(record.jobId, record.runId);
  const temporary = `${target}.${randomUUID()}.tmp`;
  try {
    fs.writeFileSync(temporary, JSON.stringify(record, null, 2), { encoding: "utf8", flag: "wx" });
    fs.linkSync(temporary, target);
    return true;
  } catch (error) {
    if (error && typeof error === "object" && "code" in error && error.code === "EEXIST") return false;
    throw error;
  } finally {
    if (fs.existsSync(temporary)) fs.unlinkSync(temporary);
  }
}

function writeLease(jobId: string, runId: string): void {
  const now = Date.now();
  const lease: RunLease = { ownerInstanceId: instanceId, heartbeatAt: new Date(now).toISOString(),
    expiresAt: new Date(now + LEASE_TIMEOUT_MS).toISOString() };
  writeJsonAtomic(leaseFile(jobId, runId), lease);
}

function leaseExpired(record: RunRecord, now: number): boolean {
  const leasePath = leaseFile(record.jobId, record.runId);
  if (fs.existsSync(leasePath)) {
    try {
      const lease = parseJsonObject(leasePath) as unknown as RunLease;
      const expiresAt = Date.parse(lease.expiresAt);
      if (lease.ownerInstanceId === record.serverInstanceId && Number.isFinite(expiresAt) &&
        expiresAt <= now + LEASE_TIMEOUT_MS + HEARTBEAT_INTERVAL_MS) return expiresAt <= now;
    } catch { /* An invalid lease uses its file modification time. */ }
    try {
      return fs.statSync(leasePath).mtimeMs + LEASE_TIMEOUT_MS <= now;
    } catch { /* The lease disappeared while it was being read. */ }
  }
  const createdAt = Date.parse(record.createdAt);
  return !Number.isFinite(createdAt) || createdAt + LEASE_TIMEOUT_MS <= now;
}

function stopHeartbeat(runId: string): void {
  const heartbeat = activeHeartbeats.get(runId);
  if (heartbeat) clearInterval(heartbeat);
  activeHeartbeats.delete(runId);
}

function startHeartbeat(jobId: string, runId: string): void {
  const heartbeat = setInterval(() => {
    try {
      const record = readRunRecord(jobId, runId);
      if (record.status !== "running" || record.serverInstanceId !== instanceId) {
        stopHeartbeat(runId);
        return;
      }
      writeLease(jobId, runId);
    } catch (error) {
      console.error("Product run heartbeat failed:", error);
    }
  }, HEARTBEAT_INTERVAL_MS);
  heartbeat.unref();
  activeHeartbeats.set(runId, heartbeat);
}

function sha256File(filePath: string): string {
  return createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function hasEvidenceShape(value: unknown): value is ProductAutoEvidence {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const evidence = value as Record<string, unknown>;
  return Object.keys(evidence).every((key) => ["page", "start", "end", "quote", "kind"].includes(key)) &&
    (evidence.kind === undefined || evidence.kind === "text_match") &&
    Number.isInteger(evidence.page) && typeof evidence.page === "number" && evidence.page > 0 &&
    Number.isInteger(evidence.start) && typeof evidence.start === "number" && evidence.start >= 0 &&
    Number.isInteger(evidence.end) && typeof evidence.end === "number" && evidence.end > evidence.start &&
    typeof evidence.quote === "string" && evidence.quote.length > 0;
}

function hasHumanSourcePageShape(value: unknown): value is ProductAutoHumanSourcePage {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const source = value as Record<string, unknown>;
  return Object.keys(source).sort().join(",") === "kind,page" &&
    source.kind === "human_observed_page" && typeof source.page === "number" &&
    Number.isSafeInteger(source.page) && source.page > 0;
}

function assertSourceEvidence(value: unknown, pages: unknown): asserts value is ProductAutoEvidence {
  if (!hasEvidenceShape(value)) throw new Error("Invalid candidate evidence.");
  const page = Array.isArray(pages) ? pages.find((item) => item && typeof item === "object" && item.page === value.page) : null;
  if (!page || typeof page.text !== "string" || [...page.text].slice(value.start, value.end).join("") !== value.quote) {
    throw new Error("Candidate evidence does not match source text.");
  }
}

function linkedValueMatchesQuote(value: string, quote: string): boolean {
  const needle = value.toLowerCase();
  const text = quote.toLowerCase();
  if (!needle) return false;
  const word = /[\p{L}\p{N}_]/u;
  let index = text.indexOf(needle);
  while (index >= 0) {
    const before = index > 0 ? [...text.slice(0, index)].at(-1) : undefined;
    const after = [...text.slice(index + needle.length)][0];
    if ((!before || !word.test(before)) && (!after || !word.test(after))) return true;
    index = text.indexOf(needle, index + 1);
  }
  return false;
}

function addedLinkedValueMatchesQuote(value: string, quote: string): boolean {
  const needle = value.toLowerCase();
  const text = quote.toLowerCase();
  const word = /[\p{L}\p{N}_]/u;
  const numeric = /^[+-]?\d+(?:[.,]\d+)*$/u.test(value);
  let matches = 0;
  let index = text.indexOf(needle);
  while (index >= 0) {
    const prefix = text.slice(0, index);
    const suffix = text.slice(index + needle.length);
    const before = [...prefix].at(-1);
    const after = [...suffix][0];
    const separateToken = (!before || !word.test(before)) && (!after || !word.test(after));
    const partialNumber = numeric && (/[+-]$/u.test(prefix) || /\d[.,]$/u.test(prefix) ||
      /^[.,-]\d/u.test(suffix));
    if (separateToken && !partialNumber) matches += 1;
    index = text.indexOf(needle, index + 1);
  }
  return matches === 1;
}

function canonicalDecimal(value: string): string | null {
  const match = /^([+-]?)(\d+)(?:\.(\d+))?(?:e([+-]?\d+))?$/i.exec(value);
  if (!match) return null;
  let digits = `${match[2]}${match[3] ?? ""}`.replace(/^0+/, "");
  if (!digits) return "0";
  let exponent = Number(match[4] ?? 0) - (match[3]?.length ?? 0);
  while (digits.endsWith("0")) {
    digits = digits.slice(0, -1);
    exponent += 1;
  }
  return `${match[1] === "-" ? "-" : ""}${digits}e${exponent}`;
}

function acceptedScalarMatchesQuote(value: unknown, type: string, quote: string, fieldId: string): boolean {
  if (type === "string" || type === "date") {
    if (typeof value !== "string" || !value.trim()) return false;
    if (type === "date" && (!/^\d{4}-\d{2}-\d{2}$/.test(value) ||
      Number.isNaN(Date.parse(`${value}T00:00:00Z`)) ||
      new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) !== value)) return false;
    const identifier = ["id", "number", "reference", "phone", "postal_code", "zip_code"].includes(fieldId) ||
      ["_id", "_number", "_reference", "_code", "_phone"].some((suffix) => fieldId.endsWith(suffix));
    return type === "string" && identifier
      ? quote.trim().toLowerCase() === value.trim().toLowerCase()
      : linkedValueMatchesQuote(value.trim(), quote);
  }
  if (type === "boolean") {
    if (typeof value !== "boolean") return false;
    const tokens = quote.toLowerCase().match(/(?<![\p{L}\p{N}_])(?:true|false|yes|no)(?![\p{L}\p{N}_])/gu) ?? [];
    const polarities = new Set(tokens.map((token) => token === "true" || token === "yes"));
    return polarities.size === 1 && polarities.has(value);
  }
  if (type === "integer" || type === "decimal") {
    if (typeof value !== "number" || !Number.isFinite(value) || Math.abs(value) > Number.MAX_SAFE_INTEGER ||
      type === "integer" && !Number.isSafeInteger(value)) return false;
    const numbers = quote.match(/[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?/g) ?? [];
    return numbers.length === 1 &&
      canonicalDecimal(numbers[0].replaceAll(",", "")) === canonicalDecimal(String(value));
  }
  return false;
}

function machineLinkedRows(value: unknown): ProductAutoLinkedCell[] | null {
  if (!Array.isArray(value) || value.length > MAX_LINKED_ROWS) return null;
  const seen = new Set<number>();
  for (const item of value) {
    if (!item || typeof item !== "object" || Array.isArray(item)) return null;
    const cell = item as Record<string, unknown>;
    const visualCell = ["visual_page", "visual_grounding_verified", "review_state"].some((key) => key in cell);
    if (Object.keys(cell).some((key) => !["row", "value", "status", "evidence", "visual_page",
      "visual_grounding_verified", "review_state"].includes(key)) ||
      !Number.isInteger(cell.row) || typeof cell.row !== "number" || cell.row < 0 || cell.row >= MAX_LINKED_ROWS ||
      seen.has(cell.row) || typeof cell.value !== "string" || !cell.value.trim() || [...cell.value].length > 500 ||
      !["accepted", "needs_review"].includes(String(cell.status)) ||
      visualCell && (!Number.isSafeInteger(cell.visual_page) || typeof cell.visual_page !== "number" ||
        cell.visual_page < 1 || cell.visual_grounding_verified !== false || cell.review_state !== "pending" ||
        cell.status !== "needs_review") ||
      cell.status === "accepted" && !hasEvidenceShape(cell.evidence) ||
      cell.status === "accepted" && hasEvidenceShape(cell.evidence) &&
        (cell.evidence.kind !== undefined || !linkedValueMatchesQuote(cell.value, cell.evidence.quote)) ||
      cell.evidence != null && !hasEvidenceShape(cell.evidence)) return null;
    seen.add(cell.row);
  }
  return value as ProductAutoLinkedCell[];
}

function linkedRowsAreVerified(value: unknown): boolean {
  const rows = machineLinkedRows(value);
  return Boolean(rows?.length && rows.every((cell) => cell.status === "accepted" && cell.evidence &&
    cell.evidence.kind === undefined && cell.visual_page === undefined));
}

function linkedRowsCanBeHumanVerified(value: unknown, visual: boolean): boolean {
  if (linkedRowsAreVerified(value)) return true;
  if (!visual) return false;
  const rows = machineLinkedRows(value);
  return Boolean(rows?.length && rows.every((cell) => cell.status === "needs_review" &&
    cell.review_state === "pending" && cell.visual_grounding_verified === false &&
    Number.isSafeInteger(cell.visual_page)));
}

function sealedVisualReview(review: ProductAutoReview | null): boolean {
  return Boolean(review?.reviewer_user_id && /^[a-f0-9]{64}$/.test(review.source_container_sha256 ?? "") &&
    /^[a-f0-9]{64}$/.test(review.source_pages_sha256 ?? "") &&
    /^[a-f0-9]{64}$/.test(review.machine_result_sha256 ?? ""));
}

function validVisualScalar(value: unknown, type: string): boolean {
  if (type === "string") return typeof value === "string" && Boolean(value.trim());
  if (type === "boolean") return typeof value === "boolean";
  if (type === "integer") return typeof value === "number" && Number.isSafeInteger(value);
  if (type === "decimal") return typeof value === "number" && Number.isFinite(value) &&
    Math.abs(value) <= Number.MAX_SAFE_INTEGER;
  if (type === "date") return typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    !Number.isNaN(Date.parse(`${value}T00:00:00Z`)) &&
    new Date(`${value}T00:00:00Z`).toISOString().slice(0, 10) === value;
  return false;
}

function candidateFromArtifact(value: unknown, docId: string, pages: unknown): ProductAutoCandidate {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid candidate.");
  const candidate = value as Record<string, unknown>;
  if (candidate.contract_version !== 1 || candidate.doc_id !== docId ||
    !Array.isArray(candidate.proposed_schema) || candidate.proposed_schema.length > MAX_SCHEMA_FIELDS ||
    !Array.isArray(candidate.extracted_values)) {
    throw new Error("Invalid candidate.");
  }
  if (!["processed", "needs_review", "unsupported", "failed"].includes(String(candidate.document_status))) {
    throw new Error("Invalid candidate status.");
  }
  const sourcePageIds = new Set<number>();
  if (Array.isArray(pages)) {
    for (const page of pages) {
      if (page && typeof page === "object" && Number.isSafeInteger(page.page) && page.page > 0) {
        sourcePageIds.add(page.page);
      }
    }
  }
  const schemaIds = new Set<string>();
  const schemaTypes = new Map<string, string>();
  for (const field of candidate.proposed_schema) {
    if (!field || typeof field !== "object" || typeof field.field_id !== "string" ||
      !SCHEMA_FIELD_ID.test(field.field_id) || field.field_id.endsWith("_") ||
      field.field_id !== field.field_id.normalize("NFKC").toLowerCase() ||
      typeof field.type !== "string" || !SCHEMA_TYPES.has(field.type) || schemaIds.has(field.field_id) ||
      "group" in field && (typeof field.group !== "string" || !field.group ||
        field.group.trim() !== field.group || [...field.group].length > 64)) {
      throw new Error("Invalid proposed schema.");
    }
    schemaIds.add(field.field_id);
    schemaTypes.set(field.field_id, field.type);
  }
  for (const field of candidate.extracted_values) {
    if (!field || typeof field !== "object" || typeof field.field_id !== "string" ||
      !schemaIds.has(field.field_id) || !["accepted", "needs_review", "missing", "rejected"].includes(String(field.status))) {
      throw new Error("Invalid extracted value.");
    }
    if (Object.keys(field).some((key) => !["field_id", "value", "status", "review_state", "evidence",
      "visual_pages", "visual_grounding_verified"].includes(key))) {
      throw new Error("Unknown extracted value metadata.");
    }
    const visual = "visual_grounding_verified" in field || "visual_pages" in field;
    if (visual && (field.visual_grounding_verified !== false || field.status !== "needs_review" ||
      field.review_state !== "pending" || candidate.document_status !== "needs_review")) {
      throw new Error("Invalid visual review state.");
    }
    if (field.status === "accepted" && !field.evidence) throw new Error("Accepted value has no evidence.");
    if (field.evidence) assertSourceEvidence(field.evidence, pages);
    if (field.evidence && (visual && field.evidence.kind !== "text_match" ||
      !visual && field.evidence.kind !== undefined)) {
      throw new Error("Invalid visual evidence kind.");
    }
    const fieldType = schemaTypes.get(field.field_id)!;
    if (field.status === "accepted" && fieldType !== "array[object]" &&
      !acceptedScalarMatchesQuote(field.value, fieldType, field.evidence.quote, field.field_id)) {
      throw new Error("Accepted value does not match its type and source quote.");
    }
    if (fieldType === "array[object]") {
      if ("visual_pages" in field) throw new Error("Linked fields use per-cell visual pages.");
      if (field.value === null) {
        if (field.status === "accepted" || visual) throw new Error("A missing linked field cannot be accepted.");
        continue;
      }
      const rows = machineLinkedRows(field.value);
      if (!rows || field.status === "accepted" || visual && rows.length === 0) {
        throw new Error("Invalid linked row candidate.");
      }
      for (const cell of rows) {
        if (cell.evidence) assertSourceEvidence(cell.evidence, pages);
        if (visual ? cell.visual_grounding_verified !== false || cell.review_state !== "pending" ||
          cell.status !== "needs_review" || !sourcePageIds.has(cell.visual_page ?? -1) ||
          cell.evidence && (cell.evidence.kind !== "text_match" || cell.evidence.page !== cell.visual_page)
          : cell.visual_page !== undefined || cell.visual_grounding_verified !== undefined ||
            cell.review_state !== undefined || cell.evidence?.kind !== undefined) {
          throw new Error("Invalid linked visual page or review state.");
        }
      }
    } else if (visual) {
      if (field.value === null || !validVisualScalar(field.value, fieldType) ||
        !Array.isArray(field.visual_pages) || field.visual_pages.length < 1 ||
        field.visual_pages.length > sourcePageIds.size ||
        field.visual_pages.some((page: unknown, index: number) => typeof page !== "number" ||
          !Number.isSafeInteger(page) || !sourcePageIds.has(page) ||
          index > 0 && page <= field.visual_pages[index - 1]) ||
        field.evidence && !field.visual_pages.includes(field.evidence.page)) {
        throw new Error("Invalid scalar visual pages or value.");
      }
    }
  }
  return {
    contract_version: 1,
    doc_id: docId,
    document_status: candidate.document_status as ProductAutoCandidate["document_status"],
    proposed_schema: candidate.proposed_schema as ProductAutoCandidate["proposed_schema"],
    extracted_values: candidate.extracted_values as ProductAutoCandidate["extracted_values"],
    measurements: candidate.measurements as ProductAutoCandidate["measurements"],
  };
}

function readResultBytes(runId: string, docId: string): { bytes: Buffer; sha256: string } {
  requireSafeId(docId);
  const bytes = fs.readFileSync(path.join(outputDir(runId), "docs", docId, "result.json"));
  return { bytes, sha256: createHash("sha256").update(bytes).digest("hex") };
}

function parseResultBytes(bytes: Buffer): Record<string, unknown> {
  let result: unknown;
  try {
    result = JSON.parse(bytes.toString("utf8"));
  } catch {
    throw new Error("Invalid extraction artifact.");
  }
  if (!result || typeof result !== "object" || Array.isArray(result)) {
    throw new Error("Invalid extraction artifact.");
  }
  return result as Record<string, unknown>;
}

function readSourcePages(result: Record<string, unknown>): Array<{ page: number; text: string }> {
  if (!Array.isArray(result.pages)) throw new Error("Invalid source pages.");
  const seen = new Set<number>();
  return result.pages.map((value) => {
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid source page.");
    const page = value as Record<string, unknown>;
    if (!Number.isSafeInteger(page.page) || typeof page.page !== "number" || page.page < 1 ||
      seen.has(page.page) || typeof page.text !== "string") throw new Error("Invalid source page.");
    seen.add(page.page);
    return { page: page.page, text: page.text };
  });
}

function readParsedDocument(result: Record<string, unknown>): ProductAutoParsedDocument | undefined {
  const parsed = result.parsed_document;
  if (parsed === undefined) return undefined;
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Invalid native source artifact.");
  const value = parsed as Record<string, unknown>;
  if (value.contract_version !== 2 || typeof value.source_sha256 !== "string" ||
    value.source_sha256 !== result.source_container_sha256 || typeof value.source_format !== "string" ||
    typeof value.parser_id !== "string" || typeof value.parser_version !== "string" ||
    !Array.isArray(value.units) || !Array.isArray(value.tables)) {
    throw new Error("Invalid native source artifact.");
  }
  return parsed as ProductAutoParsedDocument;
}

function readReview(jobId: string, runId: string, docId: string): ProductAutoReview | null {
  return readAuditTrail(jobId, runId, docId).at(-1)?.review_snapshot ?? null;
}

function assertStoredObservedPages(
  review: ProductAutoReview, sourcePages: Array<{ page: number; text: string }>,
  visualRoute: ProductAutoDocumentDetail["visualRoute"],
): void {
  const actualPages = new Set(sourcePages.map((page) => page.page));
  const assertSource = (record: Record<string, unknown>) => {
    if (!("human_source_page" in record)) return;
    const observed = record.human_source_page;
    if ("evidence" in record || visualRoute !== "visual" || !sealedVisualReview(review) ||
      !hasHumanSourcePageShape(observed) || !actualPages.has(observed.page)) {
      throw new AccessError("The saved reviewer page reference is not bound to this visual source.", 409);
    }
  };
  if (!review.added_fields) return;
  if (!Array.isArray(review.added_fields)) throw new AccessError("Invalid saved added fields.", 409);
  for (const added of review.added_fields) {
    if (!added || typeof added !== "object") throw new AccessError("Invalid saved added field.", 409);
    if (added.type === "array[object]") {
      if (!Array.isArray(added.value)) throw new AccessError("Invalid saved linked cells.", 409);
      for (const cell of added.value) {
        if (!cell || typeof cell !== "object") throw new AccessError("Invalid saved linked cell.", 409);
        assertSource(cell as unknown as Record<string, unknown>);
      }
    } else {
      assertSource(added as unknown as Record<string, unknown>);
    }
  }
}

function effectiveReviewStatus(review: ProductAutoReview | null): "unreviewed" | "pending" | "completed" {
  if (!review) return "unreviewed";
  return review.added_fields?.some((field) => field.type === "array[object]"
    ? !field.value.length || field.value.some((cell) => !hasEvidenceShape(cell.evidence) &&
      !(hasHumanSourcePageShape(cell.human_source_page) && sealedVisualReview(review)))
    : !hasEvidenceShape(field.evidence) &&
      !(hasHumanSourcePageShape(field.human_source_page) && sealedVisualReview(review))) ? "pending" : review.status;
}

function recordedReviewStatus(record: RunRecord, document: RunRecord["documents"][number]):
  "unreviewed" | "pending" | "completed" {
  const trail = readAuditTrail(record.jobId, record.runId, document.docId);
  const review = trail.at(-1)?.review_snapshot ?? null;
  if (!review) return "unreviewed";
  const hashes = trail.flatMap((event) => [event.machine_result_sha256, event.review_snapshot.machine_result_sha256])
    .filter((hash): hash is string => typeof hash === "string" && hash.length > 0);
  const sourceHashes = trail.flatMap((event) => [event.source_container_sha256, event.review_snapshot.source_container_sha256])
    .filter((hash): hash is string => typeof hash === "string" && hash.length > 0);
  if (!document.machineResultSha256 || !hashes.length || !sourceHashes.length) return "pending";
  try {
    const resultHash = sha256File(path.join(outputDir(record.runId), "docs", document.docId, "result.json"));
    const sourceHash = verifiedReviewSourceHash(record.jobId, record.runId, document.fileId);
    if (resultHash !== document.machineResultSha256 || hashes.some((hash) => hash !== resultHash) ||
      sourceHashes.some((hash) => hash !== sourceHash)) return "pending";
  } catch {
    return "pending";
  }
  return effectiveReviewStatus(review);
}

function readAuditTrail(jobId: string, runId: string, docId: string): ProductAutoAuditEvent[] {
  const directory = auditDir(jobId, runId, docId);
  if (!fs.existsSync(directory)) return [];
  const events = fs.readdirSync(directory).filter((name) => /^\d{12}\.json$|^\d{13}_[a-f0-9]{32}\.json$/.test(name))
    .map((name) => {
      const event = parseJsonObject(path.join(directory, name)) as unknown as ProductAutoAuditEvent;
      if (/^\d{12}\.json$/.test(name) && Number(name.slice(0, 12)) !== event.revision) {
        throw new Error("Review audit filename and revision differ.");
      }
      return event;
    })
    .sort((left, right) => left.revision - right.revision);
  const seenIds = new Set<string>();
  for (let index = 0; index < events.length; index += 1) {
    const event = events[index];
    const previous = events[index - 1];
    if (event.revision !== index + 1 || event.review_snapshot?.revision !== event.revision ||
      event.review_snapshot.audit_event_id !== event.audit_event_id ||
      event.review_snapshot.job_id !== jobId || event.review_snapshot.run_id !== runId ||
      event.review_snapshot.doc_id !== docId || seenIds.has(event.audit_event_id) ||
      event.previous_event_id !== undefined && event.previous_event_id !== (previous?.audit_event_id ?? null)) {
      throw new Error("Review audit history is out of order.");
    }
    seenIds.add(event.audit_event_id);
  }
  return events;
}

function reviewAuditDigest(jobId: string, runId: string, docId: string): string {
  const directory = auditDir(jobId, runId, docId);
  const files = fs.readdirSync(directory).filter((name) => /^\d{12}\.json$|^\d{13}_[a-f0-9]{32}\.json$/.test(name)).sort();
  return createHash("sha256").update(JSON.stringify(files.map((name) =>
    [name, sha256File(path.join(directory, name))]))).digest("hex");
}

function publishAuditEvent(directory: string, event: ProductAutoAuditEvent): void {
  fs.mkdirSync(directory, { recursive: true });
  const target = path.join(directory, `${String(event.revision).padStart(12, "0")}.json`);
  const temporary = path.join(directory, `.${event.audit_event_id}.tmp`);
  try {
    fs.writeFileSync(temporary, JSON.stringify(event, null, 2), { encoding: "utf8", flag: "wx" });
    // A hard link publishes a fully written event only when this revision is free.
    // It also prevents rename-overwrite behavior on platforms that allow it.
    fs.linkSync(temporary, target);
  } catch (error) {
    if (error && typeof error === "object" && "code" in error && error.code === "EEXIST") {
      throw new AccessError("Review changed since you opened it. Reload before saving.", 409);
    }
    throw error;
  } finally {
    if (fs.existsSync(temporary)) fs.unlinkSync(temporary);
  }
}

function validatedDocuments(record: RunRecord, targetDocId?: string): RunRecord["documents"] {
  const runDir = outputDir(record.runId);
  const marker = parseJsonObject(path.join(runDir, "run.json"));
  if (marker.contract_version !== 1 || marker.run_id !== record.runId) {
    throw new Error("Run completion marker does not match this run.");
  }
  if (!matchesRecipeReceipt(marker.approved_recipe, record) ||
    !matchesConfirmedSchemaReceipt(marker.confirmed_schema, record) ||
    record.approvedRecipe && getJobOrThrow(record.jobId).ownerUserId !== record.approvedRecipe.ownerUserId ||
    record.confirmedBrief && (getJobOrThrow(record.jobId).ownerUserId !== record.confirmedBrief.ownerUserId ||
      record.confirmedBrief.jobId !== record.jobId)) {
    throw new Error("Run schema receipt does not match its owner-scoped selection.");
  }
  const receipts = parseJsonLines(path.join(runDir, "manifest.jsonl"));
  if (receipts.length !== marker.doc_count) throw new Error("Incomplete extraction manifest.");
  const byStoredName = new Map(record.selectedFiles.map((file) => [file.storedName, file]));
  const seen = new Set<string>();
  return receipts.flatMap((receipt): RunRecord["documents"] => {
    const docId = receipt.doc_id;
    const sourceFile = receipt.source_file;
    if (typeof docId !== "string" || typeof sourceFile !== "string") throw new Error("Invalid document receipt.");
    requireSafeId(docId);
    const selected = byStoredName.get(sourceFile);
    if (!selected || receipt.run_id !== record.runId || receipt.source_container_sha256 !== selected.sha256 || seen.has(docId)) {
      throw new Error("Document receipt does not match the selected source.");
    }
    seen.add(docId);
    if (typeof receipt.result_sha256 !== "string" || !/^[a-f0-9]{64}$/.test(receipt.result_sha256)) {
      throw new Error("Machine result receipt is missing or invalid.");
    }
    if (!matchesRecipeReceipt(receipt.approved_recipe, record) ||
      !matchesConfirmedSchemaReceipt(receipt.confirmed_schema, record)) {
      throw new Error("Document schema receipt differs from the selected schema.");
    }
    if (targetDocId && docId !== targetDocId) return [];
    const { bytes, sha256: machineResultHash } = readResultBytes(record.runId, docId);
    if (receipt.result_sha256 !== machineResultHash) {
      throw new Error("Machine result and extraction receipt differ.");
    }
    const result = parseResultBytes(bytes);
    if (!matchesRecipeReceipt(result.approved_recipe, record) ||
      !matchesConfirmedSchemaReceipt(result.confirmed_schema, record)) {
      throw new Error("Machine result schema differs from the selected schema.");
    }
    const candidate = candidateFromArtifact(result.candidate, docId, result.pages);
    if (candidate.document_status !== receipt.document_status) throw new Error("Candidate and receipt status differ.");
    const review = readReview(record.jobId, record.runId, docId);
    return [{
      docId,
      fileId: selected.fileId,
      fileName: selected.fileName,
      status: candidate.document_status,
      fieldCount: candidate.proposed_schema.length,
      acceptedCount: candidate.extracted_values.filter((value) => value.status === "accepted").length,
      reviewStatus: effectiveReviewStatus(review),
      machineResultSha256: machineResultHash,
    }];
  });
}

function finishRun(jobId: string, runId: string, exitCode: number | null, leaseExpiredFailure = false,
  verifiedDocuments?: RunRecord["documents"]): void {
  const record = readRunRecord(jobId, runId);
  if (!["queued", "running"].includes(record.status)) return;
  record.endedAt = new Date().toISOString();
  try {
    if (exitCode !== 0) throw new Error("The extraction process failed. Check server logs.");
    record.documents = verifiedDocuments ?? validatedDocuments(record);
    record.status = "success";
  } catch {
    record.status = "failed";
    record.error = leaseExpiredFailure
      ? "The extraction owner stopped renewing its lease. Start a new run to retry."
      : exitCode !== 0
      ? "The extraction process failed. Check server logs."
      : "Extraction finished, but its output could not be verified.";
  }
  if (publishTerminalRecord(record) && !leaseExpiredFailure) {
    fs.rmSync(stagedInputDir(runId), { recursive: true, force: true });
    if (fs.existsSync(stagedRecipeFile(runId))) fs.unlinkSync(stagedRecipeFile(runId));
    if (fs.existsSync(stagedSchemaFile(runId))) fs.unlinkSync(stagedSchemaFile(runId));
  }
  stopHeartbeat(runId);
}

function runForDisplay(jobId: string, runId: string): RunRecord {
  const record = readRunRecord(jobId, runId);
  if (!record.queueDispatch && record.status === "running" && fs.existsSync(path.join(outputDir(runId), "run.json"))) {
    return { ...record, status: "success", documents: validatedDocuments(record) };
  }
  return record;
}

/** Reconcile completed or expired runs outside request reads. Safe to invoke in multiple frontend processes. */
export function recoverProductAutoRuns(jobId?: string): { recovered: number; examined: number } {
  const root = path.join(storageRoot(), "frontend", "auto_runs");
  if (!fs.existsSync(root)) return { recovered: 0, examined: 0 };
  const jobIds = jobId ? [jobId] : fs.readdirSync(root).filter((name) => /^[a-f0-9]{32}$/i.test(name));
  let recovered = 0;
  let examined = 0;
  for (const currentJobId of jobIds) {
    const directory = path.dirname(runFile(currentJobId, "placeholder"));
    if (!fs.existsSync(directory)) continue;
    for (const name of fs.readdirSync(directory).filter((file) => /^auto_[a-f0-9]{32}\.json$/.test(file))) {
      const runId = name.slice(0, -5);
      examined += 1;
      try {
        const record = readRunRecord(currentJobId, runId);
        if (record.queueDispatch || record.status !== "running") continue;
        const expired = leaseExpired(record, Date.now());
        if (fs.existsSync(path.join(outputDir(runId), "run.json"))) {
          let documents: RunRecord["documents"];
          try {
            documents = validatedDocuments(record);
          } catch {
            if (expired) finishRun(currentJobId, runId, 0, true);
            else continue;
            if (readRunRecord(currentJobId, runId).status !== "running") recovered += 1;
            continue;
          }
          finishRun(currentJobId, runId, 0, false, documents);
        } else if (expired) {
          finishRun(currentJobId, runId, null, true);
        } else {
          continue;
        }
        if (readRunRecord(currentJobId, runId).status !== "running") recovered += 1;
      } catch (error) {
        console.error("Product run recovery failed:", error);
      }
    }
  }
  return { recovered, examined };
}

let recoveryTimer: NodeJS.Timeout | null = null;

/** Start one process-local scan; GET handlers only read run state. */
export function startProductAutoRecoveryLoop(): void {
  if (recoveryTimer) return;
  recoveryTimer = setInterval(() => {
    try { recoverProductAutoRuns(); }
    catch (error) { console.error("Product run recovery scan failed:", error); }
  }, RECOVERY_INTERVAL_MS);
  recoveryTimer.unref();
}

function publicRun(record: RunRecord): ProductAutoRun {
  return {
    runId: record.runId,
    ...(record.idempotencyKey ? { idempotencyKey: record.idempotencyKey } : {}),
    status: record.status,
    createdAt: record.createdAt,
    endedAt: record.endedAt,
    selectedCount: record.selectedFiles.length,
    ...(record.approvedRecipe ? { approvedRecipe: {
      recipeId: record.approvedRecipe.recipeId, revision: record.approvedRecipe.revision,
      familyName: record.approvedRecipe.familyName, snapshotSha256: record.approvedRecipe.snapshotSha256,
    } } : {}),
    ...(record.confirmedBrief ? { confirmedBrief: {
      briefId: record.confirmedBrief.briefId, revision: record.confirmedBrief.revision,
      payloadSha256: record.confirmedBrief.payloadSha256,
      snapshotSha256: record.confirmedBrief.snapshotSha256,
      phase: record.confirmedBrief.phase,
      ...(record.confirmedBrief.previewRunId ? { previewRunId: record.confirmedBrief.previewRunId } : {}),
    } } : {}),
    documents: record.documents.map((document) => ({
      docId: document.docId, fileId: document.fileId, fileName: document.fileName,
      status: document.status, fieldCount: document.fieldCount, acceptedCount: document.acceptedCount,
      reviewStatus: recordedReviewStatus(record, document),
    })),
    error: record.error,
  };
}

export function productAutoAvailability(): { available: boolean; modelConfigured: boolean } {
  const available = loadRunnerConfig().commands.some((command) => command.id === "idpo_process_auto");
  const model = process.env.IDPO_AUTO_MODEL?.trim();
  const baseUrl = process.env.IDPO_AUTO_API_BASE_URL?.trim();
  let modelConfigured = false;
  if (model && baseUrl) {
    try {
      configuredModelBudget();
      modelConfigured = !modelEndpointRequiresKey(baseUrl) || Boolean(process.env.ICORE_API_KEY?.trim());
    } catch {
      modelConfigured = false;
    }
  }
  return { available, modelConfigured };
}

function modelEndpointRequiresKey(baseUrl: string): boolean {
  let url: URL;
  try {
    url = new URL(baseUrl);
  } catch {
    throw new AccessError("The server model URL is invalid.", 503);
  }
  if (url.username || url.password) throw new AccessError("The server model URL must not contain credentials.", 503);
  if (url.protocol === "http:" && LOOPBACK_HOSTS.has(url.hostname)) return false;
  if (url.protocol === "https:") return true;
  throw new AccessError("The server model URL must use HTTPS or loopback HTTP.", 503);
}

export function listProductAutoRuns(jobId: string): ProductAutoRun[] {
  const directory = path.dirname(runFile(jobId, "placeholder"));
  if (!fs.existsSync(directory)) return [];
  return fs.readdirSync(directory).filter((name) => /^auto_[a-f0-9]{32}\.json$/.test(name))
    .map((name) => runForDisplay(jobId, name.slice(0, -5)))
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt))
    .map(publicRun);
}

export function getProductAutoRun(jobId: string, runId: string): ProductAutoRun {
  return publicRun(runForDisplay(jobId, runId));
}

function requireReviewedPreview(jobId: string, previewRunId: string, brief: ProductAutoBriefRevision): void {
  requireSafeId(previewRunId);
  const preview = readRunRecord(jobId, previewRunId);
  const selected = preview.confirmedBrief;
  if (preview.status !== "success" || !selected || selected.phase !== "preview" ||
    selected.briefId !== brief.brief_id || selected.revision !== brief.revision ||
    selected.auditEventId !== brief.audit_event_id || selected.payloadSha256 !== brief.payload_sha256 ||
    selected.ownerUserId !== brief.owner_user_id || selected.jobId !== jobId) {
    throw new AccessError("Review a preview from the current confirmed schema before applying it to the batch.", 409);
  }
  const samples = new Map(brief.sample_sources.map((item) => [item.file_id, item.source_sha256]));
  if (preview.selectedFiles.length !== samples.size || preview.selectedFiles.some((file) =>
    samples.get(file.fileId) !== file.sha256)) {
    throw new AccessError("The preview source set differs from the confirmed samples.", 409);
  }
  let documents: RunRecord["documents"];
  try { documents = validatedDocuments(preview); }
  catch { throw new AccessError("Preview extraction artifacts changed. Run a new preview.", 409); }
  if (!documents.length || documents.some((document) => document.status !== "needs_review" ||
    recordedReviewStatus(preview, document) !== "completed") ||
    new Set(documents.map((document) => document.fileId)).size !== samples.size) {
    throw new AccessError("Complete source-linked review of every preview document before applying the batch.", 409);
  }
}

function runRequestPayloadSha256(selectedFileIds: string[],
  approvedRecipeSelection?: { recipeId: string; expectedRevision: number },
  confirmedBriefSelection?: { expectedRevision: number; payloadSha256: string;
    phase: "preview" | "batch"; previewRunId?: string }): string {
  return createHash("sha256").update(JSON.stringify({ selectedFileIds,
    approvedRecipe: approvedRecipeSelection
      ? { recipeId: approvedRecipeSelection.recipeId, expectedRevision: approvedRecipeSelection.expectedRevision } : null,
    confirmedBrief: confirmedBriefSelection
      ? { expectedRevision: confirmedBriefSelection.expectedRevision,
        payloadSha256: confirmedBriefSelection.payloadSha256, phase: confirmedBriefSelection.phase,
        previewRunId: confirmedBriefSelection.previewRunId ?? null } : null,
  })).digest("hex");
}

async function replayProductAutoRunRequest(jobId: string, selectedFileIds: string[],
  job: ReturnType<typeof getJobOrThrow>, key: string, actorUserId: string, payloadSha256: string,
  approvedRecipeSelection?: { recipeId: string; expectedRevision: number },
  confirmedBriefSelection?: { expectedRevision: number; payloadSha256: string;
    phase: "preview" | "batch"; previewRunId?: string }): Promise<ProductAutoRun | null> {
  const receipt = readProductAutoRunRequestReceipt(storageRoot(), jobId, key);
  if (!receipt) return null;
  if (receipt.actorUserId !== actorUserId || receipt.jobOwnerUserId !== (job.ownerUserId ?? null)) {
    throw new AccessError("Extraction request not found.", 404);
  }
  if (receipt.payloadSha256 !== payloadSha256) {
    throw new AccessError("This extraction request key belongs to different options.", 409);
  }
  const brief = confirmedBriefSelection && requireCurrentProductAutoBrief(jobId,
    confirmedBriefSelection.expectedRevision, confirmedBriefSelection.payloadSha256);
  if (brief && brief.state !== "confirmed") {
    throw new AccessError("The confirmed schema changed since this extraction request.", 409);
  }
  const recipe = approvedRecipeSelection
    ? (await import("@/server/product-auto-recipes")).selectApprovedProductAutoRecipe(
      jobId, approvedRecipeSelection.recipeId, approvedRecipeSelection.expectedRevision)
    : undefined;
  const file = runFile(jobId, receipt.runId);
  if (!fs.existsSync(file)) {
    throw new AccessError("Extraction admission is incomplete or uncertain. Inspect runs before starting a new attempt.", 409);
  }
  const record = readRunRecord(jobId, receipt.runId);
  if (record.idempotencyKey !== key || record.selectedFiles.length !== selectedFileIds.length ||
    record.selectedFiles.some((selected, index) => selected.fileId !== selectedFileIds[index]) ||
    Boolean(record.approvedRecipe) !== Boolean(approvedRecipeSelection) ||
    Boolean(record.confirmedBrief) !== Boolean(confirmedBriefSelection) ||
    recipe && (record.approvedRecipe?.recipeId !== recipe.recipe_id ||
      record.approvedRecipe?.revision !== recipe.revision ||
      record.approvedRecipe?.auditEventId !== recipe.audit_event_id) ||
    brief && (record.confirmedBrief?.revision !== brief.revision ||
      record.confirmedBrief?.payloadSha256 !== brief.payload_sha256 ||
      record.confirmedBrief?.auditEventId !== brief.audit_event_id ||
      record.confirmedBrief?.phase !== confirmedBriefSelection?.phase ||
      record.confirmedBrief?.previewRunId !== confirmedBriefSelection?.previewRunId)) {
    throw new AccessError("The original extraction request receipt no longer matches its run.", 409);
  }
  const config = loadRunnerConfig();
  const sourceDir = path.resolve(config.uploadsDir, `job_${jobId}`);
  if (path.dirname(sourceDir) !== path.resolve(config.uploadsDir)) {
    throw new AccessError("Invalid job upload location.", 409);
  }
  for (const selected of record.selectedFiles) {
    const document = job.documents?.find((item) => item.fileId === selected.fileId);
    const source = path.resolve(sourceDir, selected.storedName);
    if (!document || document.storedName !== selected.storedName || document.fileName !== selected.fileName ||
      path.dirname(source) !== sourceDir || !fs.existsSync(source) || !fs.lstatSync(source).isFile() ||
      sha256File(source) !== selected.sha256) {
      throw new AccessError("An extraction source changed since this request.", 409);
    }
  }
  return publicRun(runForDisplay(jobId, receipt.runId));
}

export async function startProductAutoRun(
  jobId: string, selectedFileIds: string[], admin: boolean,
  approvedRecipeSelection?: { recipeId: string; expectedRevision: number },
  confirmedBriefSelection?: { expectedRevision: number; payloadSha256: string;
    phase: "preview" | "batch"; previewRunId?: string },
  idempotency?: { key: string; actorUserId: string },
): Promise<ProductAutoRun> {
  const config = loadRunnerConfig();
  const job = getJobOrThrow(jobId);
  if (!selectedFileIds.length || new Set(selectedFileIds).size !== selectedFileIds.length) {
    throw new AccessError("Select one or more distinct documents.", 400);
  }
  const model = process.env.IDPO_AUTO_MODEL?.trim();
  if (model && !admin) throw new AccessError("Admin access is required to start model-backed extraction.", 403);
  const requestKey = idempotency?.key;
  if (requestKey !== undefined && (!validProductAutoRunRequestKey(requestKey) ||
    !idempotency?.actorUserId)) {
    throw new AccessError("A valid extraction request key and actor are required.", 400);
  }
  const requestPayloadSha256 = requestKey
    ? runRequestPayloadSha256(selectedFileIds, approvedRecipeSelection, confirmedBriefSelection) : undefined;
  if (requestKey && requestPayloadSha256) {
    const existing = await replayProductAutoRunRequest(jobId, selectedFileIds, job, requestKey,
      idempotency!.actorUserId, requestPayloadSha256, approvedRecipeSelection, confirmedBriefSelection);
    if (existing) return existing;
  }
  if (!productAutoAvailability().available) throw new AccessError("Automatic extraction is unavailable on this deployment.", 503);
  recoverProductAutoRuns(jobId);
  if (listProductAutoRuns(jobId).some((run) => ["queued", "running"].includes(run.status))) {
    throw new AccessError("This job already has an automatic extraction run in progress.", 409);
  }
  const baseUrl = process.env.IDPO_AUTO_API_BASE_URL?.trim();
  if (Boolean(model) !== Boolean(baseUrl)) throw new AccessError("The server model configuration is incomplete.", 503);
  if (baseUrl && modelEndpointRequiresKey(baseUrl) && !process.env.ICORE_API_KEY?.trim()) {
    throw new AccessError("The server model key is missing.", 503);
  }
  const modelBudget = model ? configuredModelBudget() : undefined;
  const extractionProfile = configuredExtractionProfile(Boolean(confirmedBriefSelection));
  if (approvedRecipeSelection && !model) {
    throw new AccessError("An approved recipe requires a configured value extraction model.", 503);
  }
  if (approvedRecipeSelection && confirmedBriefSelection) {
    throw new AccessError("Choose one explicit schema for this run.", 400);
  }
  if (confirmedBriefSelection && !model) {
    throw new AccessError("A confirmed schema requires a configured value extraction model.", 503);
  }
  let recipeSnapshot: Record<string, unknown> | undefined;
  let recipeMeta: RunRecord["approvedRecipe"];
  if (approvedRecipeSelection) {
    const { selectApprovedProductAutoRecipe } = await import("@/server/product-auto-recipes");
    const recipe = selectApprovedProductAutoRecipe(jobId, approvedRecipeSelection.recipeId,
      approvedRecipeSelection.expectedRevision);
    if (recipe.owner_user_id !== job.ownerUserId) {
      throw new AccessError("Recipe owner does not match this job.", 409);
    }
    recipeSnapshot = {
      contract_version: 1, recipe_id: recipe.recipe_id, revision: recipe.revision,
      audit_event_id: recipe.audit_event_id, state: recipe.state,
      owner_user_id: recipe.owner_user_id, family_name: recipe.family_name,
      source_review_digest_sha256: recipe.source_review.source_digest_sha256,
      fields: recipe.fields, row_groups: recipe.row_groups,
    };
    recipeMeta = {
      recipeId: recipe.recipe_id, revision: recipe.revision, auditEventId: recipe.audit_event_id,
      ownerUserId: recipe.owner_user_id, familyName: recipe.family_name,
      snapshotSha256: createHash("sha256").update(JSON.stringify(recipeSnapshot)).digest("hex"),
    };
  }
  let schemaSnapshot: Record<string, unknown> | undefined;
  let schemaMeta: RunRecord["confirmedBrief"];
  if (confirmedBriefSelection) {
    const brief = requireCurrentProductAutoBrief(jobId, confirmedBriefSelection.expectedRevision,
      confirmedBriefSelection.payloadSha256);
    if (brief.state !== "confirmed" || brief.owner_user_id !== job.ownerUserId) {
      throw new AccessError("Confirm the current schema before extraction.", 409);
    }
    const sampleIds = brief.sample_sources.map((item) => item.file_id);
    if (confirmedBriefSelection.phase === "preview") {
      if (confirmedBriefSelection.previewRunId || selectedFileIds.length !== sampleIds.length ||
        selectedFileIds.some((fileId) => !sampleIds.includes(fileId))) {
        throw new AccessError("Preview exactly the confirmed sample files.", 400);
      }
    } else if (confirmedBriefSelection.phase === "batch") {
      if (!confirmedBriefSelection.previewRunId ||
        selectedFileIds.some((fileId) => sampleIds.includes(fileId))) {
        throw new AccessError("Choose remaining files and a reviewed preview.", 400);
      }
      requireReviewedPreview(jobId, confirmedBriefSelection.previewRunId, brief);
    } else {
      throw new AccessError("Invalid confirmed-schema phase.", 400);
    }
    schemaSnapshot = {
      contract_version: 1, brief_id: brief.brief_id, revision: brief.revision,
      audit_event_id: brief.audit_event_id, state: brief.state,
      owner_user_id: brief.owner_user_id, job_id: brief.job_id,
      intent: brief.intent, fields: brief.fields, sample_sources: brief.sample_sources,
      payload_sha256: brief.payload_sha256,
    };
    schemaMeta = {
      briefId: brief.brief_id, revision: brief.revision, auditEventId: brief.audit_event_id,
      ownerUserId: brief.owner_user_id, jobId, payloadSha256: brief.payload_sha256,
      snapshotSha256: createHash("sha256").update(JSON.stringify(schemaSnapshot)).digest("hex"),
      phase: confirmedBriefSelection.phase,
      ...(confirmedBriefSelection.previewRunId ? { previewRunId: confirmedBriefSelection.previewRunId } : {}),
    };
  }
  const documents = selectedFileIds.map((fileId) => job.documents?.find((document) => document.fileId === fileId));
  if (documents.some((document) => !document)) throw new AccessError("A selected document was not found.", 400);
  const runId = `auto_${randomUUID().replace(/-/g, "")}`;
  const inputDir = stagedInputDir(runId);
  const sourceDir = path.resolve(config.uploadsDir, `job_${jobId}`);
  if (path.dirname(sourceDir) !== path.resolve(config.uploadsDir)) throw new AccessError("Invalid job upload location.", 400);
  const selectedFiles: SelectedFile[] = [];
  const queued = process.env.PRODUCT_EXECUTION_MODE === "postgres";
  if (queued && !job.ownerUserId) throw new AccessError("Queued extraction requires a job owner.", 409);
  if (requestKey && requestPayloadSha256) {
    const claimed = claimProductAutoRunRequestReceipt(storageRoot(), jobId, requestKey, {
      contractVersion: 1, jobId, runId, actorUserId: idempotency!.actorUserId,
      jobOwnerUserId: job.ownerUserId ?? null, payloadSha256: requestPayloadSha256,
    });
    if (!claimed) {
      const existing = await replayProductAutoRunRequest(jobId, selectedFileIds, job, requestKey,
        idempotency!.actorUserId, requestPayloadSha256, approvedRecipeSelection, confirmedBriefSelection);
      if (existing) return existing;
      throw new AccessError("Extraction admission is incomplete or uncertain. Inspect runs before retrying.", 409);
    }
  }
  if (fs.existsSync(runFile(jobId, runId))) {
    throw new AccessError("The extraction run identity already exists.", 409);
  }
  fs.mkdirSync(inputDir, { recursive: true });
  try {
    if (recipeSnapshot && recipeMeta) {
      const handle = fs.openSync(stagedRecipeFile(runId), "wx", 0o600);
      try {
        fs.writeFileSync(handle, JSON.stringify(recipeSnapshot), "utf8");
        fs.fsyncSync(handle);
      } finally {
        fs.closeSync(handle);
      }
    }
    if (schemaSnapshot && schemaMeta) {
      const handle = fs.openSync(stagedSchemaFile(runId), "wx", 0o600);
      try {
        fs.writeFileSync(handle, JSON.stringify(schemaSnapshot), "utf8");
        fs.fsyncSync(handle);
      } finally {
        fs.closeSync(handle);
      }
    }
    for (const document of documents) {
      if (!document) continue;
      const source = path.resolve(sourceDir, document.storedName);
      if (path.dirname(source) !== sourceDir || !fs.existsSync(source) || !fs.lstatSync(source).isFile()) {
        throw new AccessError("A selected source document is unavailable.", 400);
      }
      const staged = path.join(inputDir, document.storedName);
      // A hard link lets later source edits change queued input bytes.
      fs.copyFileSync(source, staged, fs.constants.COPYFILE_EXCL);
      selectedFiles.push({ fileId: document.fileId, fileName: document.fileName,
        storedName: document.storedName, sha256: sha256File(staged) });
    }
    let dispatch: PreparedDispatch | undefined;
    let dispatchHash: string | undefined;
    if (queued) {
      dispatch = { version: 3, ownerId: job.ownerUserId!, jobId, runId, extractionProfile,
        commandSha256: commandSha256(),
        inputManifestSha256: inputManifestSha256({ selectedFiles, approvedRecipe: recipeMeta, confirmedBrief: schemaMeta }),
        ...(model && baseUrl ? { model, baseUrl, modelBudget } : {}) };
      const bytes = JSON.stringify(dispatch);
      fs.mkdirSync(path.dirname(dispatchFile(jobId, runId)), { recursive: true });
      const handle = fs.openSync(dispatchFile(jobId, runId), "wx", 0o600);
      try { fs.writeFileSync(handle, bytes, "utf8"); fs.fsyncSync(handle); }
      finally { fs.closeSync(handle); }
      dispatchHash = createHash("sha256").update(bytes).digest("hex");
    }
    const record: RunRecord = {
      runId, jobId, status: queued ? "queued" : "running", createdAt: new Date().toISOString(),
      ...(requestKey ? { idempotencyKey: requestKey } : {}),
      serverInstanceId: instanceId, selectedFiles, documents: [],
      ...(dispatch && dispatchHash ? { queueDispatch: { ownerId: dispatch.ownerId, sha256: dispatchHash } } : {}),
      ...(recipeMeta ? { approvedRecipe: recipeMeta } : {}),
      ...(schemaMeta ? { confirmedBrief: schemaMeta } : {}),
    };
    saveRunRecord(record);
    if (record.queueDispatch) {
      try { await productExecutionQueue().enqueue(dispatchRequest(record)); }
      catch (error) {
        if (error instanceof QueueAdmissionError) {
          finishRun(jobId, runId, null);
          throw new AccessError(error.message, error.statusCode);
        }
        // A lost commit acknowledgement is ambiguous. Keep the durable intent;
        // the worker reconciles the same identity without replaying extraction.
        console.error("Queue admission is awaiting database reconciliation.");
      }
      return publicRun(record);
    }
    writeLease(jobId, runId);
    const command = getCommandConfig("idpo_process_auto");
    const args = command.args.map((arg) => arg.replaceAll("{input_dir}", inputDir).replaceAll("{run_id}", runId));
    appendModelArguments(args, model, baseUrl, modelBudget);
    appendExtractionArguments(args, extractionProfile);
    if (recipeMeta) args.push("--approved-recipe-file", stagedRecipeFile(runId),
      "--approved-recipe-sha256", recipeMeta.snapshotSha256);
    if (schemaMeta) args.push("--confirmed-schema-file", stagedSchemaFile(runId),
      "--confirmed-schema-sha256", schemaMeta.snapshotSha256);
    const child = spawn(command.program, args, {
      cwd: command.cwd,
      env: extractionEnvironment({ ...process.env, ...command.env, IDPO_DATA_DIR: storageRoot() }, extractionProfile),
      windowsHide: true,
      stdio: "ignore",
    });
    startHeartbeat(jobId, runId);
    child.once("error", () => finishRun(jobId, runId, null));
    child.once("close", (code) => finishRun(jobId, runId, code));
    return publicRun(record);
  } catch (error) {
    if (fs.existsSync(runFile(jobId, runId))) finishRun(jobId, runId, null);
    else {
      fs.rmSync(inputDir, { recursive: true, force: true });
      if (fs.existsSync(stagedRecipeFile(runId))) fs.unlinkSync(stagedRecipeFile(runId));
      if (fs.existsSync(stagedSchemaFile(runId))) fs.unlinkSync(stagedSchemaFile(runId));
    }
    throw error;
  }
}

function dispatchRequest(record: RunRecord): ProductDispatch {
  if (!record.queueDispatch) throw new Error("Run has no queue dispatch.");
  return { ownerId: record.queueDispatch.ownerId, jobId: record.jobId, runId: record.runId,
    dispatchSha256: record.queueDispatch.sha256, documentCount: record.selectedFiles.length };
}

function verifiedDispatch(request: ProductDispatch): { record: RunRecord; prepared: PreparedDispatch } {
  const record = readRunRecord(request.jobId, request.runId);
  if (!record.queueDispatch || record.queueDispatch.ownerId !== request.ownerId ||
    record.queueDispatch.sha256 !== request.dispatchSha256 ||
    record.selectedFiles.length !== request.documentCount ||
    getJobOrThrow(request.jobId).ownerUserId !== request.ownerId) {
    throw new Error("Queued extraction ownership or identity changed.");
  }
  const file = dispatchFile(request.jobId, request.runId);
  if (fs.statSync(file).size > 65536 || sha256File(file) !== request.dispatchSha256) {
    throw new Error("Queued extraction profile changed.");
  }
  const prepared = parseJsonObject(file) as unknown as PreparedDispatch;
  if (![1, 2, 3].includes(prepared.version) || prepared.ownerId !== request.ownerId ||
    prepared.jobId !== request.jobId || prepared.runId !== request.runId ||
    prepared.inputManifestSha256 !== inputManifestSha256(record)) {
    throw new Error("Invalid queued extraction profile.");
  }
  if (prepared.version === 1 ? prepared.modelBudget !== undefined :
    (prepared.version === 2 || prepared.model ?
      (!prepared.model || !prepared.baseUrl || !validModelBudget(prepared.modelBudget)) : prepared.modelBudget !== undefined)) {
    throw new Error("Invalid queued model budget.");
  }
  if (prepared.version === 3 ? !validExtractionProfile(prepared.extractionProfile) : prepared.extractionProfile !== undefined) {
    throw new Error("Invalid queued extraction profile.");
  }
  if ((prepared.extractionProfile?.responseFormat === "strict_confirmed_values_v1" ||
      prepared.extractionProfile?.longDocument === "bounded_text_segments_v1" ||
      (prepared.extractionProfile?.visualDocument !== undefined && prepared.extractionProfile.visualDocument !== "disabled")) &&
      (!record.confirmedBrief || !prepared.model)) throw new Error("Selected extraction profile requires a confirmed schema and model.");
  return { record, prepared };
}

/** Called only by the independently supervised worker after PostgreSQL claims the attempt. */
export async function executePreparedProductAutoRun(request: ProductDispatch, signal: AbortSignal): Promise<void> {
  const { record, prepared } = verifiedDispatch(request);
  if (record.status !== "queued" || signal.aborted) throw new Error("Queued extraction is no longer startable.");
  if (prepared.commandSha256 !== commandSha256()) throw new Error("Worker configuration changed since admission.");
  if (Boolean(prepared.model) !== Boolean(prepared.baseUrl)) throw new Error("Invalid queued model profile.");
  if (prepared.baseUrl && modelEndpointRequiresKey(prepared.baseUrl) && !process.env.ICORE_API_KEY?.trim()) {
    throw new Error("The queued provider credential is unavailable.");
  }
  const inputDir = stagedInputDir(request.runId);
  const expectedNames = new Set(record.selectedFiles.map((file) => file.storedName));
  const actualNames = fs.readdirSync(inputDir);
  if (actualNames.length !== expectedNames.size || actualNames.some((name) => !expectedNames.has(name))) {
    throw new Error("Queued input contains files outside the selected manifest.");
  }
  for (const file of record.selectedFiles) {
    const target = path.resolve(inputDir, file.storedName);
    if (path.dirname(target) !== inputDir || !fs.lstatSync(target).isFile() || sha256File(target) !== file.sha256) {
      throw new Error("Queued source bytes changed.");
    }
  }
  for (const [file, hash] of [
    [stagedRecipeFile(request.runId), record.approvedRecipe?.snapshotSha256],
    [stagedSchemaFile(request.runId), record.confirmedBrief?.snapshotSha256],
  ]) {
    if (hash && sha256File(file!) !== hash) throw new Error("Queued schema bytes changed.");
  }
  const command = getCommandConfig("idpo_process_auto");
  const args = command.args.map((arg) => arg.replaceAll("{input_dir}", inputDir).replaceAll("{run_id}", request.runId));
  appendModelArguments(args, prepared.model, prepared.baseUrl, prepared.modelBudget);
  appendExtractionArguments(args, prepared.extractionProfile);
  if (record.approvedRecipe) args.push("--approved-recipe-file", stagedRecipeFile(request.runId),
    "--approved-recipe-sha256", record.approvedRecipe.snapshotSha256);
  if (record.confirmedBrief) args.push("--confirmed-schema-file", stagedSchemaFile(request.runId),
    "--confirmed-schema-sha256", record.confirmedBrief.snapshotSha256);
  record.status = "running";
  record.serverInstanceId = instanceId;
  saveRunRecord(record);
  writeLease(request.jobId, request.runId);
  startHeartbeat(request.jobId, request.runId);
  await new Promise<void>((resolve, reject) => {
    const child = spawn(command.program, args, { cwd: command.cwd,
      env: extractionEnvironment({ ...process.env, ...command.env, IDPO_DATA_DIR: storageRoot() }, prepared.extractionProfile),
      windowsHide: true, stdio: "ignore" });
    const abort = () => {
      // A killed attempt is terminal. Its external calls may have completed.
      if (child.exitCode === null && child.pid) {
        if (process.platform === "win32") {
          const killer = spawn("taskkill.exe", ["/PID", String(child.pid), "/T", "/F"],
            { windowsHide: true, stdio: "ignore" });
          killer.on("error", () => child.kill());
        } else child.kill("SIGTERM");
      }
    };
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
    child.once("error", () => {
      signal.removeEventListener("abort", abort);
      stopHeartbeat(request.runId);
      reject(new Error("Extraction process could not start."));
    });
    child.once("close", (code) => {
      signal.removeEventListener("abort", abort);
      stopHeartbeat(request.runId);
      if (signal.aborted) { reject(new Error("Extraction attempt interrupted.")); return; }
      try {
        finishRun(request.jobId, request.runId, code);
        if (readRunRecord(request.jobId, request.runId).status !== "success") throw new Error("Extraction output not verified.");
        resolve();
      } catch { reject(new Error("Extraction output not verified.")); }
    });
  });
}

export function failQueuedProductAutoRun(request: ProductDispatch): void {
  const record = readRunRecord(request.jobId, request.runId);
  if (!record.queueDispatch || record.queueDispatch.ownerId !== request.ownerId ||
    record.queueDispatch.sha256 !== request.dispatchSha256) throw new Error("Invalid queue failure identity.");
  if (["success", "failed"].includes(record.status)) return;
  record.status = "failed";
  record.endedAt = new Date().toISOString();
  record.error = "The extraction worker stopped or its outcome is uncertain. No automatic retry was made.";
  publishTerminalRecord(record);
  stopHeartbeat(request.runId);
}

/** Recover a lost admission acknowledgement using the same durable run identity. */
export async function recoverQueuedProductAutoAdmissions(): Promise<number> {
  const root = path.join(storageRoot(), "frontend", "auto_runs");
  if (!fs.existsSync(root)) return 0;
  let recovered = 0;
  for (const jobId of fs.readdirSync(root).filter((name) => /^[a-f0-9]{32}$/.test(name))) {
    for (const name of fs.readdirSync(path.join(root, jobId)).filter((item) => /^auto_[a-f0-9]{32}\.json$/.test(item))) {
      let record: RunRecord;
      let request: ProductDispatch;
      try {
        record = readRunRecord(jobId, name.slice(0, -5));
        if (!["queued", "running"].includes(record.status) || !record.queueDispatch) continue;
        request = dispatchRequest(record);
      }
      catch { console.error("Skipped a malformed extraction record during admission recovery."); continue; }
      const admitted = await productExecutionQueue().get(request.ownerId, request.runId);
      if (admitted?.status === "failed") { failQueuedProductAutoRun(request); continue; }
      if (record.status !== "queued" || admitted) continue;
      try { verifiedDispatch(request); }
      catch { failQueuedProductAutoRun(request); continue; }
      try {
        await productExecutionQueue().enqueue(request);
        recovered += 1;
      } catch (error) {
        if (error instanceof QueueAdmissionError) failQueuedProductAutoRun(request);
        else throw error;
      }
    }
  }
  return recovered;
}

function loadProductAutoDocument(jobId: string, runId: string, docId: string, sealedRecord?: RunRecord): {
  detail: ProductAutoDocumentDetail; machineResultHash: string; sourceHash?: string;
} {
  const record = sealedRecord ?? readRunRecord(jobId, runId);
  const runningWithOutput = record.status === "running" && fs.existsSync(path.join(outputDir(runId), "run.json"));
  const documents = runningWithOutput ? validatedDocuments(record, docId) : record.documents;
  const document = documents.find((item) => item.docId === docId);
  if (!(record.status === "success" || runningWithOutput) || !document) {
    throw new AccessError("Document result not found.", 404);
  }
  const { bytes, sha256: machineResultHash } = readResultBytes(runId, docId);
  if (document.machineResultSha256 && document.machineResultSha256 !== machineResultHash) {
    throw new AccessError("The machine result no longer matches the completed run receipt.", 409);
  }
  const result = parseResultBytes(bytes);
  const candidate = candidateFromArtifact(result.candidate, docId, result.pages);
  const sourcePages = readSourcePages(result);
  let visualRoute: ProductAutoDocumentDetail["visualRoute"];
  if (result.visual_document !== undefined) {
    if (!result.visual_document || typeof result.visual_document !== "object" ||
      Array.isArray(result.visual_document) ||
      !["visual", "text", "not_executed"].includes(String((result.visual_document as Record<string, unknown>).route))) {
      throw new Error("Invalid visual route receipt.");
    }
    visualRoute = (result.visual_document as { route: ProductAutoDocumentDetail["visualRoute"] }).route;
  }
  const parsedDocument = readParsedDocument(result);
  const auditTrail = readAuditTrail(jobId, runId, docId);
  for (const event of auditTrail) assertStoredObservedPages(event.review_snapshot, sourcePages, visualRoute);
  const review = auditTrail.at(-1)?.review_snapshot ?? null;
  const receipts = auditTrail.flatMap((event) => [event, event.review_snapshot]);
  if (review && (!document.machineResultSha256 ||
    !receipts.some((receipt) => receipt.machine_result_sha256))) {
    throw new AccessError("This review predates sealed extraction artifacts. Start a new run.", 409);
  }
  if (receipts.some((receipt) => receipt.machine_result_sha256 &&
    receipt.machine_result_sha256 !== machineResultHash)) {
    throw new AccessError("The machine result no longer matches its audit receipt.", 409);
  }
  let sourceHash: string | undefined;
  if (receipts.some((receipt) => receipt.source_container_sha256 || receipt.source_pages_sha256)) {
    sourceHash = verifiedReviewSourceHash(jobId, runId, document.fileId, record.selectedFiles);
    if (receipts.some((receipt) => receipt.source_container_sha256 && receipt.source_container_sha256 !== sourceHash)) {
      throw new AccessError("The reviewed source no longer matches its audit receipt.", 409);
    }
    const sourcePagesHash = createHash("sha256").update(JSON.stringify(sourcePages)).digest("hex");
    if (receipts.some((receipt) => receipt.source_pages_sha256 && receipt.source_pages_sha256 !== sourcePagesHash)) {
      throw new AccessError("The reviewed OCR text no longer matches its audit receipt.", 409);
    }
  }
  return {
    machineResultHash,
    sourceHash,
    detail: {
      runId, fileId: document.fileId, fileName: document.fileName,
      candidate, sourcePages, ...(visualRoute ? { visualRoute } : {}),
      ...(parsedDocument ? { parsedDocument } : {}), review, auditTrail,
      correctedResult: deriveProductAutoCorrectedResult(candidate, review, visualRoute),
    },
  };
}

export function getProductAutoDocument(jobId: string, runId: string, docId: string): ProductAutoDocumentDetail {
  return loadProductAutoDocument(jobId, runId, docId).detail;
}

export function getProductAutoReviewedExport(jobId: string, runId: string, docId: string): ProductAutoReviewedExport {
  return reviewedExportFromRecord(readRunRecord(jobId, runId), docId);
}

function reviewedExportFromRecord(record: RunRecord, docId: string): ProductAutoReviewedExport {
  const { jobId, runId } = record;
  const { detail, machineResultHash, sourceHash: verifiedSourceHash } = loadProductAutoDocument(jobId, runId, docId, record);
  const review = detail.review;
  if (!review || detail.correctedResult.review_status !== "completed" ||
    detail.correctedResult.fields.some((field) => field.status === "needs_review")) {
    throw new AccessError("Complete the document review before exporting its result.", 409);
  }
  const sourceHash = verifiedSourceHash ?? verifiedReviewSourceHash(jobId, runId, detail.fileId, record.selectedFiles);
  const sourcePagesHash = createHash("sha256").update(JSON.stringify(detail.sourcePages)).digest("hex");
  if (review.source_container_sha256 !== sourceHash || review.source_pages_sha256 !== sourcePagesHash ||
    review.machine_result_sha256 !== machineResultHash) {
    throw new AccessError("The review is not bound to the current source and extraction result.", 409);
  }
  return {
    contract_version: 1, job_id: jobId, run_id: runId,
    document: { doc_id: docId, file_id: detail.fileId, file_name: detail.fileName,
      source_sha256: sourceHash, machine_result_sha256: machineResultHash },
    review: { revision: review.revision, audit_event_id: review.audit_event_id,
      reviewer_user_id: review.reviewer_user_id, updated_at: review.updated_at },
    result: detail.correctedResult,
  };
}

export function getProductAutoReviewedBatchExport(jobId: string, runId: string): Uint8Array[] {
  const record = readRunRecord(jobId, runId);
  if (record.status !== "success") throw new AccessError("Complete the run before exporting its reviewed batch.", 409);
  const selected = record.selectedFiles;
  if (!selected.length || selected.length > MAX_REVIEWED_BATCH_DOCUMENTS) {
    throw new AccessError(`A reviewed batch must contain 1–${MAX_REVIEWED_BATCH_DOCUMENTS} documents.`, 413);
  }
  const runRecordPath = fs.existsSync(terminalFile(jobId, runId)) ? terminalFile(jobId, runId) : runFile(jobId, runId);
  const markerPath = path.join(outputDir(runId), "run.json");
  const manifestPath = path.join(outputDir(runId), "manifest.jsonl");
  let documents: RunRecord["documents"];
  let artifactHashes: string[];
  try {
    artifactHashes = [runRecordPath, markerPath, manifestPath].map(sha256File);
    documents = validatedDocuments(record);
  } catch {
    throw new AccessError(`Reviewed batch blocked: ${selected.length} selected, ${selected.length} unverifiable run artifacts.`, 409);
  }

  const selectedIds = new Set(selected.map((file) => file.fileId));
  const selectedStoredNames = new Set(selected.map((file) => file.storedName));
  const byFileId = new Map(documents.map((document) => [document.fileId, document]));
  const sealedByDocId = new Map(record.documents.map((document) => [document.docId, document]));
  if (selectedIds.size !== selected.length || selectedStoredNames.size !== selected.length ||
    byFileId.size !== documents.length || documents.length !== selected.length ||
    sealedByDocId.size !== record.documents.length || record.documents.length !== selected.length ||
    documents.some((document) => !selectedIds.has(document.fileId) ||
      sealedByDocId.get(document.docId)?.fileId !== document.fileId ||
      sealedByDocId.get(document.docId)?.machineResultSha256 !== document.machineResultSha256)) {
    throw new AccessError(`Reviewed batch blocked: ${selected.length} selected, ${selected.length} missing or inconsistent run receipts.`, 409);
  }

  const encoder = new TextEncoder();
  const lines: Uint8Array[] = [];
  const reviewSnapshots: Array<{ docId: string; revision: number; auditEventId: string; auditDigest: string;
    machineResultSha256: string }> = [];
  const counts = { unreviewed: 0, failed: 0, missing: 0, stale: 0 };
  let byteCount = 0;
  for (const file of selected) {
    const document = byFileId.get(file.fileId);
    if (!document) { counts.missing += 1; continue; }
    if (document.status === "failed" || document.status === "unsupported") { counts.failed += 1; continue; }
    if (document.reviewStatus !== "completed") { counts.unreviewed += 1; continue; }
    try {
      const exported = reviewedExportFromRecord(record, document.docId);
      if (exported.document.file_id !== file.fileId || exported.document.source_sha256 !== file.sha256 ||
        exported.document.machine_result_sha256 !== document.machineResultSha256) {
        counts.stale += 1;
        continue;
      }
      const line = encoder.encode(`${JSON.stringify(exported)}\n`);
      byteCount += line.byteLength;
      if (byteCount > MAX_REVIEWED_BATCH_BYTES) {
        throw new AccessError("Reviewed batch exceeds the 64 MiB download limit.", 413);
      }
      const latestReview = readReview(jobId, runId, document.docId);
      if (latestReview?.revision !== exported.review.revision ||
        latestReview.audit_event_id !== exported.review.audit_event_id) {
        throw new AccessError("Review changed while the batch was being assembled.", 409);
      }
      const auditDigest = reviewAuditDigest(jobId, runId, document.docId);
      lines.push(line);
      reviewSnapshots.push({ docId: document.docId, revision: exported.review.revision,
        auditEventId: exported.review.audit_event_id,
        auditDigest,
        machineResultSha256: exported.document.machine_result_sha256 });
    } catch (error) {
      if (error instanceof AccessError && error.statusCode === 413) throw error;
      counts.stale += 1;
    }
  }
  if (Object.values(counts).some((count) => count > 0) || lines.length !== selected.length) {
    throw new AccessError(`Reviewed batch blocked: ${selected.length} selected, ${lines.length} reviewed, ` +
      `${counts.unreviewed} unreviewed, ${counts.failed} failed or unsupported, ` +
      `${counts.missing} missing, ${counts.stale} stale or unverifiable.`, 409);
  }
  try {
    if ([runRecordPath, markerPath, manifestPath].some((filePath, index) =>
      sha256File(filePath) !== artifactHashes[index]) ||
      reviewSnapshots.some((snapshot) => {
        const review = readReview(jobId, runId, snapshot.docId);
        return !review || review.revision !== snapshot.revision ||
          review.audit_event_id !== snapshot.auditEventId ||
          reviewAuditDigest(jobId, runId, snapshot.docId) !== snapshot.auditDigest ||
          sha256File(path.join(outputDir(runId), "docs", snapshot.docId, "result.json")) !==
            snapshot.machineResultSha256;
      }) || selected.some((file) => verifiedReviewSourceHash(jobId, runId, file.fileId, selected) !== file.sha256)) {
      throw new Error("Batch changed while being assembled.");
    }
  } catch {
    throw new AccessError(`Reviewed batch blocked: ${selected.length} selected, ${selected.length} stale snapshots. Retry after reviewing the run.`, 409);
  }
  return lines;
}

export function deriveProductAutoCorrectedResult(
  candidate: ProductAutoCandidate, review: ProductAutoReview | null,
  visualRoute?: ProductAutoDocumentDetail["visualRoute"],
): ProductAutoCorrectedResult {
  const machineValues = new Map(candidate.extracted_values.map((item) => [item.field_id, item]));
  const decisions = new Map(review?.fields.map((item) => [item.field_id, item]) ?? []);
  const removed_field_ids: string[] = [];
  const fields: ProductAutoCorrectedResult["fields"] = [];
  let unsafeLinkedReview = false;
  for (const schema of candidate.proposed_schema) {
    const decision = decisions.get(schema.field_id);
    if (decision?.decision === "not_present" || decision?.decision === "remove") {
      removed_field_ids.push(schema.field_id);
      continue;
    }
    const machine = machineValues.get(schema.field_id);
    const identity = { field_id: schema.field_id, type: schema.type, ...(schema.group ? { group: schema.group } : {}) };
    if (decision?.decision === "corrected") {
      let value: string | number | boolean | ProductAutoLinkedCorrectionRow[] | null = null;
      try {
        if (decision.corrected_value) value = schema.type === "array[object]"
          ? parseCorrectedRows(decision.corrected_value)
          : parseCorrectedValue(decision.corrected_value, schema.type);
      } catch {
        // Older audit events could contain a correction that does not match the field type.
      }
      if (schema.type === "array[object]" && value === null) unsafeLinkedReview = true;
      fields.push({ ...identity, value, status: value === null ? "needs_review" : "accepted", provenance: "human_correction" });
    } else if (decision?.decision === "incorrect") {
      fields.push({ ...identity, value: null, status: "needs_review", provenance: "machine" });
    } else {
      const visual = machine?.visual_grounding_verified === false;
      const verified = decision?.decision === "correct" && (!visual || sealedVisualReview(review));
      const linkedVerified = schema.type !== "array[object]" ||
        linkedRowsCanBeHumanVerified(machine?.value, visual && sealedVisualReview(review));
      if (verified && !linkedVerified) unsafeLinkedReview = true;
      const status = verified && linkedVerified ? machine?.value == null ? "missing" : "accepted" : "needs_review";
      fields.push({ ...identity, value: machine?.value ?? null, status,
        provenance: verified && linkedVerified ? "human_verified" : "machine",
        ...(machine?.evidence ? { evidence: machine.evidence } : {}),
        ...(machine?.visual_pages ? { visual_pages: machine.visual_pages } : {}),
        ...(visual ? { visual_grounding_verified: false as const } : {}) });
    }
  }
  let unsafeAddedReview = false;
  const visualAdditionApproved = visualRoute === "visual" && review?.status === "completed" && sealedVisualReview(review);
  for (const added of [...(review?.added_fields ?? [])].sort((left, right) => left.field_id.localeCompare(right.field_id))) {
    if (added.type === "array[object]") {
      const grounded = added.value.length > 0 && added.value.every((cell) => hasEvidenceShape(cell.evidence) ||
        visualAdditionApproved && hasHumanSourcePageShape(cell.human_source_page));
      if (!grounded) unsafeAddedReview = true;
      const value = added.value.map((cell) => ({ ...cell,
        status: hasEvidenceShape(cell.evidence) || visualAdditionApproved &&
          hasHumanSourcePageShape(cell.human_source_page) ? "accepted" as const : "needs_review" as const }));
      fields.push({ field_id: added.field_id, type: added.type, group: added.group, value,
        status: grounded ? "accepted" : "needs_review", provenance: "human_added",
        ...(added.value.some((cell) => hasHumanSourcePageShape(cell.human_source_page))
          ? { visual_grounding_verified: false as const } : {}) });
      continue;
    }
    const grounded = hasEvidenceShape(added.evidence) ||
      visualAdditionApproved && hasHumanSourcePageShape(added.human_source_page);
    if (!grounded) unsafeAddedReview = true;
    fields.push({ field_id: added.field_id, type: added.type, value: added.value,
      status: grounded ? "accepted" : "needs_review", provenance: "human_added",
      ...(hasEvidenceShape(added.evidence) ? { evidence: added.evidence } : {}),
      ...(hasHumanSourcePageShape(added.human_source_page)
        ? { human_source_page: added.human_source_page, visual_grounding_verified: false as const } : {}) });
  }
  return { scope: "document", doc_id: candidate.doc_id, review_revision: review?.revision ?? 0,
    review_status: unsafeLinkedReview || unsafeAddedReview ? "pending" : review?.status ?? "unreviewed", fields, removed_field_ids };
}

function parseCorrectedValue(raw: string, fieldType: string): string | number | boolean {
  const text = raw.trim();
  if (!text || text.length > MAX_CORRECTION) throw new AccessError("Invalid corrected value.", 400);
  if (fieldType === "array[object]") throw new AccessError("Linked rows require structured row correction.", 400);
  if (fieldType === "boolean") {
    if (!/^(?:true|false|yes|no)$/i.test(text)) throw new AccessError("Correction must be a boolean.", 400);
    return /^(?:true|yes)$/i.test(text);
  }
  if (fieldType === "integer" || fieldType === "decimal") {
    if (!/^\$?\s*[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$/.test(text)) {
      throw new AccessError("Correction must be a number.", 400);
    }
    const value = Number(text.replace(/^\$\s*/, "").replaceAll(",", ""));
    if (!Number.isFinite(value) || Math.abs(value) > Number.MAX_SAFE_INTEGER ||
      fieldType === "integer" && !Number.isSafeInteger(value)) {
      throw new AccessError("Correction is outside the supported numeric range.", 400);
    }
    return value;
  }
  if (fieldType === "date") {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(text) || Number.isNaN(Date.parse(`${text}T00:00:00Z`)) ||
      new Date(`${text}T00:00:00Z`).toISOString().slice(0, 10) !== text) {
      throw new AccessError("Correction must be a valid ISO date.", 400);
    }
  }
  return text;
}

function parseCorrectedRows(raw: string): ProductAutoLinkedCorrectionRow[] {
  if (!raw.trim() || raw.length > MAX_LINKED_CORRECTION) {
    throw new AccessError("Invalid linked row correction.", 400);
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new AccessError("Linked row correction must be a JSON array.", 400);
  }
  if (!Array.isArray(parsed) || parsed.length < 1 || parsed.length > MAX_LINKED_ROWS) {
    throw new AccessError("Linked row correction must contain 1 to 128 rows.", 400);
  }
  const seen = new Set<number>();
  const rows: ProductAutoLinkedCorrectionRow[] = [];
  for (const item of parsed) {
    if (!item || typeof item !== "object" || Array.isArray(item)) {
      throw new AccessError("Invalid linked row.", 400);
    }
    const row = item as Record<string, unknown>;
    if (Object.keys(row).sort().join(",") !== "row,value" ||
      !Number.isInteger(row.row) || typeof row.row !== "number" || row.row < 0 || row.row >= MAX_LINKED_ROWS ||
      seen.has(row.row) || typeof row.value !== "string" || !row.value.trim() || [...row.value].length > 500) {
      throw new AccessError("Invalid linked row index or value.", 400);
    }
    seen.add(row.row);
    rows.push({ row: row.row, value: row.value.trim() });
  }
  return rows.sort((left, right) => left.row - right.row);
}

function canonicalAddedFieldId(value: unknown): value is string {
  return typeof value === "string" && SCHEMA_FIELD_ID.test(value) && !value.endsWith("_") &&
    value === value.normalize("NFKC").toLowerCase();
}

function validLinkedGroup(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && [...value].length <= 64 &&
    value.trim() === value && !/[\u0000-\u001f\u007f]/u.test(value);
}

function resolveAddedEvidence(
  source: unknown, value: string, sourcePages: Array<{ page: number; text: string }>,
  linkedCell = false,
): ProductAutoEvidence {
  if (!source || typeof source !== "object" || Array.isArray(source)) {
    throw new AccessError("Added field needs a source page and exact OCR quote.", 400);
  }
  const input = source as Record<string, unknown>;
  if (Object.keys(input).some((key) => key !== "page" && key !== "quote") ||
    !Number.isSafeInteger(input.page) || typeof input.page !== "number" ||
    typeof input.quote !== "string" || !input.quote.trim() ||
    [...input.quote].length > MAX_ADDED_QUOTE) {
    throw new AccessError("Invalid added field source quote.", 400);
  }
  const page = sourcePages.find((item) => item.page === input.page);
  const quote = input.quote;
  const offset = page?.text.indexOf(quote) ?? -1;
  if (!page || offset < 0 || !(linkedCell
    ? addedLinkedValueMatchesQuote(value, quote) : linkedValueMatchesQuote(value, quote))) {
    throw new AccessError("Added field value and quote must match the OCR source page.", 400);
  }
  if (page.text.indexOf(quote, offset + 1) >= 0) {
    throw new AccessError("Source quote occurs more than once on the page. Select a longer quote.", 400);
  }
  const start = [...page.text.slice(0, offset)].length;
  const evidence = { page: page.page, start, end: start + [...quote].length, quote };
  assertSourceEvidence(evidence, sourcePages);
  return evidence;
}

function resolveAddedSource(
  input: Record<string, unknown>, value: string, sourcePages: Array<{ page: number; text: string }>,
  visualRoute: ProductAutoDocumentDetail["visualRoute"], linkedCell = false,
): { evidence: ProductAutoEvidence } | { human_source_page: ProductAutoHumanSourcePage } {
  if (("evidence" in input) === ("human_source_page" in input)) {
    throw new AccessError("Choose exactly one source quote or reviewer-observed page.", 400);
  }
  if ("evidence" in input) {
    return { evidence: resolveAddedEvidence(input.evidence, value, sourcePages, linkedCell) };
  }
  const observedPage = input.human_source_page;
  if (visualRoute !== "visual" || !hasHumanSourcePageShape(observedPage) ||
    !sourcePages.some((page) => page.page === observedPage.page)) {
    throw new AccessError("A reviewer-observed page requires a visual extraction and an actual source page.", 400);
  }
  return { human_source_page: observedPage };
}

function parseAddedLinkedCells(
  value: unknown, sourcePages: Array<{ page: number; text: string }>,
  visualRoute: ProductAutoDocumentDetail["visualRoute"],
): ProductAutoAddedLinkedCell[] {
  if (!Array.isArray(value) || value.length < 1 || value.length > MAX_LINKED_ROWS) {
    throw new AccessError("An added linked column needs 1 to 128 cells.", 400);
  }
  const rows = new Set<number>();
  const spans = new Set<string>();
  return value.map((raw): ProductAutoAddedLinkedCell => {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new AccessError("Invalid added linked cell.", 400);
    const cell = raw as Record<string, unknown>;
    if (Object.keys(cell).some((key) => !["evidence", "human_source_page", "row", "value"].includes(key)) ||
      !Number.isSafeInteger(cell.row) || typeof cell.row !== "number" || cell.row < 0 ||
      cell.row >= MAX_LINKED_ROWS || rows.has(cell.row) ||
      typeof cell.value !== "string" || !cell.value.trim() || [...cell.value].length > 500) {
      throw new AccessError("Invalid or repeated linked row or cell value.", 400);
    }
    rows.add(cell.row);
    const source = resolveAddedSource(cell, cell.value.trim(), sourcePages, visualRoute, true);
    if ("evidence" in source) {
      const span = `${source.evidence.page}:${source.evidence.start}:${source.evidence.end}`;
      if (spans.has(span)) throw new AccessError("One source quote cannot support two rows in the same column.", 400);
      spans.add(span);
    }
    return { row: cell.row, value: cell.value.trim(),
      status: "evidence" in source ? "accepted" : "needs_review", ...source,
      ...("human_source_page" in source ? { visual_grounding_verified: false as const } : {}) };
  }).sort((left, right) => left.row - right.row);
}

function parseAddedFields(
  values: unknown, proposedIds: Set<string>, sourcePages: Array<{ page: number; text: string }>,
  visualRoute: ProductAutoDocumentDetail["visualRoute"],
): ProductAutoAddedField[] {
  if (!Array.isArray(values)) throw new AccessError("Added fields must be a list.", 400);
  if (values.length > MAX_ADDED_FIELDS) throw new AccessError("Too many added fields.", 400);
  const seen = new Set<string>();
  return values.map((value) => {
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new AccessError("Invalid added field.", 400);
    const item = value as Record<string, unknown>;
    const fieldId = item.field_id;
    const type = item.type;
    if (!canonicalAddedFieldId(fieldId) || proposedIds.has(fieldId) || seen.has(fieldId) ||
      !["string", "integer", "decimal", "boolean", "date", "array[object]"].includes(String(type))) {
      throw new AccessError("Invalid or repeated added field.", 400);
    }
    seen.add(fieldId);
    if (item.note != null && typeof item.note !== "string") throw new AccessError("Invalid added field note.", 400);
    const note = typeof item.note === "string" ? item.note.trim() : null;
    if (note && note.length > MAX_REVIEW_NOTE) throw new AccessError("Added field note is too long.", 400);
    if (type === "array[object]") {
      if (!validLinkedGroup(item.group) ||
        Object.keys(item).some((key) => !["field_id", "type", "group", "value", "note"].includes(key))) {
        throw new AccessError("Added linked columns need a valid group and column identity.", 400);
      }
      return { field_id: fieldId, type, group: item.group,
        value: parseAddedLinkedCells(item.value, sourcePages, visualRoute), note };
    }
    if (Object.keys(item).some((key) => !["field_id", "type", "value", "evidence", "human_source_page", "note"].includes(key)) ||
      typeof item.value !== "string") throw new AccessError("Invalid added field value.", 400);
    const parsedValue = parseCorrectedValue(item.value, type as string);
    const source = resolveAddedSource(item, item.value.trim(), sourcePages, visualRoute);
    return { field_id: fieldId, type: type as ProductAutoScalarType, value: parsedValue, ...source, note };
  });
}

function verifiedReviewSourceHash(jobId: string, runId: string, fileId: string, selectedFiles?: SelectedFile[]): string {
  const selected = (selectedFiles ?? readRunRecord(jobId, runId).selectedFiles).find((file) => file.fileId === fileId);
  if (!selected || !/^[a-f0-9]{64}$/.test(selected.sha256)) {
    throw new AccessError("The original source receipt is unavailable.", 409);
  }
  const sourceDirectory = path.resolve(loadRunnerConfig().uploadsDir, `job_${jobId}`);
  const sourcePath = path.resolve(sourceDirectory, selected.storedName);
  if (path.dirname(sourcePath) !== sourceDirectory || !fs.existsSync(sourcePath) ||
    !fs.lstatSync(sourcePath).isFile() || sha256File(sourcePath) !== selected.sha256) {
    throw new AccessError("The original source changed since extraction. Start a new run.", 409);
  }
  return selected.sha256;
}

export function saveProductAutoReview(
  jobId: string, runId: string, docId: string, reviewerUserId: string, expectedRevision: unknown, fields: unknown,
  addedFields: unknown = [],
  reportedActiveReviewSeconds: unknown = undefined,
): ProductAutoReview {
  if (!Number.isSafeInteger(expectedRevision) || typeof expectedRevision !== "number" || expectedRevision < 0) {
    throw new AccessError("A valid expected review revision is required.", 400);
  }
  if (reportedActiveReviewSeconds !== undefined && (!Number.isSafeInteger(reportedActiveReviewSeconds) ||
    typeof reportedActiveReviewSeconds !== "number" || reportedActiveReviewSeconds < 1 ||
    reportedActiveReviewSeconds > 14_400)) {
    throw new AccessError("Reported active review seconds must be an integer from 1 to 14400.", 400);
  }
  return saveProductAutoReviewWithRevision(jobId, runId, docId, reviewerUserId, expectedRevision, fields, addedFields,
    reportedActiveReviewSeconds);
}

function saveProductAutoReviewWithRevision(
  jobId: string, runId: string, docId: string, reviewerUserId: string, expectedRevision: number, fields: unknown,
  addedFields: unknown, reportedActiveReviewSeconds: number | undefined,
): ProductAutoReview {
  if (readRunRecord(jobId, runId).status === "running") recoverProductAutoRuns(jobId);
  const runDocument = readRunRecord(jobId, runId).documents.find((item) => item.docId === docId);
  if (!runDocument?.machineResultSha256) {
    throw new AccessError("This extraction predates sealed artifacts or has not completed. Start a new run.", 409);
  }
  const { detail, machineResultHash } = loadProductAutoDocument(jobId, runId, docId);
  if ((detail.review?.revision ?? 0) !== expectedRevision) {
    throw new AccessError("Review changed since you opened it. Reload before saving.", 409);
  }
  if (!Array.isArray(fields)) throw new AccessError("Review fields must be a list.", 400);
  const allowed = new Set(detail.candidate.proposed_schema.map((field) => field.field_id));
  const fieldTypes = new Map(detail.candidate.proposed_schema.map((field) => [field.field_id, field.type]));
  const machineValueByField = new Map(detail.candidate.extracted_values.map((field) => [field.field_id, field]));
  const seen = new Set<string>();
  const parsed: ProductAutoReviewField[] = [];
  for (const value of fields) {
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new AccessError("Invalid review field.", 400);
    const item = value as Record<string, unknown>;
    const fieldId = item.field_id;
    const decision = item.decision;
    if (typeof fieldId !== "string" || !allowed.has(fieldId) || seen.has(fieldId) ||
      !["correct", "incorrect", "corrected", "not_present", "remove"].includes(String(decision))) {
      throw new AccessError("Invalid or repeated review field.", 400);
    }
    if (item.corrected_value != null && typeof item.corrected_value !== "string") throw new AccessError("Invalid corrected value.", 400);
    if (item.note != null && typeof item.note !== "string") throw new AccessError("Invalid review note.", 400);
    const correctedValue = typeof item.corrected_value === "string" ? item.corrected_value.trim() : null;
    const note = typeof item.note === "string" ? item.note.trim() : null;
    const fieldType = fieldTypes.get(fieldId) ?? "string";
    if (correctedValue && correctedValue.length > (fieldType === "array[object]" ? MAX_LINKED_CORRECTION : MAX_CORRECTION) ||
      note && note.length > MAX_REVIEW_NOTE ||
      decision === "corrected" && !correctedValue || decision !== "corrected" && correctedValue) {
      throw new AccessError("Invalid review correction or note.", 400);
    }
    if (fieldType === "array[object]" && decision === "correct") {
      const machine = machineValueByField.get(fieldId);
      if (!linkedRowsCanBeHumanVerified(machine?.value, machine?.visual_grounding_verified === false)) {
        throw new AccessError("Linked rows need text evidence, reviewed visual pages, or a structured correction.", 400);
      }
    }
    let storedCorrection = correctedValue;
    if (decision === "corrected" && correctedValue) {
      if (fieldType === "array[object]") storedCorrection = JSON.stringify(parseCorrectedRows(correctedValue));
      else parseCorrectedValue(correctedValue, fieldType);
    }
    parsed.push({ field_id: fieldId, decision: decision as ProductAutoReviewDecision,
      corrected_value: storedCorrection, note });
    seen.add(fieldId);
  }
  const parsedAdded = parseAddedFields(addedFields, allowed, detail.sourcePages, detail.visualRoute);
  const sourceHash = verifiedReviewSourceHash(jobId, runId, detail.fileId);
  const sourcePagesHash = createHash("sha256").update(JSON.stringify(detail.sourcePages)).digest("hex");
  const removedCount = parsed.filter((field) => field.decision === "not_present" || field.decision === "remove").length;
  if (allowed.size - removedCount + parsedAdded.length > MAX_SCHEMA_FIELDS) {
    throw new AccessError("Reviewed schema exceeds the 24-field limit.", 400);
  }
  const previous = detail.review;
  const eventId = randomUUID().replace(/-/g, "");
  const createdAt = new Date().toISOString();
  const revision = (previous?.revision ?? 0) + 1;
  const review: ProductAutoReview = {
    review_version: 1, job_id: jobId, run_id: runId, doc_id: docId,
    status: seen.size === allowed.size && (seen.size > 0 || parsedAdded.length > 0) &&
      parsed.every((field) => field.decision !== "incorrect") ? "completed" : "pending",
    reviewer_user_id: reviewerUserId, updated_at: createdAt, fields: parsed, added_fields: parsedAdded,
    source_container_sha256: sourceHash,
    source_pages_sha256: sourcePagesHash,
    machine_result_sha256: machineResultHash,
    revision, audit_event_id: eventId,
  };
  const machineValues = new Map(detail.candidate.extracted_values.map((item) => [item.field_id, item]));
  const event: ProductAutoAuditEvent = {
    audit_event_id: eventId, revision, created_at: createdAt, reviewer_user_id: reviewerUserId,
    ...(reportedActiveReviewSeconds === undefined ? {} : { reported_active_review_seconds: reportedActiveReviewSeconds }),
    previous_event_id: previous?.audit_event_id ?? null,
    review_snapshot: review,
    machine_fields: parsed.map((field) => {
      const machine = machineValues.get(field.field_id);
      return { field_id: field.field_id, value: machine?.value ?? null,
        status: machine?.status ?? "not_proposed", evidence: machine?.evidence };
    }),
    review_fields: parsed,
    review_added_fields: parsedAdded,
    source_container_sha256: sourceHash,
    source_pages_sha256: sourcePagesHash,
    machine_result_sha256: machineResultHash,
  };
  const directory = auditDir(jobId, runId, docId);
  publishAuditEvent(directory, event);
  return review;
}
