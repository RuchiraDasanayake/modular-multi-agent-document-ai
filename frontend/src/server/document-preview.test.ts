import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { ChildProcess } from "node:child_process";
import { GET as preview } from "../app/api/jobs/[jobId]/docs/[docId]/preview/route";
import { POST as upload } from "../app/api/jobs/[jobId]/documents/route";
import { resetConfigCacheForTests } from "./config";
import { createWorkspaceJob, getJob } from "./jobs";
import { previewEnvironment, previewPage } from "./document-preview";

const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC", "base64");
const users: Record<string, { id: string; role: string }> = {
  alice: { id: "preview-alice", role: "viewer" }, bob: { id: "preview-bob", role: "viewer" },
};

function twoPagePdf(): Buffer {
  const stream = (color: string) => {
    const content = `${color} rg 0 0 300 400 re f\n`;
    return `<< /Length ${Buffer.byteLength(content)} >>\nstream\n${content}endstream`;
  };
  const objects = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] /Contents 5 0 R >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 400] /Contents 6 0 R >>",
    stream("1 0 0"), stream("0 0 1")];
  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  objects.forEach((object, index) => { offsets.push(Buffer.byteLength(pdf)); pdf += `${index + 1} 0 obj\n${object}\nendobj\n`; });
  const xref = Buffer.byteLength(pdf);
  pdf += `xref\n0 7\n0000000000 65535 f \n${offsets.slice(1).map((offset) => `${String(offset).padStart(10, "0")} 00000 n \n`).join("")}`;
  pdf += `trailer\n<< /Size 7 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(pdf);
}

function request(url: string, token?: string, init?: RequestInit) {
  const headers = new Headers(init?.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return new Request(`http://localhost${url}`, { ...init, headers });
}

async function withStorage(run: () => Promise<void>) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "source-preview-"));
  const previous = { data: process.env.IDPO_DATA_DIR, gateway: process.env.INTERNAL_API_URL,
    python: process.env.IDPO_PRODUCT_PYTHON, fetch: globalThis.fetch };
  process.env.IDPO_DATA_DIR = path.join(directory, "data");
  process.env.INTERNAL_API_URL = "http://preview-gateway.local";
  if (process.env.IDPO_PREVIEW_TEST_PYTHON) process.env.IDPO_PRODUCT_PYTHON = process.env.IDPO_PREVIEW_TEST_PYTHON;
  resetConfigCacheForTests();
  globalThis.fetch = async (_input, init) => {
    const token = new Headers(init?.headers).get("Authorization")?.replace(/^Bearer /, "") ?? "";
    return users[token] ? Response.json(users[token]) : Response.json({}, { status: 401 });
  };
  try { await run(); }
  finally {
    globalThis.fetch = previous.fetch;
    for (const [name, value] of [["IDPO_DATA_DIR", previous.data], ["INTERNAL_API_URL", previous.gateway],
      ["IDPO_PRODUCT_PYTHON", previous.python]] as const) {
      if (value === undefined) delete process.env[name]; else process.env[name] = value;
    }
    resetConfigCacheForTests();
    fs.rmSync(directory, { recursive: true, force: true });
  }
}

async function source(name = "source.png", bytes: Buffer = PNG) {
  const job = createWorkspaceJob({ ownerUserId: users.alice.id });
  const response = await upload(request(`/api/jobs/${job.jobId}/documents`, "alice", {
    method: "POST", headers: { "Content-Type": "application/octet-stream", "X-File-Name": name },
    body: new Uint8Array(bytes),
  }), { params: Promise.resolve({ jobId: job.jobId }) });
  assert.equal(response.status, 201);
  const document = (await response.json()).documents[0] as { fileId: string; storedName: string };
  return { url: `/api/jobs/${job.jobId}/docs/${document.fileId}/preview`,
    params: { params: Promise.resolve({ jobId: job.jobId, docId: document.fileId }) },
    file: path.join(getJob(job.jobId)!.uploadsPath!, document.storedName) };
}

test("source preview requires authentication and job ownership before reading or rendering", async () => withStorage(async () => {
  const item = await source();
  assert.equal((await preview(request(item.url), item.params)).status, 401);
  assert.equal((await preview(request(item.url, "bob"), item.params)).status, 404);
  fs.unlinkSync(item.file);
  assert.equal((await preview(request(item.url, "alice"), item.params)).status, 404);
}));

test("source preview rejects invalid page selectors and caller-selected paths", () => {
  assert.equal(previewPage(new URLSearchParams()), 1);
  assert.equal(previewPage(new URLSearchParams("page=50")), 50);
  for (const query of ["page=0", "page=-1", "page=51", "page=1.5", "page=01", "page=1&page=2",
    "page=1&path=C:/private.pdf", "url=https://example.invalid/source.pdf"]) {
    assert.throws(() => previewPage(new URLSearchParams(query)));
  }
});

test("preview child inherits runtime essentials without credentials or application settings", () => {
  const environment = previewEnvironment({ Path: "runtime-bin", SystemRoot: "os-root", TEMP: "scratch",
    ICORE_API_KEY: "private", DATABASE_URL: "private", JWT_SECRET_KEY: "private", OPENAI_API_KEY: "private",
    PYTHONPATH: "untrusted-import-path", CUSTOM_SECRET: "private", PYTHONNOUSERSITE: "0" });
  assert.deepEqual(environment, { Path: "runtime-bin", SystemRoot: "os-root", TEMP: "scratch",
    NODE_ENV: "production", PYTHONNOUSERSITE: "1", PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8", PYTHONDONTWRITEBYTECODE: "1" });
});

test("source preview refuses unsupported files and oversized source bytes", async () => withStorage(async () => {
  const text = await source("note.txt", Buffer.from("source text"));
  assert.equal((await preview(request(text.url, "alice"), text.params)).status, 415);
  const image = await source();
  fs.truncateSync(image.file, 20 * 1024 * 1024 + 1);
  const response = await preview(request(image.url, "alice"), image.params);
  assert.equal(response.status, 413);
  assert.equal(response.headers.get("cache-control"), "no-store, max-age=0");
}));

test("source preview refuses a symlinked upload directory outside its job", async (t) => withStorage(async () => {
  const item = await source();
  const directory = path.dirname(item.file);
  const moved = `${directory}-moved`;
  fs.renameSync(directory, moved);
  try {
    try { fs.symlinkSync(moved, directory, process.platform === "win32" ? "junction" : "dir"); }
    catch (error) {
      if (["EPERM", "EACCES", "ENOTSUP"].includes(String((error as NodeJS.ErrnoException).code))) {
        t.skip("Directory symlinks unavailable."); return;
      }
      throw error;
    }
    const response = await preview(request(item.url, "alice"), item.params);
    assert.equal(response.status, 404);
    assert.doesNotMatch(await response.text(), new RegExp(moved.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  } finally {
    if (fs.existsSync(directory)) fs.unlinkSync(directory);
    fs.renameSync(moved, directory);
  }
}));

test("real local renderer returns a private PNG and rejects corrupt sources and missing pages",
  { skip: !process.env.IDPO_PREVIEW_TEST_PYTHON && !process.env.IDPO_PRODUCT_PYTHON }, async () => withStorage(async () => {
    const item = await source();
    const response = await preview(request(item.url, "alice"), item.params);
    assert.equal(response.status, 200, await response.clone().text());
    assert.equal(response.headers.get("content-type"), "image/png");
    assert.equal(response.headers.get("x-content-type-options"), "nosniff");
    assert.equal(response.headers.get("x-docai-page-count"), "1");
    assert.equal(response.headers.get("cache-control"), "no-store, max-age=0");
    assert.deepEqual(Buffer.from(await response.arrayBuffer()).subarray(0, 8), PNG.subarray(0, 8));
    assert.equal((await preview(request(`${item.url}?page=2`, "alice"), item.params)).status, 404);
    fs.writeFileSync(item.file, Buffer.alloc(PNG.length, 120));
    const invalid = await preview(request(item.url, "alice"), item.params);
    assert.equal(invalid.status, 422);
    assert.doesNotMatch(await invalid.text(), /Traceback|source-preview-|private/i);
  }));

test("PDF source preview renders the requested page with the full source page count",
  { skip: !process.env.IDPO_PREVIEW_TEST_PYTHON && !process.env.IDPO_PRODUCT_PYTHON }, async () => withStorage(async () => {
    const item = await source("two-pages.pdf", twoPagePdf());
    const first = await preview(request(item.url, "alice"), item.params);
    const second = await preview(request(`${item.url}?page=2`, "alice"), item.params);
    assert.equal(first.status, 200, await first.clone().text());
    assert.equal(second.status, 200, await second.clone().text());
    assert.equal(second.headers.get("x-docai-page-count"), "2");
    assert.equal(second.headers.get("x-docai-page"), "2");
    assert.notDeepEqual(Buffer.from(await first.arrayBuffer()), Buffer.from(await second.arrayBuffer()));
    assert.equal((await preview(request(`${item.url}?page=3`, "alice"), item.params)).status, 404);
  }));

test("renderer deadline stops the child and returns a bounded error",
  { skip: !process.env.IDPO_PREVIEW_TEST_PYTHON && !process.env.IDPO_PRODUCT_PYTHON }, async (t) => withStorage(async () => {
    const item = await source();
    t.mock.timers.enable({ apis: ["setTimeout"] });
    const pending = preview(request(item.url, "alice"), item.params);
    await new Promise<void>((resolve) => setImmediate(resolve));
    t.mock.timers.tick(15_000);
    const result = await pending;
    assert.equal(result.status, 504);
    assert.match(await result.text(), /timed out/);
    t.mock.timers.reset();
    assert.equal((await preview(request(item.url, "alice"), item.params)).status, 200);
  }));

test("source rendering has bounded concurrency and admits work after completion",
  { skip: !process.env.IDPO_PREVIEW_TEST_PYTHON && !process.env.IDPO_PRODUCT_PYTHON }, async () => withStorage(async () => {
    const item = await source();
    const responses = await Promise.all([1, 2, 3].map(() => preview(request(item.url, "alice"), item.params)));
    assert.deepEqual(responses.map((response) => response.status).sort(), [200, 200, 503]);
    assert.equal((await preview(request(item.url, "alice"), item.params)).status, 200);
  }));

test("a failed termination retains renderer capacity until the child actually closes",
  { skip: !process.env.IDPO_PREVIEW_TEST_PYTHON && !process.env.IDPO_PRODUCT_PYTHON }, async (t) => withStorage(async () => {
    const item = await source();
    const failedKill = t.mock.method(ChildProcess.prototype, "kill", () => false);
    t.mock.timers.enable({ apis: ["setTimeout"] });
    const pending = [1, 2].map(() => preview(request(item.url, "alice"), item.params));
    await new Promise<void>((resolve) => setImmediate(resolve));
    t.mock.timers.tick(15_000);
    assert.deepEqual((await Promise.all(pending)).map((result) => result.status), [504, 504]);
    assert.equal(failedKill.mock.callCount(), 2);
    assert.equal((await preview(request(item.url, "alice"), item.params)).status, 503);
    t.mock.timers.reset();
    failedKill.mock.restore();
    // The real, small local renderers finish normally; their close events release capacity.
    let result: Response | undefined;
    for (let attempt = 0; attempt < 40; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 50));
      result = await preview(request(item.url, "alice"), item.params);
      if (result.status !== 503) break;
    }
    assert.equal(result?.status, 200);
  }));
