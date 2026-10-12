import fs from "node:fs";
import path from "node:path";
import { createHash, randomUUID } from "node:crypto";
import { spawn } from "node:child_process";
import { AccessError } from "@/server/auth";
import { getCommandConfig, loadRunnerConfig } from "@/server/config";
import { getJobOrThrow } from "@/server/jobs";
import type {
  ProductAutoAddedField,
  ProductAutoAddedLinkedCell,
  ProductAutoAuditEvent,
  ProductAutoCandidate,
  ProductAutoCorrectedResult,
  ProductAutoDocumentDetail,
  ProductAutoEvidence,
  ProductAutoLinkedCell,
  ProductAutoLinkedCorrectionRow,
  ProductAutoParsedDocument,
  ProductAutoReview,
  ProductAutoReviewDecision,
  ProductAutoReviewField,
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
  status: "running" | "success" | "failed";
  createdAt: string;
  endedAt?: string;
  serverInstanceId: string;
  selectedFiles: SelectedFile[];
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
  return Number.isInteger(evidence.page) && typeof evidence.page === "number" && evidence.page > 0 &&
    Number.isInteger(evidence.start) && typeof evidence.start === "number" && evidence.start >= 0 &&
    Number.isInteger(evidence.end) && typeof evidence.end === "number" && evidence.end > evidence.start &&
    typeof evidence.quote === "string" && evidence.quote.length > 0;
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
    if (Object.keys(cell).some((key) => !["row", "value", "status", "evidence"].includes(key)) ||
      !Number.isInteger(cell.row) || typeof cell.row !== "number" || cell.row < 0 || cell.row >= MAX_LINKED_ROWS ||
      seen.has(cell.row) || typeof cell.value !== "string" || !cell.value.trim() || [...cell.value].length > 500 ||
      !["accepted", "needs_review"].includes(String(cell.status)) ||
      cell.status === "accepted" && !hasEvidenceShape(cell.evidence) ||
      cell.status === "accepted" && hasEvidenceShape(cell.evidence) && !linkedValueMatchesQuote(cell.value, cell.evidence.quote) ||
      cell.evidence != null && !hasEvidenceShape(cell.evidence)) return null;
    seen.add(cell.row);
  }
  return value as ProductAutoLinkedCell[];
}

function linkedRowsAreVerified(value: unknown): boolean {
  const rows = machineLinkedRows(value);
  return Boolean(rows?.length && rows.every((cell) => cell.status === "accepted" && cell.evidence));
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
    if (field.status === "accepted" && !field.evidence) throw new Error("Accepted value has no evidence.");
    if (field.evidence) assertSourceEvidence(field.evidence, pages);
    const fieldType = schemaTypes.get(field.field_id)!;
    if (field.status === "accepted" && fieldType !== "array[object]" &&
      !acceptedScalarMatchesQuote(field.value, fieldType, field.evidence.quote, field.field_id)) {
      throw new Error("Accepted value does not match its type and source quote.");
    }
    if (fieldType === "array[object]") {
      if (field.value === null) {
        if (field.status === "accepted") throw new Error("A missing linked field cannot be accepted.");
        continue;
      }
      const rows = machineLinkedRows(field.value);
      if (!rows || field.status === "accepted") throw new Error("Invalid linked row candidate.");
      for (const cell of rows) {
        if (cell.evidence) assertSourceEvidence(cell.evidence, pages);
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

function effectiveReviewStatus(review: ProductAutoReview | null): "unreviewed" | "pending" | "completed" {
  if (!review) return "unreviewed";
  return review.added_fields?.some((field) => field.type === "array[object]"
    ? !field.value.length || field.value.some((cell) => !hasEvidenceShape(cell.evidence))
    : !hasEvidenceShape(field.evidence)) ? "pending" : review.status;
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
    if (targetDocId && docId !== targetDocId) return [];
    const { bytes, sha256: machineResultHash } = readResultBytes(record.runId, docId);
    if (receipt.result_sha256 !== machineResultHash) {
      throw new Error("Machine result and extraction receipt differ.");
    }
    const result = parseResultBytes(bytes);
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
  if (record.status !== "running") return;
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
  }
  stopHeartbeat(runId);
}

function runForDisplay(jobId: string, runId: string): RunRecord {
  const record = readRunRecord(jobId, runId);
  if (record.status === "running" && fs.existsSync(path.join(outputDir(runId), "run.json"))) {
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
        if (record.status !== "running") continue;
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
    status: record.status,
    createdAt: record.createdAt,
    endedAt: record.endedAt,
    selectedCount: record.selectedFiles.length,
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

export function startProductAutoRun(jobId: string, selectedFileIds: string[], admin: boolean): ProductAutoRun {
  const config = loadRunnerConfig();
  if (!productAutoAvailability().available) throw new AccessError("Automatic extraction is unavailable on this deployment.", 503);
  const job = getJobOrThrow(jobId);
  if (!selectedFileIds.length || new Set(selectedFileIds).size !== selectedFileIds.length) {
    throw new AccessError("Select one or more distinct documents.", 400);
  }
  recoverProductAutoRuns(jobId);
  if (listProductAutoRuns(jobId).some((run) => run.status === "running")) {
    throw new AccessError("This job already has an automatic extraction run in progress.", 409);
  }
  const model = process.env.IDPO_AUTO_MODEL?.trim();
  const baseUrl = process.env.IDPO_AUTO_API_BASE_URL?.trim();
  if (Boolean(model) !== Boolean(baseUrl)) throw new AccessError("The server model configuration is incomplete.", 503);
  if (baseUrl && modelEndpointRequiresKey(baseUrl) && !process.env.ICORE_API_KEY?.trim()) {
    throw new AccessError("The server model key is missing.", 503);
  }
  if (model && !admin) throw new AccessError("Admin access is required to start model-backed extraction.", 403);
  const documents = selectedFileIds.map((fileId) => job.documents?.find((document) => document.fileId === fileId));
  if (documents.some((document) => !document)) throw new AccessError("A selected document was not found.", 400);
  const runId = `auto_${randomUUID().replace(/-/g, "")}`;
  const inputDir = stagedInputDir(runId);
  const sourceDir = path.resolve(config.uploadsDir, `job_${jobId}`);
  if (path.dirname(sourceDir) !== path.resolve(config.uploadsDir)) throw new AccessError("Invalid job upload location.", 400);
  const selectedFiles: SelectedFile[] = [];
  fs.mkdirSync(inputDir, { recursive: true });
  try {
    for (const document of documents) {
      if (!document) continue;
      const source = path.resolve(sourceDir, document.storedName);
      if (path.dirname(source) !== sourceDir || !fs.existsSync(source) || !fs.lstatSync(source).isFile()) {
        throw new AccessError("A selected source document is unavailable.", 400);
      }
      const staged = path.join(inputDir, document.storedName);
      try {
        fs.linkSync(source, staged);
      } catch {
        fs.copyFileSync(source, staged);
      }
      selectedFiles.push({ fileId: document.fileId, fileName: document.fileName,
        storedName: document.storedName, sha256: sha256File(source) });
    }
    const record: RunRecord = {
      runId, jobId, status: "running", createdAt: new Date().toISOString(),
      serverInstanceId: instanceId, selectedFiles, documents: [],
    };
    saveRunRecord(record);
    writeLease(jobId, runId);
    const command = getCommandConfig("idpo_process_auto");
    const args = command.args.map((arg) => arg.replaceAll("{input_dir}", inputDir).replaceAll("{run_id}", runId));
    if (model && baseUrl) args.push("--model", model, "--api-base-url", baseUrl);
    const child = spawn(command.program, args, {
      cwd: command.cwd,
      env: { ...process.env, ...command.env, IDPO_DATA_DIR: storageRoot() },
      windowsHide: true,
      stdio: "ignore",
    });
    startHeartbeat(jobId, runId);
    child.once("error", () => finishRun(jobId, runId, null));
    child.once("close", (code) => finishRun(jobId, runId, code));
    return publicRun(record);
  } catch (error) {
    if (fs.existsSync(runFile(jobId, runId))) finishRun(jobId, runId, null);
    else fs.rmSync(inputDir, { recursive: true, force: true });
    throw error;
  }
}

function loadProductAutoDocument(jobId: string, runId: string, docId: string): {
  detail: ProductAutoDocumentDetail; machineResultHash: string;
} {
  const record = readRunRecord(jobId, runId);
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
  const parsedDocument = readParsedDocument(result);
  const auditTrail = readAuditTrail(jobId, runId, docId);
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
  if (receipts.some((receipt) => receipt.source_container_sha256 || receipt.source_pages_sha256)) {
    const sourceHash = verifiedReviewSourceHash(jobId, runId, document.fileId);
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
    detail: {
      runId, fileId: document.fileId, fileName: document.fileName,
      candidate, sourcePages, ...(parsedDocument ? { parsedDocument } : {}), review, auditTrail,
      correctedResult: deriveProductAutoCorrectedResult(candidate, review),
    },
  };
}

export function getProductAutoDocument(jobId: string, runId: string, docId: string): ProductAutoDocumentDetail {
  return loadProductAutoDocument(jobId, runId, docId).detail;
}

export function deriveProductAutoCorrectedResult(
  candidate: ProductAutoCandidate, review: ProductAutoReview | null,
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
      const verified = decision?.decision === "correct";
      const linkedVerified = schema.type !== "array[object]" || linkedRowsAreVerified(machine?.value);
      if (verified && !linkedVerified) unsafeLinkedReview = true;
      const status = verified && linkedVerified ? machine?.value == null ? "missing" : "accepted" : "needs_review";
      fields.push({ ...identity, value: machine?.value ?? null, status,
        provenance: verified && linkedVerified ? "human_verified" : "machine",
        ...(machine?.evidence ? { evidence: machine.evidence } : {}) });
    }
  }
  let unsafeAddedReview = false;
  for (const added of [...(review?.added_fields ?? [])].sort((left, right) => left.field_id.localeCompare(right.field_id))) {
    if (added.type === "array[object]") {
      const grounded = added.value.length > 0 && added.value.every((cell) => hasEvidenceShape(cell.evidence));
      if (!grounded) unsafeAddedReview = true;
      fields.push({ field_id: added.field_id, type: added.type, group: added.group, value: added.value,
        status: grounded ? "accepted" : "needs_review", provenance: "human_added" });
      continue;
    }
    const grounded = hasEvidenceShape(added.evidence);
    if (!grounded) unsafeAddedReview = true;
    fields.push({ field_id: added.field_id, type: added.type, value: added.value,
      status: grounded ? "accepted" : "needs_review", provenance: "human_added",
      ...(grounded ? { evidence: added.evidence } : {}) });
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

function parseAddedLinkedCells(
  value: unknown, sourcePages: Array<{ page: number; text: string }>,
): ProductAutoAddedLinkedCell[] {
  if (!Array.isArray(value) || value.length < 1 || value.length > MAX_LINKED_ROWS) {
    throw new AccessError("An added linked column needs 1 to 128 cells.", 400);
  }
  const rows = new Set<number>();
  const spans = new Set<string>();
  return value.map((raw): ProductAutoAddedLinkedCell => {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new AccessError("Invalid added linked cell.", 400);
    const cell = raw as Record<string, unknown>;
    if (Object.keys(cell).sort().join(",") !== "evidence,row,value" ||
      !Number.isSafeInteger(cell.row) || typeof cell.row !== "number" || cell.row < 0 ||
      cell.row >= MAX_LINKED_ROWS || rows.has(cell.row) ||
      typeof cell.value !== "string" || !cell.value.trim() || [...cell.value].length > 500) {
      throw new AccessError("Invalid or repeated linked row or cell value.", 400);
    }
    rows.add(cell.row);
    const evidence = resolveAddedEvidence(cell.evidence, cell.value.trim(), sourcePages, true);
    const span = `${evidence.page}:${evidence.start}:${evidence.end}`;
    if (spans.has(span)) throw new AccessError("One source quote cannot support two rows in the same column.", 400);
    spans.add(span);
    return { row: cell.row, value: cell.value.trim(), status: "accepted", evidence };
  }).sort((left, right) => left.row - right.row);
}

function parseAddedFields(
  values: unknown, proposedIds: Set<string>, sourcePages: Array<{ page: number; text: string }>,
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
        value: parseAddedLinkedCells(item.value, sourcePages), note };
    }
    if (typeof item.value !== "string") throw new AccessError("Invalid added field value.", 400);
    const parsedValue = parseCorrectedValue(item.value, type as string);
    const evidence = resolveAddedEvidence(item.evidence, item.value.trim(), sourcePages);
    return { field_id: fieldId, type: type as ProductAutoScalarType, value: parsedValue, evidence, note };
  });
}

function verifiedReviewSourceHash(jobId: string, runId: string, fileId: string): string {
  const selected = readRunRecord(jobId, runId).selectedFiles.find((file) => file.fileId === fileId);
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
  const machineValueByField = new Map(detail.candidate.extracted_values.map((field) => [field.field_id, field.value]));
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
    if (fieldType === "array[object]" && decision === "correct" && !linkedRowsAreVerified(machineValueByField.get(fieldId))) {
      throw new AccessError("Linked rows need verified evidence for every cell or a structured correction.", 400);
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
  const parsedAdded = parseAddedFields(addedFields, allowed, detail.sourcePages);
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
