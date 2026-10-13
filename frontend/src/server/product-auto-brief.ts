import fs from "node:fs";
import path from "node:path";
import { createHash, randomUUID } from "node:crypto";
import { AccessError } from "@/server/auth";
import { loadRunnerConfig } from "@/server/config";
import { getJobOrThrow } from "@/server/jobs";
import type { JobStatus } from "@/types/idpo";
import type {
  ProductAutoBriefDetail, ProductAutoBriefField, ProductAutoBriefRevision, ProductAutoBriefSample,
} from "@/types/product-auto-brief";

const JOB_ID = /^[a-f0-9]{32}$/;
const FILE_ID = /^[a-f0-9]{32}$/;
const BRIEF_ID = /^brief_[a-f0-9]{32}$/;
const EVENT_ID = /^[a-f0-9]{32}$/;
const SHA256 = /^[a-f0-9]{64}$/;
const FIELD_ID = /^[\p{L}][\p{L}\p{N}_]{0,63}$/u;
const FIELD_TYPES = new Set(["string", "integer", "decimal", "boolean", "date", "array[object]"]);
const DISALLOWED_TEXT = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/u;
const DISALLOWED_GROUP = /[\u0000-\u001f\u007f]/u;
const MAX_INTENT = 4000;
const MAX_FIELDS = 24;
const MAX_DESCRIPTION = 1000;
const MAX_EXAMPLES = 3;
const MAX_EXAMPLE = 200;
const MAX_SAMPLES = 5;

function ownerForJob(job: JobStatus): string {
  if (!job.ownerUserId) throw new AccessError("An owned job is required for an extraction brief.", 409);
  return job.ownerUserId;
}

function eventDirectory(jobId: string, owner: string): string {
  if (!JOB_ID.test(jobId)) throw new AccessError("Job not found.", 404);
  const ownerKey = createHash("sha256").update(owner).digest("hex");
  return path.join(path.dirname(loadRunnerConfig().runsDir), "frontend", "auto_briefs", ownerKey, jobId, "events");
}

function boundedText(value: unknown, max: number, label: string): string {
  if (typeof value !== "string") throw new AccessError(`${label} must be text.`, 400);
  const text = value.trim();
  if ([...text].length > max || DISALLOWED_TEXT.test(text)) {
    throw new AccessError(`${label} is too long or contains invalid characters.`, 400);
  }
  return text;
}

function parseFields(value: unknown): ProductAutoBriefField[] {
  if (!Array.isArray(value) || value.length > MAX_FIELDS) {
    throw new AccessError("Provide at most 24 typed fields.", 400);
  }
  const ids = new Set<string>();
  return value.map((raw): ProductAutoBriefField => {
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) throw new AccessError("Invalid brief field.", 400);
    const field = raw as Record<string, unknown>;
    if (Object.keys(field).some((key) => !["field_id", "type", "group", "description", "example_values"].includes(key)) ||
      typeof field.field_id !== "string" || !FIELD_ID.test(field.field_id) || field.field_id.endsWith("_") ||
      field.field_id !== field.field_id.normalize("NFKC").toLowerCase() || ids.has(field.field_id) ||
      typeof field.type !== "string" || !FIELD_TYPES.has(field.type)) {
      throw new AccessError("Invalid or repeated brief field ID or type.", 400);
    }
    ids.add(field.field_id);
    const group = field.group;
    if (group !== undefined && (typeof group !== "string" || !group.trim() ||
      group !== group.trim() || [...group].length > 64 || DISALLOWED_GROUP.test(group))) {
      throw new AccessError("Invalid brief field group.", 400);
    }
    if (field.type === "array[object]" && group === undefined) {
      throw new AccessError("A repeated field needs a group.", 400);
    }
    const description = boundedText(field.description ?? "", MAX_DESCRIPTION, "Field description");
    const examples = field.example_values ?? [];
    if (!Array.isArray(examples) || examples.length > MAX_EXAMPLES) {
      throw new AccessError("A field may have at most three examples.", 400);
    }
    const exampleValues = examples.map((example) => {
      const text = boundedText(example, MAX_EXAMPLE, "Field example");
      if (!text) throw new AccessError("Field examples must not be blank.", 400);
      return text;
    });
    return { field_id: field.field_id, type: field.type as ProductAutoBriefField["type"],
      ...(group === undefined ? {} : { group }), description, example_values: exampleValues };
  });
}

export function validateProductAutoBriefFields(value: unknown): ProductAutoBriefField[] {
  return parseFields(value);
}

function sourcePath(jobId: string, storedName: string): string | null {
  const uploadsRoot = path.resolve(loadRunnerConfig().uploadsDir);
  const directory = path.resolve(uploadsRoot, `job_${jobId}`);
  const source = path.resolve(directory, storedName);
  if (path.dirname(directory) !== uploadsRoot || path.dirname(source) !== directory) return null;
  try {
    if (!fs.lstatSync(directory).isDirectory() || !fs.lstatSync(source).isFile()) return null;
  } catch { return null; }
  return source;
}

function currentSourceHash(job: JobStatus, fileId: string): string | null {
  const document = job.documents?.find((item) => item.fileId === fileId);
  if (!document || !FILE_ID.test(fileId)) return null;
  const source = sourcePath(job.jobId, document.storedName);
  if (!source) return null;
  try { return createHash("sha256").update(fs.readFileSync(source)).digest("hex"); }
  catch { return null; }
}

function parseSamples(job: JobStatus, value: unknown): ProductAutoBriefSample[] {
  if (!Array.isArray(value) || value.length < 1 || value.length > MAX_SAMPLES) {
    throw new AccessError("Select 1 to 5 sample files from this job.", 400);
  }
  const seen = new Set<string>();
  return value.map((fileId): ProductAutoBriefSample => {
    if (typeof fileId !== "string" || !FILE_ID.test(fileId) || seen.has(fileId)) {
      throw new AccessError("Invalid or repeated sample file ID.", 400);
    }
    seen.add(fileId);
    const hash = currentSourceHash(job, fileId);
    if (!hash) throw new AccessError("A sample source is unavailable in this job.", 400);
    return { file_id: fileId, source_sha256: hash };
  });
}

function payloadDigest(event: Pick<ProductAutoBriefRevision, "intent" | "fields" | "sample_sources">): string {
  return createHash("sha256").update(JSON.stringify({ intent: event.intent, fields: event.fields,
    sample_sources: event.sample_sources })).digest("hex");
}

function storedFieldsValid(value: unknown): boolean {
  try { return JSON.stringify(parseFields(value)) === JSON.stringify(value); }
  catch { return false; }
}

function storedIntentValid(value: unknown): value is string {
  try { return typeof value === "string" && boundedText(value, MAX_INTENT, "Extraction intent") === value; }
  catch { return false; }
}

function readTrail(jobId: string, owner: string): ProductAutoBriefRevision[] {
  const directory = eventDirectory(jobId, owner);
  if (!fs.existsSync(directory)) return [];
  const names = fs.readdirSync(directory).filter((name) => /^\d{12}\.json$/.test(name)).sort();
  if (!names.length) throw new Error("Extraction brief audit history is invalid.");
  const events = names.map((name) => {
    try { return JSON.parse(fs.readFileSync(path.join(directory, name), "utf8")) as ProductAutoBriefRevision; }
    catch { throw new Error("Extraction brief audit history is invalid."); }
  });
  for (let index = 0; index < events.length; index += 1) {
    const event = events[index];
    const previous = events[index - 1];
    if (!event || event.contract_version !== 1 || !["draft", "confirmed"].includes(event.state) ||
      !BRIEF_ID.test(event.brief_id) || event.brief_id !== (previous?.brief_id ?? event.brief_id) ||
      event.owner_user_id !== owner || event.job_id !== jobId || event.revision !== index + 1 ||
      names[index] !== `${String(event.revision).padStart(12, "0")}.json` ||
      !EVENT_ID.test(event.audit_event_id) || event.previous_event_id !== (previous?.audit_event_id ?? null) ||
      typeof event.actor_user_id !== "string" || !event.actor_user_id ||
      typeof event.created_at !== "string" || !Number.isFinite(Date.parse(event.created_at)) ||
      !SHA256.test(event.payload_sha256) || !Array.isArray(event.fields) ||
      !Array.isArray(event.sample_sources) || event.sample_sources.length < 1 ||
      event.sample_sources.length > MAX_SAMPLES ||
      event.sample_sources.some((sample) => !sample || typeof sample !== "object" ||
        !FILE_ID.test(sample.file_id) || !SHA256.test(sample.source_sha256)) ||
      new Set(event.sample_sources.map((sample) => sample.file_id)).size !== event.sample_sources.length ||
      event.fields.length > MAX_FIELDS || !storedFieldsValid(event.fields) || !storedIntentValid(event.intent) ||
      (!event.intent && event.fields.length === 0) || event.payload_sha256 !== payloadDigest(event) ||
      event.state === "confirmed" && (!previous || previous.state !== "draft" ||
        event.fields.length === 0 || event.payload_sha256 !== previous.payload_sha256 ||
        JSON.stringify(event.sample_sources) !== JSON.stringify(previous.sample_sources))) {
      throw new Error("Extraction brief audit history is invalid.");
    }
  }
  return events;
}

function publishEvent(jobId: string, owner: string, event: ProductAutoBriefRevision): void {
  const directory = eventDirectory(jobId, owner);
  fs.mkdirSync(directory, { recursive: true });
  const target = path.join(directory, `${String(event.revision).padStart(12, "0")}.json`);
  const temporary = path.join(directory, `.${event.audit_event_id}.tmp`);
  let handle: number | undefined;
  try {
    handle = fs.openSync(temporary, "wx", 0o600);
    fs.writeFileSync(handle, JSON.stringify(event, null, 2), "utf8");
    fs.fsyncSync(handle);
    fs.closeSync(handle);
    handle = undefined;
    fs.linkSync(temporary, target);
  } catch (error) {
    if (error && typeof error === "object" && "code" in error && error.code === "EEXIST") {
      throw new AccessError("Extraction brief changed. Reload before saving.", 409);
    }
    throw error;
  } finally {
    if (handle !== undefined) fs.closeSync(handle);
    if (fs.existsSync(temporary)) fs.unlinkSync(temporary);
  }
}

export function getProductAutoBrief(jobId: string): ProductAutoBriefDetail {
  const job = getJobOrThrow(jobId);
  const brief = readTrail(jobId, ownerForJob(job)).at(-1) ?? null;
  return { brief, staleSampleFileIds: brief?.sample_sources
    .filter((sample) => currentSourceHash(job, sample.file_id) !== sample.source_sha256)
    .map((sample) => sample.file_id) ?? [] };
}

/** Future clarification/preview code must pin this revision and digest and recheck sample bytes. */
export function requireCurrentProductAutoBrief(
  jobId: string, expectedRevision: number, expectedPayloadSha256: string,
): ProductAutoBriefRevision {
  const detail = getProductAutoBrief(jobId);
  const brief = detail.brief;
  if (!brief || brief.revision !== expectedRevision || brief.payload_sha256 !== expectedPayloadSha256 ||
    detail.staleSampleFileIds.length > 0) {
    throw new AccessError("Extraction brief or sample source changed. Reload before continuing.", 409);
  }
  return brief;
}

/** Resolve only the pinned job uploads; callers must already enforce job access. */
export function currentProductAutoBriefSampleFiles(
  jobId: string, expectedRevision: number, expectedPayloadSha256: string,
): { file_id: string; source_sha256: string; path: string }[] {
  const brief = requireCurrentProductAutoBrief(jobId, expectedRevision, expectedPayloadSha256);
  const job = getJobOrThrow(jobId);
  return brief.sample_sources.map((sample) => {
    const stored = job.documents?.find((document) => document.fileId === sample.file_id)?.storedName;
    const resolved = stored && sourcePath(jobId, stored);
    if (!resolved) throw new AccessError("A sample source is unavailable in this job.", 409);
    return { file_id: sample.file_id, source_sha256: sample.source_sha256, path: resolved };
  });
}

export function saveProductAutoBrief(jobId: string, actorUserId: string, input: unknown): ProductAutoBriefRevision {
  const job = getJobOrThrow(jobId);
  const owner = ownerForJob(job);
  if (!input || typeof input !== "object" || Array.isArray(input)) {
    throw new AccessError("Invalid extraction brief.", 400);
  }
  const request = input as Record<string, unknown>;
  if (Object.keys(request).some((key) => !["expectedRevision", "intent", "fields", "sampleFileIds"].includes(key)) ||
    !Number.isSafeInteger(request.expectedRevision) || typeof request.expectedRevision !== "number" ||
    request.expectedRevision < 0) {
    throw new AccessError("A valid expected extraction brief revision is required.", 400);
  }
  const current = readTrail(jobId, owner).at(-1);
  if ((current?.revision ?? 0) !== request.expectedRevision) {
    throw new AccessError("Extraction brief changed. Reload before saving.", 409);
  }
  const intent = boundedText(request.intent ?? "", MAX_INTENT, "Extraction intent");
  const fields = parseFields(request.fields ?? []);
  if (!intent && fields.length === 0) {
    throw new AccessError("Describe what to extract or provide typed fields.", 400);
  }
  const sampleSources = parseSamples(job, request.sampleFileIds);
  const event: ProductAutoBriefRevision = {
    contract_version: 1, brief_id: current?.brief_id ?? `brief_${randomUUID().replaceAll("-", "")}`,
    owner_user_id: owner, job_id: jobId, revision: (current?.revision ?? 0) + 1,
    audit_event_id: randomUUID().replaceAll("-", ""), previous_event_id: current?.audit_event_id ?? null,
    actor_user_id: actorUserId, created_at: new Date().toISOString(), state: "draft", intent, fields,
    sample_sources: sampleSources, payload_sha256: payloadDigest({ intent, fields, sample_sources: sampleSources }),
  };
  publishEvent(jobId, owner, event);
  return event;
}

export function confirmProductAutoBrief(jobId: string, actorUserId: string, input: unknown): ProductAutoBriefRevision {
  const job = getJobOrThrow(jobId);
  const owner = ownerForJob(job);
  if (!input || typeof input !== "object" || Array.isArray(input) ||
    Object.keys(input).some((key) => !["expectedRevision", "expectedPayloadSha256"].includes(key))) {
    throw new AccessError("Invalid extraction brief confirmation.", 400);
  }
  const request = input as Record<string, unknown>;
  if (!Number.isSafeInteger(request.expectedRevision) || typeof request.expectedRevision !== "number" ||
    request.expectedRevision < 1 || typeof request.expectedPayloadSha256 !== "string" ||
    !SHA256.test(request.expectedPayloadSha256)) {
    throw new AccessError("Confirm the current extraction brief revision and digest.", 400);
  }
  const current = requireCurrentProductAutoBrief(jobId, request.expectedRevision, request.expectedPayloadSha256);
  if (current.state !== "draft" || current.fields.length === 0 ||
    current.fields.some((field) => !field.description)) {
    throw new AccessError("Describe every typed field in the draft before confirming its schema.", 409);
  }
  const event: ProductAutoBriefRevision = {
    ...current, revision: current.revision + 1, audit_event_id: randomUUID().replaceAll("-", ""),
    previous_event_id: current.audit_event_id, actor_user_id: actorUserId,
    created_at: new Date().toISOString(), state: "confirmed",
  };
  publishEvent(jobId, owner, event);
  return event;
}
