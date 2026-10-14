import assert from "node:assert/strict";
import test from "node:test";
import type { ProductAutoRun } from "@/types/product-auto";
import { ProductAutoRunRefresh } from "./product-auto-run-refresh";

function delayed<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((accept, fail) => { resolve = accept; reject = fail; });
  return { promise, resolve, reject };
}

function run(id: string): ProductAutoRun {
  return { runId: id, status: "queued", createdAt: "2026-10-14T00:00:00Z", selectedCount: 1, documents: [] };
}

test("a list response begun before admission cannot remove the newly queued run or reconcile an older request", async () => {
  const oldRead = delayed<ProductAutoRun[]>();
  let shown: ProductAutoRun[] = [run("old")];
  let reconciled = false;
  const refresh = new ProductAutoRunRefresh((runs) => { shown = runs; }, () => undefined);
  const pending = refresh.refresh(() => oldRead.promise, () => { reconciled = true; });
  const completeAdmission = refresh.beginAdmission();
  let duringAdmissionCalls = 0;
  await refresh.refresh(async () => { duringAdmissionCalls += 1; return []; });
  assert.equal(duringAdmissionCalls, 0);
  completeAdmission();
  shown = [run("new"), ...shown];
  oldRead.resolve([run("old")]);
  await pending;
  assert.deepEqual(shown.map((item) => item.runId), ["new", "old"]);
  assert.equal(shown.some((item) => item.status === "queued"), true);
  assert.equal(reconciled, false);
  await refresh.refresh(async () => [run("new"), run("old")]);
  assert.deepEqual(shown.map((item) => item.runId), ["new", "old"]);
});

test("old refresh completion cannot clear the busy state of a later refresh", async () => {
  const oldRead = delayed<ProductAutoRun[]>();
  const currentRead = delayed<ProductAutoRun[]>();
  let busy = false;
  let shown: ProductAutoRun[] = [];
  const refresh = new ProductAutoRunRefresh((runs) => { shown = runs; }, (value) => { busy = value; });
  const old = refresh.refresh(() => oldRead.promise);
  const finish = refresh.beginAdmission();
  finish();
  const current = refresh.refresh(() => currentRead.promise);
  oldRead.resolve([]);
  await old;
  assert.equal(busy, true);
  currentRead.resolve([run("current")]);
  await current;
  assert.equal(busy, false);
  assert.equal(shown[0].runId, "current");
});

test("focus and polling share one read and current reconciliation still runs", async () => {
  const response = delayed<ProductAutoRun[]>();
  let requests = 0;
  let reconciled: string | undefined;
  const refresh = new ProductAutoRunRefresh(() => undefined, () => undefined);
  const load = () => { requests += 1; return response.promise; };
  const focus = refresh.refresh(load);
  const polling = refresh.refresh(load);
  const checkRequest = refresh.refresh(load, (runs) => { reconciled = runs[0]?.runId; });
  response.resolve([run("accepted")]);
  await Promise.all([focus, polling, checkRequest]);
  assert.equal(requests, 1);
  assert.equal(reconciled, "accepted");
});

test("old errors stay hidden after invalidation and failed admission permits a fresh read", async () => {
  const response = delayed<ProductAutoRun[]>();
  let applied = 0;
  const refresh = new ProductAutoRunRefresh(() => { applied += 1; }, () => undefined);
  const pending = refresh.refresh(() => response.promise);
  const finish = refresh.beginAdmission();
  try { throw new Error("admission failed"); }
  catch { /* The caller keeps its existing request receipt and reports admission failure. */ }
  finally { finish(); }
  response.reject(new Error("stale network failure"));
  await assert.doesNotReject(pending);
  assert.equal(applied, 0);
  await assert.rejects(refresh.refresh(async () => { throw new Error("current network failure"); }), /current network/);
  await refresh.refresh(async () => []);
  assert.equal(applied, 1);
});

test("job navigation invalidates both list application and reconciliation callbacks", async () => {
  const response = delayed<ProductAutoRun[]>();
  let applied = 0;
  let reconciled = 0;
  const refresh = new ProductAutoRunRefresh(() => { applied += 1; }, () => undefined);
  const pending = refresh.refresh(() => response.promise, () => { reconciled += 1; });
  refresh.invalidate();
  response.resolve([run("old-job")]);
  await pending;
  assert.deepEqual([applied, reconciled], [0, 0]);
});
