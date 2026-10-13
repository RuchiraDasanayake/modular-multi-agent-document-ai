import assert from "node:assert/strict";
import test from "node:test";
import { idpoApi } from "./idpo-api";
import { clearPendingProductAutoRunRequest, pendingProductAutoRunRequest,
  reserveProductAutoRunRequest } from "./product-auto-run-request";

class MemoryStorage implements Storage {
  private readonly entries = new Map<string, string>();
  get length(): number { return this.entries.size; }
  clear(): void { this.entries.clear(); }
  getItem(key: string): string | null { return this.entries.get(key) ?? null; }
  key(index: number): string | null { return [...this.entries.keys()][index] ?? null; }
  removeItem(key: string): void { this.entries.delete(key); }
  setItem(key: string, value: string): void { this.entries.set(key, value); }
}

test("browser preserves a paid run request key after a lost response and refuses changed options", () => {
  const storage = new MemoryStorage();
  const jobId = "a".repeat(32);
  const payload = { selectedFileIds: ["source-1"], confirmedBrief: {
    expectedRevision: 2, payloadSha256: "b".repeat(64), phase: "preview" as const,
  } };
  const first = reserveProductAutoRunRequest(storage, jobId, payload);
  assert.match(first.key, /^[a-f0-9]{32}$/);
  assert.equal(reserveProductAutoRunRequest(storage, jobId, structuredClone(payload)).key, first.key);
  assert.deepEqual(pendingProductAutoRunRequest(storage, jobId), first);
  assert.throws(() => reserveProductAutoRunRequest(storage, jobId,
    { ...payload, selectedFileIds: ["source-2"] }), /previous extraction start/);
  clearPendingProductAutoRunRequest(storage, jobId, "c".repeat(32));
  assert.equal(pendingProductAutoRunRequest(storage, jobId)?.key, first.key);
  clearPendingProductAutoRunRequest(storage, jobId, first.key);
  assert.equal(pendingProductAutoRunRequest(storage, jobId), null);
});

test("damaged browser request receipt fails closed", () => {
  const storage = new MemoryStorage();
  const jobId = "d".repeat(32);
  storage.setItem(`docai:auto-run-request:${jobId}`, "{broken");
  assert.throws(() => reserveProductAutoRunRequest(storage, jobId,
    { selectedFileIds: ["source-1"] }), /damaged/);
});

test("product run client forwards only the reserved key as a request header", async () => {
  const previous = globalThis.fetch;
  const captured: Array<{ input: string; headers: Headers; body: string }> = [];
  globalThis.fetch = async (input, init) => {
    captured.push({ input: String(input), headers: new Headers(init?.headers), body: String(init?.body) });
    return Response.json({ runId: `auto_${"e".repeat(32)}`, status: "queued" });
  };
  try {
    await idpoApi.startProductAutoRun("f".repeat(32), ["source-1"], undefined, undefined, "e".repeat(32));
    assert.equal(captured.length, 1);
    assert.equal(captured[0].headers.get("Idempotency-Key"), "e".repeat(32));
    assert.deepEqual(JSON.parse(captured[0].body), { selectedFileIds: ["source-1"] });
  } finally { globalThis.fetch = previous; }
});
