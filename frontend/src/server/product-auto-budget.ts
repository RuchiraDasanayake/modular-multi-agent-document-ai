import fs from "node:fs";
import path from "node:path";
import { AccessError } from "./auth";

export const MAX_PRODUCT_LOGICAL_DOCUMENTS = 5000;
export const MAX_PRODUCT_SOURCE_BYTES = 20 * 1024 * 1024;

export interface ProductBudgetSource {
  name: string;
  path: string;
}

function jsonDocumentCount(file: string): number {
  const descriptor = fs.openSync(file, "r");
  try {
    const stat = fs.fstatSync(descriptor);
    if (!stat.isFile()) throw new AccessError("An extraction source is unavailable.", 409);
    if (stat.size > MAX_PRODUCT_SOURCE_BYTES) throw new AccessError("An extraction source exceeds 20 MiB.", 413);
    const bytes = Buffer.allocUnsafe(stat.size);
    let offset = 0;
    while (offset < bytes.length) {
      const read = fs.readSync(descriptor, bytes, offset, bytes.length - offset, offset);
      if (!read) break;
      offset += read;
    }
    if (offset !== bytes.length || fs.fstatSync(descriptor).size !== stat.size) {
      throw new AccessError("An extraction source changed during budget preparation.", 409);
    }
    let value: unknown;
    try { value = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)); }
    catch { return 1; }
    // Invalid entries may become a single parser failure. Reserve their upper
    // bound without interpreting schemas or suppressing that failure outcome.
    return Array.isArray(value) ? Math.max(1, value.length) : 1;
  } finally { fs.closeSync(descriptor); }
}

/** Count admitted immutable copies before queue admission or direct execution. */
export function plannedProductLogicalDocuments(sources: readonly ProductBudgetSource[]): number {
  if (!sources.length) throw new AccessError("Select one or more extraction sources.", 400);
  if (sources.length > MAX_PRODUCT_LOGICAL_DOCUMENTS) {
    throw new AccessError(`An extraction run may contain at most ${MAX_PRODUCT_LOGICAL_DOCUMENTS} logical documents.`, 413);
  }
  let total = 0;
  for (const source of sources) {
    total += path.extname(source.name).toLowerCase() === ".json" ? jsonDocumentCount(source.path) : 1;
    if (total > MAX_PRODUCT_LOGICAL_DOCUMENTS) {
      throw new AccessError(`An extraction run may contain at most ${MAX_PRODUCT_LOGICAL_DOCUMENTS} logical documents.`, 413);
    }
  }
  return total;
}
