export interface ProductAutoRunPayload {
  selectedFileIds: string[];
  approvedRecipe?: { recipeId: string; expectedRevision: number };
  confirmedBrief?: { expectedRevision: number; payloadSha256: string; phase: "preview" | "batch";
    previewRunId?: string };
}

export interface PendingProductAutoRunRequest {
  contractVersion: 1;
  key: string;
  payload: ProductAutoRunPayload;
}

const ID = /^[a-f0-9]{32}$/;

function storageKey(jobId: string): string {
  if (!ID.test(jobId)) throw new Error("Invalid job identity for extraction request.");
  return `docai:auto-run-request:${jobId}`;
}

function samePayload(left: ProductAutoRunPayload, right: ProductAutoRunPayload): boolean {
  return JSON.stringify(left) === JSON.stringify(right);
}

export function pendingProductAutoRunRequest(storage: Storage, jobId: string): PendingProductAutoRunRequest | null {
  const raw = storage.getItem(storageKey(jobId));
  if (raw === null) return null;
  let value: unknown;
  try { value = JSON.parse(raw); }
  catch { throw new Error("The previous extraction request receipt is damaged. Inspect runs before continuing."); }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("The previous extraction request receipt is invalid. Inspect runs before continuing.");
  }
  const receipt = value as Record<string, unknown>;
  const payload = receipt.payload;
  if (Object.keys(receipt).sort().join(",") !== "contractVersion,key,payload" ||
    receipt.contractVersion !== 1 || typeof receipt.key !== "string" || !ID.test(receipt.key) ||
    !payload || typeof payload !== "object" || Array.isArray(payload) ||
    !Array.isArray((payload as Record<string, unknown>).selectedFileIds) ||
    !(payload as { selectedFileIds: unknown[] }).selectedFileIds.every((item) => typeof item === "string")) {
    throw new Error("The previous extraction request receipt is invalid. Inspect runs before continuing.");
  }
  return receipt as unknown as PendingProductAutoRunRequest;
}

/** Keep the same key across a lost HTTP response; changing the request needs an explicit reset. */
export function reserveProductAutoRunRequest(storage: Storage, jobId: string,
  payload: ProductAutoRunPayload): PendingProductAutoRunRequest {
  const pending = pendingProductAutoRunRequest(storage, jobId);
  if (pending) {
    if (!samePayload(pending.payload, payload)) {
      throw new Error("A previous extraction start may have been accepted. Refresh runs and resolve it before changing the request.");
    }
    return pending;
  }
  const receipt: PendingProductAutoRunRequest = { contractVersion: 1,
    key: crypto.randomUUID().replaceAll("-", ""), payload };
  storage.setItem(storageKey(jobId), JSON.stringify(receipt));
  return receipt;
}

export function clearPendingProductAutoRunRequest(storage: Storage, jobId: string, key: string): void {
  if (pendingProductAutoRunRequest(storage, jobId)?.key === key) storage.removeItem(storageKey(jobId));
}
