import fs from "node:fs";
import path from "node:path";
import { createHash, randomUUID } from "node:crypto";
import { AccessError } from "@/server/auth";
import { loadRunnerConfig } from "@/server/config";
import { getJobOrThrow } from "@/server/jobs";
import { getProductAutoDocument } from "@/server/product-auto";
import type { ProductAutoDocumentDetail, ProductAutoField } from "@/types/product-auto";
import type {
  ProductAutoRecipeDetail,
  ProductAutoRecipeRevision,
  ProductAutoRecipeRowGroup,
  ProductAutoRecipeSourceReview,
} from "@/types/product-auto-recipes";

const RECIPE_ID = /^recipe_[a-f0-9]{32}$/;
const FIELD_ID = /^[\p{L}][\p{L}\p{N}_]{0,63}$/u;
const EVENT_ID = /^[a-f0-9]{32}$/;
const SHA256 = /^[a-f0-9]{64}$/;
const MAX_FIELDS = 24;
const MAX_LINKED_ROWS = 128;
const FIELD_TYPES = new Set(["string", "integer", "decimal", "boolean", "date", "array[object]"]);

function canonicalId(value: string): boolean {
  return FIELD_ID.test(value) && !value.endsWith("_") && value === value.normalize("NFKC").toLowerCase();
}

function validGroup(value: string): boolean {
  return value.length > 0 && [...value].length <= 64 && value.trim() === value &&
    !/[\u0000-\u001f\u007f]/u.test(value);
}

function ownerForJob(jobId: string): string {
  const owner = getJobOrThrow(jobId).ownerUserId;
  if (!owner) throw new AccessError("An owner is required to create or use a recipe.", 409);
  return owner;
}

function ownerDirectory(owner: string): string {
  const ownerKey = createHash("sha256").update(owner).digest("hex");
  return path.join(path.dirname(loadRunnerConfig().runsDir), "frontend", "auto_recipes", ownerKey);
}

function eventDirectory(owner: string, recipeId: string): string {
  if (!RECIPE_ID.test(recipeId)) throw new AccessError("Recipe not found.", 404);
  return path.join(ownerDirectory(owner), recipeId, "events");
}

function sourceDigest(detail: ProductAutoDocumentDetail): string {
  return createHash("sha256").update(JSON.stringify({ candidate: detail.candidate, review: detail.review })).digest("hex");
}

function parseFamilyName(value: unknown): string {
  if (typeof value !== "string") throw new AccessError("A family name is required.", 400);
  const name = value.trim();
  if (name.length < 2 || name.length > 100 || /[\u0000-\u001f\u007f]/u.test(name)) {
    throw new AccessError("Family name must be 2 to 100 printable characters.", 400);
  }
  return name;
}

function validTypedValue(value: unknown, type: string): boolean {
  if (type === "string") return typeof value === "string" && value.trim().length > 0;
  if (type === "boolean") return typeof value === "boolean";
  if (type === "integer") return typeof value === "number" && Number.isSafeInteger(value);
  if (type === "decimal") return typeof value === "number" && Number.isFinite(value) && Math.abs(value) <= Number.MAX_SAFE_INTEGER;
  if (type === "date") {
    if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    const parsed = new Date(`${value}T00:00:00Z`);
    return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
  }
  return false;
}

function validEvidence(value: unknown): boolean {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const evidence = value as Record<string, unknown>;
  return typeof evidence.page === "number" && Number.isInteger(evidence.page) && evidence.page > 0 &&
    typeof evidence.start === "number" && Number.isInteger(evidence.start) && evidence.start >= 0 &&
    typeof evidence.end === "number" && Number.isInteger(evidence.end) && evidence.end > evidence.start &&
    typeof evidence.quote === "string" && evidence.quote.length > 0;
}

function linkedRowIds(value: unknown): Set<number> {
  if (!Array.isArray(value) || value.length < 1 || value.length > MAX_LINKED_ROWS) {
    throw new AccessError("A linked field needs 1 to 128 reviewed cells.", 400);
  }
  const seen = new Set<number>();
  for (const cell of value) {
    if (!cell || typeof cell !== "object" || Array.isArray(cell)) {
      throw new AccessError("Invalid linked cell.", 400);
    }
    const linkedCell = cell as Record<string, unknown>;
    const row = linkedCell.row;
    const text = linkedCell.value;
    if (typeof row !== "number" || !Number.isInteger(row) || row < 0 || row >= MAX_LINKED_ROWS ||
      seen.has(row) || typeof text !== "string" || !text.trim() || [...text].length > 500 ||
      "status" in linkedCell && linkedCell.status !== "accepted" ||
      "evidence" in linkedCell && !validEvidence(linkedCell.evidence)) {
      throw new AccessError("Invalid linked row index or cell value.", 400);
    }
    seen.add(row);
  }
  return seen;
}

function reviewedSchema(detail: ProductAutoDocumentDetail): {
  fields: ProductAutoField[];
  rowGroups: ProductAutoRecipeRowGroup[];
} {
  if (detail.candidate.document_status === "failed" || detail.candidate.document_status === "unsupported") {
    throw new AccessError("Failed or unsupported documents cannot seed a recipe.", 409);
  }
  const review = detail.review;
  if (!review || review.status !== "completed" || detail.correctedResult.review_status !== "completed") {
    throw new AccessError("Complete the document review before drafting a recipe.", 409);
  }
  if (review.fields.some((field) => field.decision === "incorrect" || field.decision === "not_present")) {
    throw new AccessError("Resolve incorrect and absent-field decisions before drafting a recipe.", 400);
  }
  const resultFields = detail.correctedResult.fields;
  if (resultFields.length < 1 || resultFields.length > MAX_FIELDS) {
    throw new AccessError("A recipe needs 1 to 24 reviewed fields.", 400);
  }
  const seenIds = new Set<string>();
  const linkedByGroup = new Map<string, Array<{ fieldId: string; rows: Set<number> }>>();
  const scalarGroups = new Set<string>();
  const fields = resultFields.map((field) => {
    const fieldId = field.field_id;
    const fieldType = field.type;
    const group = field.group;
    if (!canonicalId(fieldId) || seenIds.has(fieldId) || !FIELD_TYPES.has(fieldType) ||
      group !== undefined && !validGroup(group) || field.status !== "accepted" ||
      field.provenance === "machine" ||
      field.provenance === "human_added" && fieldType !== "array[object]" && !validEvidence(field.evidence)) {
      throw new AccessError("Recipe schema contains an unreviewed or invalid field.", 400);
    }
    seenIds.add(fieldId);
    if (fieldType === "array[object]") {
      if (!group) throw new AccessError("Linked columns need a canonical group name.", 400);
      const columns = linkedByGroup.get(group) ?? [];
      const rows = linkedRowIds(field.value);
      if (field.provenance === "human_added" &&
        (field.value as Array<Record<string, unknown>>).some((cell) => !validEvidence(cell.evidence))) {
        throw new AccessError("Human-added linked cells need source evidence.", 400);
      }
      columns.push({ fieldId, rows });
      linkedByGroup.set(group, columns);
    } else {
      if (!validTypedValue(field.value, fieldType)) {
        throw new AccessError("Recipe schema has a value that does not match its type.", 400);
      }
      if (group) scalarGroups.add(group);
    }
    return { field_id: fieldId, type: fieldType, ...(group ? { group } : {}) };
  });
  const rowGroups: ProductAutoRecipeRowGroup[] = [];
  for (const [group, columns] of linkedByGroup) {
    if (scalarGroups.has(group) || columns.length < 2) {
      throw new AccessError("A linked group needs at least two linked columns and no scalar columns.", 400);
    }
    const rowCounts = new Map<number, number>();
    for (const column of columns) {
      for (const row of column.rows) rowCounts.set(row, (rowCounts.get(row) ?? 0) + 1);
    }
    if (columns.some((column) => ![...column.rows].some((row) => (rowCounts.get(row) ?? 0) > 1))) {
      throw new AccessError("Every linked column needs a reviewed row shared with another column.", 400);
    }
    rowGroups.push({ group, field_ids: columns.map((column) => column.fieldId).sort(), alignment: "shared_ordinal" });
  }
  return { fields, rowGroups: rowGroups.sort((left, right) => left.group.localeCompare(right.group)) };
}

function sourceReview(jobId: string, runId: string, docId: string, expectedReviewRevision: number): {
  source: ProductAutoRecipeSourceReview;
  fields: ProductAutoField[];
  rowGroups: ProductAutoRecipeRowGroup[];
} {
  if (!Number.isSafeInteger(expectedReviewRevision) || expectedReviewRevision < 1) {
    throw new AccessError("A completed review revision is required.", 400);
  }
  const detail = getProductAutoDocument(jobId, runId, docId);
  if (!detail.review || detail.review.revision !== expectedReviewRevision) {
    throw new AccessError("Source review changed. Reload before creating or approving the recipe.", 409);
  }
  const schema = reviewedSchema(detail);
  return {
    source: {
      job_id: jobId,
      run_id: runId,
      doc_id: docId,
      review_revision: detail.review.revision,
      review_audit_event_id: detail.review.audit_event_id,
      source_digest_sha256: sourceDigest(detail),
    },
    ...schema,
  };
}

function storedSchemaValid(event: ProductAutoRecipeRevision): boolean {
  if (!Array.isArray(event.fields) || event.fields.length < 1 || event.fields.length > MAX_FIELDS ||
    !Array.isArray(event.row_groups) || !Array.isArray(event.confirmed_row_groups)) return false;
  const fieldIds = new Set<string>();
  const linked = new Map<string, string[]>();
  const scalarGroups = new Set<string>();
  for (const field of event.fields) {
    if (!field || typeof field !== "object" || typeof field.field_id !== "string" ||
      !canonicalId(field.field_id) || fieldIds.has(field.field_id) || !FIELD_TYPES.has(field.type) ||
      field.group !== undefined && (typeof field.group !== "string" || !validGroup(field.group))) return false;
    fieldIds.add(field.field_id);
    if (field.type === "array[object]") {
      if (!field.group) return false;
      linked.set(field.group, [...(linked.get(field.group) ?? []), field.field_id]);
    } else if (field.group) {
      scalarGroups.add(field.group);
    }
  }
  const expectedGroups = [...linked.entries()].sort(([a], [b]) => a.localeCompare(b));
  if (expectedGroups.some(([group, fieldIds]) => scalarGroups.has(group) || fieldIds.length < 2) ||
    event.row_groups.length !== expectedGroups.length) return false;
  for (let index = 0; index < expectedGroups.length; index += 1) {
    const group = event.row_groups[index];
    if (!group || group.group !== expectedGroups[index][0] || group.alignment !== "shared_ordinal" ||
      !Array.isArray(group.field_ids) ||
      JSON.stringify(group.field_ids) !== JSON.stringify(expectedGroups[index][1].sort())) return false;
  }
  const confirmed = event.row_groups.map((group) => group.group);
  return event.state === "draft"
    ? event.confirmed_row_groups.length === 0
    : JSON.stringify(event.confirmed_row_groups) === JSON.stringify(confirmed);
}

function readTrail(owner: string, recipeId: string): ProductAutoRecipeRevision[] {
  const directory = eventDirectory(owner, recipeId);
  if (!fs.existsSync(directory)) throw new AccessError("Recipe not found.", 404);
  const names = fs.readdirSync(directory).filter((name) => /^\d{12}\.json$/.test(name)).sort();
  if (!names.length) throw new AccessError("Recipe not found.", 404);
  if (names.length > 3) throw new Error("Recipe audit history is invalid.");
  const events = names.map((name) => JSON.parse(fs.readFileSync(path.join(directory, name), "utf8")) as ProductAutoRecipeRevision);
  for (let index = 0; index < events.length; index += 1) {
    const event = events[index];
    const previous = events[index - 1];
    const expectedAction = index === 0 ? "draft_created" : index === 1 ? "approved_shadow" : "disabled";
    if (!event || event.contract_version !== 1 || event.recipe_id !== recipeId ||
      event.owner_user_id !== owner || event.revision !== index + 1 ||
      names[index] !== `${String(event.revision).padStart(12, "0")}.json` ||
      !EVENT_ID.test(event.audit_event_id) || event.previous_event_id !== (previous?.audit_event_id ?? null) ||
      event.action !== expectedAction || event.state !== (index === 0 ? "draft" : expectedAction) ||
      typeof event.actor_user_id !== "string" || !event.actor_user_id ||
      typeof event.created_at !== "string" || !event.created_at ||
      typeof event.family_name !== "string" || !event.family_name ||
      !storedSchemaValid(event) ||
      !event.source_review || event.source_review.review_revision < 1 ||
      !EVENT_ID.test(event.source_review.review_audit_event_id) ||
      !SHA256.test(event.source_review.source_digest_sha256) ||
      previous && (event.family_name !== previous.family_name ||
        JSON.stringify(event.fields) !== JSON.stringify(previous.fields) ||
        JSON.stringify(event.row_groups) !== JSON.stringify(previous.row_groups) ||
        JSON.stringify(event.source_review) !== JSON.stringify(previous.source_review))) {
      throw new Error("Recipe audit history is invalid.");
    }
  }
  return events;
}

function publishEvent(owner: string, event: ProductAutoRecipeRevision): void {
  const directory = eventDirectory(owner, event.recipe_id);
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
    // One immutable file contains both the revision and audit event; linking is an atomic CAS.
    fs.linkSync(temporary, target);
  } catch (error) {
    if (error && typeof error === "object" && "code" in error && error.code === "EEXIST") {
      throw new AccessError("Recipe changed since you opened it. Reload before saving.", 409);
    }
    throw error;
  } finally {
    if (handle !== undefined) fs.closeSync(handle);
    if (fs.existsSync(temporary)) fs.unlinkSync(temporary);
  }
}

export function listProductAutoRecipes(jobId: string): ProductAutoRecipeRevision[] {
  const owner = ownerForJob(jobId);
  const directory = ownerDirectory(owner);
  if (!fs.existsSync(directory)) return [];
  return fs.readdirSync(directory, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && RECIPE_ID.test(entry.name))
    .map((entry) => readTrail(owner, entry.name).at(-1)!)
    .sort((left, right) => right.created_at.localeCompare(left.created_at));
}

export function getProductAutoRecipe(jobId: string, recipeId: string): ProductAutoRecipeDetail {
  const auditTrail = readTrail(ownerForJob(jobId), recipeId);
  return { recipe: auditTrail.at(-1)!, auditTrail };
}

export function createProductAutoRecipeDraft(
  jobId: string, runId: string, docId: string, actorUserId: string,
  expectedReviewRevision: number, familyName: unknown,
): ProductAutoRecipeRevision {
  const owner = ownerForJob(jobId);
  const name = parseFamilyName(familyName);
  const { source, fields, rowGroups } = sourceReview(jobId, runId, docId, expectedReviewRevision);
  const event: ProductAutoRecipeRevision = {
    contract_version: 1,
    recipe_id: `recipe_${randomUUID().replaceAll("-", "")}`,
    owner_user_id: owner,
    revision: 1,
    audit_event_id: randomUUID().replaceAll("-", ""),
    previous_event_id: null,
    action: "draft_created",
    state: "draft",
    actor_user_id: actorUserId,
    created_at: new Date().toISOString(),
    family_name: name,
    fields,
    row_groups: rowGroups,
    source_review: source,
    confirmed_row_groups: [],
  };
  publishEvent(owner, event);
  return event;
}

export function transitionProductAutoRecipe(
  jobId: string, recipeId: string, actorUserId: string, expectedRevision: number,
  action: "approve" | "disable", confirmedRowGroups: unknown,
): ProductAutoRecipeRevision {
  const owner = ownerForJob(jobId);
  if (!Number.isSafeInteger(expectedRevision) || expectedRevision < 1) {
    throw new AccessError("A valid expected recipe revision is required.", 400);
  }
  const current = readTrail(owner, recipeId).at(-1)!;
  if (current.revision !== expectedRevision) {
    throw new AccessError("Recipe changed since you opened it. Reload before saving.", 409);
  }
  let confirmedGroups = current.confirmed_row_groups;
  if (action === "approve") {
    if (current.state !== "draft") throw new AccessError("Only a draft can be approved.", 409);
    if (!Array.isArray(confirmedRowGroups) ||
      confirmedRowGroups.some((group) => typeof group !== "string") ||
      JSON.stringify([...confirmedRowGroups].sort()) !== JSON.stringify(current.row_groups.map((group) => group.group))) {
      throw new AccessError("Confirm every reviewed linked-row group before approval.", 400);
    }
    confirmedGroups = [...confirmedRowGroups].sort();
    if (ownerForJob(current.source_review.job_id) !== owner) {
      throw new AccessError("Source review owner changed.", 409);
    }
    const checked = sourceReview(current.source_review.job_id, current.source_review.run_id,
      current.source_review.doc_id, current.source_review.review_revision);
    if (JSON.stringify(checked.source) !== JSON.stringify(current.source_review) ||
      JSON.stringify(checked.fields) !== JSON.stringify(current.fields) ||
      JSON.stringify(checked.rowGroups) !== JSON.stringify(current.row_groups)) {
      throw new AccessError("Source review changed. Create a new draft.", 409);
    }
  } else if (action === "disable") {
    if (current.state !== "approved_shadow") throw new AccessError("Only an approved recipe can be disabled.", 409);
  } else {
    throw new AccessError("Invalid recipe action.", 400);
  }
  const event: ProductAutoRecipeRevision = {
    ...current,
    revision: current.revision + 1,
    audit_event_id: randomUUID().replaceAll("-", ""),
    previous_event_id: current.audit_event_id,
    action: action === "approve" ? "approved_shadow" : "disabled",
    state: action === "approve" ? "approved_shadow" : "disabled",
    actor_user_id: actorUserId,
    created_at: new Date().toISOString(),
    confirmed_row_groups: confirmedGroups,
  };
  publishEvent(owner, event);
  return event;
}
