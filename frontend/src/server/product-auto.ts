import fs from "node:fs";
import path from "node:path";
import { createHash, randomUUID } from "node:crypto";
import { spawn } from "node:child_process";
import { AccessError } from "@/server/auth";
import { getCommandConfig, loadRunnerConfig } from "@/server/config";
import { getJobOrThrow } from "@/server/jobs";
import type {
  ProductAutoAddedField,
  ProductAutoAuditEvent,
  ProductAutoCandidate,
  ProductAutoCorrectedResult,
  ProductAutoDocumentDetail,
  ProductAutoReview,
  ProductAutoReviewDecision,
  ProductAutoReviewField,
  ProductAutoRun,
  ProductAutoRunDocument,
} from "@/types/product-auto";

const SAFE_ID = /^[a-zA-Z0-9_-]{1,100}$/;
const MAX_REVIEW_NOTE = 2000;
const MAX_CORRECTION = 10000;
const MAX_ADDED_FIELDS = 100;
const ADDED_FIELD_ID = /^[a-z][a-z0-9_]{0,63}$/;
const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);
const interrupted = "The server stopped before extraction finished. Run the documents again.";
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
  documents: ProductAutoRunDocument[];
  error?: string;
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
  const parsed: unknown = JSON.parse(fs.readFileSync(filePath, "utf8"));
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("Invalid extraction artifact.");
  }
  return parsed as Record<string, unknown>;
}

function parseJsonLines(filePath: string): Record<string, unknown>[] {
  return fs.readFileSync(filePath, "utf8").split(/\r?\n/).filter(Boolean).map((line) => {
    const value: unknown = JSON.parse(line);
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new Error("Invalid extraction artifact.");
    }
    return value as Record<string, unknown>;
  });
}

function readRunRecord(jobId: string, runId: string): RunRecord {
  const filePath = runFile(jobId, runId);
  if (!fs.existsSync(filePath)) throw new AccessError("Run not found.", 404);
  return parseJsonObject(filePath) as unknown as RunRecord;
}

function saveRunRecord(record: RunRecord): void {
  writeJsonAtomic(runFile(record.jobId, record.runId), record);
}

function sha256File(filePath: string): string {
  return createHash("sha256").update(fs.readFileSync(filePath)).digest("hex");
}

function candidateFromArtifact(value: unknown, docId: string, pages: unknown): ProductAutoCandidate {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid candidate.");
  const candidate = value as Record<string, unknown>;
  if (candidate.contract_version !== 1 || candidate.doc_id !== docId ||
    !Array.isArray(candidate.proposed_schema) || !Array.isArray(candidate.extracted_values)) {
    throw new Error("Invalid candidate.");
  }
  if (!["processed", "needs_review", "unsupported", "failed"].includes(String(candidate.document_status))) {
    throw new Error("Invalid candidate status.");
  }
  const schemaIds = new Set<string>();
  for (const field of candidate.proposed_schema) {
    if (!field || typeof field !== "object" || typeof field.field_id !== "string" ||
      typeof field.type !== "string" || !field.field_id || schemaIds.has(field.field_id)) {
      throw new Error("Invalid proposed schema.");
    }
    schemaIds.add(field.field_id);
  }
  for (const field of candidate.extracted_values) {
    if (!field || typeof field !== "object" || typeof field.field_id !== "string" ||
      !schemaIds.has(field.field_id) || !["accepted", "needs_review", "missing", "rejected"].includes(String(field.status))) {
      throw new Error("Invalid extracted value.");
    }
    if (field.status === "accepted" && !field.evidence) throw new Error("Accepted value has no evidence.");
    if (field.evidence) {
      const evidence = field.evidence as Record<string, unknown>;
      const page = Array.isArray(pages) ? pages.find((item) => item && typeof item === "object" && item.page === evidence.page) : null;
      if (!page || typeof page.text !== "string" || !Number.isInteger(evidence.start) ||
        !Number.isInteger(evidence.end) || typeof evidence.start !== "number" || typeof evidence.end !== "number" ||
        evidence.start < 0 || evidence.end <= evidence.start || typeof evidence.quote !== "string" ||
        [...page.text].slice(evidence.start, evidence.end).join("") !== evidence.quote) {
        throw new Error("Candidate evidence does not match source text.");
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

function readCandidate(runId: string, docId: string): ProductAutoCandidate {
  requireSafeId(docId);
  const result = parseJsonObject(path.join(outputDir(runId), "docs", docId, "result.json"));
  return candidateFromArtifact(result.candidate, docId, result.pages);
}

function readReview(jobId: string, runId: string, docId: string): ProductAutoReview | null {
  return readAuditTrail(jobId, runId, docId).at(-1)?.review_snapshot ?? null;
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

function validatedDocuments(record: RunRecord): ProductAutoRunDocument[] {
  const runDir = outputDir(record.runId);
  const marker = parseJsonObject(path.join(runDir, "run.json"));
  if (marker.contract_version !== 1 || marker.run_id !== record.runId) {
    throw new Error("Run completion marker does not match this run.");
  }
  const receipts = parseJsonLines(path.join(runDir, "manifest.jsonl"));
  if (receipts.length !== marker.doc_count) throw new Error("Incomplete extraction manifest.");
  const byStoredName = new Map(record.selectedFiles.map((file) => [file.storedName, file]));
  const seen = new Set<string>();
  return receipts.map((receipt) => {
    const docId = receipt.doc_id;
    const sourceFile = receipt.source_file;
    if (typeof docId !== "string" || typeof sourceFile !== "string") throw new Error("Invalid document receipt.");
    requireSafeId(docId);
    const selected = byStoredName.get(sourceFile);
    if (!selected || receipt.run_id !== record.runId || receipt.source_container_sha256 !== selected.sha256 || seen.has(docId)) {
      throw new Error("Document receipt does not match the selected source.");
    }
    seen.add(docId);
    const candidate = readCandidate(record.runId, docId);
    if (candidate.document_status !== receipt.document_status) throw new Error("Candidate and receipt status differ.");
    const review = readReview(record.jobId, record.runId, docId);
    return {
      docId,
      fileId: selected.fileId,
      fileName: selected.fileName,
      status: candidate.document_status,
      fieldCount: candidate.proposed_schema.length,
      acceptedCount: candidate.extracted_values.filter((value) => value.status === "accepted").length,
      reviewStatus: review?.status ?? "unreviewed",
    };
  });
}

function finishRun(jobId: string, runId: string, exitCode: number | null): void {
  const record = readRunRecord(jobId, runId);
  if (record.status !== "running") return;
  record.endedAt = new Date().toISOString();
  try {
    if (exitCode !== 0) throw new Error("The extraction process failed. Check server logs.");
    record.documents = validatedDocuments(record);
    record.status = "success";
  } catch {
    record.status = "failed";
    record.error = exitCode !== 0
      ? "The extraction process failed. Check server logs."
      : "Extraction finished, but its output could not be verified.";
  }
  saveRunRecord(record);
  fs.rmSync(stagedInputDir(runId), { recursive: true, force: true });
}

function refreshRun(jobId: string, runId: string): RunRecord {
  const record = readRunRecord(jobId, runId);
  if (record.status === "running" && fs.existsSync(path.join(outputDir(runId), "run.json"))) {
    finishRun(jobId, runId, 0);
    return readRunRecord(jobId, runId);
  }
  if (record.status === "running" && record.serverInstanceId !== instanceId) {
    record.status = "failed";
    record.error = interrupted;
    record.endedAt = new Date().toISOString();
    saveRunRecord(record);
  }
  return record;
}

function publicRun(record: RunRecord): ProductAutoRun {
  return {
    runId: record.runId,
    status: record.status,
    createdAt: record.createdAt,
    endedAt: record.endedAt,
    selectedCount: record.selectedFiles.length,
    documents: record.documents.map((document) => ({
      ...document,
      reviewStatus: readReview(record.jobId, record.runId, document.docId)?.status ?? "unreviewed",
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
    .map((name) => refreshRun(jobId, name.slice(0, -5)))
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt))
    .map(publicRun);
}

export function getProductAutoRun(jobId: string, runId: string): ProductAutoRun {
  return publicRun(refreshRun(jobId, runId));
}

export function startProductAutoRun(jobId: string, selectedFileIds: string[], admin: boolean): ProductAutoRun {
  const config = loadRunnerConfig();
  if (!productAutoAvailability().available) throw new AccessError("Automatic extraction is unavailable on this deployment.", 503);
  const job = getJobOrThrow(jobId);
  if (!selectedFileIds.length || new Set(selectedFileIds).size !== selectedFileIds.length) {
    throw new AccessError("Select one or more distinct documents.", 400);
  }
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
    const command = getCommandConfig("idpo_process_auto");
    const args = command.args.map((arg) => arg.replaceAll("{input_dir}", inputDir).replaceAll("{run_id}", runId));
    if (model && baseUrl) args.push("--model", model, "--api-base-url", baseUrl);
    const child = spawn(command.program, args, {
      cwd: command.cwd,
      env: { ...process.env, ...command.env, IDPO_DATA_DIR: storageRoot() },
      windowsHide: true,
      stdio: "ignore",
    });
    child.once("error", () => finishRun(jobId, runId, null));
    child.once("close", (code) => finishRun(jobId, runId, code));
    return publicRun(record);
  } catch (error) {
    fs.rmSync(inputDir, { recursive: true, force: true });
    throw error;
  }
}

export function getProductAutoDocument(jobId: string, runId: string, docId: string): ProductAutoDocumentDetail {
  const run = getProductAutoRun(jobId, runId);
  const document = run.documents.find((item) => item.docId === docId);
  if (run.status !== "success" || !document) throw new AccessError("Document result not found.", 404);
  const candidate = readCandidate(runId, docId);
  const auditTrail = readAuditTrail(jobId, runId, docId);
  const review = auditTrail.at(-1)?.review_snapshot ?? null;
  return {
    runId, fileId: document.fileId, fileName: document.fileName,
    candidate, review, auditTrail,
    correctedResult: deriveProductAutoCorrectedResult(candidate, review),
  };
}

export function deriveProductAutoCorrectedResult(
  candidate: ProductAutoCandidate, review: ProductAutoReview | null,
): ProductAutoCorrectedResult {
  const machineValues = new Map(candidate.extracted_values.map((item) => [item.field_id, item]));
  const decisions = new Map(review?.fields.map((item) => [item.field_id, item]) ?? []);
  const removed_field_ids: string[] = [];
  const fields: ProductAutoCorrectedResult["fields"] = [];
  for (const schema of candidate.proposed_schema) {
    const decision = decisions.get(schema.field_id);
    if (decision?.decision === "not_present" || decision?.decision === "remove") {
      removed_field_ids.push(schema.field_id);
      continue;
    }
    const machine = machineValues.get(schema.field_id);
    const identity = { field_id: schema.field_id, type: schema.type, ...(schema.group ? { group: schema.group } : {}) };
    if (decision?.decision === "corrected") {
      let value: string | number | boolean | null = null;
      try {
        if (decision.corrected_value) value = parseCorrectedValue(decision.corrected_value, schema.type);
      } catch {
        // Older audit events could contain a correction that does not match the field type.
      }
      fields.push({ ...identity, value, status: value === null ? "needs_review" : "accepted", provenance: "human_correction" });
    } else if (decision?.decision === "incorrect") {
      fields.push({ ...identity, value: null, status: "needs_review", provenance: "machine" });
    } else {
      const verified = decision?.decision === "correct";
      const status = verified ? machine?.value == null ? "missing" : "accepted" : "needs_review";
      fields.push({ ...identity, value: machine?.value ?? null, status,
        provenance: verified ? "human_verified" : "machine",
        ...(machine?.evidence ? { evidence: machine.evidence } : {}) });
    }
  }
  for (const added of [...(review?.added_fields ?? [])].sort((left, right) => left.field_id.localeCompare(right.field_id))) {
    fields.push({ field_id: added.field_id, type: added.type, value: added.value,
      status: "accepted", provenance: "human_added" });
  }
  return { scope: "document", doc_id: candidate.doc_id, review_revision: review?.revision ?? 0,
    review_status: review?.status ?? "unreviewed", fields, removed_field_ids };
}

function parseCorrectedValue(raw: string, fieldType: string): string | number | boolean {
  const text = raw.trim();
  if (!text || text.length > MAX_CORRECTION) throw new AccessError("Invalid corrected value.", 400);
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

function parseAddedFields(values: unknown, proposedIds: Set<string>): ProductAutoAddedField[] {
  if (!Array.isArray(values)) throw new AccessError("Added fields must be a list.", 400);
  if (values.length > MAX_ADDED_FIELDS) throw new AccessError("Too many added fields.", 400);
  const seen = new Set<string>();
  return values.map((value) => {
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new AccessError("Invalid added field.", 400);
    const item = value as Record<string, unknown>;
    const fieldId = item.field_id;
    const type = item.type;
    if (typeof fieldId !== "string" || !ADDED_FIELD_ID.test(fieldId) || proposedIds.has(fieldId) || seen.has(fieldId) ||
      !["string", "integer", "decimal", "boolean", "date"].includes(String(type))) {
      throw new AccessError("Invalid or repeated added field.", 400);
    }
    seen.add(fieldId);
    if (item.note != null && typeof item.note !== "string") throw new AccessError("Invalid added field note.", 400);
    const note = typeof item.note === "string" ? item.note.trim() : null;
    if (note && note.length > MAX_REVIEW_NOTE) throw new AccessError("Added field note is too long.", 400);
    if (typeof item.value !== "string") throw new AccessError("Invalid added field value.", 400);
    const parsedValue = parseCorrectedValue(item.value, type as string);
    return { field_id: fieldId, type: type as ProductAutoAddedField["type"], value: parsedValue, note };
  });
}

export function saveProductAutoReview(
  jobId: string, runId: string, docId: string, reviewerUserId: string, expectedRevision: unknown, fields: unknown,
  addedFields: unknown = [],
): ProductAutoReview {
  if (!Number.isSafeInteger(expectedRevision) || typeof expectedRevision !== "number" || expectedRevision < 0) {
    throw new AccessError("A valid expected review revision is required.", 400);
  }
  return saveProductAutoReviewWithRevision(jobId, runId, docId, reviewerUserId, expectedRevision, fields, addedFields);
}

function saveProductAutoReviewWithRevision(
  jobId: string, runId: string, docId: string, reviewerUserId: string, expectedRevision: number, fields: unknown,
  addedFields: unknown,
): ProductAutoReview {
  const detail = getProductAutoDocument(jobId, runId, docId);
  if ((detail.review?.revision ?? 0) !== expectedRevision) {
    throw new AccessError("Review changed since you opened it. Reload before saving.", 409);
  }
  if (!Array.isArray(fields)) throw new AccessError("Review fields must be a list.", 400);
  const allowed = new Set(detail.candidate.proposed_schema.map((field) => field.field_id));
  const fieldTypes = new Map(detail.candidate.proposed_schema.map((field) => [field.field_id, field.type]));
  const parsedAdded = parseAddedFields(addedFields, allowed);
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
    if (correctedValue && correctedValue.length > MAX_CORRECTION || note && note.length > MAX_REVIEW_NOTE ||
      decision === "corrected" && !correctedValue || decision !== "corrected" && correctedValue) {
      throw new AccessError("Invalid review correction or note.", 400);
    }
    if (decision === "corrected" && correctedValue) parseCorrectedValue(correctedValue, fieldTypes.get(fieldId) ?? "string");
    parsed.push({ field_id: fieldId, decision: decision as ProductAutoReviewDecision,
      corrected_value: correctedValue, note });
    seen.add(fieldId);
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
    revision, audit_event_id: eventId,
  };
  const machineValues = new Map(detail.candidate.extracted_values.map((item) => [item.field_id, item]));
  const event: ProductAutoAuditEvent = {
    audit_event_id: eventId, revision, created_at: createdAt, reviewer_user_id: reviewerUserId,
    previous_event_id: previous?.audit_event_id ?? null,
    review_snapshot: review,
    machine_fields: parsed.map((field) => {
      const machine = machineValues.get(field.field_id);
      return { field_id: field.field_id, value: machine?.value ?? null,
        status: machine?.status ?? "not_proposed", evidence: machine?.evidence };
    }),
    review_fields: parsed,
    review_added_fields: parsedAdded,
  };
  const directory = auditDir(jobId, runId, docId);
  publishAuditEvent(directory, event);
  return review;
}
