import fs from "node:fs";
import path from "node:path";
import { AccessError } from "./auth";

const ID = /^[a-f0-9]{32}$/;
const RUN_ID = /^auto_[a-f0-9]{32}$/;
const HASH = /^[a-f0-9]{64}$/;

export interface ProductAutoRunRequestReceipt {
  contractVersion: 1;
  jobId: string;
  runId: string;
  actorUserId: string;
  jobOwnerUserId: string | null;
  payloadSha256: string;
}

export function validProductAutoRunRequestKey(key: string): boolean {
  return ID.test(key);
}

function receiptPath(storageRoot: string, jobId: string, key: string): string {
  if (!ID.test(jobId) || !ID.test(key)) throw new AccessError("Invalid extraction request key.", 400);
  return path.join(storageRoot, "frontend", "auto_run_requests", jobId, `${key}.json`);
}

export function readProductAutoRunRequestReceipt(
  storageRoot: string, jobId: string, key: string,
): ProductAutoRunRequestReceipt | null {
  const file = receiptPath(storageRoot, jobId, key);
  if (!fs.existsSync(file)) return null;
  let value: unknown;
  try { value = JSON.parse(fs.readFileSync(file, "utf8")); }
  catch { throw new AccessError("Extraction request receipt is incomplete; inspect runs before retrying.", 409); }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new AccessError("Extraction request receipt is invalid.", 409);
  }
  const receipt = value as Record<string, unknown>;
  if (Object.keys(receipt).sort().join(",") !==
      "actorUserId,contractVersion,jobId,jobOwnerUserId,payloadSha256,runId" ||
    receipt.contractVersion !== 1 || receipt.jobId !== jobId ||
    typeof receipt.runId !== "string" || !RUN_ID.test(receipt.runId) ||
    typeof receipt.actorUserId !== "string" || !receipt.actorUserId ||
    receipt.jobOwnerUserId !== null &&
      (typeof receipt.jobOwnerUserId !== "string" || !receipt.jobOwnerUserId) ||
    typeof receipt.payloadSha256 !== "string" || !HASH.test(receipt.payloadSha256)) {
    throw new AccessError("Extraction request receipt is invalid.", 409);
  }
  return receipt as unknown as ProductAutoRunRequestReceipt;
}

/** Claim an attempt before staging or queue admission. Never erase a claim after an uncertain failure. */
export function claimProductAutoRunRequestReceipt(
  storageRoot: string, jobId: string, key: string, receipt: ProductAutoRunRequestReceipt,
): boolean {
  const file = receiptPath(storageRoot, jobId, key);
  if (receipt.jobId !== jobId || !RUN_ID.test(receipt.runId) ||
    !receipt.actorUserId || typeof receipt.actorUserId !== "string" ||
    !HASH.test(receipt.payloadSha256)) {
    throw new AccessError("Invalid extraction request receipt.", 400);
  }
  fs.mkdirSync(path.dirname(file), { recursive: true });
  let handle: number;
  try { handle = fs.openSync(file, "wx", 0o600); }
  catch (error) {
    if (error && typeof error === "object" && "code" in error && error.code === "EEXIST") return false;
    throw error;
  }
  try {
    fs.writeFileSync(handle, JSON.stringify(receipt), "utf8");
    fs.fsyncSync(handle);
  } finally { fs.closeSync(handle); }
  return true;
}
