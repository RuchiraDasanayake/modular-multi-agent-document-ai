import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { NextRequest } from "next/server";
import { proxy } from "../proxy";
import { recoveryReadOnlyResponse } from "../lib/recovery-access";
import { POST as upload } from "../app/api/jobs/[jobId]/documents/route";
import { register } from "../instrumentation";

test("passive recovery refuses mutations before authentication or upload body parsing", async () => {
  const old = process.env.IDPO_RECOVERY_READ_ONLY;
  process.env.IDPO_RECOVERY_READ_ONLY = "1";
  try {
    for (const endpoint of ["/api/jobs", "/api/jobs/job/auto", "/api/jobs/job/brief/suggest",
      "/api/jobs/job/review", "/api/idpo/process", "/api/auth/register", "/api/auth/logout"]) {
      for (const method of ["POST", "PUT", "PATCH", "DELETE"]) {
        const response = await proxy(new NextRequest(`http://localhost${endpoint}`, { method }));
        assert.equal(response.status, 423, `${method} ${endpoint}`);
        assert.equal(response.headers.get("x-docai-recovery"), "read-only");
      }
    }
    const request = new Request("http://localhost/api/jobs/job/documents", { method: "POST", body: "must-not-be-read" });
    const response = await upload(request, { params: Promise.resolve({ jobId: "job" }) });
    assert.equal(response.status, 423);
    assert.equal(request.bodyUsed, false);
  } finally {
    if (old === undefined) delete process.env.IDPO_RECOVERY_READ_ONLY;
    else process.env.IDPO_RECOVERY_READ_ONLY = old;
  }
});

test("passive allowlist is exact, marks readiness and still authenticates artifact reads", async () => {
  process.env.IDPO_RECOVERY_READ_ONLY = "1";
  try {
    for (const endpoint of ["/api/jobs/job/docs/doc/content", "/api/jobs/job/auto/run/export"]) {
      const response = await proxy(new NextRequest(`http://localhost${endpoint}`));
      assert.equal(response.status, 401);
      assert.equal(response.headers.get("x-docai-recovery"), "read-only");
    }
    for (const endpoint of ["/api/jobs", "/dashboard", "/api/auth/refresh", "/api/jobs/job/auto/run/export?anything=1",
      "/api/jobs/job/auto/run/export/extra", "/api/jobs/job/docs/doc/content/"]) {
      assert.equal((await proxy(new NextRequest(`http://localhost${endpoint}`))).status, 423, endpoint);
    }
    const login = await proxy(new NextRequest("http://localhost/api/auth/login", { method: "POST" }));
    assert.equal(login.headers.get("x-middleware-next"), "1");
    const health = await proxy(new NextRequest("http://localhost/api/health"));
    assert.equal(health.headers.get("x-docai-recovery"), "read-only");
  } finally { delete process.env.IDPO_RECOVERY_READ_ONLY; }
  assert.equal(recoveryReadOnlyResponse(new Request("http://localhost/api/jobs", { method: "POST" })), null);
});

test("passive registration cannot schedule the copied-run reconciliation loop", async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "recovery-record-"));
  const record = path.join(directory, "stale.json");
  const bytes = '{"status":"running","createdAt":"2000-01-01T00:00:00Z"}';
  fs.writeFileSync(record, bytes);
  const original = globalThis.setInterval;
  const runtime = process.env.NEXT_RUNTIME;
  let scheduled = 0;
  globalThis.setInterval = ((...args: Parameters<typeof setInterval>) => {
    scheduled += 1;
    return original(...args);
  }) as typeof setInterval;
  process.env.NEXT_RUNTIME = "nodejs";
  process.env.IDPO_RECOVERY_READ_ONLY = "1";
  try {
    await register();
    assert.equal(scheduled, 0);
    assert.equal(fs.readFileSync(record, "utf8"), bytes);
  } finally {
    globalThis.setInterval = original;
    delete process.env.IDPO_RECOVERY_READ_ONLY;
    if (runtime === undefined) delete process.env.NEXT_RUNTIME; else process.env.NEXT_RUNTIME = runtime;
    fs.rmSync(directory, { recursive: true, force: true });
  }
});
